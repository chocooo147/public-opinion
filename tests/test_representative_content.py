import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from representative_content import (  # noqa: E402
    build_representative_contents,
    valid_source_url,
    validate_representative_contents,
)


class RepresentativeContentTests(unittest.TestCase):
    def test_bilibili_contents_are_grouped_by_real_video(self):
        rows = [
            {
                "text_id": "c1", "bvid": "BV1tPja6mErU", "title": "真实标题",
                "url": "https://www.bilibili.com/video/BV1tPja6mErU/", "text": "a",
                "data_version": "source-v1",
            },
            {
                "text_id": "c2", "bvid": "BV1tPja6mErU", "title": "真实标题",
                "url": "https://www.bilibili.com/video/BV1tPja6mErU/", "text": "b",
                "data_version": "source-v1",
            },
            {
                "text_id": "c3", "bvid": "BV1JEjT6wEND", "title": "另一个真实标题",
                "url": "https://www.bilibili.com/video/BV1JEjT6wEND/", "text": "c",
                "data_version": "source-v1",
            },
        ]
        contents = build_representative_contents(rows, platform="B站")
        self.assertEqual(len(contents), 2)
        self.assertEqual(contents[0]["content_id"], "BV1tPja6mErU")
        self.assertEqual(contents[0]["topic_text_count"], 2)
        self.assertEqual(contents[0]["evidence_text_ids"], ["c1", "c2"])
        self.assertEqual(contents[0]["source_data_version"], "source-v1")
        self.assertFalse(validate_representative_contents(contents))

    def test_missing_title_is_preserved_when_bvid_is_traceable(self):
        contents = build_representative_contents(
            [{
                "text_id": "c1", "bvid": "BV1tPja6mErU", "title": "",
                "url": "https://www.bilibili.com/video/BV1tPja6mErU/", "text": "真实评论",
            }],
            platform="bilibili",
        )
        self.assertEqual(contents[0]["title"], "")
        self.assertEqual(contents[0]["content_id"], "BV1tPja6mErU")
        self.assertFalse(validate_representative_contents(contents))

    def test_invalid_ids_and_placeholder_objects_are_not_valid_content(self):
        contents = build_representative_contents(
            [
                {"text_id": "a", "bvid": "undefined", "url": "https://www.bilibili.com/video/undefined", "text": "a"},
                {"text_id": "b", "bvid": "", "url": "", "text": "b"},
            ],
            platform="B站",
        )
        self.assertEqual(contents, [])
        self.assertTrue(validate_representative_contents([{}]))

    def test_platform_url_allowlist(self):
        self.assertTrue(valid_source_url("https://www.bilibili.com/video/BV1tPja6mErU/", "bilibili"))
        self.assertTrue(valid_source_url("https://www.xiaoheihe.cn/app/bbs/link/123", "heybox"))
        self.assertFalse(valid_source_url("https://example.com/video/BV1tPja6mErU", "bilibili"))
        self.assertFalse(valid_source_url("https://www.bilibili.com/video/undefined", "bilibili"))

    def test_frontend_uses_unified_schema_and_explicit_empty_state(self):
        for path in (ROOT / "index.html", ROOT / "game_sentiment_dashboard_v5.html"):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("representative_contents", source)
                self.assertIn("暂无可验证的代表性B站视频", source)
                self.assertIn("APEX_REPRESENTATIVE_CONTENT_SCHEMA_ERROR", source)
                self.assertIn("validRepresentativeUrl", source)
                self.assertNotIn("${v.bvid}", source)
                self.assertNotIn("${v.comment_count}", source)
                self.assertNotIn("/video/undefined", source)


if __name__ == "__main__":
    unittest.main()
