#!/usr/bin/env python3

################################################################################
# SPDX-FileCopyrightText: Copyright (c) 2019-2021 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
################################################################################

import sys
sys.path.append('../')
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst, GLib
from common.bus_call import bus_call
import yaml
import configparser
import pyds


def parse_config(config_file):
    with open(config_file) as conf:
        config = yaml.full_load(conf)
        return config

def cb_newpad(decodebin, decoder_src_pad, data):
    print("In cb_newpad\n")
    caps = decoder_src_pad.get_current_caps()
    gststruct = caps.get_structure(0)
    gstname = gststruct.get_name()
    source_bin = data
    features = caps.get_features(0)

    # Need to check if the pad created by the decodebin is for video and not
    # audio.
    print("gstname=", gstname)
    if gstname.find("video") != -1:
        # Link the decodebin pad only if decodebin has picked nvidia
        # decoder plugin nvdec_*. We do this by checking if the pad caps contain
        # NVMM memory features.
        print("features=", features)
        if features.contains("memory:NVMM"):
            # Get the source bin ghost pad
            bin_ghost_pad = source_bin.get_static_pad("src")
            if not bin_ghost_pad.set_target(decoder_src_pad):
                sys.stderr.write("Failed to link decoder src pad to source bin ghost pad\n")
        else:
            sys.stderr.write(" Error: Decodebin did not pick nvidia decoder plugin.\n")


def decodebin_child_added(child_proxy, Object, name, user_data):
    print("Decodebin child added:", name, "\n")
    if name.find("decodebin") != -1:
        Object.connect("child-added", decodebin_child_added, user_data)


def create_source_bin(index, uri):
    print("Creating source bin")

    # Create a source GstBin to abstract this bin's content from the rest of the
    # pipeline
    bin_name = "source-bin-%02d" % index
    print(bin_name)
    nbin = Gst.Bin.new(bin_name)
    if not nbin:
        sys.stderr.write(" Unable to create source bin \n")

    uri_decode_bin = Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")

    if not uri_decode_bin:
        sys.stderr.write(" Unable to create uri decode bin \n")
    uri_decode_bin.set_property("uri", uri)

    uri_decode_bin.connect("pad-added", cb_newpad, nbin)
    uri_decode_bin.connect("child-added", decodebin_child_added, nbin)

    Gst.Bin.add(nbin, uri_decode_bin)
    bin_pad = nbin.add_pad(Gst.GhostPad.new_no_target("src", Gst.PadDirection.SRC))
    if not bin_pad:
        sys.stderr.write(" Failed to add ghost pad in source bin \n")
        return None
    return nbin



def main(args):
    # Check input arguments
    if len(args) != 2:
        sys.stderr.write("usage: %s <main config file>\n" % args[0])
        sys.exit(1)
    config = parse_config(args[1])

    if config is None:
        sys.stderr.write("Parsing Config failed")
        sys.exit(1)
    print(config)

    # Standard GStreamer initialization
    GObject.threads_init()
    Gst.init(None)
    
    print("Creating Pipeline \n ")
    pipeline = Gst.Pipeline()

    if not pipeline:
        sys.stderr.write(" Unable to create Pipeline \n")

    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    if not streammux:
        sys.stderr.write(" Unable to create NvStreamMux \n")
    
    pipeline.add(streammux)

    is_live = False

    for i, uri_name in enumerate(config['sources']):

        if uri_name.find("rtsp://") == 0 :
            is_live = True
        source_bin=create_source_bin(i, uri_name)
        if not source_bin:
            sys.stderr.write("Unable to create source bin \n")
        pipeline.add(source_bin)
        padname="sink_%u" %i
        sinkpad= streammux.get_request_pad(padname) 
        if not sinkpad:
            sys.stderr.write("Unable to create sink pad bin \n")
        srcpad=source_bin.get_static_pad("src")
        if not srcpad:
            sys.stderr.write("Unable to create src pad bin \n")
        srcpad.link(sinkpad)
    
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    if not pgie:
        sys.stderr.write(" Unable to create pgie \n")
    
    tracker = Gst.ElementFactory.make("nvtracker", "tracker")
    if not tracker:
        sys.stderr.write(" Unable to create tracker \n")

    print("Creating Queue \n")
    queue = Gst.ElementFactory.make("queue", "queue")
    if not queue:
        sys.stderr.write(" Unable to create queue \n")

    print("Creating Sender Sink \n")
    sink = Gst.ElementFactory.make("sendersink", "sendersink")
    if not sink:
        sys.stderr.write(" Unable to create file sink \n")
    sink.set_property("send-result-url", config['sender']['url'])
    sink.set_property("sync", 0)

    print("Playing file %s " %args[1])
    streammux.set_property('width', 1280)
    streammux.set_property('height', 720)
    streammux.set_property('batch-size', 1)
    streammux.set_property('batched-push-timeout', 4000000)
    if is_live:
        print("Atleast one of the sources is live")
        streammux.set_property('live-source', 1)
    
    pgie.set_property('config-file-path', config['detector']['config_file'])

    tracker_config = configparser.ConfigParser()
    tracker_config.read(config['tracker']['config_file'])
    tracker_config.sections()

    for key in tracker_config['tracker']:
        if key == 'tracker-width' :
            tracker_width = tracker_config.getint('tracker', key)
            tracker.set_property('tracker-width', tracker_width)
        if key == 'tracker-height' :
            tracker_height = tracker_config.getint('tracker', key)
            tracker.set_property('tracker-height', tracker_height)
        if key == 'gpu-id' :
            tracker_gpu_id = tracker_config.getint('tracker', key)
            tracker.set_property('gpu_id', tracker_gpu_id)
        if key == 'll-lib-file' :
            tracker_ll_lib_file = tracker_config.get('tracker', key)
            tracker.set_property('ll-lib-file', tracker_ll_lib_file)
        if key == 'll-config-file' :
            tracker_ll_config_file = tracker_config.get('tracker', key)
            tracker.set_property('ll-config-file', tracker_ll_config_file)
        if key == 'enable-batch-process' :
            tracker_enable_batch_process = tracker_config.getint('tracker', key)
            tracker.set_property('enable_batch_process', tracker_enable_batch_process)
        if key == 'enable-past-frame' :
            tracker_enable_past_frame = tracker_config.getint('tracker', key)
            tracker.set_property('enable_past_frame', tracker_enable_past_frame)

    print("Adding elements to Pipeline \n")

    pipeline.add(pgie)
    pipeline.add(tracker)
    pipeline.add(queue)
    pipeline.add(sink)

    print("Linking elements in the Pipeline \n")
    
    streammux.link(pgie)
    pgie.link(tracker)
    tracker.link(queue)
    queue.link(sink)

    # create an event loop and feed gstreamer bus mesages to it
    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect ("message", bus_call, loop)

    print("Starting pipeline \n")
    pipeline.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    except:
        pass
    # cleanup
    pipeline.set_state(Gst.State.NULL)

if __name__ == '__main__':
    sys.exit(main(sys.argv))

