from __future__ import annotations
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))
from bilibili_apex_collector import assign_week, last_complete_week

class WeekAssignmentTests(unittest.TestCase):
    def test_current_date_targets_last_complete_week(self):
        start, end, wid = last_complete_week(datetime(2026, 7, 14, 12, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual((start.date().isoformat(), end.date().isoformat(), wid), ("2026-07-06", "2026-07-12", "2026_W28"))
    def test_boundaries(self):
        self.assertEqual(assign_week(datetime(2026, 7, 12, 23, 59))[0], "2026_W28")
        self.assertEqual(assign_week(datetime(2026, 7, 13, 0, 0))[0], "2026_W29")

if __name__ == "__main__": unittest.main()
