import gi
gi.require_version('GstBase', '1.0')
from gi.repository import Gst, GObject, GstBase
import pyds
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
                                )
    }
    connection_url = None
    def do_set_property(self, prop: GObject.GParamSpec, value):
        if prop.name == 'send-result-url':
            self.connection_url = value

    def extract_data_from_frame(self, frame_meta):
        frame_number = frame_meta.frame_num
        num_rects = frame_meta.num_obj_meta
        frame_data = {
            'source_id': frame_meta.source_id,
            'frame_no': frame_number,
            'objects': [],
            'timestamp': frame_meta.ntp_timestamp
        }
        print('Frame no: {}, Num Rects: {}'.format(frame_number, num_rects))
        l_obj = frame_meta.obj_meta_list
        while l_obj is not None:
            try:
                # Casting l_obj.data to pyds.NvDsObjectMeta
                
                obj_meta=pyds.NvDsObjectMeta.cast(l_obj.data)
                cords_data = obj_meta.tracker_bbox_info.org_bbox_coords

                bbox = {
                    'left': int(cords_data.left),
                    'top': int(cords_data.top),
                    'width': int(cords_data.width),
                    'height': int(cords_data.height)
                }
                obj_data = {
                    'object_id': obj_meta.object_id,
                    'class_id': obj_meta.class_id,
                    'label': obj_meta.obj_label,
                    'confidence': round(obj_meta.confidence, 4),
                    'tracker_confidence': round(obj_meta.tracker_confidence, 4),
                    'bounding_box': bbox
                }
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
            except StopIteration:
                break

            frame_data = self.extract_data_from_frame(frame_meta)

            requests.post(self.connection_url, json=frame_data)
            try:
                l_frame=l_frame.next
            except StopIteration:
                break
        
        return Gst.FlowReturn.OK

GObject.type_register(SenderSink)
__gstelementfactory__ = ("sendersink", Gst.Rank.NONE, SenderSink)