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

    def test_all_platform_week_deltas_match_visible_volume_semantics(self):
        expected = {
            "B站": [set(), set(), set()],
            "综合": [set(), set(), set()],
            "小黑盒": [
                {"APEX-T005"},
                {"APEX-T001"},
                {"APEX-T011", "APEX-T012"},
            ],
        }
        weeks = self.data["weeks"]
        for platform, transitions in expected.items():
            for index, expected_ids in enumerate(transitions, start=1):
                with self.subTest(platform=platform, week=weeks[index]["week_id"]):
                    actual = visible_ids(weeks[index], platform) - visible_ids(weeks[index - 1], platform)
                    self.assertEqual(actual, expected_ids)

    def test_every_platform_metric_is_real_input(self):
        for week in self.data["weeks"]:
            for topic in week["topics"]:
                for platform in ("B站", "小黑盒"):
                    with self.subTest(week=week["week_id"], topic=topic["id"], platform=platform):
                        self.assertIs(topic["platform_metrics"][platform].get("simulated"), False)
                self.assertIs(topic["combined_metrics"].get("simulated"), False)

    def test_published_html_uses_platform_week_delta(self):
        for path in HTML_PATHS:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertEqual(source.count("function newVisibleTopicIds("), 1)
                self.assertIn("new_topics:newVisibleTopicIds(w,platform).length", source)
                self.assertIn("newIds.has(x.t.id)", source)

    def test_published_html_has_only_real_data_ui(self):
        forbidden = (
            "SIMULATION_SEED",
            "simulatedMetricFromBilibili",
            "heybox_simulated_for_ui_test",
            "当前为演示面板",
            "综合 · 测试",
            "B站 · 真实",
            "小黑盒 · 真实样本",
        )
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(source.count('class="sidebar-note sidebar-model-note"'), 1)
                self.assertIn("当前数据说明", source)
                self.assertIn("BERTopic已接入·B站&amp;小黑盒真实数据", source)
                self.assertIn("trend-value-volume", source)
                self.assertIn("trend-value-negative", source)
                self.assertIn("grid-template-columns:minmax(300px,3fr) minmax(0,7fr)", source)
                for token in forbidden:
                    self.assertNotIn(token, source)

    def test_keyword_stats_are_observed_and_vary_by_week_and_platform(self):
        counts = {platform: [] for platform in ("B站", "小黑盒", "综合")}
        top_tens = {platform: [] for platform in counts}
        for week in self.data["weeks"]:
            for platform in counts:
                stats = week["keyword_stats"][platform]
                effective = [row for row in stats if row["document_count"] >= 2 and row["document_coverage"] >= 0.02]
                counts[platform].append(len(effective))
                top_tens[platform].append(tuple(row["keyword"] for row in effective[:10]))
                self.assertTrue(all(row["occurrences"] > 0 for row in stats))
                self.assertTrue(all(row["document_count"] > 0 for row in stats))
                self.assertTrue(all(0 < row["document_coverage"] <= 1 for row in stats))
        for platform in counts:
            with self.subTest(platform=platform):
                self.assertGreater(len(set(counts[platform])), 1)
                self.assertGreater(len(set(top_tens[platform])), 1)
                self.assertNotIn(188, counts[platform])

    def test_topic_keywords_use_platform_week_text_not_registry_descriptors(self):
        by_topic = {}
        for week in self.data["weeks"]:
            for topic in week["topics"]:
                by_topic.setdefault(topic["id"], []).append(
                    tuple(row["keyword"] for row in topic["platform_keyword_stats"]["B站"][:15])
                )
                self.assertIn("descriptor_keywords", topic)
        self.assertTrue(all(len(set(weekly_lists)) > 1 for weekly_lists in by_topic.values()))

    def test_published_keyword_ui_uses_real_frequency(self):
        forbidden = (
            "freq[k]=(freq[k]||0)+(metricFor(t)?metricFor(t).count:0)",
            "关键词按本周主题声量加权汇总",
        )
        for path in HTML_PATHS:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("const KEYWORD_MIN_DOCUMENT_COVERAGE=.02", source)
                self.assertIn("Number(x.document_count)>=2", source)
                self.assertIn("有效关键词", source)
                self.assertIn("实际出现次数", source)
                self.assertIn("x.document_count", source)
                self.assertEqual(source.count("function dashboardKeywordStats("), 1)
                for token in forbidden:
                    self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
