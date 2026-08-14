from ultralytics import YOLO

model = YOLO("best.pt")

model.predict(
    source="test_video.mp4",
    save=True,
    conf=0.5
)