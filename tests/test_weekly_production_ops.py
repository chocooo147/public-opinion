from __future__ import annotations

import importlib.util
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class WeeklyProductionOpsTests(unittest.TestCase):
    def test_previous_complete_week_uses_monday_sunday_boundary(self):
        module = load_module(
            "weekly_pipeline",
            ROOT / "ops/production/weekly_pipeline.py",
        )
        now = datetime(2026, 8, 3, 0, 15, tzinfo=ZoneInfo("Asia/Shanghai"))
        week = module.previous_complete_week(now)
        self.assertEqual(week.week_id, "2026_W31")
        self.assertEqual(week.start, "2026-07-27")
        self.assertEqual(week.end, "2026-08-02")

    def test_previous_complete_week_handles_iso_year_rollover(self):
        module = load_module(
            "weekly_pipeline_rollover",
            ROOT / "ops/production/weekly_pipeline.py",
        )
        now = datetime(2027, 1, 4, 0, 15, tzinfo=ZoneInfo("Asia/Shanghai"))
        week = module.previous_complete_week(now)
        self.assertEqual(week.week_id, "2026_W53")
        self.assertEqual(week.start, "2026-12-28")
        self.assertEqual(week.end, "2027-01-03")

    def test_public_status_excludes_paths_and_internal_errors(self):
        module = load_module(
            "weekly_pipeline_public_status",
            ROOT / "ops/production/weekly_pipeline.py",
        )
        run = {
            "run_id": "2026_W31_test",
            "week_id": "2026_W31",
            "week_start": "2026-07-27",
            "week_end": "2026-08-02",
            "status": "failed",
            "error": "secret internal path /opt/apex/private",
            "started_at": "2026-08-03T00:15:00+08:00",
            "finished_at": "2026-08-03T08:45:00+08:00",
            "stages": [
                {
                    "name": "collect_bilibili",
                    "status": "failed",
                    "log": "/var/lib/apex/private.log",
                }
            ],
            "artifacts": {
                "weekly_report": {
                    "path": "/opt/apex/private/report.xlsx",
                    "bytes": 123,
                    "sha256": "a" * 64,
                }
            },
        }
        status = module.public_status(run)
        rendered = str(status)
        self.assertEqual(status["failed_stage"], "collect_bilibili")
        self.assertNotIn("/opt/apex", rendered)
        self.assertNotIn("/var/lib/apex", rendered)
        self.assertNotIn("secret internal", rendered)
        self.assertEqual(
            status["artifacts"]["weekly_report"],
            {"bytes": 123, "sha256": "a" * 64},
        )
        self.assertEqual(
            status["milestones"]["platform_collection"]["status"],
            "failed",
        )
        self.assertEqual(
            status["milestones"]["model_and_dashboard"]["status"],
            "pending",
        )
        self.assertEqual(
            status["milestones"]["weekly_report"]["status"],
            "pending",
        )

    def test_simulation_status_cannot_be_mistaken_for_real_data(self):
        module = load_module(
            "weekly_pipeline_simulation_status",
            ROOT / "ops/production/weekly_pipeline.py",
        )
        status = module.public_status(
            {
                "run_id": "2026_W31_sim",
                "week_id": "2026_W31",
                "mode": "simulate",
                "status": "success",
                "stages": [],
                "artifacts": {},
            }
        )
        self.assertEqual(status["mode"], "simulate")
        self.assertEqual(
            status["data_boundary"]["bilibili"],
            "simulated_fixture",
        )
        self.assertFalse(status["data_boundary"]["formal_reporting_qualified"])

    def test_collector_csv_is_normalized_to_weekly_json_contract(self):
        module = load_module(
            "run_platform_collector",
            ROOT / "scripts/run_platform_collector.py",
        )
        with tempfile.TemporaryDirectory(prefix="apex-collector-contract-") as temp:
            path = Path(temp) / "heybox.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "text_id",
                        "publish_time",
                        "platform",
                        "text",
                        "likes",
                        "comments",
                        "url",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "text_id": "heybox:test",
                        "publish_time": "2026-07-27T12:00:00+08:00",
                        "platform": "小黑盒",
                        "text": "contract fixture",
                        "likes": "3",
                        "comments": "2",
                        "url": "https://invalid.example/test",
                    }
                )
            payload = module._csv_payload(
                path,
                platform="小黑盒",
                week_id="2026_W31",
                week_start="2026-07-27",
                week_end="2026-08-02",
            )
            self.assertEqual(payload["meta"]["week_id"], "2026_W31")
            self.assertEqual(payload["meta"]["raw_rows"], 1)
            self.assertFalse(payload["meta"]["simulation_only"])
            self.assertEqual(payload["records"][0]["week_id"], "2026_W31")
            self.assertEqual(payload["records"][0]["likes"], 3)

    def test_collector_rejects_unchanged_stale_fallback(self):
        with tempfile.TemporaryDirectory(prefix="apex-stale-fallback-") as temp:
            work = Path(temp)
            stale = work / "stale.json"
            stale.write_text('{"meta": {}, "records": [{"text": "old"}]}', encoding="utf-8")
            command = [
                sys.executable,
                str(ROOT / "scripts/run_platform_collector.py"),
                "--target",
                str(work / "fresh.json"),
                "--fallback",
                str(stale),
                "--platform",
                "B站",
                "--week",
                "2026_W31",
                "--week-start",
                "2026-07-27",
                "--week-end",
                "2026-08-02",
                "--",
                sys.executable,
                "-c",
                "pass",
            ]
            completed = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("produced no contract JSON", completed.stderr)

    def test_email_has_only_confirmed_recipient_and_failure_boundary(self):
        module = load_module(
            "send_weekly_email",
            ROOT / "ops/production/send_weekly_email.py",
        )
        status = {
            "run_id": "2026_W31_test",
            "week_id": "2026_W31",
            "week_start": "2026-07-27",
            "week_end": "2026-08-02",
            "started_at": "2026-08-03T00:15:00+08:00",
            "finished_at": "2026-08-03T08:45:00+08:00",
            "status": "failed",
            "error": "SafetyStop: CAPTCHA",
            "artifacts": {},
        }
        message = module.build_message(
            status,
            "chocooo147@gmail.com",
            "yifewang@contractor.ea.com",
        )
        self.assertEqual(message["From"], "chocooo147@gmail.com")
        self.assertEqual(message["To"], "yifewang@contractor.ea.com")
        self.assertNotIn("chocooo147@gmail.com", str(message["To"]))
        body = message.get_body().get_content()
        self.assertIn("上一版生产网站保持不变", body)
        self.assertIn("SafetyStop: CAPTCHA", body)

    def test_systemd_deadlines_are_explicit(self):
        pipeline_timer = (
            ROOT / "ops/systemd/apex-weekly-pipeline.timer"
        ).read_text(encoding="utf-8")
        email_timer = (
            ROOT / "ops/systemd/apex-weekly-email.timer"
        ).read_text(encoding="utf-8")
        service = (
            ROOT / "ops/systemd/apex-weekly-pipeline.service"
        ).read_text(encoding="utf-8")
        self.assertIn("00:15:00 Asia/Shanghai", pipeline_timer)
        self.assertIn("09:00:00 Asia/Shanghai", email_timer)
        self.assertIn("TimeoutStartSec=8h30m", service)
        nginx = (
            ROOT / "ops/nginx/apex-protected-site.conf.template"
        ).read_text(encoding="utf-8")
        self.assertIn("location = /status/weekly.json", nginx)
        self.assertIn("auth_basic off", nginx)

    def test_simulated_w31_runs_all_seven_stages_end_to_end(self):
        with tempfile.TemporaryDirectory(prefix="apex-weekly-e2e-") as temp:
            work = Path(temp)
            command = [
                sys.executable,
                str(ROOT / "ops/production/weekly_pipeline.py"),
                "--root",
                str(ROOT),
                "--state-dir",
                str(work / "state"),
                "--public-status",
                str(work / "public/weekly.json"),
                "--release-root",
                str(work / "release"),
                "--site-root",
                str(work / "site"),
                "--mode",
                "simulate",
                "--now",
                "2026-08-03T00:15:00+08:00",
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=completed.stdout + completed.stderr,
            )
            state = json.loads(
                (work / "state/latest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["status"], "success")
            self.assertEqual(
                [stage["name"] for stage in state["stages"]],
                [
                    "collect_bilibili",
                    "collect_heybox",
                    "prepare_release",
                    "build_report",
                    "validate_release",
                    "publish_site",
                    "verify_live",
                ],
            )
            self.assertTrue(
                all(stage["status"] == "success" for stage in state["stages"])
            )
            validation = json.loads(
                (
                    work
                    / "release/2026_W31/validation.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                validation["history_week_ids"],
                [
                    "2026-W27",
                    "2026-W28",
                    "2026-W29",
                    "2026-W30",
                    "2026-W31",
                ],
            )
            self.assertEqual(validation["report_driver_count"], 10)
            public = json.loads(
                (work / "public/weekly.json").read_text(encoding="utf-8")
            )
            self.assertEqual(public["status"], "success")
            self.assertEqual(public["mode"], "simulate")
            self.assertTrue(
                all(
                    milestone["status"] == "success"
                    for milestone in public["milestones"].values()
                )
            )
            current = work / "site/current"
            self.assertTrue(current.is_symlink())
            live = json.loads(
                (
                    work
                    / "release/2026_W31/live_verification.json"
                ).read_text(encoding="utf-8")
            )
            self.assertTrue(live["hashes_verified"])
            self.assertFalse(live["protected_auth_verified"])


if __name__ == "__main__":
    unittest.main()
