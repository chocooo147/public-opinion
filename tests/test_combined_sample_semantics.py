import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATHS = [
    ROOT / "index.html",
    ROOT / "game_sentiment_dashboard_apex_W25_W30_mixed_sample.html",
]


class CombinedSampleSemanticsTests(unittest.TestCase):
    def test_combined_kpi_and_drawer_use_incomparable_sample_label(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn(
                    'loc("样本观察量（不可比）","Sample observations (not comparable)")',
                    source,
                )
                self.assertIn(
                    'state.platform==="综合"?loc("样本观察量（不可比）"',
                    source,
                )
                self.assertIn(
                    "Bilibili counts comments while Heybox counts search-visible posts; do not interpret their sum as a cross-platform total.",
                    source,
                )
                self.assertNotIn(
                    'showMetricDrawer(loc("本周总声量","Total volume this week")',
                    source,
                )
                self.assertIn(
                    "样本观察量与模型负面率同步观察；综合视图中的两平台单位不可比。",
                    source,
                )

    def test_current_and_previous_week_copy_is_current(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("W27—W31为最近五个完整自然周；W32为开放周，未纳入", source)
        self.assertNotIn("W29（7.13—7.19）截至2026-07-18未完成", source)


if __name__ == "__main__":
    unittest.main()
