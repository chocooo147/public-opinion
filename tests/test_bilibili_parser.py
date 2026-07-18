from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))
from bilibili_apex_collector import extract_bvid, parse_count, parse_video_html

class ParserTests(unittest.TestCase):
    def test_bvid_and_counts(self):
        self.assertEqual(extract_bvid("https://www.bilibili.com/video/BV1Ab411c7Xy"), "BV1Ab411c7Xy")
        self.assertEqual(parse_count("1.2万"), 12000)
        self.assertIsNone(parse_count("--"))

    def test_initial_state(self):
        source = (Path(__file__).parent / "fixtures" / "bilibili_video_sample.html").read_text(encoding="utf-8")
        item = parse_video_html(source, "https://www.bilibili.com/video/BV1Ab411c7Xy", "Apex英雄")
        self.assertEqual(item["bvid"], "BV1Ab411c7Xy")
        self.assertEqual(item["author_name"], "测试UP主")
        self.assertEqual(item["views"], 1200)

if __name__ == "__main__": unittest.main()
