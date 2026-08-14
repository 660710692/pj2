import time
from spray_controller import SprayDecision

decision = SprayDecision(
    confidence_threshold=0.60,
    min_speed=0.10,
    cooldown_seconds=5
)

result, reason = decision.should_spray(
    confidence=0.90,
    speed=0.50,
    chemical_available=True
)

print("First:", result, reason)

decision.record_spray()

result, reason = decision.should_spray(
    confidence=0.90,
    speed=0.50,
    chemical_available=True
)

print("Immediately:", result, reason)

time.sleep(6)

result, reason = decision.should_spray(
    confidence=0.90,
    speed=0.50,
    chemical_available=True
)

print("After 6 sec:", result, reason)