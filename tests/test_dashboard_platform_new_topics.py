import json
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


def visible_ids(week, platform):
    def count(topic):
        metrics = topic["combined_metrics"] if platform == "综合" else topic["platform_metrics"][platform]
        return int(metrics.get("count") or 0)

    return {topic["id"] for topic in week["topics"] if count(topic) > 0}


class PlatformNewTopicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "dashboard_data_apex_W25_W28.json").read_text(encoding="utf-8"))

    def test_w28_heybox_has_two_newly_visible_topics(self):
        w27, w28 = self.data["weeks"][2:4]
        new_ids = visible_ids(w28, "小黑盒") - visible_ids(w27, "小黑盒")
        self.assertEqual(new_ids, {"APEX-T011", "APEX-T012"})

    def test_other_w28_views_do_not_inherit_heybox_delta(self):
        w27, w28 = self.data["weeks"][2:4]
        for platform in ("B站", "综合"):
            with self.subTest(platform=platform):
                self.assertEqual(visible_ids(w28, platform) - visible_ids(w27, platform), set())

    def test_published_html_uses_platform_week_delta(self):
        for path in HTML_PATHS:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertEqual(source.count("function newVisibleTopicIds("), 1)
                self.assertIn("new_topics:newVisibleTopicIds(w,platform).length", source)
                self.assertIn("newIds.has(x.t.id)", source)


if __name__ == "__main__":
    unittest.main()
