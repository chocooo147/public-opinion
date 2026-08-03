#!/usr/bin/env python3
"""Run the APEX weekly production pipeline before the Monday 09:00 deadline.

The collector and release commands are deliberately explicit.  A failed stage
stops the run, records a machine-readable status, and leaves the previously
published site untouched.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


TIMEZONE = ZoneInfo("Asia/Shanghai")
DEFAULT_ROOT = Path("/opt/apex")
DEFAULT_STATE_DIR = Path("/var/lib/apex/weekly")
DEFAULT_PUBLIC_STATUS = Path("/srv/apex-status/weekly.json")
DEFAULT_SITE_ROOT = Path("/srv/apex-site")


@dataclass(frozen=True)
class Week:
    week_id: str
    start: str
    end: str


def previous_complete_week(now: datetime) -> Week:
    local = now.astimezone(TIMEZONE)
    this_monday = (local - timedelta(days=local.weekday())).date()
    start = this_monday - timedelta(days=7)
    end = this_monday - timedelta(days=1)
    iso_year, iso_week, _ = start.isocalendar()
    return Week(f"{iso_year}_W{iso_week:02d}", start.isoformat(), end.isoformat())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def public_status(run: dict) -> dict:
    stage_status = {
        stage["name"]: stage.get("status", "pending")
        for stage in run.get("stages", [])
    }

    def milestone(required: list[str]) -> dict:
        statuses = [stage_status.get(name, "pending") for name in required]
        if all(status == "success" for status in statuses):
            status = "success"
        elif any(status == "failed" for status in statuses):
            status = "failed"
        elif any(status == "running" for status in statuses):
            status = "running"
        else:
            status = "pending"
        return {"status": status, "required_stages": required}

    failed_stage = next(
        (
            stage["name"]
            for stage in run.get("stages", [])
            if stage.get("status") == "failed"
        ),
        None,
    )
    artifacts = {}
    for name, item in run.get("artifacts", {}).items():
        artifacts[name] = {
            key: item[key]
            for key in ("bytes", "sha256")
            if key in item
        }
    simulated = run.get("mode") == "simulate"
    return {
        "schema_version": 1,
        "service": "apex-weekly-report",
        "run_id": run.get("run_id"),
        "week_id": run.get("week_id"),
        "week_start": run.get("week_start"),
        "week_end": run.get("week_end"),
        "status": run.get("status"),
        "mode": run.get("mode", "production"),
        "failed_stage": failed_stage,
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "artifacts": artifacts,
        "milestones": {
            "platform_collection": milestone(
                ["collect_bilibili", "collect_heybox"]
            ),
            "model_and_dashboard": milestone(
                ["prepare_release", "validate_release"]
            ),
            "weekly_report": milestone(
                ["build_report", "validate_release"]
            ),
            "protected_site_publication": milestone(
                ["publish_site", "verify_live"]
            ),
        },
        "data_boundary": {
            "bilibili": (
                "simulated_fixture" if simulated else "real_bounded_sample"
            ),
            "heybox": (
                "simulated_fixture"
                if simulated
                else "real_public_search_sample"
            ),
            "combined": (
                "simulated_fixture_incomparable_units"
                if simulated
                else "mixed_real_observations_incomparable_units"
            ),
            "formal_reporting_qualified": False,
        },
    }


def run_stage(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    log_dir: Path,
    run: dict,
) -> None:
    started = datetime.now(TIMEZONE)
    log_path = log_dir / f"{name}.log"
    stage = {
        "name": name,
        "status": "running",
        "started_at": started.isoformat(),
        "command": command,
        "log": str(log_path),
    }
    run["stages"].append(stage)
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    stage["finished_at"] = datetime.now(TIMEZONE).isoformat()
    stage["duration_seconds"] = round(
        (datetime.now(TIMEZONE) - started).total_seconds(),
        3,
    )
    stage["exit_code"] = completed.returncode
    stage["status"] = "success" if completed.returncode == 0 else "failed"
    if completed.returncode:
        raise RuntimeError(f"stage {name} failed with exit code {completed.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument(
        "--public-status",
        type=Path,
        default=DEFAULT_PUBLIC_STATUS,
    )
    parser.add_argument(
        "--release-root",
        type=Path,
        help="Isolated release workspace; defaults to ROOT/release",
    )
    parser.add_argument(
        "--site-root",
        type=Path,
        default=DEFAULT_SITE_ROOT,
    )
    parser.add_argument(
        "--mode",
        choices=("production", "simulate", "revision"),
        default="production",
    )
    parser.add_argument(
        "--bilibili-source",
        type=Path,
        help="Immutable existing Bilibili collection input for --mode revision",
    )
    parser.add_argument(
        "--heybox-source",
        type=Path,
        help="Immutable existing Heybox collection input for --mode revision",
    )
    parser.add_argument("--base-url", default=os.environ.get("APEX_BASE_URL"))
    parser.add_argument(
        "--editorial-package",
        type=Path,
        default=(
            Path(os.environ["APEX_EDITORIAL_PACKAGE"])
            if os.environ.get("APEX_EDITORIAL_PACKAGE")
            else None
        ),
        help="Skill-reviewed narrative package; required for production",
    )
    parser.add_argument("--now", help="Test-only ISO timestamp")
    args = parser.parse_args()

    root = args.root.resolve()
    sys.path.insert(0, str(root / "scripts"))
    from project_paths import configured_root

    data_root = configured_root(root, "data_root")
    historical_output_root = configured_root(root, "historical_output_root")
    policy_path = root / "config/weekly_production_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    state_dir = args.state_dir.resolve()
    release_root = (
        args.release_root.resolve()
        if args.release_root
        else (root / "release").resolve()
    )
    site_root = args.site_root.resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_handle = (state_dir / "pipeline.lock").open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another weekly pipeline run is active", file=sys.stderr)
        return 75

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(TIMEZONE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TIMEZONE)
    week = previous_complete_week(now)
    run_id = f"{week.week_id}_{now.astimezone(TIMEZONE):%Y%m%dT%H%M%S}"
    run_dir = state_dir / "runs" / run_id
    log_dir = run_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=False)
    latest_path = state_dir / "latest.json"
    run_path = run_dir / "status.json"

    run = {
        "schema_version": 1,
        "run_id": run_id,
        "week_id": week.week_id,
        "week_start": week.start,
        "week_end": week.end,
        "timezone": "Asia/Shanghai",
        "deadline": f"{now.date().isoformat()}T08:45:00+08:00",
        "mode": args.mode,
        "status": "running",
        "started_at": datetime.now(TIMEZONE).isoformat(),
        "stages": [],
        "artifacts": {},
        "production_policy_version": policy["policy_version"],
        "weekly_report_skill": policy["weekly_report"]["skill_name"],
        "weekly_report_skill_version": policy["weekly_report"]["skill_version"],
        "narrative_rule_version": policy["weekly_report"]["narrative_rule_version"],
    }
    atomic_json(run_path, run)
    atomic_json(latest_path, run)

    env = dict(os.environ)
    env["APEX_TARGET_WEEK"] = week.week_id
    env["APEX_WEEK_START"] = week.start
    env["APEX_WEEK_END"] = week.end
    python_collect = Path(
        os.environ.get("APEX_COLLECTION_PYTHON", sys.executable)
    ).expanduser()
    python_analysis = Path(
        os.environ.get("APEX_ANALYSIS_PYTHON", sys.executable)
    ).expanduser()
    if not python_collect.is_absolute():
        python_collect = root / python_collect
    if not python_analysis.is_absolute():
        python_analysis = root / python_analysis
    ingest_dir = run_dir / "ingest"
    ingest_dir.mkdir()
    bilibili_ingest = ingest_dir / f"bilibili_apex_{week.week_id}.json"
    heybox_ingest = (
        ingest_dir / f"heybox_apex_{week.week_id}_public_search.json"
    )
    allow_simulated: list[str] = (
        ["--allow-simulated"] if args.mode == "simulate" else []
    )
    if args.mode == "simulate":
        collector = root / "scripts/simulate_weekly_collection.py"
        collection_stages = [
            (
                "collect_bilibili",
                [
                    sys.executable,
                    str(collector),
                    "--platform",
                    "B站",
                    "--week",
                    week.week_id,
                    "--output",
                    str(bilibili_ingest),
                ],
            ),
            (
                "collect_heybox",
                [
                    sys.executable,
                    str(collector),
                    "--platform",
                    "小黑盒",
                    "--week",
                    week.week_id,
                    "--output",
                    str(heybox_ingest),
                ],
            ),
        ]
        analysis_python = Path(sys.executable)
    elif args.mode == "revision":
        if not args.bilibili_source or not args.heybox_source:
            parser.error(
                "--mode revision requires --bilibili-source and --heybox-source"
            )
        collector_wrapper = root / "scripts/run_platform_collector.py"
        collection_stages = [
            (
                "collect_bilibili",
                [
                    str(python_analysis),
                    str(collector_wrapper),
                    "--target",
                    str(bilibili_ingest),
                    "--platform",
                    "B站",
                    "--week",
                    week.week_id,
                    "--week-start",
                    week.start,
                    "--week-end",
                    week.end,
                    "--source-existing",
                    str(args.bilibili_source.resolve()),
                ],
            ),
            (
                "collect_heybox",
                [
                    str(python_analysis),
                    str(collector_wrapper),
                    "--target",
                    str(heybox_ingest),
                    "--platform",
                    "小黑盒",
                    "--week",
                    week.week_id,
                    "--week-start",
                    week.start,
                    "--week-end",
                    week.end,
                    "--source-existing",
                    str(args.heybox_source.resolve()),
                ],
            ),
        ]
        analysis_python = python_analysis
    else:
        env["APEX_BILIBILI_OUTPUT"] = str(bilibili_ingest)
        env["APEX_HEYBOX_OUTPUT"] = str(heybox_ingest)
        collector_wrapper = root / "scripts/run_platform_collector.py"
        collection_stages = [
            (
                "collect_bilibili",
                [
                    str(python_analysis),
                    str(collector_wrapper),
                    "--target",
                    str(bilibili_ingest),
                    "--fallback",
                    str(historical_output_root / f"bilibili_apex_{week.week_id}.json"),
                    "--fallback-glob",
                    str(
                        data_root
                        / f"raw/bilibili/bilibili_apex_{week.week_id}*.csv"
                    ),
                    "--platform",
                    "B站",
                    "--week",
                    week.week_id,
                    "--week-start",
                    week.start,
                    "--week-end",
                    week.end,
                    "--",
                    str(python_collect),
                    str(root / "crawler/bilibili_apex_collector.py"),
                    "--week",
                    week.week_id,
                ],
            ),
            (
                "collect_heybox",
                [
                    str(python_analysis),
                    str(collector_wrapper),
                    "--target",
                    str(heybox_ingest),
                    "--fallback",
                    str(
                        historical_output_root
                        / (
                            "outputs/heybox_apex_"
                            f"{week.week_id}_public_search.json"
                        )
                    ),
                    "--fallback-glob",
                    str(
                        historical_output_root
                        / (
                            "outputs/heybox_public_search_"
                            f"{week.week_id}_*.csv"
                        )
                    ),
                    "--platform",
                    "小黑盒",
                    "--week",
                    week.week_id,
                    "--week-start",
                    week.start,
                    "--week-end",
                    week.end,
                    "--",
                    str(python_collect),
                    str(root / "crawler/heybox_public_search_collector.py"),
                ],
            ),
        ]
        analysis_python = python_analysis

    stages = collection_stages + [
        (
            "prepare_release",
            [
                str(analysis_python),
                str(root / "scripts/prepare_weekly_release.py"),
                "--week",
                week.week_id,
                "--project-root",
                str(root),
                "--release-root",
                str(release_root),
                "--bilibili",
                str(bilibili_ingest),
                "--heybox",
                str(heybox_ingest),
                *allow_simulated,
            ],
        ),
        (
            "build_report",
            [
                str(analysis_python),
                str(root / "scripts/build_weekly_report.py"),
                "--week",
                week.week_id,
                "--project-root",
                str(root),
                "--release-root",
                str(release_root),
                *(
                    ["--editorial-package", str(args.editorial_package.resolve())]
                    if args.editorial_package
                    else []
                ),
            ],
        ),
        (
            "validate_release",
            [
                str(analysis_python),
                str(root / "scripts/validate_weekly_release.py"),
                "--week",
                week.week_id,
                "--project-root",
                str(root),
                "--release-root",
                str(release_root),
            ],
        ),
        (
            "publish_site",
            [
                str(analysis_python),
                str(root / "scripts/publish_protected_site.py"),
                "--week",
                week.week_id,
                "--release-root",
                str(release_root),
                "--site-root",
                str(site_root),
                *allow_simulated,
            ],
        ),
        (
            "verify_live",
            [
                str(analysis_python),
                str(root / "scripts/verify_production_site.py"),
                "--week",
                week.week_id,
                "--release-root",
                str(release_root),
                "--site-root",
                str(site_root),
                *(
                    ["--base-url", args.base_url]
                    if args.base_url
                    else []
                ),
            ],
        ),
    ]

    try:
        for name, command in stages:
            missing = [part for part in command[:2] if part.startswith("/") and not Path(part).exists()]
            if missing:
                raise RuntimeError(f"stage {name} is not deployable; missing {missing}")
            run_stage(
                name=name,
                command=command,
                cwd=root,
                env=env,
                log_dir=log_dir,
                run=run,
            )
            atomic_json(run_path, run)
            atomic_json(latest_path, run)

        site_manifest = release_root / week.week_id / "manifest.json"
        report_path = (
            release_root
            / week.week_id
            / "reports"
            / (
                "APEX_CHINA_"
                f"{week.week_id.split('_')[-1]}_Weekly_Community_Report.xlsx"
            )
        )
        for label, path in (("site_manifest", site_manifest), ("weekly_report", report_path)):
            if not path.is_file():
                raise RuntimeError(f"final artifact missing: {path}")
            run["artifacts"][label] = {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        run["status"] = "success"
    except Exception as exc:
        run["status"] = "failed"
        run["error"] = f"{type(exc).__name__}: {exc}"
        error_payload = {
            "schema_version": 1,
            "run_id": run_id,
            "week_id": week.week_id,
            "publication_blocked": True,
            "failed_stage": next(
                (stage["name"] for stage in run["stages"] if stage.get("status") == "failed"),
                None,
            ),
            "error": run["error"],
        }
        atomic_json(run_dir / "error_report.json", error_payload)
        (run_dir / "error_report.md").write_text(
            "# APEX weekly pipeline error\n\n"
            f"- Week: {week.week_id}\n"
            "- Publication: BLOCKED\n"
            f"- Error: {run['error']}\n",
            encoding="utf-8",
        )
    finally:
        run["finished_at"] = datetime.now(TIMEZONE).isoformat()
        run["duration_seconds"] = round(
            (
                datetime.fromisoformat(run["finished_at"])
                - datetime.fromisoformat(run["started_at"])
            ).total_seconds(),
            3,
        )
        atomic_json(run_path, run)
        atomic_json(latest_path, run)
        atomic_json(args.public_status.resolve(), public_status(run))

    return 0 if run["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
