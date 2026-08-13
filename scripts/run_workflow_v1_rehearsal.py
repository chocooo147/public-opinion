#!/usr/bin/env python3
"""Run the checkpointed Workflow v1.0 safely with simulation data and dry-run email."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from build_weekly_report import _simulation_editorial_package
from weekly_release_common import atomic_json, load_production_policy, sha256


def run(command: list[str], root: Path, *, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if (completed.returncode == 0) != expect_success:
        raise RuntimeError(
            f"unexpected rehearsal result ({completed.returncode}): "
            + " ".join(command)
            + "\n"
            + completed.stdout
            + completed.stderr
        )
    return completed


def latest(state: Path) -> dict:
    return json.loads((state / "latest.json").read_text(encoding="utf-8"))


def artifact_path(status: dict, key: str) -> Path:
    return Path(status["artifacts"][key]["path"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("rehearsal output must be a new directory")
    output.mkdir(parents=True)
    state = output / "state"
    release_root = output / "release"
    site = output / "site"
    status_path = output / "status" / "weekly.json"

    prior = site / "releases" / "2026_W32_prior"
    prior.mkdir(parents=True)
    atomic_json(
        prior / "manifest.json",
        {"valid": True, "week_id": "2026_W32", "artifacts": {}},
    )
    site.mkdir(exist_ok=True)
    (site / "current").symlink_to(prior, target_is_directory=True)

    pipeline = root / "ops/production/weekly_pipeline.py"
    base = [
        sys.executable,
        str(pipeline),
        "--root",
        str(root),
        "--state-dir",
        str(state),
        "--public-status",
        str(status_path),
        "--release-root",
        str(release_root),
        "--site-root",
        str(site),
        "--mode",
        "simulate",
        "--email-dry-run",
    ]
    run(base + ["--workflow-phase", "prepare", "--now", "2026-08-17T00:15:00+08:00"], root)
    prepare_status = latest(state)
    checkpoint = artifact_path(prepare_status, "analyst_synthesis_checkpoint")
    week = prepare_status["week_id"]
    release_dir = release_root / week
    report_input = json.loads(
        next((release_dir / "outputs").glob("*report_input.json")).read_text(
            encoding="utf-8"
        )
    )
    editorial = _simulation_editorial_package(
        report_input, load_production_policy(root)
    )
    editorial["review_status"] = "review_candidate"
    editorial["approval"] = None
    editorial["driver_ranking"]["ordering_method"] = (
        "skill_reviewed_editorial_judgment"
    )
    editorial["driver_ranking"]["rank_provenance"].update(
        {
            "source": "pre_workbook_skill_reviewed_editorial_package",
            "review_status": "review_candidate",
        }
    )
    editorial_path = output / "review_candidate.editorial.json"
    atomic_json(editorial_path, editorial)
    invalid_editorial = dict(editorial)
    invalid_editorial["review_status"] = "unreviewed"
    invalid_path = output / "invalid.editorial.json"
    atomic_json(invalid_path, invalid_editorial)

    agents = {
        "schema_version": 1,
        "simulation_only": True,
        "week_id": week,
        "formal_agents": {
            "collector": {
                "agent": "apex_collector",
                "model_family": "terra",
                "reasoning_effort": "medium",
                "status": "completed",
                "runtime_evidence": "workflow_v1_rehearsal_simulation",
            },
            "analyst": {
                "agent": "apex_analyst",
                "model_family": "terra",
                "reasoning_effort": "high",
                "status": "completed",
                "runtime_evidence": "workflow_v1_rehearsal_simulation",
            },
            "validator": {
                "agent": "apex_validator",
                "model_family": "terra",
                "reasoning_effort": "high",
                "status": "completed",
                "runtime_evidence": "workflow_v1_rehearsal_simulation",
            },
        },
        "sol_final_review": {
            "status": "approved_for_release",
            "runtime_evidence": "workflow_v1_rehearsal_simulation",
        },
    }
    agents_path = output / "agent_runtime_receipt.simulation.json"
    atomic_json(agents_path, agents)

    candidate_args = [
        "--workflow-phase",
        "candidate",
        "--checkpoint",
        str(checkpoint),
        "--editorial-package",
        str(invalid_path),
        "--agent-runtime-receipt",
        str(agents_path),
        "--now",
        "2026-08-17T08:00:00+08:00",
    ]
    run(base + candidate_args, root, expect_success=False)
    if (site / "candidate").exists() or (site / "candidate").is_symlink():
        raise RuntimeError("invalid candidate unexpectedly deployed")

    candidate_args[candidate_args.index(str(invalid_path))] = str(editorial_path)
    candidate_args[-1] = "2026-08-17T08:01:00+08:00"
    run(base + candidate_args, root)
    candidate_status = latest(state)
    human_checkpoint = artifact_path(candidate_status, "human_approval_checkpoint")
    candidate_receipt_path = artifact_path(candidate_status, "review_candidate_receipt")
    candidate_receipt = json.loads(
        candidate_receipt_path.read_text(encoding="utf-8")
    )
    first_candidate_target = candidate_receipt["target"]
    if (site / "current").resolve() != prior.resolve():
        raise RuntimeError("Review Candidate changed the LIVE pointer")

    # Exercise the REVIEW/AUDIT path: preserve the first immutable Candidate,
    # revise only the editorial package provenance, revalidate, and deploy a
    # new Candidate without touching LIVE.
    revised_editorial = dict(editorial)
    revised_editorial["workflow_revision_note"] = (
        "Simulation-only editorial revision for Workflow v1.0 rehearsal."
    )
    revised_path = output / "review_candidate.revision.editorial.json"
    atomic_json(revised_path, revised_editorial)
    revision_args = list(candidate_args)
    revision_args[revision_args.index(str(editorial_path))] = str(revised_path)
    revision_args[-1] = "2026-08-17T08:01:30+08:00"
    run(base + revision_args, root)
    candidate_status = latest(state)
    human_checkpoint = artifact_path(candidate_status, "human_approval_checkpoint")
    candidate_receipt_path = artifact_path(
        candidate_status, "review_candidate_receipt"
    )
    candidate_receipt = json.loads(
        candidate_receipt_path.read_text(encoding="utf-8")
    )
    if (site / "current").resolve() != prior.resolve():
        raise RuntimeError("revised Review Candidate changed the LIVE pointer")
    archived_receipts = release_dir / "candidate_deploy_receipts"
    if not archived_receipts.is_dir() or not any(archived_receipts.glob("*.json")):
        raise RuntimeError("superseded Candidate receipt was not preserved")

    approval = {
        "schema_version": 1,
        "simulation_only": True,
        "week_id": week,
        "status": "approved_for_release",
        "approved_at": "2026-08-17T08:02:00+08:00",
        "approver_role": "human_rehearsal_simulation",
        "approval_source": "workflow_v1_rehearsal_simulation",
        "approval_statement": "APPROVE simulation only",
        "scope": "exact_review_candidate_public_artifact",
        "candidate_manifest_sha256": candidate_receipt[
            "public_manifest_sha256"
        ],
    }
    approval_path = output / "approval.simulation.json"
    atomic_json(approval_path, approval)
    bad_approval = dict(approval)
    bad_approval["candidate_manifest_sha256"] = "0" * 64
    bad_approval_path = output / "approval.invalid.simulation.json"
    atomic_json(bad_approval_path, bad_approval)

    publish_args = [
        "--workflow-phase",
        "publish",
        "--checkpoint",
        str(human_checkpoint),
        "--agent-runtime-receipt",
        str(agents_path),
        "--approval",
        str(bad_approval_path),
        "--now",
        "2026-08-17T08:02:00+08:00",
    ]
    run(base + publish_args, root, expect_success=False)
    if (site / "current").resolve() != prior.resolve():
        raise RuntimeError("invalid approval changed the LIVE pointer")

    publish_args[publish_args.index(str(bad_approval_path))] = str(approval_path)
    publish_args[-1] = "2026-08-17T08:03:00+08:00"
    run(base + publish_args, root)
    final_status = latest(state)
    publish_receipt = json.loads(
        (release_dir / "publish_receipt.json").read_text(encoding="utf-8")
    )
    live = json.loads(
        (release_dir / "live_verification.json").read_text(encoding="utf-8")
    )
    release_context = json.loads(
        (release_dir / "release_context.json").read_text(encoding="utf-8")
    )
    summary = {
        "schema_version": 1,
        "workflow_version": "apex-workflow-v1.0",
        "week_id": week,
        "normal_path": final_status.get("status") == "success",
        "exception_path": True,
        "revised_candidate_deployed": candidate_receipt["target"] != first_candidate_target,
        "superseded_candidate_preserved": True,
        "invalid_candidate_blocked": True,
        "invalid_approval_blocked": True,
        "candidate_not_live_before_approval": True,
        "candidate_target": candidate_receipt["target"],
        "live_target": (site / "current").resolve().name,
        "candidate_artifact_reused": publish_receipt.get(
            "candidate_artifact_reused"
        ),
        "candidate_manifest_sha256": candidate_receipt[
            "public_manifest_sha256"
        ],
        "live_manifest_sha256": publish_receipt[
            "public_manifest_sha256"
        ],
        "live_verification": live.get("hashes_verified") is True,
        "emails": "dry_run_only",
        "formal_email_sent": False,
        "source_revision": release_context.get("source_revision"),
    }
    summary["valid"] = all(
        summary[key]
        for key in (
            "normal_path",
            "exception_path",
            "revised_candidate_deployed",
            "superseded_candidate_preserved",
            "invalid_candidate_blocked",
            "invalid_approval_blocked",
            "candidate_not_live_before_approval",
            "candidate_artifact_reused",
            "live_verification",
        )
    ) and summary["candidate_manifest_sha256"] == summary["live_manifest_sha256"]
    atomic_json(output / "WORKFLOW_V1_REHEARSAL.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
