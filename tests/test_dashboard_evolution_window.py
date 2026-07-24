import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATHS = [
    ROOT / "index.html",
    ROOT / "game_sentiment_dashboard_apex_W25_W29_mixed_sample.html",
]


class DashboardEvolutionWindowTests(unittest.TestCase):
    def test_evolution_uses_the_same_five_week_window_as_history(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn(
                    "展示截至所选周的最近5个自然周",
                    source,
                )
                self.assertIn(
                    "const start=Math.max(0,end-DASHBOARD_HISTORY_LIMIT);",
                    source,
                )
                self.assertNotIn(
                    "const start=Math.max(0,end-3);",
                    source,
                )

    def test_five_columns_keep_readable_node_width_and_scroll_horizontally(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn(
                    "compactColumns=colCount>=4, nodeW=compactColumns?200:246",
                    source,
                )
                self.assertIn(
                    "Array.from({length:colCount},(_,i)=>sidePad+i*colStep)",
                    source,
                )
                self.assertIn("svg.style.minWidth=W+'px';", source)
                self.assertIn(
                    "flowWrap.scrollLeft=Math.max(0,flowWrap.scrollWidth-flowWrap.clientWidth);",
                    source,
                )


if __name__ == "__main__":
    unittest.main()
