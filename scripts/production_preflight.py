#!/usr/bin/env python3
"""Fail-closed preflight for an APEX production or revision run."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from canonical_rules import load_canonical_rules
from weekly_release_common import (
    atomic_json,
    load_production_policy,
    sha256,
    verify_policy_asset_hashes,
)


def _read_json(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"{label} is missing: {path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is unreadable: {exc}")
        return None


def _git_source(root: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

    status = git("status", "--porcelain=v1")
    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "clean": not bool(status),
        "dirty_entry_count": len(status.splitlines()) if status else 0,
    }


def _validate_agent_receipt(
    receipt: dict[str, Any] | None,
    policy: dict[str, Any],
    week: str,
    errors: list[str],
    *,
    required_roles: tuple[str, ...],
    allowed_sol_statuses: set[str],
) -> None:
    if receipt is None:
        return
    if receipt.get("week_id") != week:
        errors.append("Agent Runtime Receipt week does not match the target week")
    stages = receipt.get("formal_agents") or {}
    for role in required_roles:
        expected = policy["formal_agents"][role]
        actual = stages.get(role) or {}
        for key in ("agent", "model_family", "reasoning_effort"):
            if str(actual.get(key) or "").casefold() != str(expected[key]).casefold():
                errors.append(f"Agent Runtime Receipt {role}.{key} is incorrect")
        if actual.get("status") != "completed":
            errors.append(f"Agent Runtime Receipt {role} is not completed")
        if not actual.get("runtime_evidence"):
            errors.append(f"Agent Runtime Receipt {role} lacks runtime evidence")
    final_review = receipt.get("sol_final_review") or {}
    if final_review.get("status") not in allowed_sol_statuses:
        errors.append("Agent Runtime Receipt lacks Sol authorization")


def _validate_platform_readiness(
    receipt: dict[str, Any] | None,
    week: str,
    errors: list[str],
) -> None:
    if receipt is None:
        return
    if receipt.get("week_id") != week:
        errors.append("platform readiness receipt week does not match target")
    for platform in ("bilibili", "heybox"):
        item = receipt.get(platform) or {}
        if item.get("login_status") != "verified_authenticated":
            errors.append(f"{platform} login status is not verified_authenticated")
        if not item.get("checked_at") or not item.get("evidence"):
            errors.append(f"{platform} readiness receipt lacks timestamp/evidence")


def _validate_revision_provenance(
    payload: dict[str, Any] | None,
    week: str,
    errors: list[str],
) -> None:
    if payload is None:
        return
    if payload.get("week_id") != week:
        errors.append("revision provenance week does not match target")
    for key in ("intervention_reason", "replaced_automatic_stages", "rerun_stages"):
        if not payload.get(key):
            errors.append(f"revision provenance is missing {key}")
    reused = payload.get("reused_artifacts")
    if not isinstance(reused, list):
        errors.append("revision provenance reused_artifacts must be a list")
        return
    for index, item in enumerate(reused):
        if not item.get("sha256") or not item.get("source_stage"):
            errors.append(f"revision reused_artifacts[{index}] lacks hash/stage")


def _validate_human_approval(
    payload: dict[str, Any] | None,
    week: str,
    errors: list[str],
) -> None:
    if payload is None:
        return
    if payload.get("week_id") != week:
        errors.append("human approval week does not match target")
    if payload.get("status") != "approved_for_release":
        errors.append("human approval status is not approved_for_release")
    required = {
        "approved_at",
        "approver_role",
        "approval_source",
        "approval_statement",
        "scope",
        "candidate_manifest_sha256",
    }
    missing = sorted(key for key in required if not payload.get(key))
    if missing:
        errors.append(f"human approval is missing fields: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--week", required=True)
    parser.add_argument("--mode", choices=("production", "revision"), required=True)
    parser.add_argument(
        "--stage",
        choices=("prepare", "candidate", "publish"),
        default="prepare",
    )
    parser.add_argument("--editorial-package", type=Path)
    parser.add_argument("--agent-runtime-receipt", type=Path)
    parser.add_argument("--platform-readiness-receipt", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--revision-provenance", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    policy = load_production_policy(root)
    rules = load_canonical_rules(root)
    errors: list[str] = []
    try:
        source = _git_source(root)
    except (OSError, subprocess.CalledProcessError) as exc:
        source = {
            "commit": None,
            "branch": None,
            "clean": False,
            "dirty_entry_count": None,
            "error": str(exc),
        }
    if policy["release_provenance"].get("clean_git_revision_required") and not source["clean"]:
        errors.append(
            "production source is not a clean Git revision; preserve the dirty "
            "work and archive/commit it through an authorized Git workflow"
        )
    try:
        assets = verify_policy_asset_hashes(root, policy)
    except (FileNotFoundError, ValueError) as exc:
        assets = {}
        errors.append(str(exc))
    if rules["heat"]["status"] != "approved":
        errors.append(
            "BLOCKED — BUSINESS APPROVAL REQUIRED: Heat has competing rules and "
            "no approved canonical formula/inputs/weights"
        )
    omission_rule = rules["weekly_report_drivers"]["high_impact_topic_omission_rule"]
    if omission_rule.get("machine_numeric_threshold") is not None:
        errors.append("high-impact omission governance contains an unapproved numeric threshold")
    if omission_rule.get("machine_hard_gate") is not False:
        errors.append("high-impact omission governance incorrectly enables a machine hard gate")

    editorial = (
        _read_json(args.editorial_package.resolve(), "editorial package", errors)
        if args.editorial_package
        else None
    )
    if args.stage == "candidate" and editorial is None:
        errors.append(
            "candidate requires the current-week Analyst editorial package"
        )
    elif editorial is not None:
        if editorial.get("week_id") != args.week:
            errors.append("editorial package week does not match target")
        allowed = (
            policy["weekly_report"]["candidate_review_statuses"]
            if args.stage == "candidate"
            else policy["weekly_report"]["approved_review_statuses"]
        )
        if editorial.get("review_status") not in allowed:
            errors.append(f"editorial package has invalid {args.stage} review status")
        if args.stage == "candidate" and editorial.get("approval"):
            errors.append("review candidate must not contain human approval")

    approval = (
        _read_json(args.approval.resolve(), "human approval", errors)
        if args.approval
        else None
    )
    if args.stage == "publish" and approval is None:
        errors.append("publish requires structured human approval")
    _validate_human_approval(approval, args.week, errors)

    agent_receipt = (
        _read_json(
            args.agent_runtime_receipt.resolve(), "Agent Runtime Receipt", errors
        )
        if args.agent_runtime_receipt
        else None
    )
    required_agent_roles = {
        "prepare": (),
        "candidate": ("collector", "analyst"),
        "publish": ("collector", "analyst", "validator"),
    }[args.stage]
    allowed_sol_statuses = {
        "prepare": set(),
        "candidate": {"authorized_for_candidate_build"},
        "publish": {"approved_for_release"},
    }[args.stage]
    if required_agent_roles and agent_receipt is None:
        errors.append(
            f"{args.stage} requires an external Sol/Agent Runtime Receipt; "
            "systemd cannot fabricate Custom Agent execution"
        )
    if agent_receipt is not None:
        _validate_agent_receipt(
            agent_receipt,
            policy,
            args.week,
            errors,
            required_roles=required_agent_roles,
            allowed_sol_statuses=allowed_sol_statuses,
        )

    readiness = (
        _read_json(
            args.platform_readiness_receipt.resolve(),
            "platform readiness receipt",
            errors,
        )
        if args.platform_readiness_receipt
        else None
    )
    if args.stage == "prepare" and readiness is None:
        errors.append("current-week Bilibili/Heybox login readiness receipt is required")
    if readiness is not None:
        _validate_platform_readiness(readiness, args.week, errors)

    revision = None
    if args.mode == "revision" and args.stage == "prepare":
        revision = (
            _read_json(
                args.revision_provenance.resolve(), "revision provenance", errors
            )
            if args.revision_provenance
            else None
        )
        if revision is None:
            errors.append("manual revision provenance is required in revision mode")
        _validate_revision_provenance(revision, args.week, errors)

    result = {
        "schema_version": 1,
        "week_id": args.week,
        "mode": args.mode,
        "stage": args.stage,
        "valid": not errors,
        "publication_blocked": bool(errors),
        "source_revision": source,
        "canonical_business_rules": {
            "version": rules["policy_version"],
            "sha256": rules["_sha256"],
            "heat_status": rules["heat"]["status"],
        },
        "approved_model_assets": assets,
        "receipts": {
            "editorial_package_sha256": sha256(args.editorial_package)
            if args.editorial_package and args.editorial_package.is_file()
            else None,
            "agent_runtime_receipt_sha256": sha256(args.agent_runtime_receipt)
            if args.agent_runtime_receipt and args.agent_runtime_receipt.is_file()
            else None,
            "platform_readiness_receipt_sha256": sha256(args.platform_readiness_receipt)
            if args.platform_readiness_receipt
            and args.platform_readiness_receipt.is_file()
            else None,
            "revision_provenance_sha256": sha256(args.revision_provenance)
            if args.revision_provenance and args.revision_provenance.is_file()
            else None,
            "human_approval_sha256": sha256(args.approval)
            if args.approval and args.approval.is_file()
            else None,
        },
        "errors": errors,
    }
    if args.output:
        atomic_json(args.output.resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
