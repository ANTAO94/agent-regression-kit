import unittest

from agent_regression import wilson_interval


class StatisticsTests(unittest.TestCase):
    def test_wilson_interval_is_bounded_and_records_confidence(self):
        interval = wilson_interval(9, 10)

        self.assertEqual(0.95, interval["confidence"])
        self.assertLessEqual(0.0, interval["low"])
        self.assertLess(interval["low"], 0.9)
        self.assertGreater(interval["high"], 0.9)
        self.assertLessEqual(interval["high"], 1.0)

    def test_wilson_interval_handles_empty_and_rejects_invalid_counts(self):
        self.assertIsNone(wilson_interval(0, 0))
        with self.assertRaises(ValueError):
            wilson_interval(2, 1)
        with self.assertRaises(ValueError):
            wilson_interval(1, 1, confidence=1.0)


if __name__ == "__main__":
    unittest.main()
