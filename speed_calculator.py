import math
import time


class SpeedCalculator:

    def __init__(self, pixels_per_meter=100.0):   # ค่า MOCK !!!!!!!!!!!!!! placeholder
        self.pixels_per_meter = pixels_per_meter

        self.previous_positions = {}

    def update(self, object_id, center_x, center_y):

        current_time = time.time()

        if object_id not in self.previous_positions:

            self.previous_positions[object_id] = {
                "x": center_x,
                "y": center_y,
                "time": current_time
            }

            return 0.0

        previous = self.previous_positions[object_id]

        dx = center_x - previous["x"]
        dy = center_y - previous["y"]

        pixel_distance = math.sqrt(
            dx ** 2 + dy ** 2
        )

        time_difference = current_time - previous["time"]

        if time_difference <= 0:
            return 0.0

        speed_pixels_per_second = (
            pixel_distance / time_difference
        )

        speed_meters_per_second = (
            speed_pixels_per_second /
            self.pixels_per_meter
        )

        self.previous_positions[object_id] = {
            "x": center_x,
            "y": center_y,
            "time": current_time
        }

        return speed_meters_per_second