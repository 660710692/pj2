"""
สั่ง ESP32 พ่นยาผ่าน WiFi ด้วย UDP (port 4210)

คำสั่งที่ส่ง -> คำตอบจาก ESP32 (ต้องใช้ sketch esp32_udp_pump.ino เวอร์ชันใหม่)
    "1 <ms>" เปิดปั๊มนาน <ms> (ตั้งจากหน้าตั้งค่า) -> "OK <ms>" เริ่มพ่น นาน <ms>
    "1"      เปิดปั๊มตามค่าเริ่มต้นใน ESP32
                       "BUSY <ms>"      ปั๊มทำงานอยู่แล้ว เหลืออีก <ms> (ไม่รีเซ็ตเวลา)
    "0"  หยุดปั๊ม     -> "STOPPED"
    "?"  ถามสถานะ    -> "STATUS ON <ms>" / "STATUS OFF"

- ถามสถานะทุก ๆ 5 วินาที เพื่อแสดงว่า ESP32 ออนไลน์อยู่ไหม
- ระหว่างที่ปั๊มทำงาน จะไม่ส่งคำสั่งเปิดซ้ำ (ล็อกทั้งฝั่ง Pi และ ESP32)
- ทุกการสื่อสารทำใน background thread เดียว -> ไม่ทำให้ YOLO ช้า และไม่อ่านคำตอบสลับกัน
- ใช้แค่ standard library

ทดสอบเดี่ยว ๆ:  python esp32_udp.py 192.168.1.50
"""

import os
import queue
import socket
import threading
import time

UDP_PORT = 4210
BROADCAST = "255.255.255.255"
SAFETY_MARGIN = 0.5      # วินาที เผื่อดีเลย์เครือข่าย ก่อนอนุญาต trigger ใหม่
OFFLINE_AFTER_FAILS = 2  # ถามสถานะไม่ตอบกี่ครั้งติดกัน ถึงถือว่าออฟไลน์

_WAKE = "WAKE"
_PING = "PING"


class ESP32UDP:

    def __init__(self, host=None, port=UDP_PORT, reply_timeout=0.5, attempts=3,
                 ping_interval=5.0, on_event=None, name="ESP32"):
        self.host = host or os.environ.get("ESP32_HOST", BROADCAST)
        self.port = port
        self.reply_timeout = reply_timeout
        self.attempts = attempts
        self.ping_interval = ping_interval
        self.on_event = on_event          # callback(source, outcome, duration_ms, context)
        self.name = name

        self.lock = threading.Lock()
        self.busy_until = 0.0             # time.monotonic() ที่ปั๊มจะปิด
        self.pending = False              # มีคำสั่งเปิดปั๊มรอส่งอยู่
        self.online = None                # None = ยังไม่รู้, True/False
        self.last_seen = None             # time.monotonic() ที่ได้คำตอบล่าสุด
        self.pump_duration_ms = None      # ESP32 บอกมาตอนตอบ OK
        self.failed_pings = 0
        self.requested_ms = None          # ระยะเวลาที่สั่งล่าสุด
        self.stop_requested = threading.Event()

        self.commands = queue.Queue()
        self.running = True

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.settimeout(self.reply_timeout)

        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        print(f"[{self.name}] UDP -> {self.host}:{self.port}")

    # ------------------------------------------------------------------
    # เรียกจาก detector / หน้าเว็บ
    # ------------------------------------------------------------------

    def is_pump_active(self):
        with self.lock:
            return self.pending or time.monotonic() < self.busy_until

    def trigger(self, context=None, duration_ms=None):
        """
        สั่งพ่น (ไม่ block)
        คืนค่า True = ส่งคำสั่งแล้ว, False = ข้าม เพราะปั๊มกำลังทำงานอยู่
        context: dict เช่น {"source": "auto", "track_id": 3, "confidence": 0.8}
        duration_ms: ระยะเวลาพ่น (None = ใช้ค่าเริ่มต้นใน ESP32)
        """
        with self.lock:
            now = time.monotonic()
            if self.pending or now < self.busy_until:
                return False
            self.pending = True

        self.commands.put(("1", context or {"source": "auto"}, duration_ms))
        return True

    def stop_pump(self):
        """หยุดปั๊มทันที (ทำก่อนคำสั่งอื่นที่รออยู่)"""
        self.stop_requested.set()
        self.commands.put(_WAKE)

    def get_status(self):
        with self.lock:
            now = time.monotonic()
            remaining = max(0.0, self.busy_until - now - SAFETY_MARGIN)
            pump_on = now < self.busy_until - SAFETY_MARGIN
            return {
                "host": self.host,
                "broadcast": self.host == BROADCAST,
                "online": self.online,
                "pump_on": pump_on,
                "remaining_s": round(remaining, 1) if pump_on else 0,
                "duration_s": (
                    None if self.pump_duration_ms is None
                    else round(self.pump_duration_ms / 1000, 1)
                ),
                # ESP32 พ่นไม่ตรงกับที่สั่ง = ยังใช้ sketch เก่าที่ไม่รองรับการตั้งเวลาจากหน้าเว็บ
                "duration_mismatch": (
                    self.requested_ms is not None
                    and self.pump_duration_ms is not None
                    and abs(self.pump_duration_ms - self.requested_ms) > 50
                ),
                "last_seen_s": (
                    None if self.last_seen is None else round(now - self.last_seen, 1)
                ),
            }

    def stop(self):
        self.running = False
        self.commands.put(None)   # ปลุก thread ให้ออก

    # ------------------------------------------------------------------
    # ภายใน
    # ------------------------------------------------------------------

    def _clear_old_replies(self):
        """ทิ้งคำตอบเก่าที่ค้างอยู่ จะได้ไม่อ่านผิดตัว"""
        self.sock.setblocking(False)
        try:
            while True:
                self.sock.recvfrom(64)
        except (BlockingIOError, OSError):
            pass
        self.sock.settimeout(self.reply_timeout)

    def _exchange(self, message, attempts):
        """ส่งข้อความ รอคำตอบ คืนค่าข้อความตอบกลับ หรือ None"""
        self._clear_old_replies()
        for _ in range(attempts):
            try:
                self.sock.sendto(message.encode(), (self.host, self.port))
                reply, _address = self.sock.recvfrom(64)
                with self.lock:
                    self.online = True
                    self.last_seen = time.monotonic()
                    self.failed_pings = 0
                return reply.decode(errors="ignore").strip()
            except socket.timeout:
                continue
            except OSError as error:
                print(f"[{self.name}] send failed: {error}")
                time.sleep(0.2)
        return None

    @staticmethod
    def _number(parts, index):
        try:
            return int(parts[index])
        except (IndexError, ValueError):
            return 0

    def _apply_reply(self, text):
        """อัปเดตสถานะจากคำตอบ คืนค่า outcome"""
        parts = text.split()
        kind = parts[0].upper() if parts else ""
        now = time.monotonic()

        with self.lock:
            if kind == "OK":
                ms = self._number(parts, 1)
                self.pump_duration_ms = ms or self.pump_duration_ms
                self.busy_until = now + ms / 1000 + SAFETY_MARGIN
                return "pump_on", ms
            if kind == "BUSY":
                ms = self._number(parts, 1)
                self.busy_until = now + ms / 1000 + SAFETY_MARGIN
                return "busy", ms
            if kind == "STOPPED":
                self.busy_until = 0.0
                return "stopped", 0
            if kind == "STATUS":
                state = parts[1].upper() if len(parts) > 1 else "OFF"
                if state == "ON":
                    ms = self._number(parts, 2)
                    self.busy_until = now + ms / 1000 + SAFETY_MARGIN
                elif not self.pending:
                    self.busy_until = 0.0
                return "status", 0
        return "unknown", 0

    def _emit(self, source, outcome, duration_ms, context):
        if self.on_event is None:
            return
        try:
            self.on_event(source, outcome, duration_ms, context or {})
        except Exception as error:   # บันทึกไม่ได้ ไม่ควรทำให้ระบบพัง
            print(f"[{self.name}] event log error: {error}")

    def _discard_triggers(self):
        kept = []
        while True:
            try:
                item = self.commands.get_nowait()
            except queue.Empty:
                break
            if not isinstance(item, tuple):
                kept.append(item)
        for item in kept:
            self.commands.put(item)
        with self.lock:
            self.pending = False

    def _do_stop(self):
        reply = self._exchange("0", self.attempts)
        if reply is None:
            print(f"[{self.name}] STOP: no reply")
            self._emit("stop", "no_reply", None, {})
            return
        outcome, _ = self._apply_reply(reply)
        print(f"[{self.name}] STOP -> {reply}")
        self._emit("stop", "stopped" if outcome == "stopped" else outcome, None, {})

    def _do_trigger(self, context, duration_ms=None):
        try:
            message = "1" if duration_ms is None else f"1 {int(duration_ms)}"
            with self.lock:
                self.requested_ms = None if duration_ms is None else int(duration_ms)
            reply = self._exchange(message, self.attempts)
            if reply is None:
                print(f"[{self.name}] No reply to spray command")
                self._emit(context.get("source", "auto"), "no_reply", None, context)
                return
            outcome, ms = self._apply_reply(reply)
            print(f"[{self.name}] spray -> {reply}")
            self._emit(context.get("source", "auto"), outcome, ms, context)
        finally:
            with self.lock:
                self.pending = False

    def _do_ping(self):
        reply = self._exchange("?", 1)
        if reply is None:
            with self.lock:
                self.failed_pings += 1
                if self.failed_pings >= OFFLINE_AFTER_FAILS:
                    self.online = False
            return
        self._apply_reply(reply)

    def _worker(self):
        next_ping = 0.0
        while self.running:
            timeout = max(0.05, next_ping - time.monotonic())
            try:
                item = self.commands.get(timeout=timeout)
            except queue.Empty:
                item = _PING

            if item is None:
                break

            # หยุดฉุกเฉินมาก่อนทุกอย่าง และยกเลิกคำสั่งพ่นที่ค้างอยู่ในคิว
            if self.stop_requested.is_set():
                self.stop_requested.clear()
                self._discard_triggers()
                self._do_stop()
                if isinstance(item, tuple):
                    continue        # คำสั่งพ่นนี้ถูกสั่งก่อนหยุด -> ไม่ส่ง

            if item == _PING:
                self._do_ping()
                next_ping = time.monotonic() + self.ping_interval
            elif isinstance(item, tuple) and item[0] == "1":
                self._do_trigger(item[1], item[2])

        self.sock.close()


if __name__ == "__main__":
    import sys

    def show(source, outcome, ms, context):
        print(f"  event: {source} -> {outcome} ({ms} ms)")

    esp32 = ESP32UDP(host=sys.argv[1] if len(sys.argv) > 1 else None, on_event=show)
    print("Enter = spray, s = stop, ? = status, q = quit")
    while True:
        command = input().strip()
        if command == "q":
            break
        if command == "s":
            esp32.stop_pump()
        elif command == "?":
            print(" ", esp32.get_status())
        elif not esp32.trigger({"source": "manual"}):
            print("  pump is running -> skipped")
    esp32.stop()
