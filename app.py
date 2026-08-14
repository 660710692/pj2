from flask import Flask, render_template, Response
from detector import Detector
from iot_controller import IoTController

app = Flask(__name__)

detector = Detector()

iot = IoTController(
    esp_ip="192.168.1.30",    #เปลี่ยนตอนเชื่อม ESP01
    mock_mode=True              # จะปิด ก็ False
)

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/admin")
def admin():
    return render_template("admin.html")


@app.route("/video_feed")
def video_feed():
    return Response(
        detector.generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@app.route("/iot/status")
def iot_status():
    return iot.get_status()

@app.route("/iot/pump/on", methods=["POST"])
def pump_on():
    return iot.pump_on()

@app.route("/iot/pump/off", methods=["POST"])
def pump_off():
    return iot.pump_off()

@app.route("/status")
def status():
    return detector.get_status()


if __name__ == "__main__":

    print("=" * 50)
    print("Water Hyacinth Detection Dashboard")
    print("=" * 50)

    app.run(
        host="0.0.0.0",
        port=5000,
        threaded=True,
        debug=False
    )