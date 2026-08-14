import cv2
from ultralytics import YOLO
import time

model = YOLO("best.pt")

# RTSP URL ของ Hikvision
url = "rtsp://admin:bm9BqimE@192.168.1.100:554/Streaming/Channels/101"

cap = cv2.VideoCapture(url)

if not cap.isOpened():
    print("Cannot open camera")
    exit()

prev_time = time.time()

while True:

    ret, frame = cap.read()

    if not ret:
        print("Cannot receive frame")
        break

    # Detect
    results = model(frame)

    # วาด Bounding Box
    annotated_frame = results[0].plot()

    # FPS
    current_time = time.time()

    fps = 1 / (current_time - prev_time)

    prev_time = current_time

    cv2.putText(
        annotated_frame,
        f"FPS : {fps:.2f}",
        (20,40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0,255,0),
        2
    )

    cv2.imshow("Water Hyacinth Detection", annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()