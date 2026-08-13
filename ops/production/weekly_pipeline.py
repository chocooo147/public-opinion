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
    latest_pipeline_run = {
        "run_id": run.get("run_id"),
        "week_id": run.get("week_id"),
        "status": run.get("status"),
        "mode": run.get("mode", "production"),
        "workflow_phase": run.get("workflow_phase"),
        "failed_stage": failed_stage,
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
    }
    return {
        "schema_version": 2,
        "service": "apex-weekly-report",
        "current_live_release": run.get("current_live_release"),
        "review_candidate": run.get("review_candidate"),
        "latest_pipeline_run": latest_pipeline_run,
        # Compatibility aliases retained for existing status consumers.
        "run_id": run.get("run_id"),
        "week_id": run.get("week_id"),
        "week_start": run.get("week_start"),
        "week_end": run.get("week_end"),
        "status": run.get("status"),
        "mode": run.get("mode", "production"),
        "workflow_phase": run.get("workflow_phase"),
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


def inspect_current_live_release(site_root: Path) -> dict | None:
    current = site_root / "current"
    if not current.is_symlink():
        return None
    resolved = current.resolve()
    manifest_path = resolved / "manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "status": "live",
        "target": resolved.name,
        "week_id": manifest.get("week_id"),
        "manifest_sha256": sha256(manifest_path),
        "verified": bool(manifest.get("valid")),
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
        "--workflow-phase",
        choices=("full", "prepare", "candidate", "publish"),
        help=(
            "Machine workflow phase. Production/revision default to prepare; "
            "simulation defaults to full."
        ),
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help="Immutable checkpoint required for candidate or publish",
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
    parser.add_argument(
        "--agent-runtime-receipt",
        type=Path,
        default=(
            Path(os.environ["APEX_AGENT_RUNTIME_RECEIPT"])
            if os.environ.get("APEX_AGENT_RUNTIME_RECEIPT")
            else None
        ),
    )
    parser.add_argument(
        "--platform-readiness-receipt",
        type=Path,
        default=(
            Path(os.environ["APEX_PLATFORM_READINESS_RECEIPT"])
            if os.environ.get("APEX_PLATFORM_READINESS_RECEIPT")
            else None
        ),
    )
    parser.add_argument("--revision-provenance", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--email-dry-run", action="store_true")
    parser.add_argument("--now", help="Test-only ISO timestamp")
    args = parser.parse_args()

    workflow_phase = args.workflow_phase or (
        "full" if args.mode == "simulate" else "prepare"
    )
    if (
        args.mode == "simulate"
        and workflow_phase != "full"
        and not args.email_dry_run
    ):
        parser.error(
            "checkpointed simulation phases require --email-dry-run rehearsal mode"
        )
    if args.mode != "simulate" and workflow_phase == "full":
        parser.error(
            "production/revision cannot run as a single shot; use prepare, "
            "candidate, then publish checkpoints"
        )
    if workflow_phase in {"candidate", "publish"} and not args.checkpoint:
        parser.error(f"--workflow-phase {workflow_phase} requires --checkpoint")
    if workflow_phase == "candidate" and not args.editorial_package:
        parser.error("--workflow-phase candidate requires --editorial-package")
    if workflow_phase in {"candidate", "publish"} and not args.agent_runtime_receipt:
        parser.error(
            f"--workflow-phase {workflow_phase} requires --agent-runtime-receipt"
        )
    if workflow_phase == "publish" and not args.approval:
        parser.error("--workflow-phase publish requires --approval")

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
    prior_live = inspect_current_live_release(site_root)
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
    if args.checkpoint:
        checkpoint_payload = json.loads(
            args.checkpoint.resolve().read_text(encoding="utf-8")
        )
        week = Week(
            str(checkpoint_payload["week_id"]),
            str(checkpoint_payload["week_start"]),
            str(checkpoint_payload["week_end"]),
        )
    else:
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
        "workflow_phase": workflow_phase,
        "status": "running",
        "started_at": datetime.now(TIMEZONE).isoformat(),
        "stages": [],
        "artifacts": {},
        "production_policy_version": policy["policy_version"],
        "weekly_report_skill": policy["weekly_report"]["skill_name"],
        "weekly_report_skill_version": policy["weekly_report"]["skill_version"],
        "narrative_rule_version": policy["weekly_report"]["narrative_rule_version"],
        "current_live_release": prior_live,
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
    needs_collection = workflow_phase in {"full", "prepare"}
    if not needs_collection:
        collection_stages = []
        analysis_python = python_analysis
    elif args.mode == "simulate":
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

    release_dir = release_root / week.week_id
    checkpoint_tool = root / "scripts/workflow_checkpoint.py"
    analyst_checkpoint = run_dir / "analyst_synthesis_checkpoint.json"
    human_checkpoint = run_dir / "human_approval_checkpoint.json"
    release_authorization = run_dir / "release_authorization.json"
    candidate_receipt = release_dir / "candidate_deploy_receipt.json"

    governance_preflight: list[tuple[str, list[str]]] = []
    if args.mode != "simulate":
        preflight_command = [
            str(analysis_python),
            str(root / "scripts/production_preflight.py"),
            "--root",
            str(root),
            "--week",
            week.week_id,
            "--mode",
            args.mode,
            "--stage",
            workflow_phase,
            "--output",
            str(run_dir / "production_preflight.json"),
        ]
        for option, path in (
            ("--editorial-package", args.editorial_package),
            ("--agent-runtime-receipt", args.agent_runtime_receipt),
            ("--platform-readiness-receipt", args.platform_readiness_receipt),
            ("--revision-provenance", args.revision_provenance),
            ("--approval", args.approval),
        ):
            if path:
                preflight_command.extend([option, str(path.resolve())])
        governance_preflight.append(("production_preflight", preflight_command))

    prepare_governance_args: list[str] = []
    if args.revision_provenance:
        prepare_governance_args.extend(
            ["--revision-provenance", str(args.revision_provenance.resolve())]
        )
    prepare_stage = (
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
            "--run-mode",
            args.mode,
            *allow_simulated,
            *prepare_governance_args,
        ],
    )
    build_stage = (
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
    )
    validate_stage = (
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
            *(["--candidate-only"] if workflow_phase == "candidate" else []),
        ],
    )
    publish_stage = (
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
            *(
                ["--release-authorization", str(release_authorization)]
                if workflow_phase == "publish"
                else []
            ),
            *(["--candidate-only"] if workflow_phase == "candidate" else []),
            *allow_simulated,
        ],
    )
    verify_live_stage = (
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
            *(["--base-url", args.base_url] if args.base_url else []),
        ],
    )
    email_script = root / "ops/production/send_weekly_email.py"
    email_dry_run = ["--dry-run"] if args.email_dry_run else []
    internal_review_email_stage = (
        "send_internal_review_email",
        [
            str(analysis_python),
            str(email_script),
            "--state",
            str(latest_path),
            "--kind",
            "internal-review",
            "--candidate-receipt",
            str(candidate_receipt),
            "--sent-dir",
            str(state_dir / "sent"),
            *email_dry_run,
        ],
    )
    verify_candidate_stage = (
        "verify_review_candidate",
        [
            str(analysis_python),
            str(root / "scripts/verify_review_candidate.py"),
            "--week",
            week.week_id,
            "--release-root",
            str(release_root),
            "--site-root",
            str(site_root),
        ],
    )
    final_delivery_email_stage = (
        "send_final_delivery_email",
        [
            str(analysis_python),
            str(email_script),
            "--state",
            str(latest_path),
            "--kind",
            "final-delivery",
            "--approval",
            str(args.approval.resolve()) if args.approval else "",
            "--live-verification",
            str(release_dir / "live_verification.json"),
            "--sent-dir",
            str(state_dir / "sent"),
            *email_dry_run,
        ],
    )

    if workflow_phase == "full":
        stages = collection_stages + [
            prepare_stage,
            build_stage,
            validate_stage,
            publish_stage,
            verify_live_stage,
        ]
    elif workflow_phase == "prepare":
        stages = governance_preflight + collection_stages + [
            prepare_stage,
            (
                "checkpoint_analyst_synthesis",
                [
                    str(analysis_python),
                    str(checkpoint_tool),
                    "create",
                    "--root",
                    str(root),
                    "--release-dir",
                    str(release_dir),
                    "--week",
                    week.week_id,
                    "--state",
                    "awaiting_analyst_synthesis",
                    "--output",
                    str(analyst_checkpoint),
                ],
            ),
        ]
    elif workflow_phase == "candidate":
        stages = [
            (
                "verify_analyst_checkpoint",
                [
                    str(analysis_python),
                    str(checkpoint_tool),
                    "verify",
                    "--root",
                    str(root),
                    "--release-dir",
                    str(release_dir),
                    "--checkpoint",
                    str(args.checkpoint.resolve()),
                    "--expected-state",
                    "awaiting_analyst_synthesis",
                    "--editorial-package",
                    str(args.editorial_package.resolve()),
                    "--expected-editorial-status",
                    "review_candidate",
                    "--output",
                    str(run_dir / "analyst_checkpoint_verification.json"),
                ],
            ),
            *governance_preflight,
            build_stage,
            validate_stage,
            publish_stage,
            verify_candidate_stage,
            internal_review_email_stage,
            (
                "checkpoint_human_approval",
                [
                    str(analysis_python),
                    str(checkpoint_tool),
                    "create",
                    "--root",
                    str(root),
                    "--release-dir",
                    str(release_dir),
                    "--week",
                    week.week_id,
                    "--state",
                    "awaiting_human_approval",
                    "--output",
                    str(human_checkpoint),
                ],
            ),
        ]
    else:
        stages = [
            *governance_preflight,
            (
                "authorize_release",
                [
                    str(analysis_python),
                    str(checkpoint_tool),
                    "authorize",
                    "--root",
                    str(root),
                    "--release-dir",
                    str(release_dir),
                    "--checkpoint",
                    str(args.checkpoint.resolve()),
                    "--agent-runtime-receipt",
                    str(args.agent_runtime_receipt.resolve()),
                    "--approval",
                    str(args.approval.resolve()),
                    "--output",
                    str(release_authorization),
                ],
            ),
            publish_stage,
            verify_live_stage,
            final_delivery_email_stage,
        ]

    try:
        for name, command in stages:
            if name == "send_internal_review_email":
                run["status"] = "awaiting_human_approval"
                run["review_candidate"] = {
                    "status": "deployed_not_live",
                    "receipt_sha256": sha256(candidate_receipt),
                }
                atomic_json(run_path, run)
                atomic_json(latest_path, run)
            elif name == "send_final_delivery_email":
                report_path = (
                    release_dir
                    / "reports"
                    / (
                        "APEX_CHINA_"
                        f"{week.week_id.split('_')[-1]}_Weekly_Community_Report.xlsx"
                    )
                )
                run["status"] = "success"
                run["artifacts"]["weekly_report"] = {
                    "path": str(report_path),
                    "bytes": report_path.stat().st_size,
                    "sha256": sha256(report_path),
                }
                run["current_live_release"] = inspect_current_live_release(site_root)
                promoted_candidate = json.loads(
                    candidate_receipt.read_text(encoding="utf-8")
                )
                run["review_candidate"] = {
                    "status": "promoted_to_live",
                    "target": promoted_candidate.get("target"),
                    "manifest_sha256": promoted_candidate.get(
                        "public_manifest_sha256"
                    ),
                }
                atomic_json(run_path, run)
                atomic_json(latest_path, run)
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

        if workflow_phase == "prepare":
            expected_artifacts = (("analyst_synthesis_checkpoint", analyst_checkpoint),)
            run["status"] = "awaiting_analyst_synthesis"
        else:
            site_manifest = release_dir / "manifest.json"
            report_path = (
                release_dir
                / "reports"
                / (
                    "APEX_CHINA_"
                    f"{week.week_id.split('_')[-1]}_Weekly_Community_Report.xlsx"
                )
            )
            expected_artifacts = (
                ("site_manifest", site_manifest),
                ("weekly_report", report_path),
            )
            if workflow_phase == "candidate":
                expected_artifacts += (
                    ("review_candidate_receipt", candidate_receipt),
                    ("human_approval_checkpoint", human_checkpoint),
                )
                run["status"] = "awaiting_human_approval"
            else:
                run["status"] = "success"
        for label, path in expected_artifacts:
            if not path.is_file():
                raise RuntimeError(f"workflow artifact missing: {path}")
            run["artifacts"][label] = {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        run["current_live_release"] = inspect_current_live_release(site_root)
    except Exception as exc:
        run["status"] = "failed"
        run["error"] = f"{type(exc).__name__}: {exc}"
        failed_stage = next(
            (stage["name"] for stage in run["stages"] if stage.get("status") == "failed"),
            None,
        )
        if failed_stage == "verify_live":
            rollback_command = [
                str(analysis_python),
                str(root / "scripts/rollback_protected_site.py"),
                "--week",
                week.week_id,
                "--release-root",
                str(release_root),
                "--site-root",
                str(site_root),
            ]
            rollback = subprocess.run(
                rollback_command,
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            run["rollback"] = {
                "required": True,
                "status": "success" if rollback.returncode == 0 else "failed",
                "exit_code": rollback.returncode,
                "command": rollback_command,
            }
            if rollback.returncode:
                run["error"] += "; canonical rollback failed; manual Sol intervention required"
        error_payload = {
            "schema_version": 1,
            "run_id": run_id,
            "week_id": week.week_id,
            "publication_blocked": True,
            "failed_stage": failed_stage,
            "rollback": run.get("rollback"),
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
        run["current_live_release"] = inspect_current_live_release(site_root) or prior_live
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

    return 0 if run["status"] in {
        "success",
        "awaiting_analyst_synthesis",
        "awaiting_human_approval",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
