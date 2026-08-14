from spray_controller import SprayDecision

decision = SprayDecision(
    confidence_threshold=0.60,
    min_speed=0.10,
    cooldown_seconds=5
)

tests = [
    {
        "confidence": 0.80,
        "speed": 0.50,
        "chemical_available": True
    },
    {
        "confidence": 0.50,
        "speed": 0.50,
        "chemical_available": True
    },
    {
        "confidence": 0.80,
        "speed": 0.05,
        "chemical_available": True
    },
    {
        "confidence": 0.80,
        "speed": 0.50,
        "chemical_available": False
    }
]

for i, test in enumerate(tests, start=1):

    result, reason = decision.should_spray(
        confidence=test["confidence"],
        speed=test["speed"],
        chemical_available=test["chemical_available"]
    )

    print(
        f"Test {i}: "
        f"spray={result}, "
        f"reason={reason}"
    )