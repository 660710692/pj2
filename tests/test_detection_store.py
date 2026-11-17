import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from detection_store import DetectionStore


class DetectionStoreTests(unittest.TestCase):
    def test_summary_counts_persisted_detections_from_last_24_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "detections.sqlite3"
            store = DetectionStore(str(database))
            now = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)

            store.record_detection(
                1, 0.6, detected_at=now - timedelta(hours=24, seconds=1)
            )
            store.record_detection(
                2, 0.8, detected_at=now - timedelta(hours=1)
            )
            store.record_detection(3, 1.0, detected_at=now)

            summary = DetectionStore(str(database)).get_summary(now=now)

            self.assertEqual(summary["count_24h"], 2)
            self.assertEqual(summary["total_count"], 3)
            self.assertAlmostEqual(summary["average_confidence_24h"], 0.9)
            self.assertEqual(
                summary["last_detected_at"],
                "2026-10-18T00:00:00+00:00",
            )
            self.assertEqual(
                [event["track_id"] for event in summary["recent_events"]],
                [3, 2, 1],
            )

    def test_empty_store_returns_no_last_detection_or_average(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DetectionStore(str(Path(directory) / "detections.sqlite3"))

            summary = store.get_summary()

            self.assertEqual(summary["count_24h"], 0)
            self.assertEqual(summary["total_count"], 0)
            self.assertIsNone(summary["average_confidence_24h"])
            self.assertIsNone(summary["last_detected_at"])
            self.assertEqual(summary["recent_events"], [])


if __name__ == "__main__":
    unittest.main()
