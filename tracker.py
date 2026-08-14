class ObjectTracker:

    def __init__(self):
        self.tracked_objects = {}

    def update(self, result):
        """
        รับผลจาก YOLO.track()
        คืนค่าข้อมูล object ที่มี track ID
        """

        objects = []

        if result.boxes is None:
            return objects

        boxes = result.boxes

        for i in range(len(boxes)):

            # ต้องมี tracking ID
            if boxes.id is None:
                continue

            track_id = int(boxes.id[i].item())
            confidence = float(boxes.conf[i].item())

            x1, y1, x2, y2 = boxes.xyxy[i].tolist()

            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2

            objects.append({
                "id": track_id,
                "confidence": confidence,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "center_x": center_x,
                "center_y": center_y
            })

        return objects