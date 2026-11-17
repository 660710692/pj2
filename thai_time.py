"""
เวลาไทยสำหรับแสดงผลบนหน้าเว็บ

ฐานข้อมูลเก็บเวลาเป็น UTC (เหมือนเดิม) แล้วแปลงเป็นเวลาไทย (UTC+7) ที่ฝั่ง server
-> ไม่ขึ้นกับ timezone ของ Raspberry Pi หรือของเบราว์เซอร์ที่เปิดดู
(ประเทศไทยไม่มี Daylight Saving จึงใช้ +7 คงที่ได้)

ถ้าต้องการเปลี่ยน offset ให้ตั้ง env DISPLAY_UTC_OFFSET เช่น 7
"""

import os
from datetime import datetime, timedelta, timezone

UTC_OFFSET_HOURS = float(os.environ.get("DISPLAY_UTC_OFFSET", "7"))
LOCAL_TZ = timezone(timedelta(hours=UTC_OFFSET_HOURS))

TH_MONTHS = [
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]


def now_utc():
    return datetime.now(timezone.utc)


def now_local():
    return datetime.now(LOCAL_TZ)


def to_utc_iso(value):
    """datetime -> ISO string แบบ UTC (รูปแบบเดียวกับที่ detection_store ใช้เดิม)"""
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse(value):
    """ISO string จากฐานข้อมูล -> datetime (ถ้าไม่มี timezone ถือว่าเป็น UTC)"""
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def to_local(value):
    dt = parse(value)
    return dt.astimezone(LOCAL_TZ) if dt else None


def fmt_datetime(value):
    """'18 พ.ย. 2569 00:44:18' (ปี พ.ศ.)"""
    dt = to_local(value)
    if not dt:
        return "-"
    return (
        f"{dt.day} {TH_MONTHS[dt.month - 1]} {dt.year + 543} "
        f"{dt:%H:%M:%S}"
    )


def fmt_time(value):
    dt = to_local(value)
    return f"{dt:%H:%M:%S}" if dt else "-"


def fmt_csv(value):
    """รูปแบบสำหรับไฟล์ CSV / Excel: 2026-11-18 00:44:18 (เวลาไทย)"""
    dt = to_local(value)
    return f"{dt:%Y-%m-%d %H:%M:%S}" if dt else ""


def epoch(value):
    dt = parse(value)
    return dt.timestamp() if dt else None


def local_midnight_utc_iso(now=None):
    """เที่ยงคืนของวันนี้ (เวลาไทย) ในรูป UTC ISO สำหรับ query 'วันนี้'"""
    local = (now or now_utc()).astimezone(LOCAL_TZ)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return to_utc_iso(midnight)


def fmt_date(value):
    """'18 พ.ย. 2569'"""
    dt = to_local(value)
    return f"{dt.day} {TH_MONTHS[dt.month - 1]} {dt.year + 543}" if dt else "-"


def event_time(value):
    """ข้อมูลเวลาที่หน้าเว็บใช้"""
    return {
        "text": fmt_datetime(value),
        "date": fmt_date(value),
        "time": fmt_time(value),
        "epoch": epoch(value),
    }
