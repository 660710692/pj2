import csv
import io

from flask import Flask, Response, abort, jsonify, render_template, request

import thai_time
from camera_manager import CameraManager, DEFAULT_SETTINGS, LIMITS
from detection_store import DetectionStore

app = Flask(__name__)
app.json.ensure_ascii = False   # ส่งภาษาไทยใน JSON ตรง ๆ

store = DetectionStore()
manager = CameraManager(store)


# ----------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/admin")
def admin():
    return render_template("admin.html")


@app.route("/admin/devices")
def devices():
    return render_template("devices.html")


@app.route("/admin/settings")
def settings_page():
    return render_template("settings.html")


# ----------------------------------------------------------------------
# Live data
# ----------------------------------------------------------------------

@app.route("/api/overview")
def api_overview():
    return jsonify(manager.overview())


@app.route("/api/stats")
def api_stats():
    return jsonify(store.get_stats(manager.camera_names()))


@app.route("/video_frame")
@app.route("/video_frame/<camera_id>")
def video_frame(camera_id=None):
    frame = manager.get_frame(camera_id)
    if frame is None:
        abort(404)
    return Response(frame, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


@app.route("/video_feed/<camera_id>")
def video_feed(camera_id):
    detector = manager.get_detector(camera_id)
    if detector is None:
        abort(404)
    return Response(
        detector.generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# ----------------------------------------------------------------------
# Pump control
# ----------------------------------------------------------------------

@app.post("/api/cameras/<camera_id>/spray")
def api_manual_spray(camera_id):
    ok, message = manager.manual_spray(camera_id)
    return jsonify({"ok": ok, "message": message}), (200 if ok else 409)


@app.post("/api/cameras/<camera_id>/stop")
def api_stop_pump(camera_id):
    ok, message = manager.stop_pump(camera_id)
    return jsonify({"ok": ok, "message": message}), (200 if ok else 409)


@app.post("/api/emergency_stop")
def api_emergency_stop():
    count = manager.emergency_stop()
    return jsonify({
        "ok": True,
        "message": f"สั่งหยุดปั๊มทั้งหมด {count} จุด และปิดการพ่นอัตโนมัติแล้ว",
    })


@app.post("/api/auto_spray")
def api_auto_spray():
    data = request.get_json(silent=True) or {}
    settings = manager.set_auto_spray(bool(data.get("enabled")))
    return jsonify({"ok": True, "auto_spray": settings["auto_spray"]})


# ----------------------------------------------------------------------
# Devices (จุดติดตั้ง)
# ----------------------------------------------------------------------

@app.post("/api/cameras")
def api_add_camera():
    camera, errors = manager.add_camera(request.get_json(silent=True) or {})
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    return jsonify({"ok": True, "camera": camera})


@app.put("/api/cameras/<camera_id>")
def api_update_camera(camera_id):
    camera, errors = manager.update_camera(camera_id, request.get_json(silent=True) or {})
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    return jsonify({"ok": True, "camera": camera})


@app.delete("/api/cameras/<camera_id>")
def api_delete_camera(camera_id):
    if not manager.delete_camera(camera_id):
        return jsonify({"ok": False, "message": "ไม่พบจุดติดตั้งนี้"}), 404
    return jsonify({"ok": True})


# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------

@app.get("/api/settings")
def api_get_settings():
    return jsonify({
        "settings": manager.get_settings(),
        "defaults": DEFAULT_SETTINGS,
        "limits": LIMITS,
    })


@app.post("/api/settings")
def api_save_settings():
    settings, errors = manager.update_settings(request.get_json(silent=True) or {})
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    return jsonify({"ok": True, "settings": settings})


# ----------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------

@app.route("/admin/export/<kind>.csv")
def export_csv(kind):
    if kind not in ("detections", "sprays"):
        abort(404)
    header, rows = store.export_rows(kind, manager.camera_names())
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    # utf-8-sig (BOM) -> Excel เปิดภาษาไทยได้ถูกต้อง
    data = buffer.getvalue().encode("utf-8-sig")
    stamp = thai_time.now_local().strftime("%Y%m%d_%H%M")
    filename = f"{'detections' if kind == 'detections' else 'sprays'}_{stamp}.csv"
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":

    print("=" * 50)
    print("Water Hyacinth Detection Dashboard")
    print("=" * 50)

    try:
        app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)
    finally:
        manager.shutdown()
