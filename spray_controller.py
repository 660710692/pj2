import time


class SprayDecision:

    def __init__(
        self,
        confidence_threshold=0.60,
        min_speed=0.0,
        cooldown_seconds=10
    ):

        self.confidence_threshold = confidence_threshold
        self.min_speed = min_speed
        self.cooldown_seconds = cooldown_seconds

        self.last_spray_time = 0

    def should_spray(
        self,
        confidence,
        speed,
        chemical_available=True
    ):

        # 1. Confidence
        if confidence <= self.confidence_threshold:
            return False, "Low confidence"

        # 2. Chemical
        if not chemical_available:
            return False, "Chemical unavailable"

        # 3. Speed
        if speed < self.min_speed:
            return False, "Invalid speed"

        # 4. Cooldown
        current_time = time.time()

        if (
            current_time - self.last_spray_time
            < self.cooldown_seconds
        ):
            return False, "Cooldown"

        return True, "Spray required"

    def record_spray(self):

        self.last_spray_time = time.time()