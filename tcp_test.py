# import socket

# ESP32_IP = "192.168.1.50"  # placeholder ESP32 ip 
# ESP32_PORT = 5000

# while True:
#     command = input("Enter A = Trigger, B = No trigger, Q = Quit: ").strip().upper()

#     if command == "Q":
#         break

#     if command not in ("A", "B"):
#         print("Please enter A, B, or Q.")
#         continue

#     try:
#         with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
#             client.settimeout(3)
#             client.connect((ESP32_IP, ESP32_PORT))
#             client.sendall(command.encode("ascii"))

#         print(f"Sent command: {command}")

#     except OSError as error:
#         print(f"Connection failed: {error}")