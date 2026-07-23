import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATHS = [
    ROOT / "index.html",
    ROOT / "game_sentiment_dashboard_v3.html",
    ROOT / "game_sentiment_dashboard_v5.html",
    ROOT / "game_sentiment_dashboard_apex_W25_W28_mixed_test.html",
    ROOT / "outputs/game_sentiment_dashboard_apex_W25_W28_mixed_test.html",
]


class DashboardViewerAndVisualTests(unittest.TestCase):
    def test_sidebar_drops_empty_sentiment_navigation(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn('data-anchor="sentiment"', source)

    def test_apex_is_seeded_as_fixed_read_only_viewer(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(source.count("const VIEWER_USERNAME='apex';"), 1)
                self.assertEqual(
                    source.count(
                        "const VIEWER_PASSWORD_HASH='314ffd6162923d94123a7010c7c67be278592e5922ac5e3e404d65aa01608293';"
                    ),
                    1,
                )
                self.assertIn("viewer.role='viewer'", source)
                self.assertIn("function requireContentManager()", source)
                self.assertIn("body.viewer-mode #downloadBtn", source)
                self.assertIn("body.viewer-mode #importBtn", source)
                self.assertIn("body.viewer-mode #downloadSchema", source)
                self.assertIn(
                    'if(!requireContentManager()) return;\n  const file=e.target.files[0]',
                    source,
                )

    def test_trend_uses_data_scaled_nice_axis(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("const roughStep=rawMaxV/4;", source)
                self.assertIn(
                    "const maxV=Math.ceil(rawMaxV/volumeStep)*volumeStep;",
                    source,
                )
                self.assertNotIn(
                    "Math.ceil(Math.max(...vols)/5000)*5000",
                    source,
                )
                self.assertIn("stroke-width:4", source)

    def test_topic_and_chain_drawers_have_distinct_responsibilities(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(source.count("function openChain(chain)"), 1)
                self.assertIn(
                    "el.onclick=()=>openChain(el.dataset.chain)",
                    source,
                )
                self.assertIn("本周主题快照", source)
                self.assertIn("持续主题追踪", source)
                topic_drawer = source[
                    source.index("function openTopic(id)"):
                    source.index("function closeDrawer()", source.index("function openTopic(id)"))
                ]
                self.assertNotIn('class="timeline"', topic_drawer)
                self.assertIn("openChainDetail", topic_drawer)

    def test_drawers_follow_selected_platform(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("function detailPlatforms()", source)
                self.assertIn(
                    "return state.platform==='综合'?['B站','小黑盒']:[state.platform];",
                    source,
                )
                self.assertIn("function platformChainHistory(", source)
                self.assertIn("metricFor(t,platform)", source)
                self.assertIn("if(state.platform==='小黑盒')", source)
                self.assertIn("不使用B站文本补位", source)
                self.assertIn("不合并为单一正式累计声量", source)


if __name__ == "__main__":
    unittest.main()
