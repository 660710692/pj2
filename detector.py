
import cv2
import time
import threading
from datetime import datetime
from tracker import ObjectTracker
from speed_calculator import SpeedCalculator
from spray_controller import SprayDecision
from esp32_sender import send_detection

from ultralytics import YOLO

from flask import jsonify

class Detector:

    def __init__(self):

        self.model = YOLO("models/best.pt")

        self.rtsp_url = (
            "rtsp://admin:bm9BqimE@192.168.1.100:554/"
            "Streaming/Channels/102"
        )

        self.cap = None

        self.camera_status = "Disconnected"

        self.fps = 0

        self.detected_count = 0

        self.timestamp = ""

        self.prev_time = time.time()

        self.best_confidence = 0.0

        self.tracker = ObjectTracker()

        self.speed_calculator = SpeedCalculator(
            pixels_per_meter=100
        )

        self.spray_decision = SprayDecision(
            confidence_threshold=0.60,
            min_speed=0.0,
            cooldown_seconds=10
        )

        # ---------- Multi Thread Buffer ----------

        self.latest_frame = None
        self.output_frame = None
        self.lock = threading.Lock()
        self.running = True
        self.last_sent_detected = None



        self.connect_camera()
        
        self.camera_thread = threading.Thread(
            target=self.camera_worker
        )

        self.detect_thread = threading.Thread(
            target=self.detect_worker
        )

        self.camera_thread.daemon = True
        self.detect_thread.daemon = True

        self.camera_thread.start()
        self.detect_thread.start()

    def connect_camera(self):

        if self.cap is not None:

            self.cap.release()

        self.cap = cv2.VideoCapture(self.rtsp_url)

        if self.cap.isOpened():

            self.camera_status = "Connected"

            print("Camera Connected")

        else:

            self.camera_status = "Disconnected"

            print("Cannot connect to camera")


    def camera_worker(self):

        while self.running:

            if self.cap is None or not self.cap.isOpened():
                self.camera_status = "Disconnected"
                self.connect_camera()
                time.sleep(1)
                continue

            ret, frame = self.cap.read()

            if not ret:
                self.camera_status = "Disconnected"
                self.connect_camera()
                time.sleep(1)
                continue

            self.camera_status = "Connected"

            with self.lock:
                self.latest_frame = frame

    def detect_worker(self):   # แบบ Track
        while self.running:

        # 1. เอา frame ล่าสุดมา
            with self.lock:
                if self.latest_frame is None:
                    continue

                frame = self.latest_frame.copy()

        # 2. YOLO + ByteTrack
            results = self.model.track(
                frame,
                conf=0.6,
                imgsz=320,
                tracker="bytetrack.yaml",
                persist=True,
                verbose=False
            )

            result = results[0]


        # 3. ดึงข้อมูล Object ที่ Track ได้
            objects = self.tracker.update(result)

            # Send detection status to ESP32 when status changes
            detected = len(objects) > 0

            confidence = max(
                (float(obj["confidence"]) for obj in objects),
                default=0.0
            )

            if detected != self.last_sent_detected:
                threading.Thread(
                    target=send_detection,
                    args=(detected, confidence),
                    daemon=True
                ).start()

                self.last_sent_detected = detected


        # 4. คำนวณ Speed + Spray Decision
            for obj in objects:

                object_id = obj["id"]
                confidence = obj["confidence"]

                speed = self.speed_calculator.update(
                    object_id,
                    obj["center_x"],
                    obj["center_y"]
                )

                should_spray, reason = (
                    self.spray_decision.should_spray(
                        confidence=confidence,
                        speed=speed,
                        chemical_available=True
                    )
                )

                print(
                    f"ID={object_id} "
                    f"Conf={confidence:.2f} "
                    f"Speed={speed:.2f} m/s "
                    f"Decision={should_spray} "
                    f"Reason={reason}"
                )

        # 5. สร้างภาพสำหรับ Dashboard
            output = result.plot()

            with self.lock:
                self.output_frame = output


    #def detect_worker(self):      # แบบ ไม่มี Track

        # while self.running:

        #     with self.lock:

        #         if self.latest_frame is None:
        #             frame = None
        #         else:
        #             frame = self.latest_frame.copy()

        #     if frame is None:
        #         time.sleep(0.01)
        #         continue

        # # ---------------- YOLO ----------------
        #     results = self.model.track(
        #         frame,
        #         conf=0.6,
        #         imgsz=320,
        #         tracker="bytetrack.yaml",
        #         persist=True,
        #         verbose=False
        #     )

        #     annotated = frame.copy()

        #     boxes = results[0].boxes
        #     self.best_confidence = 0.0
        #     self.detected_count = len(boxes)

        #     for box in boxes:
        #         confidence = float(box.conf)

        #         if confidence > self.best_confidence:
        #             self.best_confidence = confidence    
        #         x1, y1, x2, y2 = map(int, box.xyxy[0])

        #         confidence = float(box.conf)

        #         class_id = int(box.cls)

        #         class_name = self.model.names[class_id]

        #         label = f"{confidence*100:.1f}%"

        #         cv2.rectangle(
        #             annotated,
        #             (x1, y1),
        #             (x2, y2),
        #             (0, 255, 0),
        #             2
        #         )

        #         cv2.putText(
        #             annotated,
        #             label,
        #             (x1, y1 - 10),
        #             cv2.FONT_HERSHEY_SIMPLEX,
        #             0.6,
        #             (0, 255, 0),
        #             2
        #         )

        #     current_time = time.time()

        #     self.fps = 1 / (current_time - self.prev_time)

        #     self.prev_time = current_time

        #     self.timestamp = datetime.now().strftime(
        #         "%Y-%m-%d %H:%M:%S"
        #     )

        #     self.draw_dashboard(annotated)

        #     with self.lock:
        #         self.output_frame = annotated
        

    def get_status(self):

        return jsonify({

            "camera": self.camera_status,

            "fps": round(self.fps,2),

            "detected": self.detected_count,

            "timestamp": self.timestamp

        })

    def draw_dashboard(self, frame):

        overlay = frame.copy()

    # ---------- Glass Panel ----------
        cv2.rectangle(
            overlay,
            (15, 15),
            (300, 125),
            (35, 35, 35),
            -1
        )

        cv2.addWeighted(
            overlay,
            0.35,
            frame,
            0.65,
            0,
            frame
        )

        white = (255, 255, 255)
        green = (0, 255, 120)
        yellow = (0, 255, 255)

    # ---------- Title ----------
        cv2.putText(
            frame,
            "Water Hyacinth",
            (30, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            white,
            2,
            cv2.LINE_AA
        )

    # ---------- FPS ----------
        cv2.putText(
            frame,
            f"FPS : {self.fps:.2f}",
            (30, 68),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            green,
            2,
            cv2.LINE_AA
        )

    # ---------- Count ----------
        cv2.putText(
            frame,
            f"Detected : {self.detected_count}",
            (30, 93),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            yellow,
            2,
            cv2.LINE_AA
        )

    # ---------- Confidence ----------
        cv2.putText(
            frame,
            f"Conf : {self.best_confidence*100:.1f}%",
            (30, 118),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            white,
            2,
            cv2.LINE_AA
        )
# prev_time = time.time()

    def generate_frames(self):

        while True:

            with self.lock:

                if self.output_frame is None:
                    frame = None
                else:
                    frame = self.output_frame.copy()

            if frame is None:
                time.sleep(0.01)
                continue

            small_frame = cv2.resize(frame, (480, 270))
            ret, buffer = cv2.imencode(
                ".jpg",
                small_frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), 70]
            )

            if not ret:
                continue

            frame = buffer.tobytes()

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + frame +
                b'\r\n'
            )