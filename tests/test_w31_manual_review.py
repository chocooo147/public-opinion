import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "dashboard_data_apex_W27_W31.json"
HTML_PATHS = [ROOT / "index.html", ROOT / "game_sentiment_dashboard_v5.html"]


class W31ManualReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        cls.week = next(
            week for week in cls.data["weeks"] if week["week_id"] == "2026-W31"
        )
        cls.topics = {topic["id"]: topic for topic in cls.week["topics"]}

    def test_w31_has_combined_keywords_for_every_topic(self):
        self.assertEqual(len(self.week["topics"]), 13)
        for topic in self.week["topics"]:
            with self.subTest(topic=topic["id"]):
                stats = topic["platform_keyword_stats"].get("综合")
                self.assertIsInstance(stats, list)
                self.assertTrue(stats)
                self.assertTrue(all(row["occurrences"] > 0 for row in stats))

    def test_w31_chinese_and_english_labels_are_separated(self):
        chinese_statuses = {"新生", "上升", "稳定延续", "回落", "复燃", "爆发事件"}
        for topic in self.week["topics"]:
            with self.subTest(topic=topic["id"]):
                self.assertIn(topic["status"], chinese_statuses)
                self.assertIn(
                    topic["status_en"],
                    {"New", "Rising", "Stable", "Declining"},
                )
                self.assertRegex(
                    topic["status_code"],
                    r"^(new|rising|persistent|declining)$",
                )
                self.assertIsNone(re.search(r"[\u4e00-\u9fff]", topic["name_en"]))

    def test_revision1_sample_gate_and_domain_sentiment_provenance(self):
        quality = self.week["kpis"]["sample_quality"]
        self.assertEqual(quality["effective_rows"], 105)
        self.assertEqual(quality["independent_source_count"], 24)
        self.assertEqual(quality["independent_author_count"], 105)
        self.assertTrue(quality["production_gate_passed"])
        self.assertFalse(quality["low_sample_week"])
        self.assertIn(
            "HDBSCAN cluster membership strength",
            quality["confidence_semantics"],
        )
        for topic in self.week["topics"]:
            with self.subTest(topic=topic["id"]):
                metric = topic["platform_metrics"]["B站"]
                self.assertEqual(
                    metric["sentiment_model"],
                    "domain_char_tfidf_logistic_v1",
                )
                self.assertEqual(
                    metric["sentiment_status"],
                    "auxiliary_primary_independent_review_required",
                )

    def test_page_shows_keywords_and_count_backed_negative_rate(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn(
                    'keywordCard&&keywordCard.classList.remove("legacy-layout-hidden")',
                    source,
                )
                self.assertIn("function negativeRateHtml(", source)
                self.assertIn("m?.negative_rate", source)
                self.assertIn("sentiment_valid_count", source)
                self.assertIn("情感数据不足", source)
                self.assertNotIn("reviewedNegativeRate", source)
                self.assertIn("const statusChinese=", source)
                self.assertIn("function negativeRateCompact(", source)
                self.assertIn("'皮肤与外观':'Skins & cosmetics'", source)
                self.assertIn(
                    "'官方运营与沟通':'Official operations & communication'",
                    source,
                )


if __name__ == "__main__":
    unittest.main()
