import cv2
from ultralytics import YOLO

from tracker import ObjectTracker
from speed_calculator import SpeedCalculator
from spray_controller import SprayDecision


model = YOLO("models/best.pt")

tracker = ObjectTracker()

speed_calculator = SpeedCalculator(
    pixels_per_meter=100
)

spray_decision = SprayDecision(
    confidence_threshold=0.60,
    min_speed=0.10,
    cooldown_seconds=10
)


cap = cv2.VideoCapture("test.mp4")


while True:

    ret, frame = cap.read()

    if not ret:
        break

    results = model.track(
        frame,
        conf=0.6,
        imgsz=320,
        tracker="bytetrack.yaml",
        persist=True,
        verbose=False
    )

    result = results[0]

    objects = tracker.update(result)

    for obj in objects:

        object_id = obj["id"]
        confidence = obj["confidence"]

        speed = speed_calculator.update(
            object_id,
            obj["center_x"],
            obj["center_y"]
        )

        should_spray, reason = (
            spray_decision.should_spray(
                confidence=confidence,
                speed=speed,
                chemical_available=True
            )
        )

        print(
            f"ID={object_id} | "
            f"Conf={confidence:.2f} | "
            f"Speed={speed:.2f} m/s | "
            f"Spray={should_spray} | "
            f"Reason={reason}"
        )

    output = result.plot()

    cv2.imshow("Water Hyacinth Test", output)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break


cap.release()
cv2.destroyAllWindows()