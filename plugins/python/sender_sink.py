import gi
gi.require_version('GstBase', '1.0')
from gi.repository import Gst, GObject, GstBase
import pyds
import cv2
import numpy as np
import os
from uuid import uuid4
import requests
Gst.init(None)

#
# Simple Sink element created entirely in python
#
class SenderSink(GstBase.BaseSink):
    GST_PLUGIN_NAME = 'sendersink'

    __gstmetadata__ = ('sendersink','Sink', \
                      'Sender Sink to send Detection Results to server', 'Behnam Samadi')

    __gsttemplates__ = Gst.PadTemplate.new("sink",
                                           Gst.PadDirection.SINK,
                                           Gst.PadPresence.ALWAYS,
                                           Gst.Caps.new_any())
    __gproperties__ = {
        'send-result-url': (GObject.TYPE_STRING,
                                "Config file for connection",
                                "Address of config file for connection",
                                "",
                                GObject.ParamFlags.READWRITE
                                ),
        'image-save-dir': (GObject.TYPE_STRING,
                                "directory for saving outputs",
                                "objects getting croped and would save here",
                                "./",
                                GObject.ParamFlags.READWRITE
                                ),
        'image-path-prefix': (GObject.TYPE_STRING,
                                "image path prefix",
                                "prefix for file link generation",
                                "./",
                                GObject.ParamFlags.READWRITE
                                )
    }
    connection_url = None
    def do_set_property(self, prop: GObject.GParamSpec, value):
        if prop.name == 'send-result-url':
            self.connection_url = value
        if prop.name == 'image-save-dir':
            self.base_save_dir = value
        if prop.name == 'image-path-prefix':
            self.image_path_prefix = value
    
    def crop_and_save_box(self, image, bounding_box):
        file_name = str(uuid4()) + '.jpg'
        file_path = os.path.join(self.base_save_dir, file_name)
        file_link = os.path.join(self.image_path_prefix, file_name)
        croped = image[bounding_box['top']:bounding_box['top']+bounding_box['height'], bounding_box['left']:bounding_box['left']+bounding_box['width']]
        cv2.imwrite(file_path, croped)
        return file_link

    def extract_data_from_frame(self, frame_meta, frame):
        frame_number = frame_meta.frame_num
        num_rects = frame_meta.num_obj_meta
        frame_data = {
            'source_id': frame_meta.source_id,
            'frame_no': frame_number,
            'objects': [],
            'timestamp': frame_meta.ntp_timestamp
        }
        # print('Frame no: {}, Num Rects: {}'.format(frame_number, num_rects))
        l_obj = frame_meta.obj_meta_list
        while l_obj is not None:
            try:
                # Casting l_obj.data to pyds.NvDsObjectMeta
                
                obj_meta=pyds.NvDsObjectMeta.cast(l_obj.data)
                cords_data = obj_meta.tracker_bbox_info.org_bbox_coords

                bbox = {
                    'left': max(0, int(cords_data.left)),
                    'top': max(0, int(cords_data.top)),
                    'width': int(cords_data.width),
                    'height': int(cords_data.height)
                }
                if bbox['width'] <= 0 or bbox['height'] <= 0:
                    print('shit')
                    continue
                obj_data = {
                    'object_id': obj_meta.object_id,
                    'class_id': obj_meta.class_id,
                    'label': obj_meta.obj_label,
                    'confidence': round(obj_meta.confidence, 4),
                    'tracker_confidence': round(obj_meta.tracker_confidence, 4),
                    'bounding_box': bbox
                }
                if obj_data['label'] == 'person':
                    image_link = self.crop_and_save_box(frame, bbox)
                    obj_data['image_url'] = image_link
                    frame_data['objects'].append(obj_data)
            except StopIteration:
                break
            try: 
                l_obj=l_obj.next
            except StopIteration:
                break
        return frame_data

    def do_render(self, buffer):
        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(buffer))
        l_frame = batch_meta.frame_meta_list
        while l_frame is not None:
            try:
                frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
                n_frame = pyds.get_nvds_buf_surface(hash(buffer), frame_meta.batch_id)
                frame_copy = np.array(n_frame, copy=True, order='C')
                frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_RGBA2BGR)
            except StopIteration:
                break

            frame_data = self.extract_data_from_frame(frame_meta, frame_copy)
            try:
                requests.post(self.connection_url, json=frame_data)
            except Exception as e:
                print("Can't establish connection to backend except:", e)
            try:
                l_frame=l_frame.next
            except StopIteration:
                break
        
        return Gst.FlowReturn.OK

GObject.type_register(SenderSink)
__gstelementfactory__ = ("sendersink", Gst.Rank.NONE, SenderSink)