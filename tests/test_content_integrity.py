import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

import sys

sys.path.insert(0, str(SCRIPTS))

from content_integrity import extract_keywords, generate_events


def record(text_id, text, content_id, topic="APEX-T013", platform="B站"):
    return {
        "text_id": text_id,
        "text": text,
        "bvid": content_id if platform == "B站" else None,
        "post_id": content_id if platform == "小黑盒" else None,
        "platform": platform,
        "canonical_topic_id": topic,
        "publish_time": "2026-08-01T12:00:00+08:00",
    }


class ContentIntegrityTests(unittest.TestCase):
    def test_domain_aliases_are_normalized_and_traceable(self):
        rows = [
            record("a", "S30赛季准备削弱r99并进行补给箱改动", "BV1"),
            record("b", "R-99强度和补给箱改动值得关注", "BV2"),
            record("c", "car冲锋枪本赛季也会调整", "P1", platform="小黑盒"),
            record("d", "C.A.R.和RE45的平衡讨论", "BV3"),
        ]
        result = extract_keywords(rows)
        by_name = {row["normalized_keyword"]: row for row in result["qualified"]}
        self.assertIn("R-99", by_name)
        self.assertIn("补给箱改动", by_name)
        self.assertIn("CAR冲锋枪", by_name)
        for item in by_name.values():
            self.assertEqual(item["quality_status"], "passed")
            self.assertGreaterEqual(item["text_coverage_count"], 2)
            self.assertTrue(item["evidence_text_ids"])
            self.assertTrue(item["topic_ids"])

    def test_pure_numbers_are_excluded_but_season_context_is_preserved(self):
        rows = [
            record("a", "S30赛季有新改动，12 只是普通数量", "BV1"),
            record("b", "第30赛季继续观察，15 没有明确含义", "BV2"),
        ]
        result = extract_keywords(rows)
        names = {row["normalized_keyword"] for row in result["qualified"]}
        self.assertIn("S30赛季", names)
        excluded = {
            row["raw_keyword"]
            for row in result["filter_log"]
            if row["action"] == "excluded"
        }
        self.assertIn("12", excluded)
        self.assertIn("15", excluded)
        self.assertNotIn("30", excluded)
        self.assertTrue(all(not name.isdigit() for name in names))

    def test_events_require_independent_content_and_have_full_contract(self):
        rows = [
            record("a", "S30赛季补给箱移除后物资更少", "BV1", "APEX-T005"),
            record("b", "30赛季战利品和r99强度都改了", "P1", "APEX-T013", "小黑盒"),
            record("c", "终于复活了", "BV9", "APEX-T001"),
            record("d", "你复活了", "BV9", "APEX-T003"),
        ]
        result = generate_events(rows, week_id="2026_W31")
        qualified = {row["rule_id"]: row for row in result["events"]}
        excluded = {row["rule_id"]: row for row in result["excluded"]}
        self.assertIn("s30_gameplay_loot_changes", qualified)
        self.assertIn("creator_return_discussion", excluded)
        self.assertIn("independent_content_coverage_under_2", excluded["creator_return_discussion"]["exclusion_reasons"])
        required = {
            "event_id", "week_id", "title", "summary", "event_date", "platforms",
            "topic_ids", "content_ids", "evidence_text_ids", "comment_count",
            "content_count", "impact_score", "event_type", "event_status",
            "data_quality_status",
        }
        self.assertTrue(required <= set(qualified["s30_gameplay_loot_changes"]))

    def test_frontend_uses_backend_contract_and_new_zero_display(self):
        for path in (ROOT / "index.html", ROOT / "game_sentiment_dashboard_v5.html"):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("x?.quality_status==='passed'", source)
                self.assertIn("APEX_EVENT_DATA_UNAVAILABLE", source)
                self.assertIn("本周暂无达到展示门槛的关键事件", source)
                self.assertIn("低样本：样本量较小 不单独用于风险结论", source)
                self.assertIn("Low sample: insufficient for standalone risk conclusions", source)
                self.assertNotIn("0%（0 /", source)
                self.assertNotIn("Object.assign(dashboardData", source)


if __name__ == "__main__":
    unittest.main()
