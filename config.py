"""
=========================================================
Water Hyacinth Detection System
Configuration File

Author : Kantapong
Platform : Raspberry Pi 5
Model : YOLOv11
=========================================================
"""

import os

# =========================================================
# Project Information
# =========================================================

PROJECT_NAME = "Water Hyacinth Detection System"

MODEL_NAME = "YOLOv11"

DEVICE_NAME = "Raspberry Pi 5"

VERSION = "1.0"


# =========================================================
# Model
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.path.join(
    BASE_DIR,
    "models",
    "best.pt"
)


# =========================================================
# Camera
# =========================================================

RTSP_URL = (
    "rtsp://admin:bm9BqimE@192.168.1.100:554/"
    "Streaming/Channels/101"
)

CAMERA_NAME = "Hikvision IP Camera"

CAMERA_TIMEOUT = 5


# =========================================================
# Detection
# =========================================================

CONFIDENCE_THRESHOLD = 0.40

IOU_THRESHOLD = 0.45

IMAGE_SIZE = 640

CLASS_NAMES = [
    "Water Hyacinth"
]


# =========================================================
# Drawing
# =========================================================

BOX_COLOR = (0, 255, 0)

TEXT_COLOR = (255, 255, 255)

BOX_THICKNESS = 2

FONT_SCALE = 0.7

FONT_THICKNESS = 2


# =========================================================
# Dashboard
# =========================================================

WINDOW_TITLE = PROJECT_NAME

WEB_PORT = 5000

HOST = "0.0.0.0"


# =========================================================
# Streaming
# =========================================================

JPEG_QUALITY = 85

FRAME_DELAY = 1


# =========================================================
# Reconnect
# =========================================================

AUTO_RECONNECT = True

RECONNECT_DELAY = 2


# =========================================================
# Logging
# =========================================================

SHOW_FPS = True

SHOW_CONFIDENCE = True

SHOW_TIMESTAMP = True

SHOW_CAMERA_STATUS = True

SHOW_DETECTION_COUNT = True