#!/usr/bin/env python3
"""Create and verify immutable weekly workflow checkpoints.

The checkpoint is private orchestration state. It lets the machine pipeline stop
before human approval and later continue without recollecting or rebuilding the
prepared Data Topic package. It does not create human or Agent approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from weekly_release_common import atomic_json, load_production_policy, sha256


CHECKPOINT_STATES = {
    "awaiting_analyst_synthesis",
    "awaiting_human_approval",
}
POST_AUTHORIZATION_FILES = {
    "publish_receipt.json",
    "live_verification.json",
    "rollback_receipt.json",
}
POST_PREPARE_FILES = POST_AUTHORIZATION_FILES | {
    "candidate_deploy_receipt.json",
    "candidate_verification.json",
    "manifest.json",
    "report_build.json",
    "validation.json",
}


def _git_revision(root: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=root, check=True, text=True, capture_output=True
        ).stdout.strip()

    status = git("status", "--porcelain=v1")
    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "clean": not bool(status),
        "dirty_entry_count": len(status.splitlines()) if status else 0,
    }


def release_inventory(
    release_dir: Path, *, checkpoint_state: str | None = None
) -> dict[str, dict[str, Any]]:
    def included(relative: str) -> bool:
        if relative in POST_AUTHORIZATION_FILES:
            return False
        if checkpoint_state != "awaiting_analyst_synthesis":
            return True
        return not (
            relative in POST_PREPARE_FILES
            or relative.startswith("reports/")
            or relative.startswith("candidate_deploy_receipts/")
        )

    return {
        path.relative_to(release_dir).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(release_dir.rglob("*"))
        if path.is_file() and included(path.relative_to(release_dir).as_posix())
    }


def inventory_sha256(inventory: dict[str, dict[str, Any]]) -> str:
    payload = json.dumps(
        inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def create_checkpoint(
    *,
    root: Path,
    release_dir: Path,
    week_id: str,
    state: str,
    output: Path,
) -> dict[str, Any]:
    if state not in CHECKPOINT_STATES:
        raise ValueError(f"unsupported checkpoint state: {state}")
    context = _load(release_dir / "release_context.json", "release context")
    if context.get("week_id") != week_id:
        raise ValueError("release context week differs from checkpoint week")
    inventory = release_inventory(release_dir, checkpoint_state=state)
    payload = {
        "schema_version": 1,
        "week_id": week_id,
        "week_start": context.get("week_start"),
        "week_end": context.get("week_end"),
        "state": state,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "release_dir": str(release_dir.resolve()),
        "source_revision": context.get("source_revision"),
        "production_policy": context.get("production_policy"),
        "canonical_business_rules": context.get("canonical_business_rules"),
        "release_inventory": inventory,
        "release_inventory_sha256": inventory_sha256(inventory),
    }
    atomic_json(output, payload)
    return payload


def verify_checkpoint(
    *,
    root: Path,
    release_dir: Path,
    checkpoint: Path,
    expected_state: str,
    editorial_package: Path | None = None,
    expected_editorial_status: str | None = None,
) -> dict[str, Any]:
    payload = _load(checkpoint, "workflow checkpoint")
    errors: list[str] = []
    if payload.get("state") != expected_state:
        errors.append(
            f"checkpoint state {payload.get('state')} != {expected_state}"
        )
    if Path(str(payload.get("release_dir") or "")).resolve() != release_dir.resolve():
        errors.append("checkpoint release directory differs from requested release")
    current_inventory = release_inventory(
        release_dir, checkpoint_state=str(payload.get("state") or "")
    )
    current_inventory_hash = inventory_sha256(current_inventory)
    if current_inventory != payload.get("release_inventory"):
        errors.append("release files changed after checkpoint creation")
    if current_inventory_hash != payload.get("release_inventory_sha256"):
        errors.append("release inventory hash differs from checkpoint")
    try:
        current_revision = _git_revision(root)
    except (OSError, subprocess.CalledProcessError) as exc:
        current_revision = {"error": str(exc), "clean": False, "commit": None}
        errors.append(f"cannot resolve current production revision: {exc}")
    expected_revision = payload.get("source_revision") or {}
    if current_revision.get("commit") != expected_revision.get("commit"):
        errors.append("current production revision differs from prepared checkpoint")
    if not current_revision.get("clean"):
        errors.append("current production source is not clean")

    editorial: dict[str, Any] | None = None
    if editorial_package is not None:
        editorial = _load(editorial_package, "editorial package")
        if editorial.get("week_id") != payload.get("week_id"):
            errors.append("editorial package week differs from checkpoint")
        if expected_editorial_status and editorial.get("review_status") != expected_editorial_status:
            errors.append(
                "editorial package review status differs from checkpoint stage"
            )
        if expected_editorial_status == "review_candidate" and editorial.get("approval"):
            errors.append("review candidate must not contain human approval")

    return {
        "schema_version": 1,
        "valid": not errors,
        "week_id": payload.get("week_id"),
        "checkpoint_state": payload.get("state"),
        "checkpoint_sha256": sha256(checkpoint),
        "release_inventory_sha256": current_inventory_hash,
        "source_revision": current_revision,
        "editorial_package_sha256": (
            sha256(editorial_package) if editorial_package is not None else None
        ),
        "errors": errors,
    }


def _validate_final_agent_receipt(
    receipt: dict[str, Any], policy: dict[str, Any], week_id: str
) -> list[str]:
    errors: list[str] = []
    if receipt.get("week_id") != week_id:
        errors.append("Agent Runtime Receipt week differs from checkpoint")
    formal_agents = receipt.get("formal_agents") or {}
    for role in ("collector", "analyst", "validator"):
        expected = policy["formal_agents"][role]
        actual = formal_agents.get(role) or {}
        for key in ("agent", "model_family", "reasoning_effort"):
            if str(actual.get(key) or "").casefold() != str(expected[key]).casefold():
                errors.append(f"Agent Runtime Receipt {role}.{key} is incorrect")
        if actual.get("status") != "completed":
            errors.append(f"Agent Runtime Receipt {role} is not completed")
        if not actual.get("runtime_evidence"):
            errors.append(f"Agent Runtime Receipt {role} lacks runtime evidence")
    final_review = receipt.get("sol_final_review") or {}
    if final_review.get("status") != "approved_for_release":
        errors.append("Sol final review is not approved_for_release")
    if not final_review.get("runtime_evidence"):
        errors.append("Sol final review lacks runtime evidence")
    return errors


def authorize_release(
    *,
    root: Path,
    release_dir: Path,
    checkpoint: Path,
    agent_runtime_receipt: Path,
    approval: Path,
    output: Path,
) -> dict[str, Any]:
    verification = verify_checkpoint(
        root=root,
        release_dir=release_dir,
        checkpoint=checkpoint,
        expected_state="awaiting_human_approval",
    )
    policy = load_production_policy(root)
    receipt = _load(agent_runtime_receipt, "Agent Runtime Receipt")
    approval_payload = _load(approval, "human approval")
    context = _load(release_dir / "release_context.json", "release context")
    errors = list(verification["errors"])
    errors.extend(
        _validate_final_agent_receipt(receipt, policy, str(verification["week_id"]))
    )
    if not context.get("simulation_only") and (
        receipt.get("simulation_only") or approval_payload.get("simulation_only")
    ):
        errors.append("simulation receipt or approval cannot authorize production")
    if approval_payload.get("week_id") != verification["week_id"]:
        errors.append("human approval week differs from checkpoint")
    if approval_payload.get("status") != "approved_for_release":
        errors.append("human approval status is not approved_for_release")
    required_approval = {
        "approved_at",
        "approver_role",
        "approval_source",
        "approval_statement",
        "scope",
        "candidate_manifest_sha256",
    }
    missing_approval = sorted(
        key for key in required_approval if not approval_payload.get(key)
    )
    if missing_approval:
        errors.append(f"human approval is missing fields: {missing_approval}")
    candidate_receipt_path = release_dir / "candidate_deploy_receipt.json"
    if not candidate_receipt_path.is_file():
        errors.append("review candidate deployment receipt is missing")
    else:
        candidate_receipt = _load(
            candidate_receipt_path, "review candidate deployment receipt"
        )
        if (
            approval_payload.get("candidate_manifest_sha256")
            != candidate_receipt.get("public_manifest_sha256")
        ):
            errors.append("human approval does not identify the deployed candidate")
    authorization = {
        "schema_version": 1,
        "valid": not errors,
        "week_id": verification["week_id"],
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint_sha256": verification["checkpoint_sha256"],
        "release_inventory_sha256": verification["release_inventory_sha256"],
        "source_revision": verification["source_revision"],
        "agent_runtime_receipt_sha256": sha256(agent_runtime_receipt),
        "human_approval_sha256": sha256(approval),
        "candidate_manifest_sha256": approval_payload.get(
            "candidate_manifest_sha256"
        ),
        "formal_agent_roles": {
            role: {
                key: (receipt.get("formal_agents") or {}).get(role, {}).get(key)
                for key in ("agent", "model_family", "reasoning_effort", "status")
            }
            for role in ("collector", "analyst", "validator")
        },
        "sol_final_review_status": (
            receipt.get("sol_final_review") or {}
        ).get("status"),
        "errors": errors,
    }
    atomic_json(output, authorization)
    return authorization


def verify_release_authorization(
    authorization_path: Path, release_dir: Path, week_id: str
) -> list[str]:
    authorization = _load(authorization_path, "release authorization")
    errors: list[str] = []
    if authorization.get("valid") is not True:
        errors.append("release authorization is not valid")
    if authorization.get("week_id") != week_id:
        errors.append("release authorization week differs from target")
    current = inventory_sha256(release_inventory(release_dir))
    if authorization.get("release_inventory_sha256") != current:
        errors.append("release changed after final Agent/Sol authorization")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--release-dir", type=Path, required=True)
    create.add_argument("--week", required=True)
    create.add_argument("--state", choices=sorted(CHECKPOINT_STATES), required=True)
    create.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--release-dir", type=Path, required=True)
    verify.add_argument("--checkpoint", type=Path, required=True)
    verify.add_argument("--expected-state", choices=sorted(CHECKPOINT_STATES), required=True)
    verify.add_argument("--editorial-package", type=Path)
    verify.add_argument("--expected-editorial-status")
    verify.add_argument("--output", type=Path, required=True)

    authorize = subparsers.add_parser("authorize")
    authorize.add_argument("--root", type=Path, required=True)
    authorize.add_argument("--release-dir", type=Path, required=True)
    authorize.add_argument("--checkpoint", type=Path, required=True)
    authorize.add_argument("--agent-runtime-receipt", type=Path, required=True)
    authorize.add_argument("--approval", type=Path, required=True)
    authorize.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    root = args.root.resolve()
    release_dir = args.release_dir.resolve()
    if args.command == "create":
        result = create_checkpoint(
            root=root,
            release_dir=release_dir,
            week_id=args.week,
            state=args.state,
            output=args.output.resolve(),
        )
        valid = True
    elif args.command == "verify":
        result = verify_checkpoint(
            root=root,
            release_dir=release_dir,
            checkpoint=args.checkpoint.resolve(),
            expected_state=args.expected_state,
            editorial_package=(
                args.editorial_package.resolve() if args.editorial_package else None
            ),
            expected_editorial_status=args.expected_editorial_status,
        )
        atomic_json(args.output.resolve(), result)
        valid = bool(result["valid"])
    else:
        result = authorize_release(
            root=root,
            release_dir=release_dir,
            checkpoint=args.checkpoint.resolve(),
            agent_runtime_receipt=args.agent_runtime_receipt.resolve(),
            approval=args.approval.resolve(),
            output=args.output.resolve(),
        )
        valid = bool(result["valid"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
