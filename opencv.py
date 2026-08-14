import cv2

url = "rtsp://admin:bm9BqimE@192.168.1.100:554/Streaming/Channels/101"

cap = cv2.VideoCapture(url)

while True:
    ret, frame = cap.read()

    if not ret:
        print("Cannot read frame")
        break

    print(frame.shape)

cap.release()


#bm9BqimE