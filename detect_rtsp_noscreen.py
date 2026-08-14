import cv2
from ultralytics import YOLO

model = YOLO("best.pt")

url = "rtsp://admin:bm9BqimE@192.168.1.100:554/Streaming/Channels/101"

cap = cv2.VideoCapture(url)

if not cap.isOpened():
    print("Open failed")
    exit()

while True:

    ret, frame = cap.read()

    if not ret:
        break

    results = model(frame)

    boxes = results[0].boxes

    print("----------------")

    print("Detected :", len(boxes))

    for box in boxes:

        cls = int(box.cls)

        conf = float(box.conf)

        print(model.names[cls], conf)