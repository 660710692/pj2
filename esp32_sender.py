import requests

ESP32_IP = "192.168.1.50"  # ip esp 
ESP32_URL = f"http://{ESP32_IP}/detect"


def send_detection(detected, confidence=0.0):
    data = {
        "detected": bool(detected),
        "confidence": float(confidence)
    }

    try:
        response = requests.post(
            ESP32_URL,
            json=data,
            timeout=1
        )

        response.raise_for_status()
        print("ESP32 response:", response.text)
        return True

    except requests.RequestException as error:
        print("Cannot send data to ESP32:", error)
        return False


if __name__ == "__main__":
    send_detection(True, 0.87)
