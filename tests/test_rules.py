from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import parse_datetime, week_fields


class WeekRuleTests(unittest.TestCase):
    def test_monday_and_sunday_same_week(self):
        monday = week_fields(datetime(2026, 7, 6, 0, 0))
        sunday = week_fields(datetime(2026, 7, 12, 23, 59))
        self.assertEqual(monday, sunday)
        self.assertEqual(monday, ("2026-07-06", "2026-07-12", "2026年7.6—7.12"))

    def test_next_monday_starts_new_week(self):
        self.assertEqual(week_fields(datetime(2026, 7, 13))[0], "2026-07-13")

    def test_cross_year_label(self):
        self.assertEqual(week_fields(datetime(2026, 12, 31))[2], "2026年12.28—2027年1.3")

    def test_iso_timezone_parsing(self):
        parsed = parse_datetime("2026-07-19T16:20:00Z")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.hour, 0)
        self.assertEqual(parsed.day, 20)


if __name__ == "__main__":
    unittest.main()
