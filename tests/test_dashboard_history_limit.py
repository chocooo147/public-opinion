import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATHS = [
    ROOT / "index.html",
    ROOT / "game_sentiment_dashboard_apex_W25_W29_mixed_sample.html",
]


class DashboardHistoryLimitTests(unittest.TestCase):
    def test_history_is_capped_to_five_weeks_in_memory_and_storage(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("const DASHBOARD_HISTORY_LIMIT=5;", source)
                self.assertIn('id="historyLabel">历史记录 · 最近 5 周</span>', source)
                self.assertIn(".slice(-DASHBOARD_HISTORY_LIMIT);", source)
                self.assertIn(
                    "const normalizedWeeks=mergeDashboardWeeks([],weeks);",
                    source,
                )
                self.assertIn("weeks:normalizedWeeks", source)

    def test_loaded_history_is_compacted_and_wrong_version_is_removed(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn(
                    "dashboardData.weeks=mergeDashboardWeeks(dashboardData.weeks,storedDashboardHistory.weeks);",
                    source,
                )
                self.assertIn(
                    "writeDashboardHistory(dashboardData.meta,dashboardData.weeks);",
                    source,
                )
                self.assertIn(
                    "localStorage.removeItem(DASHBOARD_HISTORY_KEY)",
                    source,
                )

    def test_import_replaces_history_with_latest_five_from_payload(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn(
            "dashboardData.weeks=mergeDashboardWeeks([],obj.weeks);",
            source,
        )


if __name__ == "__main__":
    unittest.main()
