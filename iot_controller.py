import requests


class IoTController:

    def __init__(self, esp_ip="192.168.1.30", mock_mode=True):
        self.esp_ip = esp_ip
        self.mock_mode = mock_mode

        self.pump_status = "OFF"
        self.device_status = "Mock Device"

    def pump_on(self):
        if self.mock_mode:
            self.pump_status = "ON"
            print("[MOCK] Pump ON")
            return {
                "success": True,
                "pump": "ON",
                "mode": "mock"
            }

        try:
            response = requests.post(
                f"http://{self.esp_ip}/pump/on",
                timeout=2
            )

            response.raise_for_status()

            self.pump_status = "ON"

            return {
                "success": True,
                "pump": "ON",
                "mode": "esp"
            }

        except requests.RequestException as e:

            return {
                "success": False,
                "error": str(e)
            }

    def pump_off(self):
        if self.mock_mode:
            self.pump_status = "OFF"
            print("[MOCK] Pump OFF")
            return {
                "success": True,
                "pump": "OFF",
                "mode": "mock"
            }

        try:
            response = requests.post(
                f"http://{self.esp_ip}/pump/off",
                timeout=2
            )

            response.raise_for_status()

            self.pump_status = "OFF"

            return {
                "success": True,
                "pump": "OFF",
                "mode": "esp"
            }

        except requests.RequestException as e:

            return {
                "success": False,
                "error": str(e)
            }

    def get_status(self):

        return {
            "device": self.device_status,
            "esp_ip": self.esp_ip,
            "pump": self.pump_status,
            "mode": "mock" if self.mock_mode else "esp"
        }