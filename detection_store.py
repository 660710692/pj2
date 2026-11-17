import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import thai_time


class DetectionStore:
    """
    เก็บประวัติการตรวจพบ + ประวัติการพ่น ลง SQLite (instance/detections.sqlite3)

    - ใช้ไฟล์ฐานข้อมูลเดิม ข้อมูลเก่ายังอยู่ครบ
    - เพิ่มคอลัมน์ camera_id ให้ตารางเดิมอัตโนมัติ (ข้อมูลเก่าจะเป็นของ cam1)
    - เพิ่มตาราง spray_events สำหรับประวัติการพ่น
    - เวลาเก็บเป็น UTC เหมือนเดิม แปลงเป็นเวลาไทยตอนแสดงผล (thai_time.py)
    """

    def __init__(self, db_path=None):
        self.db_path = db_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "instance",
            "detections.sqlite3",
        )
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self.write_lock = threading.Lock()   # หลายกล้องเขียนพร้อมกันได้อย่างปลอดภัย

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS detection_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    detected_at TEXT NOT NULL,
                    track_id INTEGER NOT NULL,
                    confidence REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_detection_events_detected_at
                ON detection_events (detected_at)
                """
            )

            # migration: เพิ่ม camera_id ให้ฐานข้อมูลเดิม
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(detection_events)")
            }
            if "camera_id" not in columns:
                connection.execute(
                    "ALTER TABLE detection_events "
                    "ADD COLUMN camera_id TEXT NOT NULL DEFAULT 'cam1'"
                )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS spray_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sprayed_at TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    source TEXT NOT NULL,      -- auto / manual / stop
                    outcome TEXT NOT NULL,     -- pump_on / busy / stopped / no_reply
                    track_id INTEGER,
                    confidence REAL,
                    duration_ms INTEGER
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_spray_events_sprayed_at
                ON spray_events (sprayed_at)
                """
            )

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _format_timestamp(value):
        return value.astimezone(timezone.utc).isoformat(timespec="seconds")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_detection(self, track_id, confidence, detected_at=None, camera_id="cam1"):
        timestamp = self._format_timestamp(
            detected_at or datetime.now(timezone.utc)
        )
        with self.write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO detection_events (detected_at, track_id, confidence, camera_id)
                VALUES (?, ?, ?, ?)
                """,
                (timestamp, int(track_id), float(confidence), str(camera_id)),
            )

    def record_spray(self, camera_id, source, outcome, track_id=None,
                     confidence=None, duration_ms=None, sprayed_at=None):
        timestamp = self._format_timestamp(sprayed_at or datetime.now(timezone.utc))
        with self.write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO spray_events
                    (sprayed_at, camera_id, source, outcome, track_id, confidence, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp, str(camera_id), source, outcome,
                    None if track_id is None else int(track_id),
                    None if confidence is None else float(confidence),
                    None if duration_ms is None else int(duration_ms),
                ),
            )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_summary(self, now=None):
        """รูปแบบเดิม (เผื่อมีโค้ดอื่นเรียกใช้)"""
        current_time = now or datetime.now(timezone.utc)
        cutoff = self._format_timestamp(current_time - timedelta(hours=24))

        with self._connect() as connection:
            totals = connection.execute(
                """
                SELECT COUNT(*) AS total_count, MAX(detected_at) AS last_detected_at
                FROM detection_events
                """
            ).fetchone()
            recent_totals = connection.execute(
                """
                SELECT COUNT(*) AS count, AVG(confidence) AS average_confidence
                FROM detection_events
                WHERE detected_at >= ?
                """,
                (cutoff,),
            ).fetchone()
            recent_events = connection.execute(
                """
                SELECT detected_at, track_id, confidence
                FROM detection_events
                ORDER BY detected_at DESC, id DESC
                LIMIT 10
                """
            ).fetchall()

        return {
            "count_24h": recent_totals["count"],
            "total_count": totals["total_count"],
            "average_confidence_24h": recent_totals["average_confidence"],
            "last_detected_at": totals["last_detected_at"],
            "recent_events": [dict(event) for event in recent_events],
        }

    def get_stats(self, camera_names=None, recent_limit=15):
        """ข้อมูลสำหรับแดชบอร์ด (เวลาเป็นเวลาไทยแล้ว)"""
        names = camera_names or {}
        now = thai_time.now_utc()
        today_cutoff = thai_time.local_midnight_utc_iso(now)
        cutoff_24h = self._format_timestamp(now - timedelta(hours=24))

        with self._connect() as connection:
            det_today = connection.execute(
                """
                SELECT camera_id, COUNT(*) AS count FROM detection_events
                WHERE detected_at >= ? GROUP BY camera_id
                """,
                (today_cutoff,),
            ).fetchall()
            spray_today = connection.execute(
                """
                SELECT camera_id, COUNT(*) AS count FROM spray_events
                WHERE sprayed_at >= ? AND outcome = 'pump_on' GROUP BY camera_id
                """,
                (today_cutoff,),
            ).fetchall()
            det_24h = connection.execute(
                "SELECT detected_at FROM detection_events WHERE detected_at >= ?",
                (cutoff_24h,),
            ).fetchall()
            spray_24h = connection.execute(
                """
                SELECT sprayed_at FROM spray_events
                WHERE sprayed_at >= ? AND outcome = 'pump_on'
                """,
                (cutoff_24h,),
            ).fetchall()
            recent_detections = connection.execute(
                """
                SELECT detected_at, track_id, confidence, camera_id
                FROM detection_events ORDER BY detected_at DESC, id DESC LIMIT ?
                """,
                (recent_limit,),
            ).fetchall()
            recent_sprays = connection.execute(
                """
                SELECT sprayed_at, camera_id, source, outcome, track_id, confidence, duration_ms
                FROM spray_events ORDER BY sprayed_at DESC, id DESC LIMIT ?
                """,
                (recent_limit,),
            ).fetchall()
            last_detection = connection.execute(
                "SELECT MAX(detected_at) AS t FROM detection_events"
            ).fetchone()["t"]
            last_spray = connection.execute(
                "SELECT MAX(sprayed_at) AS t FROM spray_events WHERE outcome = 'pump_on'"
            ).fetchone()["t"]
            total_detections = connection.execute(
                "SELECT COUNT(*) AS c FROM detection_events"
            ).fetchone()["c"]
            total_sprays = connection.execute(
                "SELECT COUNT(*) AS c FROM spray_events WHERE outcome = 'pump_on'"
            ).fetchone()["c"]

        def camera_name(camera_id):
            return names.get(camera_id, f"{camera_id} (ลบแล้ว)")

        # กราฟรายชั่วโมง 24 ชม. ล่าสุด (ชั่วโมงตามเวลาไทย)
        local_now = now.astimezone(thai_time.LOCAL_TZ)
        start = local_now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
        hourly = [
            {"label": f"{(start + timedelta(hours=i)):%H}:00", "detections": 0, "sprays": 0}
            for i in range(24)
        ]

        def bucket(value):
            local = thai_time.to_local(value)
            index = int((local - start).total_seconds() // 3600)
            return index if 0 <= index < 24 else None

        for row in det_24h:
            index = bucket(row["detected_at"])
            if index is not None:
                hourly[index]["detections"] += 1
        for row in spray_24h:
            index = bucket(row["sprayed_at"])
            if index is not None:
                hourly[index]["sprays"] += 1

        det_today_map = {row["camera_id"]: row["count"] for row in det_today}
        spray_today_map = {row["camera_id"]: row["count"] for row in spray_today}

        return {
            "today": {
                "detections": sum(det_today_map.values()),
                "sprays": sum(spray_today_map.values()),
                "by_camera": {
                    camera_id: {
                        "detections": det_today_map.get(camera_id, 0),
                        "sprays": spray_today_map.get(camera_id, 0),
                    }
                    for camera_id in set(det_today_map) | set(spray_today_map) | set(names)
                },
            },
            "totals": {"detections": total_detections, "sprays": total_sprays},
            "last_detection": thai_time.event_time(last_detection) if last_detection else None,
            "last_spray": thai_time.event_time(last_spray) if last_spray else None,
            "hourly": hourly,
            "recent_detections": [
                {
                    **thai_time.event_time(row["detected_at"]),
                    "camera_id": row["camera_id"],
                    "camera_name": camera_name(row["camera_id"]),
                    "track_id": row["track_id"],
                    "confidence": row["confidence"],
                }
                for row in recent_detections
            ],
            "recent_sprays": [
                {
                    **thai_time.event_time(row["sprayed_at"]),
                    "camera_id": row["camera_id"],
                    "camera_name": camera_name(row["camera_id"]),
                    "source": row["source"],
                    "outcome": row["outcome"],
                    "track_id": row["track_id"],
                    "confidence": row["confidence"],
                    "duration_ms": row["duration_ms"],
                }
                for row in recent_sprays
            ],
        }

    def export_rows(self, kind, camera_names=None, limit=100000):
        """แถวสำหรับไฟล์ CSV (เวลาไทย)"""
        names = camera_names or {}
        with self._connect() as connection:
            if kind == "detections":
                rows = connection.execute(
                    """
                    SELECT detected_at, camera_id, track_id, confidence
                    FROM detection_events ORDER BY detected_at DESC, id DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                header = ["เวลา (ไทย)", "จุดติดตั้ง", "รหัสกล้อง", "Track ID", "ความมั่นใจ (%)"]
                body = [
                    [
                        thai_time.fmt_csv(r["detected_at"]),
                        names.get(r["camera_id"], r["camera_id"]),
                        r["camera_id"],
                        r["track_id"],
                        round(r["confidence"] * 100, 1),
                    ]
                    for r in rows
                ]
            else:
                rows = connection.execute(
                    """
                    SELECT sprayed_at, camera_id, source, outcome, track_id, confidence, duration_ms
                    FROM spray_events ORDER BY sprayed_at DESC, id DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                source_text = {"auto": "อัตโนมัติ", "manual": "สั่งเอง", "stop": "สั่งหยุด"}
                outcome_text = {
                    "pump_on": "ปั๊มทำงาน", "busy": "ปั๊มทำงานอยู่แล้ว",
                    "stopped": "หยุดแล้ว", "no_reply": "ESP32 ไม่ตอบสนอง",
                }
                header = ["เวลา (ไทย)", "จุดติดตั้ง", "รหัสกล้อง", "ประเภท", "ผล",
                          "ระยะเวลาพ่น (วินาที)", "Track ID", "ความมั่นใจ (%)"]
                body = [
                    [
                        thai_time.fmt_csv(r["sprayed_at"]),
                        names.get(r["camera_id"], r["camera_id"]),
                        r["camera_id"],
                        source_text.get(r["source"], r["source"]),
                        outcome_text.get(r["outcome"], r["outcome"]),
                        "" if r["duration_ms"] is None else round(r["duration_ms"] / 1000, 1),
                        "" if r["track_id"] is None else r["track_id"],
                        "" if r["confidence"] is None else round(r["confidence"] * 100, 1),
                    ]
                    for r in rows
                ]
        return header, body
