from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))
from bilibili_apex_collector import content_hash, deduplicate, filter_excluded

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

if __name__ == "__main__": unittest.main()
