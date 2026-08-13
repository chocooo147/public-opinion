from __future__ import annotations
import json
import tempfile
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))
from bilibili_apex_collector import (
    Collector,
    content_hash,
    deduplicate,
    filter_excluded,
    select_candidates_round_robin,
)

class DeduplicationTests(unittest.TestCase):
    def test_comment_text_hash_and_suspected(self):
        rows = [
            {"source_type":"top_level_comment","comment_id":"1","text":"服务器延迟很高","author_name":"甲","publish_time":"2026-07-06T10:00:00"},
            {"source_type":"top_level_comment","comment_id":"1","text":"另一文本","author_name":"乙","publish_time":"2026-07-06T10:01:00"},
            {"source_type":"top_level_comment","comment_id":"2","text":"服务器 延迟很高","author_name":"甲","publish_time":"2026-07-06T10:02:00"},
            {"source_type":"top_level_comment","comment_id":"3","text":"服务器延迟很高啊","author_name":"甲","publish_time":"2026-07-06T10:03:00"},
        ]
        kept, filtered = deduplicate(rows, .85, 10)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0]["duplicate_reason"], "duplicate_comment_id")
        self.assertEqual(filtered[1]["duplicate_reason"], "normalized_hash_duplicate")
        self.assertEqual(kept[-1]["suspected_duplicate"], 1)
        self.assertEqual(content_hash("A P E X"), content_hash("apex"))

    def test_exclusion_terms(self):
        kept, filtered = filter_excluded([
            {"title": "Oracle APEX 教程", "text": "数据库开发"},
            {"title": "Apex英雄排位", "text": "服务器延迟"},
        ], ["Oracle APEX", "APEX数据库"])
        self.assertEqual(len(kept), 1)
        self.assertEqual(filtered[0]["duplicate_reason"], "excluded_term:Oracle APEX")

    def test_fallback_comment_ids_are_scoped_to_video(self):
        rows = [
            {"source_type":"top_level_comment","bvid":"BV1111111111","comment_id":"visible-0","text":"第一条","author_name":"甲","publish_time":"2026-08-03T10:00:00"},
            {"source_type":"top_level_comment","bvid":"BV2222222222","comment_id":"visible-0","text":"第二条","author_name":"乙","publish_time":"2026-08-03T10:01:00"},
            {"source_type":"top_level_comment","bvid":"BV2222222222","comment_id":"visible-0","text":"重复编号","author_name":"丙","publish_time":"2026-08-03T10:02:00"},
        ]
        kept, filtered = deduplicate(rows)
        self.assertEqual([row["bvid"] for row in kept], ["BV1111111111", "BV2222222222"])
        self.assertEqual(filtered[0]["duplicate_reason"], "duplicate_comment_id")

    def test_candidate_selection_round_robins_across_queries(self):
        selected = select_candidates_round_robin(
            {
                "q1": [{"bvid": "a"}, {"bvid": "b"}, {"bvid": "c"}],
                "q2": [{"bvid": "d"}, {"bvid": "b"}, {"bvid": "e"}],
            },
            ["q1", "q2"],
            4,
        )
        self.assertEqual([row["bvid"] for row in selected], ["a", "d", "b", "c"])

    def test_controlled_recovery_uses_isolated_artifact_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            start = datetime(2026, 8, 3, tzinfo=ZoneInfo("Asia/Shanghai"))
            collector = Collector(
                {"mobile_keywords": []},
                {"timezone": "Asia/Shanghai", "page_delay_seconds": [0, 0]},
                start,
                start,
                "2026_W32",
                artifact_dir=artifact_dir,
            )
            self.assertEqual(collector.paths.checkpoint.parent, artifact_dir)
            self.assertEqual(collector.report_path.parent, artifact_dir)
            row = collector._row(
                "top_level_comment",
                "测试",
                {"bvid": "BV1111111111"},
                {"comment_id": "visible-0", "publish_time": "2026-08-03T10:00:00", "author_name": "甲"},
            )
            self.assertEqual(row["text_id"], "bilibili:BV1111111111:visible-0")

    def test_checkpoint_resume_rebuilds_rows_from_completed_raw_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            start = datetime(2026, 8, 3, tzinfo=ZoneInfo("Asia/Shanghai"))
            config = {
                "timezone": "Asia/Shanghai",
                "page_delay_seconds": [0, 0],
                "headless": True,
                "max_videos": 75,
                "similarity_threshold": .9,
                "similarity_window_minutes": 10,
            }
            collector = Collector(
                {"core_keywords": ["q1"], "experience_keywords": [], "mobile_keywords": [], "exclude_terms": []},
                config,
                start,
                start,
                "2026_W32",
                artifact_dir=artifact_dir,
            )
            video = {"bvid": "BV1111111111", "url": "https://www.bilibili.com/video/BV1111111111", "title": "测试", "query_keyword": "q1"}
            comment = {"bvid": "BV1111111111", "comment_id": "visible-0", "text": "恢复记录", "publish_time": "2026-08-03T10:00:00", "author_name": "甲"}
            collector.paths.videos.write_text(json.dumps(video, ensure_ascii=False) + "\n", encoding="utf-8")
            collector.paths.comments.write_text(json.dumps(comment, ensure_ascii=False) + "\n", encoding="utf-8")
            collector.paths.checkpoint.write_text(json.dumps({
                "completed_keywords": ["q1"],
                "completed_bvids": ["BV1111111111"],
                "discovered_candidates_by_keyword": {"q1": [video]},
                "discovery_stats_by_keyword": {"q1": {"requests": 3, "hits": 1}},
            }), encoding="utf-8")

            class FakeContext:
                pages = []
                def new_page(self): return object()
                def close(self): pass
            class FakeBrowser:
                def new_context(self, **kwargs): return FakeContext()
                def close(self): pass
            class FakeChromium:
                def launch(self, **kwargs): return FakeBrowser()
            class FakePlaywright:
                chromium = FakeChromium()
            class FakeManager:
                def __enter__(self): return FakePlaywright()
                def __exit__(self, *args): return False

            package = types.ModuleType("playwright")
            sync_api = types.ModuleType("playwright.sync_api")
            sync_api.sync_playwright = lambda: FakeManager()
            old_package = sys.modules.get("playwright")
            old_sync_api = sys.modules.get("playwright.sync_api")
            sys.modules["playwright"] = package
            sys.modules["playwright.sync_api"] = sync_api
            try:
                valid, filtered = collector.run_live()
            finally:
                if old_package is None: sys.modules.pop("playwright", None)
                else: sys.modules["playwright"] = old_package
                if old_sync_api is None: sys.modules.pop("playwright.sync_api", None)
                else: sys.modules["playwright.sync_api"] = old_sync_api

            self.assertEqual(len(valid), 1)
            self.assertEqual(valid[0]["text"], "恢复记录")
            self.assertEqual(filtered, [])
            self.assertEqual(collector.stats["discovery_requests"], 3)

if __name__ == "__main__": unittest.main()
