from gi.repository import GstRtspServer

def creater_rtsp_server(codec, udp_port, rtsp_port):
    server = GstRtspServer.RTSPServer.new()
    server.props.service = "%d" % rtsp_port
    server.attach(None)

    factory = GstRtspServer.RTSPMediaFactory.new()
    factory.set_launch(
        '( udpsrc name=pay0 port=%d buffer-size=524288 caps="application/x-rtp, media=video, clock-rate=90000, encoding-name=(string)%s, payload=96 " )'
        % (udp_port, codec)
        )
    factory.set_shared(True)
    server.get_mount_points().add_factory("/ds-test", factory)

    print(
        "\n *** DeepStream: Launched RTSP Streaming at rtsp://localhost:%d/ds-test ***\n\n"
        % rtsp_port
        )
    return server