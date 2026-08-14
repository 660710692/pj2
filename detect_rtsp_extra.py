
import cv2
from ultralytics import YOLO
import time
from datetime import datetime

# ==========================
# Load YOLO Model
# ==========================
model = YOLO("best.pt")

# ==========================
# RTSP URL
# ==========================
url = "rtsp://admin:bm9BqimE@192.168.1.100:554/Streaming/Channels/101"

cap = cv2.VideoCapture(url)

if not cap.isOpened():
    print("Cannot connect to camera")
    exit()

print("Camera Connected")

prev_time = time.time()

while True:

    ret, frame = cap.read()

    if not ret:
        print("Camera Disconnected")
        break

    # -----------------------
    # YOLO Detection
    # -----------------------
    results = model(frame, verbose=False)

    annotated = frame.copy()

    boxes = results[0].boxes

    detected_count = len(boxes)

    # -----------------------
    # Draw Bounding Boxes
    # -----------------------
    for box in boxes:

        x1, y1, x2, y2 = map(int, box.xyxy[0])

        confidence = float(box.conf)

        class_id = int(box.cls)

        class_name = model.names[class_id]

        label = f"{class_name} {confidence:.2f}"

        cv2.rectangle(
            annotated,
            (x1, y1),
            (x2, y2),
            (0,255,0),
            2
        )

        cv2.putText(
            annotated,
            label,
            (x1, y1-10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0,255,0),
            2
        )

    # -----------------------
    # FPS
    # -----------------------
    current_time = time.time()

    fps = 1/(current_time-prev_time)

    prev_time = current_time

    # -----------------------
    # Timestamp
    # -----------------------
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # -----------------------
    # Information Panel
    # -----------------------
    cv2.rectangle(
        annotated,
        (0,0),
        (500,140),
        (40,40,40),
        -1
    )

    cv2.putText(
        annotated,
        "Water Hyacinth Detection System",
        (15,30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (255,255,255),
        2
    )

    cv2.putText(
        annotated,
        "Camera : Connected",
        (15,60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0,255,0),
        2
    )

    cv2.putText(
        annotated,
        f"FPS : {fps:.2f}",
        (15,85),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255,255,255),
        2
    )

    cv2.putText(
        annotated,
        f"Detected : {detected_count}",
        (15,110),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0,255,255),
        2
    )

    cv2.putText(
        annotated,
        timestamp,
        (15,135),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255,255,255),
        1
    )

    # -----------------------
    # Display
    # -----------------------
    cv2.imshow("Water Hyacinth Detection", annotated)



#     cv2.imwrite("result.jpg", annotated)
# print("Image saved")


    key = cv2.waitKey(1)

    if key == ord('q'):
        break
# out.write(annotated)

cap.release()
cv2.destroyAllWindows()

