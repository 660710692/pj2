import time
from speed_calculator import SpeedCalculator

speed = SpeedCalculator(pixels_per_meter=100)

# ตำแหน่งเริ่มต้น
print("Frame 1:", speed.update(1, 100, 100))

time.sleep(1)

# ขยับ 100 pixels ใน 1 วินาที
print("Frame 2:", speed.update(1, 200, 100))

time.sleep(1)

# ขยับอีก 100 pixels
print("Frame 3:", speed.update(1, 300, 100))