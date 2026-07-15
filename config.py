MAX_DISPLAY_LEN = 64
PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3
MUXER_OUTPUT_WIDTH = 1920
MUXER_OUTPUT_HEIGHT = 1080
MUXER_BATCH_TIMEOUT_USEC = 33000
TILED_OUTPUT_WIDTH = 1280
TILED_OUTPUT_HEIGHT = 720
GST_CAPS_FEATURES_NVMM = "memory:NVMM"
OSD_PROCESS_MODE = 0
OSD_DISPLAY_TEXT = 0
pgie_classes_str = ["Vehicle", "TwoWheeler", "Person", "RoadSign"]

# Переменные для сохранения видео
video_writer = None
video_frames = []
VIDEO_FRAMES_LIMIT = 500
video_counter = 0
output_dir = "output_videos"

udp_port = 5400
rtsp_port = 8560