import sys
import gi
gi.require_version("Gst","1.0")
from gi.repository import Gst
import pyds

def cb_newpad(decodebin, decoder_src_pad, data):
    print("In cb_newpad\n")
    caps = decoder_src_pad.get_current_caps()
    gststruct = caps.get_structure(0)
    gstname = gststruct.get_name()
    source_bin = data
    features = caps.get_features(0)

    print("gstname=", gstname)
    if gstname.find("video") != -1:
        print("features=", features)
        if features.contains("memory:NVMM"):
            bin_ghost_pad = source_bin.get_static_pad("src")
            if not bin_ghost_pad.set_target(decoder_src_pad):
                sys.stderr.write(
                    "Failed to link decoder src pad to source bin ghost pad\n"
                )
        else:
            sys.stderr.write(
                " Error: Decodebin did not pick nvidia decoder plugin.\n")

def decodebin_child_added(child_proxy, Object, name, user_data):
    source_bin, ts_from_rtsp = user_data
    print("Decodebin child added:", name, "\n")
    if name.find("decodebin") != -1:
        Object.connect("child-added", decodebin_child_added, user_data)

    if ts_from_rtsp:
        if name.find("source") != -1:
            pyds.configure_source_for_ntp_sync(hash(Object))


def create_source_bin(index, uri, ts_from_rtsp):
    print("Creating source bin")

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
    uri_decode_bin.connect("child-added", decodebin_child_added, (nbin, ts_from_rtsp))

    Gst.Bin.add(nbin, uri_decode_bin)
    bin_pad = nbin.add_pad(
        Gst.GhostPad.new_no_target(
            "src", Gst.PadDirection.SRC))
    if not bin_pad:
        sys.stderr.write(" Failed to add ghost pad in source bin \n")
        return None
    return nbin