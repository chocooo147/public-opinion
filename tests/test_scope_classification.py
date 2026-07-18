from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from classify_bilibili_scope_w25_w28 import classify_scope


def row(text: str, title: str = "Apex玩家讨论", **overrides: str) -> dict[str, str]:
    result = {
        "source_type": "top_level_comment",
        "text": text,
        "title": title,
        "query_keyword": "Apex玩家",
        "week_assignment_confidence": "high",
        "candidate_training_include": "1",
        "parent_video_relevant": "1",
        "rule_filtered": "0",
        "deduplication_valid": "1",
        "filter_reason": "",
    }
    result.update(overrides)
    return result


class ScopeClassificationTests(unittest.TestCase):
    def test_local_driver_fix_is_technical(self):
        result = classify_scope(row("更新显卡驱动后就正常了"))
        self.assertEqual(result["analysis_scope"], "technical")
        self.assertEqual(result["new_media_include"], "0")
        self.assertEqual(result["technical_issue_include"], "1")
        self.assertEqual(result["issue_attribution"], "driver_environment")

    def test_official_nonresponse_is_mixed_and_kept(self):
        result = classify_scope(row("官方一直不回应掉帧问题，态度太差"))
        self.assertEqual(result["analysis_scope"], "mixed")
        self.assertEqual(result["new_media_include"], "1")
        self.assertEqual(result["technical_issue_include"], "1")
        self.assertEqual(result["training_include"], "1")

    def test_bug_spread_event_is_mixed(self):
        result = classify_scope(row("这次BUG已经成为全网笑话"))
        self.assertEqual(result["analysis_scope"], "mixed")
        self.assertEqual(result["new_media_include"], "1")

    def test_short_but_clear_performance_problem_is_technical(self):
        result = classify_scope(row("太卡了"))
        self.assertEqual(result["analysis_scope"], "technical")
        self.assertEqual(result["issue_category"], "performance")

    def test_nontechnical_opinion_stays_new_media(self):
        result = classify_scope(row("匹配很烂"))
        self.assertEqual(result["analysis_scope"], "new_media")
        self.assertEqual(result["training_include"], "1")

    def test_high_latency_in_highlight_title_does_not_route_child_comment(self):
        result = classify_scope(
            row(
                "这波一打三太强了",
                title="主播精彩时刻：什么叫顶着高延迟用长弓一打三",
            )
        )
        self.assertEqual(result["analysis_scope"], "new_media")


if __name__ == "__main__":
    unittest.main()
