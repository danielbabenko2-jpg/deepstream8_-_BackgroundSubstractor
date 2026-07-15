import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GLib
from common.bus_call import bus_call
from common.platform_info import PlatformInfo
import sys
import math

from rtsp_stream import creater_rtsp_server
from source import create_source_bin
from probe import pgie_src_pad_buffer_probe
import config

def run_pipeline(args):
    number_sources = len(args.input)

    platform_info = PlatformInfo()
    Gst.init(None)

    print("Creating Pipeline \n ")
    pipeline = Gst.Pipeline()
    is_live = False

    if not pipeline:
        sys.stderr.write(" Unable to create Pipeline \n")
    print("Creating streamux \n ")

    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    if not streammux:
        sys.stderr.write(" Unable to create NvStreamMux \n")

    pipeline.add(streammux)
    for i in range(number_sources):
        print("Creating source_bin ", i, " \n ")
        uri_name = args.input[i]
        if uri_name.find("rtsp://") == 0:
            is_live = True
        source_bin = create_source_bin(i, uri_name, args.rtsp_ts)
        if not source_bin:
            sys.stderr.write("Unable to create source bin \n")
        pipeline.add(source_bin)
        padname = "sink_%u" % i
        sinkpad = streammux.request_pad_simple(padname)
        if not sinkpad:
            sys.stderr.write("Unable to create sink pad bin \n")
        srcpad = source_bin.get_static_pad("src")
        if not srcpad:
            sys.stderr.write("Unable to create src pad bin \n")
        srcpad.link(sinkpad)

    print("Creating Pgie \n ")
    if args.gie=="nvinfer":
        pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    else:
        pgie = Gst.ElementFactory.make("nvinferserver", "primary-inference")
    if not pgie:
        sys.stderr.write(" Unable to create pgie \n")
    print("Creating tiler \n ")

    caps_pre_tiler = Gst.ElementFactory.make("capsfilter", "filter_pre_tiler")
    caps_pre_tiler.set_property(
        "caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=RGBA")
    )

    nvconv_pre_tiler = Gst.ElementFactory.make("nvvideoconvert", "convertor_pre_tiler")
    if not nvconv_pre_tiler:
        sys.stderr.write(" Unable to create nvvidconv_pre_tiler \n")

    tiler = Gst.ElementFactory.make("nvmultistreamtiler", "nvtiler")
    if not tiler:
        sys.stderr.write(" Unable to create tiler \n")

    print("Creating nvvidconv \n ")
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "convertor")
    if not nvvidconv:
        sys.stderr.write(" Unable to create nvvidconv \n")
    print("Creating nvosd \n ")
    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
    if not nvosd:
        sys.stderr.write(" Unable to create nvosd \n")
    nvvidconv_postosd = Gst.ElementFactory.make(
        "nvvideoconvert", "convertor_postosd")
    if not nvvidconv_postosd:
        sys.stderr.write(" Unable to create nvvidconv_postosd \n")

    caps = Gst.ElementFactory.make("capsfilter", "filter")
    caps.set_property(
        "caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=I420")
    )

    if args.codec == "H264":
        encoder = Gst.ElementFactory.make("nvv4l2h264enc", "encoder")
        print("Creating H264 Encoder")
    elif args.codec == "H265":
        encoder = Gst.ElementFactory.make("nvv4l2h265enc", "encoder")
        print("Creating H265 Encoder")
    if not encoder:
        sys.stderr.write(" Unable to create encoder")
    encoder.set_property("bitrate", args.bitrate)
    if platform_info.is_integrated_gpu():
        encoder.set_property("preset-level", 1)
        encoder.set_property("insert-sps-pps", 1)
        #encoder.set_property("bufapi-version", 1)

    if args.codec == "H264":
        rtppay = Gst.ElementFactory.make("rtph264pay", "rtppay")
        rtppay.set_property("config_interval", 1)
        print("Creating H264 rtppay")
    elif args.codec == "H265":
        rtppay = Gst.ElementFactory.make("rtph265pay", "rtppay")
        print("Creating H265 rtppay")
    if not rtppay:
        sys.stderr.write(" Unable to create rtppay")

    updsink_port_num = 5400
    sink = Gst.ElementFactory.make("udpsink", "udpsink")
    if not sink:
        sys.stderr.write(" Unable to create udpsink")

    sink.set_property("host", "224.224.255.255")
    sink.set_property("port", updsink_port_num)
    sink.set_property("async", False)
    sink.set_property("sync", 1)

    streammux.set_property("width", 1920)
    streammux.set_property("height", 1080)
    streammux.set_property("batch-size", number_sources)
    streammux.set_property("batched-push-timeout", config.MUXER_BATCH_TIMEOUT_USEC)
    
    if args.rtsp_ts:
        streammux.set_property("attach-sys-ts", 0)

    if args.gie=="nvinfer":
        pgie.set_property("config-file-path", "dstest1_pgie_config.txt")
    else:
        pgie.set_property("config-file-path", "dstest1_pgie_inferserver_config.txt")


    pgie_batch_size = pgie.get_property("batch-size")
    if pgie_batch_size != number_sources:
        print(
            "WARNING: Overriding infer-config batch-size",
            pgie_batch_size,
            " with number of sources ",
            number_sources,
            " \n",
        )
        pgie.set_property("batch-size", number_sources)

    print("Adding elements to Pipeline \n")
    tiler_rows = int(math.sqrt(number_sources))
    tiler_columns = int(math.ceil((1.0 * number_sources) / tiler_rows))
    tiler.set_property("rows", tiler_rows)
    tiler.set_property("columns", tiler_columns)
    tiler.set_property("width", config.TILED_OUTPUT_WIDTH)
    tiler.set_property("height", config.TILED_OUTPUT_HEIGHT)
    sink.set_property("qos", 0)

    pipeline.add(pgie)
    pipeline.add(tiler)
    pipeline.add(nvvidconv)
    pipeline.add(nvosd)
    pipeline.add(nvvidconv_postosd)
    pipeline.add(caps)
    pipeline.add(encoder)
    pipeline.add(rtppay)
    pipeline.add(sink)
    pipeline.add(caps_pre_tiler)
    pipeline.add(nvconv_pre_tiler)

    streammux.link(nvconv_pre_tiler)
    nvconv_pre_tiler.link(caps_pre_tiler)
    caps_pre_tiler.link(pgie)
    pgie.link(nvvidconv)
    nvvidconv.link(tiler)
    tiler.link(nvosd)
    nvosd.link(nvvidconv_postosd)
    nvvidconv_postosd.link(caps)
    caps.link(encoder)
    encoder.link(rtppay)
    rtppay.link(sink)

    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", bus_call, loop)

    pgie_src_pad=pgie.get_static_pad("src")
    if not pgie_src_pad:
        sys.stderr.write(" Unable to get src pad \n")
    else:
        pgie_src_pad.add_probe(Gst.PadProbeType.BUFFER, pgie_src_pad_buffer_probe, 0)

    creater_rtsp_server(args.codec, config.udp_port, config.rtsp_port)

    print("Starting pipeline \n")
    pipeline.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    except BaseException:
        pass

    pipeline.set_state(Gst.State.NULL)