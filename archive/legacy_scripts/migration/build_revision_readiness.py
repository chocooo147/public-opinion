#!/usr/bin/env python3
"""Build non-publishable revision lineage and readiness evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from project_paths import resolve_project_asset
from weekly_release_common import atomic_json, load_production_policy, sha256


def fingerprint(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--raw-revision-manifest", type=Path, required=True)
    parser.add_argument("--previous-report", type=Path)
    parser.add_argument("--previous-platform-json", type=Path)
    parser.add_argument("--previous-dashboard", type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    release_dir = args.release_root.resolve() / args.week
    context = json.loads((release_dir / "release_context.json").read_text(encoding="utf-8"))
    raw_revision = json.loads(args.raw_revision_manifest.read_text(encoding="utf-8"))
    quality = json.loads((release_dir / "quality_report.json").read_text(encoding="utf-8"))
    validation = json.loads((release_dir / "validation.json").read_text(encoding="utf-8"))
    report_build = json.loads((release_dir / "report_build.json").read_text(encoding="utf-8"))
    preview_path = release_dir / "reports" / context["files"]["report_preview"]
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    policy = load_production_policy(root)
    model_gate = policy["model_gate"]
    current_paths = {
        "platform_json": release_dir / "outputs" / context["files"]["bilibili"],
        "heybox_json": release_dir / "outputs" / context["files"]["heybox"],
        "report_input": release_dir / "outputs" / context["files"]["report_input"],
        "dashboard_json": release_dir / context["files"]["dashboard"],
        "workbook": release_dir / "reports" / context["files"]["report"],
        "workbook_preview": preview_path,
        "quality_report": release_dir / "quality_report.json",
        "error_report": release_dir / "error_report.json",
    }
    approval_status = preview.get("review_status")
    approved = approval_status in policy["weekly_report"]["approved_review_statuses"]
    readiness = {
        "schema_version": 1,
        "week_id": args.week,
        "status": "blocked" if validation.get("publication_blocked") else "ready",
        "revision_reason": raw_revision["revision_reason"],
        "previous_data_version": raw_revision["previous_data_version"],
        "current_data_version": raw_revision["current_data_version"],
        "raw_lineage": raw_revision["lineage"],
        "supersession": {
            "previous_report": fingerprint(args.previous_report.resolve()) if args.previous_report else None,
            "previous_platform_json": fingerprint(args.previous_platform_json.resolve()) if args.previous_platform_json else None,
            "previous_dashboard": fingerprint(args.previous_dashboard.resolve()) if args.previous_dashboard else None,
            "previous_status": "superseded_retained_for_audit",
            "current_status": "revision_preview_not_published",
        },
        "current_artifacts": {name: fingerprint(path) for name, path in current_paths.items()},
        "models_and_rules": {
            "bertopic_model": fingerprint(resolve_project_asset(root, model_gate["bertopic_model_path"])),
            "bertopic_manifest": fingerprint(resolve_project_asset(root, model_gate["bertopic_manifest_path"])),
            "topic_registry": fingerprint(resolve_project_asset(root, model_gate["topic_registry_path"])),
            "topic_mapping": fingerprint(resolve_project_asset(root, model_gate["topic_mapping_path"])),
            "domain_sentiment_model": fingerprint(resolve_project_asset(root, model_gate["domain_sentiment_model_path"])),
            "domain_sentiment_manifest": fingerprint(resolve_project_asset(root, model_gate["domain_sentiment_manifest_path"])),
            "report_rules": context["report_rules"],
        },
        "gates": {
            "data_quality": quality["status"],
            "sample_gate_passed": context["publication_gate_passed"],
            "editorial_review_status": approval_status,
            "human_approval_completed": approved,
            "narrative_validation": report_build["narrative_validation"],
            "workbook_contract_valid": report_build["contract_valid"],
            "release_validation": validation,
        },
        "actions": {
            "formal_manifest_generated": (release_dir / "manifest.json").is_file(),
            "formal_publish_executed": (release_dir / "publish_receipt.json").is_file(),
            "email_sent": False,
        },
        "manifest_generation_allowed": bool(
            quality["status"] == "passed"
            and context["publication_gate_passed"]
            and approved
            and validation.get("valid")
        ),
    }
    atomic_json(release_dir / "revision_readiness.json", readiness)
    print(json.dumps({"week_id": args.week, "status": readiness["status"], "manifest_generation_allowed": readiness["manifest_generation_allowed"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
