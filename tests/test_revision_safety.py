from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class RevisionSafetyTests(unittest.TestCase):
    def test_comment_metadata_never_falls_back_to_video(self):
        module = load_module(
            "bilibili_revision_collector",
            ROOT / "crawler/bilibili_apex_collector.py",
        )
        collector = object.__new__(module.Collector)
        collector.config = {"timezone": "Asia/Shanghai"}
        collector.keywords = {"mobile_keywords": []}
        collector.collected_at = "2026-08-03T00:00:00+08:00"
        collector.paths = module.Paths(
            Path("videos.jsonl"),
            Path("comments.jsonl"),
            Path("rows.csv"),
            Path("run.log"),
            Path("checkpoint.json"),
        )
        video = {
            "bvid": "BV1234567890",
            "author_name": "video author",
            "publish_epoch": 1785686400,
            "url": "https://www.bilibili.com/video/BV1234567890/",
        }
        with self.assertRaisesRegex(ValueError, "评论缺少自身发布时间"):
            collector._row(
                "top_level_comment",
                "comment",
                video,
                {"author_name": "comment author"},
            )
        with self.assertRaisesRegex(ValueError, "评论缺少自身作者"):
            collector._row(
                "top_level_comment",
                "comment",
                video,
                {"publish_time": "2026-08-02 12:00"},
            )

    def test_site_patch_preserves_previous_week_download(self):
        module = load_module(
            "weekly_release_common_revision",
            ROOT / "scripts/weekly_release_common.py",
        )
        dashboard = json.loads(
            (ROOT / "dashboard_data_apex_W27_W31.json").read_text(encoding="utf-8")
        )
        html = module.patch_site_html(
            (ROOT / "index.html").read_text(encoding="utf-8"),
            dashboard=dashboard,
            dashboard_filename="dashboard_data_apex_W27_W31.json",
            report_filename="APEX_CHINA_W31_Weekly_Community_Report.xlsx",
            preview_filename="APEX_CHINA_W31_Weekly_Community_Report.preview.json",
            report_markdown_filename="APEX_CHINA_W31_Weekly_Community_Report.md",
            bilibili_filename="bilibili_apex_2026_W31.json",
            heybox_filename="heybox_apex_2026_W31_public_search.json",
        )
        self.assertIn(
            'id="downloadW31Report" href="reports/APEX_CHINA_W31_Weekly_Community_Report.xlsx"',
            html,
        )
        self.assertIn(
            'id="downloadW30HistoricalReport" href="reports/APEX_CHINA_W30_Weekly_Community_Report.xlsx"',
            html,
        )

    def test_publish_is_idempotent_for_matching_receipt(self):
        with tempfile.TemporaryDirectory(prefix="apex-publish-idempotent-") as temp:
            root = Path(temp)
            release_root = root / "release"
            source = release_root / "2026_W31"
            source.mkdir(parents=True)
            manifest = {"valid": True, "week_id": "2026_W31", "simulation_only": False}
            manifest_path = source / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            module = load_module(
                "publish_idempotency_hash",
                ROOT / "scripts/weekly_release_common.py",
            )
            manifest_sha = module.sha256(manifest_path)
            site_root = root / "site"
            target = site_root / "releases" / f"2026_W31_{manifest_sha[:12]}"
            target.mkdir(parents=True)
            (source / "publish_receipt.json").write_text(
                json.dumps(
                    {
                        "week_id": "2026_W31",
                        "manifest_sha256": manifest_sha,
                        "target": target.name,
                    }
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/publish_protected_site.py"),
                    "--week",
                    "2026_W31",
                    "--release-root",
                    str(release_root),
                    "--site-root",
                    str(site_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn('"idempotent_noop": true', completed.stdout)

    def test_success_email_is_not_resent_for_same_week(self):
        with tempfile.TemporaryDirectory(prefix="apex-email-idempotent-") as temp:
            root = Path(temp)
            state = root / "state.json"
            state.write_text(
                json.dumps(
                    {
                        "run_id": "2026_W31_second_run",
                        "week_id": "2026_W31",
                        "status": "success",
                    }
                ),
                encoding="utf-8",
            )
            sent = root / "sent"
            sent.mkdir()
            (sent / "2026_W31_success.json").write_text("{}", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops/production/send_weekly_email.py"),
                    "--state",
                    str(state),
                    "--sent-dir",
                    str(sent),
                ],
                text=True,
                capture_output=True,
                check=False,
                env={},
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
