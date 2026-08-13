from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "crawler"))

from heybox_public_search_collector import CSV_FIELDS, parse_card_text, write_csv


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class HeyboxCollectorTests(unittest.TestCase):
    CARD_TEXT = """夜步十里松原
Lv.19
舍友买个号真是亏麻了
舍友花700买这个号，真是纯亏
Apex 英雄
08-01
272
99"""

    def test_visible_profile_link_becomes_stable_author_uid(self):
        row = parse_card_text(
            self.CARD_TEXT,
            "/app/bbs/link/187094109",
            "Apex英雄",
            "/app/user/profile/15726959",
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["post_id"], "187094109")
        self.assertEqual(row["author_name"], "夜步十里松原")
        self.assertEqual(row["author_uid"], "15726959")

    def test_untrusted_profile_href_is_not_promoted_to_identity(self):
        row = parse_card_text(
            self.CARD_TEXT,
            "/app/bbs/link/187094109",
            "Apex英雄",
            "https://invalid.example/user/15726959",
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["author_uid"], "")

    def test_csv_preserves_author_identity_and_missing_reach(self):
        self.assertIn("author_name", CSV_FIELDS)
        self.assertIn("author_uid", CSV_FIELDS)
        self.assertIn("views", CSV_FIELDS)
        with tempfile.TemporaryDirectory(prefix="apex-heybox-author-") as temp:
            path = Path(temp) / "heybox.csv"
            write_csv(
                path,
                [
                    {
                        "text_id": "heybox:187094109",
                        "post_id": "187094109",
                        "author_name": "夜步十里松原",
                        "author_uid": "15726959",
                        "views": "",
                    }
                ],
            )
            with path.open(encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["author_name"], "夜步十里松原")
            self.assertEqual(row["author_uid"], "15726959")
            self.assertEqual(row["views"], "")

    def test_weekly_normalizer_keeps_missing_heybox_reach_as_missing(self):
        module = load_module(
            "run_platform_collector_heybox_readiness",
            ROOT / "scripts/run_platform_collector.py",
        )
        with tempfile.TemporaryDirectory(prefix="apex-heybox-contract-") as temp:
            path = Path(temp) / "heybox.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "text_id",
                        "publish_time",
                        "author_name",
                        "author_uid",
                        "likes",
                        "comments",
                        "views",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "text_id": "heybox:187094109",
                        "publish_time": "2026-08-03T12:00:00+08:00",
                        "author_name": "夜步十里松原",
                        "author_uid": "15726959",
                        "likes": "99",
                        "comments": "272",
                        "views": "",
                    }
                )
            payload = module._csv_payload(
                path,
                platform="小黑盒",
                week_id="2026_W32",
                week_start="2026-08-03",
                week_end="2026-08-09",
            )
            row = payload["records"][0]
            self.assertEqual(row["author_uid"], "15726959")
            self.assertIsNone(row["views"])


if __name__ == "__main__":
    unittest.main()
