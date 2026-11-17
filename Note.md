cd ~/WaterHyacinth

source venv/bin/activate

ip route get 192.168.1.100

sudo ip route replace 192.168.1.100/32 dev wlan0

ping -I wlan0 -c 4 192.168.1.100

TP-Link_93F6
59403227


192.168.1.100 esp32

MODEL_PATH=models/best_ncnn_model python app.py