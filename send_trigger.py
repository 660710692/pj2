import socket

ESP32_IP = "192.168.1.102"  # เปลี่ยนเป็น IP จริงของ ESP32
ESP32_PORT = 5000

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
    client.connect((ESP32_IP, ESP32_PORT))
    print("Connected to ESP32!")

    while True:
        command = input("Enter A, B, or Q to quit: ").strip().upper()

        if command == "Q":
            break

        if command in ("A", "B"):
            client.sendall(command.encode("ascii"))
            print(f"Sent: {command}")
        else:
            print("Invalid command. Enter A, B, or Q.")