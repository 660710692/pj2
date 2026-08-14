import cv2
from ultralytics import YOLO

model = YOLO("models/best.pt")

VIDEO = "test_video.mp4"

cap = cv2.VideoCapture(VIDEO)

if not cap.isOpened():
    print(f"ERROR: Cannot open video: {VIDEO}")
    exit()

print("Video opened successfully")

frame_count = 0

while True:

    ret, frame = cap.read()

    if not ret:
        print("Video ended")
        break

    frame_count += 1

    results = model.track(
        frame,
        conf=0.3,              # ลดลงชั่วคราวเพื่อทดสอบ
        imgsz=320,
        tracker="bytetrack.yaml",
        persist=True,
        verbose=False
    )

    result = results[0]

    boxes = result.boxes

    print(f"\nFrame {frame_count}")
    print(f"Detections: {len(boxes)}")

    if boxes.id is not None:

        for i in range(len(boxes)):

            track_id = int(boxes.id[i].item())
            confidence = float(boxes.conf[i].item())

            print(
                f"  ID={track_id} "
                f"Confidence={confidence:.2f}"
            )

    else:
        print("  No tracking ID")

    output = result.plot()

    cv2.imshow("ByteTrack Test", output)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break


cap.release()
cv2.destroyAllWindows()

print(f"\nTotal frames processed: {frame_count}")