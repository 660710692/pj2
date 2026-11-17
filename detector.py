import os

# ต้องตั้งค่านี้ก่อน import cv2 เพื่อบังคับให้ RTSP ใช้ TCP (ลดภาพแตก/ค้างจากแพ็กเก็ตหาย)
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2
import numpy as np
import time
import threading
from collections import deque

import thai_time
from tracker import ObjectTracker
from speed_calculator import SpeedCalculator
from spray_controller import SprayDecision
from detection_store import DetectionStore
from esp32_udp import ESP32UDP, BROADCAST

from ultralytics import YOLO


class Detector:
    """
    ตรวจจับ + สั่งพ่น สำหรับ "จุดติดตั้ง" 1 จุด (กล้อง 1 ตัว + ปั๊ม ESP32 1 ตัว)
    CameraManager จะสร้าง Detector 1 ตัวต่อกล้อง 1 ตัว
    """

    def __init__(self, camera, settings, detection_store=None, model_path=None,
                 debug_print=False):

        self.camera_id = camera["id"]
        self.name = camera["name"]
        self.rtsp_url = camera["rtsp_url"]
        self.esp32_host = camera.get("esp32_host") or BROADCAST

        # .pt file or NCNN folder (faster on Pi), e.g. MODEL_PATH=models/best_ncnn_model
        # NCNN must be exported with the same imgsz used below (640)
        self.model_path = model_path or os.environ.get("MODEL_PATH", "models/best.pt")
        self.model = YOLO(self.model_path, task="detect")
        print(f"[{self.name}] Model: {self.model_path}")

        self.detection_store = (
            detection_store if detection_store is not None else DetectionStore()
        )

        # True = print ทุก object ทุกเฟรม (ช้า) / False = print เฉพาะตอนสั่งพ่น
        self.debug_print = debug_print

        self.cap = None
        self.camera_status = "Connecting"
        self.fps = 0
        self.detected_count = 0
        self.timestamp = ""
        self.prev_time = time.time()

        self.best_confidence = 0.0
        self.detected_objects = []
        self.recorded_track_ids = set()
        self.hit_history = {}  # track_id -> deque ของ True/False ใน spray_window เฟรมล่าสุด

        self.tracker = ObjectTracker()
        self.speed_calculator = SpeedCalculator(pixels_per_meter=100)
        self.spray_decision = SprayDecision(min_speed=0.0)

        self.lock = threading.Lock()
        self.apply_settings(settings)

        # ---------- ESP32 ของจุดนี้ (Relay -> ปั๊มพ่นยา) ----------
        self.esp32 = ESP32UDP(
            host=self.esp32_host,
            on_event=self._on_pump_event,
            name=f"ESP32 {self.name}",
        )

        # ---------- Multi Thread Buffer ----------
        self.latest_frame = None
        self.frame_sequence = 0      # เพิ่มทุกครั้งที่กล้องได้เฟรมใหม่
        self.output_frame = None
        self.output_sequence = 0     # เพิ่มทุกครั้งที่ YOLO ประมวลผลเสร็จ 1 เฟรม
        self.running = True
        self.waiting_frame = self.create_waiting_frame()

        self.camera_thread = threading.Thread(target=self.camera_worker, daemon=True)
        self.detect_thread = threading.Thread(target=self.detect_worker, daemon=True)
        self.camera_thread.start()
        self.detect_thread.start()

    # ------------------------------------------------------------------
    # Settings (เปลี่ยนจากหน้าตั้งค่าได้ทันที ไม่ต้องรีสตาร์ท)
    # ------------------------------------------------------------------

    def apply_settings(self, settings):
        with self.lock:
            # กฎ "N จาก M เฟรมล่าสุด" (เหมาะกับน้ำไหล)
            window = int(settings["spray_window"])
            if window != getattr(self, "spray_window", None):
                self.hit_history = {}
            self.spray_window = window
            self.spray_min_hits = int(settings["spray_min_hits"])
            self.min_spray_confidence = float(settings["spray_confidence"])
            self.detect_confidence = float(settings["detect_confidence"])
            self.auto_spray = bool(settings["auto_spray"])

            # แก้ค่าใน SprayDecision ตรง ๆ (ไม่สร้างใหม่ -> เวลา cooldown ล่าสุดไม่หาย)
            self.spray_decision.confidence_threshold = self.min_spray_confidence
            self.spray_decision.cooldown_seconds = float(settings["cooldown_seconds"])

            # ระยะเวลาพ่นต่อครั้ง (ส่งไปกับคำสั่งพ่น ESP32 จะพ่นตามนี้)
            self.spray_duration_ms = int(round(float(settings["spray_seconds"]) * 1000))

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def connect_camera(self):
        if self.cap is not None:
            self.cap.release()

        if str(self.rtsp_url).strip().isdigit():
            # กล้อง USB เช่น "0" (ไว้ทดสอบ)
            self.cap = cv2.VideoCapture(int(self.rtsp_url))
        else:
            timeout_params = [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000,
            ]
            self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG, timeout_params)

        if self.cap.isOpened():
            # เก็บ buffer ให้น้อยที่สุด จะได้ภาพล่าสุดเสมอ ไม่ดีเลย์สะสม
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.camera_status = "Connected"
            print(f"[{self.name}] Camera Connected")
        else:
            self.camera_status = "Disconnected"
            print(f"[{self.name}] Cannot connect to camera; retrying in 2 seconds")

    def camera_worker(self):

        while self.running:

            if self.cap is None or not self.cap.isOpened():
                try:
                    self.connect_camera()
                except cv2.error as error:
                    self.camera_status = "Disconnected"
                    print(f"[{self.name}] Camera connection failed: {error}")
                if self.cap is None or not self.cap.isOpened():
                    time.sleep(2)
                continue

            ret, frame = self.cap.read()

            if not ret:
                if not self.running:
                    break
                print(f"[{self.name}] Camera read failed; reconnecting")
                self.mark_camera_disconnected()
                time.sleep(2)
                continue

            with self.lock:
                self.latest_frame = frame
                self.frame_sequence += 1
                self.camera_status = "Connected"

        # ปิดกล้องใน thread นี้เอง (ปิดจาก thread อื่นระหว่างอ่านภาพอาจทำให้ OpenCV ค้าง)
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def mark_camera_disconnected(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        with self.lock:
            self.camera_status = "Disconnected"
            self.latest_frame = None
            self.output_frame = None
            self.output_sequence += 1   # ให้สตรีมเปลี่ยนไปแสดงภาพ "Waiting"
            self.detected_count = 0
            self.best_confidence = 0.0
            self.detected_objects = []
            self.fps = 0

    @staticmethod
    def create_waiting_frame():
        frame = np.zeros((270, 480, 3), dtype=np.uint8)
        cv2.putText(
            frame, "Waiting for camera...", (115, 135),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 220, 220), 2, cv2.LINE_AA,
        )
        return frame

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_worker(self):   # แบบ Track
        last_processed_sequence = 0

        while self.running:

            # 1. เอา frame ล่าสุดมา (ถ้ายังไม่มีเฟรมใหม่ก็รอ)
            with self.lock:
                frame_available = (
                    self.latest_frame is not None
                    and self.frame_sequence != last_processed_sequence
                )
                frame = self.latest_frame.copy() if frame_available else None
                if frame_available:
                    last_processed_sequence = self.frame_sequence
                detect_confidence = self.detect_confidence
                min_spray_confidence = self.min_spray_confidence
                spray_window = self.spray_window
                spray_min_hits = self.spray_min_hits
                auto_spray = self.auto_spray

            if frame is None:
                time.sleep(0.01)
                continue

            # 2. YOLO + ByteTrack
            try:
                results = self.model.track(
                    frame,
                    conf=detect_confidence,
                    imgsz=640,
                    tracker="bytetrack.yaml",
                    persist=True,
                    verbose=False
                )
            except Exception as error:
                print(f"[{self.name}] Detection error: {error}")
                time.sleep(0.1)
                continue

            result = results[0]

            # 3. ดึงข้อมูล Object ที่ Track ได้
            objects = self.tracker.update(result)

            best_confidence = max(
                (float(obj["confidence"]) for obj in objects),
                default=0.0
            )

            for obj in objects:
                object_id = obj["id"]
                if object_id not in self.recorded_track_ids:
                    try:
                        self.detection_store.record_detection(
                            object_id, obj["confidence"], camera_id=self.camera_id,
                        )
                    except Exception as error:
                        print(f"[{self.name}] Could not save detection: {error}")
                    self.recorded_track_ids.add(object_id)

            # 4. คำนวณ Speed + Spray Decision
            tracked_objects = []
            spray_target = None
            # ปั๊มกำลังทำงาน -> ไม่ตัดสินใจพ่นใหม่จนกว่าปั๊มจะปิด
            pump_active = self.esp32.is_pump_active()
            # ESP32 ไม่ตอบสนอง (ถามสถานะไม่ตอบ) -> ไม่สั่งพ่นอัตโนมัติ (หน้าเว็บแจ้งเตือนแล้ว)
            pump_offline = self.esp32.online is False

            # อัปเดตประวัติการตรวจเจอของแต่ละ object ใน spray_window เฟรมล่าสุด
            seen = {
                obj["id"] for obj in objects
                if float(obj["confidence"]) >= min_spray_confidence
            }
            for track_id in seen | set(self.hit_history):
                history = self.hit_history.setdefault(
                    track_id, deque(maxlen=spray_window)
                )
                history.append(track_id in seen)
            # ลบ object ที่ไม่เจอเลยตลอด window (ลอยออกจากภาพไปแล้ว)
            self.hit_history = {
                track_id: history for track_id, history in self.hit_history.items()
                if any(history)
            }

            for obj in objects:

                object_id = obj["id"]
                confidence = float(obj["confidence"])

                speed = self.speed_calculator.update(
                    object_id, obj["center_x"], obj["center_y"]
                )

                tracked_objects.append({
                    "id": object_id,
                    "confidence": confidence,
                    "speed": speed,
                })

                hits = sum(self.hit_history.get(object_id, ()))

                if not auto_spray:
                    should_spray, reason = False, "auto spray off"
                elif pump_offline:
                    should_spray, reason = False, "pump offline"
                elif pump_active or spray_target is not None:
                    # ไม่เรียก should_spray เพื่อไม่ให้เสีย cooldown โดยเปล่าประโยชน์
                    should_spray = False
                    reason = "pump active" if pump_active else "already triggered this frame"
                elif hits < spray_min_hits:
                    # ยังเจอไม่ครบ N จาก M เฟรมล่าสุด -> ยังไม่พ่น
                    should_spray = False
                    reason = f"waiting {hits}/{spray_min_hits} hits in last {spray_window} frames"
                else:
                    should_spray, reason = self.spray_decision.should_spray(
                        confidence=confidence, speed=speed, chemical_available=True
                    )

                # print ทุกเฟรมทำให้ loop ช้ามาก จึง print เฉพาะตอนสั่งพ่น
                if should_spray or self.debug_print:
                    print(
                        f"[{self.name}] ID={object_id} Conf={confidence:.2f} "
                        f"Speed={speed:.2f} m/s Decision={should_spray} Reason={reason}"
                    )

                if should_spray:
                    spray_target = (object_id, confidence)

            # ส่ง "1" ไป ESP32 แค่ครั้งเดียวต่อเฟรม แม้จะเจอหลาย object
            if spray_target is not None:
                sent = self.esp32.trigger({
                    "source": "auto",
                    "track_id": spray_target[0],
                    "confidence": spray_target[1],
                }, duration_ms=self.spray_duration_ms)
                if sent:
                    # เริ่มนับ cooldown (เดิมไม่ได้เรียก ทำให้ cooldown ไม่เคยทำงาน)
                    self.spray_decision.record_spray()

            output = result.plot()
            current_time = time.time()

            # 5. อัปเดตผลลัพธ์ (ไม่ทิ้งผลแม้จะมีเฟรมใหม่เข้ามาระหว่างประมวลผล)
            with self.lock:
                if self.latest_frame is None:
                    # กล้องหลุดระหว่างประมวลผล ไม่ต้องแสดงภาพเก่า
                    continue

                self.detected_count = len(objects)
                self.best_confidence = best_confidence
                self.detected_objects = tracked_objects
                self.timestamp = thai_time.now_local().strftime("%Y-%m-%d %H:%M:%S")

                elapsed = current_time - self.prev_time
                instant_fps = 1 / elapsed if elapsed > 0 else 0
                # ทำให้ค่า FPS นิ่งขึ้น ไม่กระโดดไปมา
                self.fps = (
                    instant_fps if self.fps == 0
                    else self.fps * 0.8 + instant_fps * 0.2
                )
                self.prev_time = current_time

                self.output_frame = output
                self.output_sequence += 1

    # ------------------------------------------------------------------
    # Pump
    # ------------------------------------------------------------------

    def _on_pump_event(self, source, outcome, duration_ms, context):
        """ESP32 ตอบกลับแล้ว -> บันทึกประวัติการพ่น"""
        self.detection_store.record_spray(
            camera_id=self.camera_id,
            source=source,
            outcome=outcome,
            track_id=context.get("track_id"),
            confidence=context.get("confidence"),
            duration_ms=duration_ms,
        )

    def manual_spray(self):
        if self.esp32.is_pump_active():
            return False
        return self.esp32.trigger({"source": "manual"}, duration_ms=self.spray_duration_ms)

    def stop_pump(self):
        self.esp32.stop_pump()

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def get_live_status(self):
        with self.lock:
            return {
                "camera_status": self.camera_status,
                "fps": round(self.fps, 1),
                "detected": self.detected_count,
                "timestamp": self.timestamp,
                "best_confidence": self.best_confidence,
                "objects": [
                    {"id": obj["id"], "confidence": round(obj["confidence"], 3)}
                    for obj in self.detected_objects
                ],
                "pump": self.esp32.get_status(),
            }

    def get_latest_frame(self):
        with self.lock:
            frame = (
                self.waiting_frame.copy()
                if self.output_frame is None
                else self.output_frame.copy()
            )

        if frame.shape[1] > 960:
            height = round(frame.shape[0] * 960 / frame.shape[1])
            frame = cv2.resize(frame, (960, height))

        success, encoded_frame = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75],
        )
        if not success:
            raise RuntimeError("Could not encode the latest camera frame")

        return encoded_frame.tobytes()

    def generate_frames(self, max_fps=20):
        """สตรีม MJPEG ไปเบราว์เซอร์ — ส่งเฉพาะตอนมีเฟรมใหม่จาก YOLO"""
        min_interval = 1 / max_fps
        last_sent_sequence = -1
        last_sent_at = 0.0
        keepalive_seconds = 1.0   # ส่งภาพซ้ำทุก 1 วิ กันเบราว์เซอร์ตัดการเชื่อมต่อ

        while self.running:
            now = time.monotonic()

            with self.lock:
                sequence = self.output_sequence
                has_new = sequence != last_sent_sequence
                need_keepalive = now - last_sent_at >= keepalive_seconds

                if not has_new and not need_keepalive:
                    frame = None
                elif self.output_frame is None:
                    frame = self.waiting_frame.copy()
                else:
                    frame = self.output_frame.copy()

            if frame is None or now - last_sent_at < min_interval:
                time.sleep(0.01)
                continue

            if frame.shape[1] > 480 or frame.shape[0] > 270:
                frame = cv2.resize(frame, (480, 270))

            ret, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if not ret:
                continue

            last_sent_sequence = sequence
            last_sent_at = now

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + buffer.tobytes() +
                b'\r\n'
            )

    def stop(self):
        """หยุดจุดนี้ (กล้องจะปิดเองใน camera thread)"""
        self.running = False
        self.esp32.stop()
