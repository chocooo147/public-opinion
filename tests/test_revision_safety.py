from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile


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
            (source / "assets").mkdir(parents=True)
            (source / "reports").mkdir()
            manifest = {
                "valid": True,
                "week_id": "2026_W31",
                "week_start": "2026-07-27",
                "week_end": "2026-08-02",
                "simulation_only": False,
                "history_week_ids": ["2026-W31"],
            }
            (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            files = {
                "dashboard": "dashboard_data_apex_W31.json",
                "report": "APEX_CHINA_W31_Weekly_Community_Report.xlsx",
                "report_preview": "APEX_CHINA_W31_Weekly_Community_Report.preview.json",
                "report_markdown": "APEX_CHINA_W31_Weekly_Community_Report.md",
            }
            (source / "release_context.json").write_text(
                json.dumps(
                    {
                        "week_id": "2026_W31",
                        "publication_gate_passed": True,
                        "files": files,
                    }
                ),
                encoding="utf-8",
            )
            dashboard = {
                "meta": {
                    "bilibili_w31_sample": {
                        "canonical_collection_artifact": True,
                        "merge_rule": "private controlled-recovery merge",
                        "scheduled_source": {
                            "path": "/" + "Users/choco/private/scheduled.json",
                            "sha256": "private-scheduled-sha",
                            "records": 21,
                        },
                        "controlled_recovery_source": {
                            "path": "/" + "var/lib/apex/private/recovery.json",
                            "sha256": "private-recovery-sha",
                            "records": 207,
                        },
                        "provenance_counts": {"scheduled_only": 1},
                        "effective_rows": 208,
                    }
                },
                "weeks": [],
            }
            (source / files["dashboard"]).write_text(json.dumps(dashboard), encoding="utf-8")
            (source / "index.html").write_text(
                '<script>const REAL_DASHBOARD_DATA = {"old":true};\nconst dashboardData = REAL_DASHBOARD_DATA;</script>',
                encoding="utf-8",
            )
            __import__("shutil").copyfile(
                ROOT / "assets/sidebar-apex-character.png",
                source / "assets/sidebar-apex-character.png",
            )
            for report_name in (
                files["report"],
                "APEX_CHINA_W30_Weekly_Community_Report.xlsx",
            ):
                __import__("shutil").copyfile(
                    ROOT / "reports/APEX_CHINA_W30_Weekly_Community_Report.xlsx",
                    source / "reports" / report_name,
                )
            (source / "reports" / files["report_preview"]).write_text(
                json.dumps(
                    {
                        "drivers": [
                            {
                                "title": "approved narrative",
                                "evidence_binding": {
                                    "bilibili_comment_ids": [
                                        "bilibili:BV1private:visible-0"
                                    ],
                                    "heybox_visible_post_ids": [
                                        "heybox:private-post"
                                    ],
                                },
                                "evidence_bindings": [
                                    {
                                        "record_id": "private-record",
                                        "source_id": "private-source",
                                        "source_url": "https://example.test/private",
                                        "text": "private raw record",
                                    }
                                ],
                                "source_urls": ["https://example.test/private"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (source / "reports" / files["report_markdown"]).write_text("approved", encoding="utf-8")
            site_root = root / "site"
            command = [
                sys.executable,
                str(ROOT / "scripts/publish_protected_site.py"),
                "--week",
                "2026_W31",
                "--release-root",
                str(release_root),
                "--site-root",
                str(site_root),
                "--project-root",
                str(ROOT),
            ]
            first = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            completed = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn('"idempotent_noop": true', completed.stdout)
            public_files = {
                path.relative_to(site_root / "current").as_posix()
                for path in (site_root / "current").rglob("*")
                if path.is_file()
            }
            self.assertNotIn("release_context.json", public_files)
            self.assertNotIn("archive/raw_inputs/bilibili.json", public_files)
            public_dashboard = json.loads(
                (site_root / "current" / files["dashboard"]).read_text(
                    encoding="utf-8"
                )
            )
            public_sample = public_dashboard["meta"]["bilibili_w31_sample"]
            self.assertEqual(public_sample, {"effective_rows": 208})
            public_html = (site_root / "current" / "index.html").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("/" + "Users/", public_html)
            self.assertNotIn("/" + "var/lib/apex", public_html)
            self.assertNotIn("choco", public_html.lower())
            public_preview = json.loads(
                (site_root / "current" / "reports" / files["report_preview"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(public_preview, {"drivers": [{"title": "approved narrative"}]})
            public_workbook = site_root / "current" / "reports" / files["report"]
            with ZipFile(public_workbook) as archive:
                threaded = ET.fromstring(
                    archive.read("xl/threadedcomments/threadedcomment.xml")
                )
                comments = [
                    node
                    for node in threaded.iter()
                    if node.tag.endswith("}threadedComment")
                ]
                self.assertEqual(len(comments), 9)
                person_xml = archive.read("xl/persons/person.xml").decode("utf-8")
                comment_xml = archive.read(
                    "xl/threadedcomments/threadedcomment.xml"
                ).decode("utf-8")
                self.assertIn("APEX Public Release", person_xml)
                self.assertIn("Public evidence note", comment_xml)
                self.assertNotIn("https://www.", comment_xml.lower())
                self.assertNotIn("choco", person_xml.lower())
                self.assertNotIn("APEX-T", comment_xml)

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
            (sent / "2026_W31_final-delivery.json").write_text("{}", encoding="utf-8")
            approval = root / "approval.json"
            approval.write_text(
                json.dumps({"status": "approved_for_release"}),
                encoding="utf-8",
            )
            live = root / "live.json"
            live.write_text(
                json.dumps({"week_id": "2026_W31", "hashes_verified": True}),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ops/production/send_weekly_email.py"),
                    "--state",
                    str(state),
                    "--sent-dir",
                    str(sent),
                    "--approval",
                    str(approval),
                    "--live-verification",
                    str(live),
                ],
                text=True,
                capture_output=True,
                check=False,
                env={},
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
