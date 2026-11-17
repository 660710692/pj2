"""
จัดการ "จุดติดตั้ง" หลายจุด (1 จุด = กล้อง 1 ตัว + ปั๊ม ESP32 1 ตัว)

- เก็บรายการกล้องและค่าตั้งค่าไว้ใน instance/config.json
  (แก้ผ่านหน้าเว็บ "อุปกรณ์" และ "ตั้งค่า" ได้ ไม่ต้องแก้โค้ด)
- ครั้งแรกที่รัน จะสร้างจุดที่ 1 จาก RTSP_URL / ESP32_HOST เดิมให้อัตโนมัติ
- แต่ละกล้องมี Detector (YOLO + tracker) ของตัวเอง
"""

import ipaddress
import json
import os
import re
import threading

import thai_time
from detector import Detector
from esp32_udp import BROADCAST

DEFAULT_SETTINGS = {
    "auto_spray": True,          # เปิด/ปิดการพ่นอัตโนมัติ
    "spray_confidence": 0.30,    # ความมั่นใจขั้นต่ำที่จะพ่น (ทดสอบกับ best_v4 แล้ว)
    "detect_confidence": 0.25,   # ความมั่นใจขั้นต่ำที่จะแสดงกรอบ / ติดตาม
    "spray_window": 6,           # ดูกี่เฟรมล่าสุด
    "spray_min_hits": 4,         # ต้องเจอกี่ครั้งในนั้น
    "cooldown_seconds": 10,      # เว้นระยะระหว่างการพ่น (วินาที, นับจากเริ่มพ่น)
    "spray_seconds": 2.0,        # ระยะเวลาพ่นต่อครั้ง (วินาที) ส่งไปให้ ESP32
}

LIMITS = {
    "spray_confidence": (0.05, 0.95),
    "detect_confidence": (0.05, 0.95),
    "spray_window": (1, 30),
    "spray_min_hits": (1, 30),
    "cooldown_seconds": (0, 3600),
    "spray_seconds": (0.5, 600),     # ESP32 จำกัดสูงสุด 10 นาทีเช่นกัน
}

DEFAULT_RTSP = "rtsp://admin:bm9BqimE@192.168.1.100:554/Streaming/Channels/102"
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9\-\.]{0,251}[A-Za-z0-9])?$")


def mask_url(url):
    """ซ่อนรหัสผ่านในลิงก์ RTSP เวลาแสดงผล"""
    return re.sub(r"(//[^:/@]+):[^@]*@", r"\1:•••@", str(url))


def is_broadcast(host):
    return (not host) or host == BROADCAST


class CameraManager:

    def __init__(self, store, config_path=None, model_path=None):
        self.store = store
        self.model_path = model_path or os.environ.get("MODEL_PATH", "models/best.pt")
        self.config_path = config_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "instance", "config.json"
        )
        self.lock = threading.RLock()
        self.detectors = {}
        self.config = self._load_config()

        for camera in self.config["cameras"]:
            if camera["enabled"]:
                self._start(camera)

    # ------------------------------------------------------------------
    # Config file
    # ------------------------------------------------------------------

    def _load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, encoding="utf-8") as file:
                config = json.load(file)
        else:
            # ครั้งแรก: สร้างจุดที่ 1 จากค่าเดิม
            config = {
                "settings": {},
                "cameras": [{
                    "id": "cam1",
                    "name": "จุดที่ 1",
                    "rtsp_url": os.environ.get("RTSP_URL", DEFAULT_RTSP),
                    "esp32_host": os.environ.get("ESP32_HOST", ""),
                    "enabled": True,
                }],
            }
        settings = dict(DEFAULT_SETTINGS)
        settings.update(config.get("settings", {}))
        config["settings"] = settings
        config.setdefault("cameras", [])
        for camera in config["cameras"]:
            camera.setdefault("enabled", True)
            camera.setdefault("esp32_host", "")
        self._write(config)
        return config

    def _write(self, config):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        temp_path = self.config_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
        os.replace(temp_path, self.config_path)   # เขียนทับแบบปลอดภัย ไฟล์ไม่เสียถ้าไฟดับ

    def _save(self):
        self._write(self.config)

    # ------------------------------------------------------------------
    # Detectors
    # ------------------------------------------------------------------

    def _start(self, camera):
        detector = Detector(
            camera, self.config["settings"],
            detection_store=self.store, model_path=self.model_path,
        )
        self.detectors[camera["id"]] = detector

    def _stop(self, camera_id):
        detector = self.detectors.pop(camera_id, None)
        if detector is not None:
            detector.stop()

    def shutdown(self):
        with self.lock:
            for camera_id in list(self.detectors):
                self._stop(camera_id)

    # ------------------------------------------------------------------
    # Cameras (จุดติดตั้ง)
    # ------------------------------------------------------------------

    def camera_names(self):
        with self.lock:
            return {camera["id"]: camera["name"] for camera in self.config["cameras"]}

    def _find(self, camera_id):
        for camera in self.config["cameras"]:
            if camera["id"] == camera_id:
                return camera
        return None

    def _next_id(self):
        numbers = [
            int(camera["id"][3:]) for camera in self.config["cameras"]
            if camera["id"].startswith("cam") and camera["id"][3:].isdigit()
        ]
        return f"cam{max(numbers, default=0) + 1}"

    def _validate(self, data, editing_id=None):
        errors = {}
        name = str(data.get("name", "")).strip()
        rtsp_url = str(data.get("rtsp_url", "")).strip()
        esp32_host = str(data.get("esp32_host", "")).strip()
        enabled = bool(data.get("enabled", True))

        if not name:
            errors["name"] = "กรุณาใส่ชื่อจุดติดตั้ง"
        elif len(name) > 60:
            errors["name"] = "ชื่อยาวเกินไป (ไม่เกิน 60 ตัวอักษร)"
        elif any(
            c["name"] == name and c["id"] != editing_id for c in self.config["cameras"]
        ):
            errors["name"] = "มีจุดติดตั้งชื่อนี้แล้ว"

        if not rtsp_url:
            errors["rtsp_url"] = "กรุณาใส่ลิงก์กล้อง"
        elif not (
            rtsp_url.isdigit()
            or rtsp_url.lower().startswith(("rtsp://", "rtsps://", "http://", "https://"))
        ):
            errors["rtsp_url"] = "ลิงก์กล้องต้องขึ้นต้นด้วย rtsp:// (หรือเป็นเลขกล้อง USB เช่น 0)"

        if esp32_host == BROADCAST:
            esp32_host = ""
        if esp32_host:
            try:
                ipaddress.ip_address(esp32_host)
            except ValueError:
                if not HOSTNAME_RE.match(esp32_host):
                    errors["esp32_host"] = "รูปแบบ IP ไม่ถูกต้อง เช่น 192.168.1.50"

        # กล้องแต่ละตัวคุมปั๊มของตัวเอง -> ถ้ามีหลายจุด ต้องระบุ IP ทุกจุด และห้ามซ้ำ
        others = [c for c in self.config["cameras"] if c["id"] != editing_id]
        if others and "esp32_host" not in errors:
            if not esp32_host:
                errors["esp32_host"] = (
                    "เมื่อมีมากกว่า 1 จุด ต้องใส่ IP ของ ESP32 "
                    "(ถ้าเว้นว่าง คำสั่งจะไปถึงปั๊มทุกจุดพร้อมกัน)"
                )
            elif any(c.get("esp32_host") == esp32_host for c in others):
                errors["esp32_host"] = "IP นี้ถูกใช้กับจุดอื่นแล้ว (1 จุดต้องมีปั๊มของตัวเอง)"
            else:
                missing = [c["name"] for c in others if is_broadcast(c.get("esp32_host"))]
                if missing:
                    errors["esp32_host"] = (
                        f"จุด “{missing[0]}” ยังไม่ได้ใส่ IP ของ ESP32 "
                        "กรุณาแก้ไขจุดนั้นให้ใส่ IP ก่อนเพิ่มจุดใหม่"
                    )

        clean = {
            "name": name, "rtsp_url": rtsp_url,
            "esp32_host": esp32_host, "enabled": enabled,
        }
        return clean, errors

    def add_camera(self, data):
        with self.lock:
            clean, errors = self._validate(data)
            if errors:
                return None, errors
            camera = {"id": self._next_id(), **clean}
            self.config["cameras"].append(camera)
            self._save()
            if camera["enabled"]:
                self._start(camera)
            return dict(camera), {}

    def update_camera(self, camera_id, data):
        with self.lock:
            camera = self._find(camera_id)
            if camera is None:
                return None, {"_": "ไม่พบจุดติดตั้งนี้"}
            clean, errors = self._validate(data, editing_id=camera_id)
            if errors:
                return None, errors

            needs_restart = (
                clean["rtsp_url"] != camera["rtsp_url"]
                or clean["esp32_host"] != camera["esp32_host"]
                or clean["enabled"] != camera["enabled"]
            )
            camera.update(clean)
            self._save()

            detector = self.detectors.get(camera_id)
            if needs_restart:
                self._stop(camera_id)
                if camera["enabled"]:
                    self._start(camera)
            elif detector is not None:
                detector.name = camera["name"]
            return dict(camera), {}

    def delete_camera(self, camera_id):
        with self.lock:
            camera = self._find(camera_id)
            if camera is None:
                return False
            self._stop(camera_id)
            self.config["cameras"].remove(camera)
            self._save()
            return True

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_settings(self):
        with self.lock:
            return dict(self.config["settings"])

    def update_settings(self, data):
        with self.lock:
            settings = dict(self.config["settings"])
            errors = {}
            for key, (low, high) in LIMITS.items():
                if key not in data:
                    continue
                try:
                    value = float(data[key])
                except (TypeError, ValueError):
                    errors[key] = "กรุณาใส่ตัวเลข"
                    continue
                if not low <= value <= high:
                    errors[key] = f"ต้องอยู่ระหว่าง {low:g} ถึง {high:g}"
                    continue
                settings[key] = int(value) if key in (
                    "spray_window", "spray_min_hits", "cooldown_seconds"
                ) else round(value, 3)
            if "auto_spray" in data:
                settings["auto_spray"] = bool(data["auto_spray"])

            if not errors:
                if settings["spray_min_hits"] > settings["spray_window"]:
                    errors["spray_min_hits"] = "จำนวนครั้งที่ต้องเห็น ต้องไม่เกินจำนวนภาพที่ดู"
                if settings["detect_confidence"] > settings["spray_confidence"]:
                    errors["detect_confidence"] = (
                        "ค่าการแสดงกรอบต้องไม่สูงกว่าค่าการพ่น "
                        "(ไม่อย่างนั้นระบบจะไม่เห็นวัตถุที่ควรพ่น)"
                    )
            if errors:
                return None, errors

            self.config["settings"] = settings
            self._save()
            for detector in self.detectors.values():
                detector.apply_settings(settings)
            return dict(settings), {}

    def set_auto_spray(self, enabled):
        settings, _ = self.update_settings({"auto_spray": bool(enabled)})
        return settings

    # ------------------------------------------------------------------
    # Pump control
    # ------------------------------------------------------------------

    def manual_spray(self, camera_id):
        with self.lock:
            detector = self.detectors.get(camera_id)
        if detector is None:
            return False, "จุดนี้ปิดใช้งานอยู่"
        if not detector.manual_spray():
            return False, "ปั๊มกำลังทำงานอยู่ รอให้หยุดก่อน"
        return True, "ส่งคำสั่งพ่นแล้ว"

    def stop_pump(self, camera_id):
        with self.lock:
            detector = self.detectors.get(camera_id)
        if detector is None:
            return False, "จุดนี้ปิดใช้งานอยู่"
        detector.stop_pump()
        return True, "ส่งคำสั่งหยุดปั๊มแล้ว"

    def emergency_stop(self):
        """หยุดปั๊มทุกจุด + ปิดการพ่นอัตโนมัติ (กันไม่ให้พ่นซ้ำทันที)"""
        self.set_auto_spray(False)
        with self.lock:
            detectors = list(self.detectors.values())
        for detector in detectors:
            detector.stop_pump()
        return len(detectors)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_frame(self, camera_id=None):
        with self.lock:
            if camera_id is None and self.detectors:
                camera_id = next(iter(self.detectors))
            detector = self.detectors.get(camera_id)
        return detector.get_latest_frame() if detector else None

    def get_detector(self, camera_id):
        with self.lock:
            return self.detectors.get(camera_id)

    def overview(self):
        with self.lock:
            cameras = [dict(c) for c in self.config["cameras"]]
            detectors = dict(self.detectors)
            settings = dict(self.config["settings"])

        items, alerts = [], []
        cameras_online = pumps_online = enabled_count = 0

        if not settings["auto_spray"]:
            alerts.append({
                "level": "warning",
                "text": "ปิดการพ่นอัตโนมัติอยู่ — ระบบยังตรวจจับ แต่จะไม่สั่งพ่น",
            })

        for camera in cameras:
            detector = detectors.get(camera["id"])
            item = {
                "id": camera["id"],
                "name": camera["name"],
                "enabled": camera["enabled"],
                "rtsp_display": mask_url(camera["rtsp_url"]),
                "rtsp_url": camera["rtsp_url"],
                "esp32_host": camera["esp32_host"],
            }
            if detector is None:
                item.update({"camera_status": "Disabled", "fps": 0, "detected": 0,
                             "objects": [], "timestamp": "", "pump": None})
            else:
                enabled_count += 1
                item.update(detector.get_live_status())
                if item["camera_status"] == "Connected":
                    cameras_online += 1
                elif item["camera_status"] == "Disconnected":
                    alerts.append({
                        "level": "danger", "camera_id": camera["id"],
                        "text": f"กล้องที่ “{camera['name']}” ไม่ได้เชื่อมต่อ "
                                "— ตรวจสอบไฟเลี้ยงและสายแลน/WiFi ของกล้อง",
                    })
                pump = item["pump"]
                if pump["online"]:
                    pumps_online += 1
                if pump["duration_mismatch"]:
                    alerts.append({
                        "level": "warning", "camera_id": camera["id"],
                        "text": f"ปั๊มที่ \u201c{camera['name']}\u201d พ่น {pump['duration_s']:g} วินาที "
                                f"ไม่ตรงกับที่ตั้งไว้ ({settings['spray_seconds']:g} วินาที) "
                                "— กรุณาอัปโหลด esp32_udp_pump.ino เวอร์ชันใหม่ให้ ESP32 ตัวนี้",
                    })
                elif pump["online"] is False:
                    alerts.append({
                        "level": "danger", "camera_id": camera["id"],
                        "text": f"ปั๊มที่ “{camera['name']}” ไม่ตอบสนอง "
                                "— ตรวจสอบไฟเลี้ยงและ WiFi ของ ESP32",
                    })
            items.append(item)

        if not cameras:
            alerts.append({
                "level": "info",
                "text": "ยังไม่มีจุดติดตั้ง — เพิ่มกล้องและปั๊มได้ที่หน้า “อุปกรณ์”",
            })

        now = thai_time.now_utc()
        return {
            "server_epoch": now.timestamp(),
            "server_time": thai_time.fmt_datetime(now),
            "utc_offset_hours": thai_time.UTC_OFFSET_HOURS,
            "auto_spray": settings["auto_spray"],
            "model_path": self.model_path,
            "cameras": items,
            "alerts": alerts,
            "counts": {
                "cameras_total": enabled_count,
                "cameras_online": cameras_online,
                "pumps_online": pumps_online,
            },
        }
