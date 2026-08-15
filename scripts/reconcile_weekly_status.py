#!/usr/bin/env python3
"""Rebuild the public weekly status without touching a release.

This command is deliberately narrower than the weekly production pipeline. It
reads the two site pointers, their public manifests, explicitly supplied
receipts/verifications, and the existing pipeline/status context. All evidence
is validated before the only permitted output, ``weekly.json``, is atomically
replaced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_SITE_ROOT = Path("/srv/apex-site")
DEFAULT_STATUS_PATH = Path("/srv/apex-status/weekly.json")
WEEK_ID_RE = re.compile(r"^\d{4}_W\d{2}$")
PUBLIC_BOUNDARY = "authenticated_whitelist_only"
MILESTONE_REQUIREMENTS = {
    "platform_collection": ["collect_bilibili", "collect_heybox"],
    "model_and_dashboard": ["prepare_release", "validate_release"],
    "weekly_report": ["build_report", "validate_release"],
    "protected_site_publication": ["publish_site", "verify_live"],
}


class ReconciliationError(RuntimeError):
    """A required status evidence check failed before the output write."""


def _fail(message: str) -> None:
    raise ReconciliationError(message)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        _fail(f"{label} is missing: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail(f"{label} cannot be read as JSON: {path}: {exc}")
    if not isinstance(payload, dict):
        _fail(f"{label} must be a JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        _fail(f"cannot hash evidence file {path}: {exc}")
    return digest.hexdigest()


def _require_string(payload: dict[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        _fail(f"{label}.{key} is missing or invalid")
    return value


def _require_week_id(payload: dict[str, Any], label: str) -> str:
    week_id = _require_string(payload, "week_id", label)
    if not WEEK_ID_RE.fullmatch(week_id):
        _fail(f"{label}.week_id is invalid: {week_id}")
    return week_id


def _pointer_target(site_root: Path, name: str) -> tuple[Path, Path]:
    if not site_root.is_dir():
        _fail(f"site root is missing: {site_root}")
    pointer = site_root / name
    if not pointer.is_symlink():
        _fail(f"{name} pointer is not a symlink: {pointer}")
    try:
        target = pointer.resolve(strict=True)
    except OSError as exc:
        _fail(f"{name} pointer target cannot be resolved: {exc}")
    if not target.is_dir():
        _fail(f"{name} pointer target is not a directory: {target}")
    releases = (site_root / "releases").resolve()
    try:
        target.relative_to(releases)
    except ValueError:
        _fail(f"{name} pointer escapes the release root: {target}")
    return pointer, target


def _read_manifest(target: Path, label: str) -> tuple[dict[str, Any], str]:
    manifest_path = target / "manifest.json"
    manifest = _read_json(manifest_path, f"{label} manifest")
    if manifest.get("schema_version") not in {1, 2}:
        _fail(f"{label} manifest schema is unsupported")
    week_id = _require_week_id(manifest, f"{label} manifest")
    if manifest.get("valid") is not True:
        _fail(f"{label} manifest is not valid")
    if manifest.get("simulation_only") is not False:
        _fail(f"{label} manifest is simulated or missing simulation_only=false")
    if manifest.get("boundary") != PUBLIC_BOUNDARY:
        _fail(f"{label} manifest has an invalid public boundary")
    manifest_hash = _sha256(manifest_path)
    expected_target = f"{week_id}_{manifest_hash[:12]}"
    if target.name != expected_target:
        _fail(
            f"{label} target name does not match its public manifest: "
            f"{target.name} != {expected_target}"
        )
    return manifest, manifest_hash


def _validate_current_evidence(
    *,
    receipt_path: Path,
    verification_path: Path,
    target: Path,
    manifest: dict[str, Any],
    manifest_hash: str,
) -> None:
    receipt = _read_json(receipt_path, "current publish receipt")
    verification = _read_json(verification_path, "current live verification")
    week_id = manifest["week_id"]
    if _require_week_id(receipt, "current publish receipt") != week_id:
        _fail("current publish receipt week differs from current manifest")
    if receipt.get("target") != target.name:
        _fail("current publish receipt target differs from current pointer")
    if receipt.get("public_manifest_sha256") != manifest_hash:
        _fail("current publish receipt hash differs from current manifest")
    if receipt.get("public_boundary") != PUBLIC_BOUNDARY:
        _fail("current publish receipt boundary is invalid")

    if _require_week_id(verification, "current live verification") != week_id:
        _fail("current live verification week differs from current manifest")
    if verification.get("current_target") != target.name:
        _fail("current live verification target differs from current pointer")
    if verification.get("hashes_verified") is not True:
        _fail("current live verification did not verify hashes")
    if verification.get("public_boundary") != PUBLIC_BOUNDARY:
        _fail("current live verification boundary is invalid")
    privacy_scan = verification.get("privacy_scan")
    if not isinstance(privacy_scan, dict) or privacy_scan.get("errors") != []:
        _fail("current live verification privacy scan is missing or failed")


def _validate_candidate_evidence(
    *,
    receipt_path: Path,
    verification_path: Path,
    target: Path,
    current_target: Path,
    manifest: dict[str, Any],
    manifest_hash: str,
) -> str:
    receipt = _read_json(receipt_path, "candidate deploy receipt")
    verification = _read_json(verification_path, "candidate verification")
    week_id = manifest["week_id"]
    if target == current_target:
        _fail("candidate pointer resolves to the current live target")
    if _require_week_id(receipt, "candidate deploy receipt") != week_id:
        _fail("candidate deploy receipt week differs from candidate manifest")
    if receipt.get("target") != target.name:
        _fail("candidate deploy receipt target differs from candidate pointer")
    if receipt.get("public_manifest_sha256") != manifest_hash:
        _fail("candidate deploy receipt hash differs from candidate manifest")
    if receipt.get("public_boundary") != PUBLIC_BOUNDARY:
        _fail("candidate deploy receipt boundary is invalid")
    if receipt.get("candidate_status") != "deployed_not_live":
        _fail("candidate deploy receipt is not deployed_not_live")

    if _require_week_id(verification, "candidate verification") != week_id:
        _fail("candidate verification week differs from candidate manifest")
    if verification.get("valid") is not True:
        _fail("candidate verification is not valid")
    if verification.get("state") != "review_candidate_not_live":
        _fail("candidate verification is not review_candidate_not_live")
    if verification.get("target") != target.name:
        _fail("candidate verification target differs from candidate pointer")
    if verification.get("public_manifest_sha256") != manifest_hash:
        _fail("candidate verification hash differs from candidate manifest")
    if verification.get("live_pointer_unchanged") is not True:
        _fail("candidate verification does not confirm unchanged live pointer")
    if verification.get("errors") != []:
        _fail("candidate verification contains errors")
    return _sha256(receipt_path)


def _validate_data_boundary(status: dict[str, Any]) -> dict[str, Any]:
    boundary = status.get("data_boundary")
    if not isinstance(boundary, dict):
        _fail("existing public status has no data_boundary evidence")
    required = ("bilibili", "heybox", "combined", "formal_reporting_qualified")
    if any(key not in boundary for key in required):
        _fail("existing public status data_boundary is incomplete")
    if any(not isinstance(boundary[key], str) for key in required[:3]):
        _fail("existing public status data_boundary labels are invalid")
    if not isinstance(boundary["formal_reporting_qualified"], bool):
        _fail("existing public status formal_reporting_qualified is invalid")
    return {key: boundary[key] for key in required}


def _sanitize_artifacts(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    artifacts = state.get("artifacts", {})
    if not isinstance(artifacts, dict):
        _fail("latest pipeline state artifacts is not an object")
    sanitized: dict[str, dict[str, Any]] = {}
    for name, item in artifacts.items():
        if not isinstance(name, str) or not isinstance(item, dict):
            _fail("latest pipeline state contains invalid artifact metadata")
        safe: dict[str, Any] = {}
        if "bytes" in item:
            if not isinstance(item["bytes"], int) or item["bytes"] < 0:
                _fail(f"latest pipeline state artifact bytes is invalid: {name}")
            safe["bytes"] = item["bytes"]
        if "sha256" in item:
            if not isinstance(item["sha256"], str) or not re.fullmatch(
                r"[0-9a-f]{64}", item["sha256"]
            ):
                _fail(f"latest pipeline state artifact hash is invalid: {name}")
            safe["sha256"] = item["sha256"]
        sanitized[name] = safe
    return sanitized


def _latest_context(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    run_id = _require_string(state, "run_id", "latest pipeline state")
    week_id = _require_week_id(state, "latest pipeline state")
    status = _require_string(state, "status", "latest pipeline state")
    mode = _require_string(state, "mode", "latest pipeline state")
    # Historical successful pipeline states predate the phase field. The
    # field is context only; its absence is compatible, while a present value
    # must still have the expected scalar type.
    workflow_phase = state.get("workflow_phase")
    if workflow_phase is not None and not isinstance(workflow_phase, str):
        _fail("latest pipeline state.workflow_phase is invalid")
    if "started_at" not in state or not isinstance(state["started_at"], str):
        _fail("latest pipeline state.started_at is missing or invalid")
    if "finished_at" not in state or (
        state["finished_at"] is not None and not isinstance(state["finished_at"], str)
    ):
        _fail("latest pipeline state.finished_at is invalid")
    stages = state.get("stages")
    if not isinstance(stages, list):
        _fail("latest pipeline state.stages is missing or invalid")
    stage_status: dict[str, str] = {}
    for stage in stages:
        if not isinstance(stage, dict):
            _fail("latest pipeline state contains an invalid stage")
        name = _require_string(stage, "name", "latest pipeline stage")
        stage_value = _require_string(stage, "status", f"latest pipeline stage {name}")
        if name in stage_status:
            _fail(f"latest pipeline state duplicates stage: {name}")
        stage_status[name] = stage_value

    failed_stage = next(
        (name for name, stage_value in stage_status.items() if stage_value == "failed"),
        None,
    )
    latest_run = {
        "run_id": run_id,
        "week_id": week_id,
        "status": status,
        "mode": mode,
        "workflow_phase": workflow_phase,
        "failed_stage": failed_stage,
        "started_at": state["started_at"],
        "finished_at": state["finished_at"],
    }

    def milestone(required: list[str]) -> dict[str, Any]:
        statuses = [stage_status.get(name, "pending") for name in required]
        if all(value == "success" for value in statuses):
            value = "success"
        elif any(item == "failed" for item in statuses):
            value = "failed"
        elif any(item == "running" for item in statuses):
            value = "running"
        else:
            value = "pending"
        return {"status": value, "required_stages": required}

    milestones = {
        name: milestone(required)
        for name, required in MILESTONE_REQUIREMENTS.items()
    }
    aliases = {
        "run_id": run_id,
        "week_id": week_id,
        "week_start": state.get("week_start"),
        "week_end": state.get("week_end"),
        "status": status,
        "mode": mode,
        "workflow_phase": workflow_phase,
        "failed_stage": failed_stage,
        "started_at": state["started_at"],
        "finished_at": state["finished_at"],
    }
    return latest_run, milestones, aliases


def _assert_input_boundaries(status_path: Path, evidence_paths: list[Path]) -> None:
    if status_path.name != "weekly.json":
        _fail(f"status output must be weekly.json: {status_path}")
    if status_path.is_symlink():
        _fail(f"status output must not be a symlink: {status_path}")
    if not status_path.is_file():
        _fail(f"existing weekly.json evidence is missing: {status_path}")
    resolved_status = status_path.resolve()
    for evidence_path in evidence_paths:
        if evidence_path.resolve() == resolved_status:
            _fail("status output was also supplied as evidence")


def build_status(
    *,
    site_root: Path,
    status_path: Path,
    current_receipt_path: Path,
    current_verification_path: Path,
    candidate_receipt_path: Path,
    candidate_verification_path: Path,
    latest_state_path: Path,
) -> dict[str, Any]:
    evidence_paths = [
        current_receipt_path,
        current_verification_path,
        candidate_receipt_path,
        candidate_verification_path,
        latest_state_path,
    ]
    _assert_input_boundaries(status_path, evidence_paths)
    existing_status = _read_json(status_path, "existing public status")
    data_boundary = _validate_data_boundary(existing_status)

    current_pointer, current_target = _pointer_target(site_root, "current")
    candidate_pointer, candidate_target = _pointer_target(site_root, "candidate")
    if current_pointer.resolve() == candidate_pointer.resolve():
        _fail("current and candidate pointers are identical")
    current_manifest, current_hash = _read_manifest(current_target, "current")
    candidate_manifest, candidate_hash = _read_manifest(candidate_target, "candidate")
    _validate_current_evidence(
        receipt_path=current_receipt_path,
        verification_path=current_verification_path,
        target=current_target,
        manifest=current_manifest,
        manifest_hash=current_hash,
    )
    candidate_receipt_hash = _validate_candidate_evidence(
        receipt_path=candidate_receipt_path,
        verification_path=candidate_verification_path,
        target=candidate_target,
        current_target=current_target,
        manifest=candidate_manifest,
        manifest_hash=candidate_hash,
    )

    latest_state = _read_json(latest_state_path, "latest pipeline state")
    latest_run, milestones, aliases = _latest_context(latest_state)
    payload: dict[str, Any] = {
        "schema_version": 2,
        "service": "apex-weekly-report",
        "current_live_release": {
            "status": "live",
            "target": current_target.name,
            "week_id": current_manifest["week_id"],
            "manifest_sha256": current_hash,
            "verified": True,
        },
        "review_candidate": {
            "status": "deployed_not_live",
            "target": candidate_target.name,
            "week_id": candidate_manifest["week_id"],
            "manifest_sha256": candidate_hash,
            "receipt_sha256": candidate_receipt_hash,
        },
        "latest_pipeline_run": latest_run,
        **aliases,
        "artifacts": _sanitize_artifacts(latest_state),
        "milestones": milestones,
        "data_boundary": data_boundary,
    }
    return payload


def _atomic_write_status(status_path: Path, payload: dict[str, Any]) -> None:
    if status_path.name != "weekly.json" or status_path.is_symlink():
        _fail(f"status output is not a regular weekly.json path: {status_path}")
    parent = status_path.parent
    if not parent.is_dir():
        _fail(f"status output directory is missing: {parent}")
    try:
        existing_mode = stat.S_IMODE(status_path.stat().st_mode)
    except OSError as exc:
        _fail(f"cannot inspect existing weekly.json: {exc}")
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=".weekly.json.", suffix=".tmp", dir=str(parent)
    )
    temp_path = Path(temp_name)
    replaced = False
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as handle:
            temp_fd = -1
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, existing_mode)
        os.replace(temp_path, status_path)
        replaced = True
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        _fail(f"atomic weekly.json update failed: {exc}")
    finally:
        if temp_fd != -1:
            try:
                os.close(temp_fd)
            except OSError:
                pass
        if not replaced:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                _fail(f"cannot clean temporary status file {temp_path}: {exc}")


def reconcile(
    *,
    site_root: Path,
    status_path: Path,
    current_receipt_path: Path,
    current_verification_path: Path,
    candidate_receipt_path: Path,
    candidate_verification_path: Path,
    latest_state_path: Path,
) -> dict[str, Any]:
    payload = build_status(
        site_root=site_root,
        status_path=status_path,
        current_receipt_path=current_receipt_path,
        current_verification_path=current_verification_path,
        candidate_receipt_path=candidate_receipt_path,
        candidate_verification_path=candidate_verification_path,
        latest_state_path=latest_state_path,
    )
    _atomic_write_status(status_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile weekly.json from validated read-only production evidence."
    )
    parser.add_argument("--site-root", type=Path, default=DEFAULT_SITE_ROOT)
    parser.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument("--current-receipt", type=Path, required=True)
    parser.add_argument("--current-verification", type=Path, required=True)
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--candidate-verification", type=Path, required=True)
    parser.add_argument("--latest-state", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = reconcile(
            site_root=args.site_root,
            status_path=args.status_path,
            current_receipt_path=args.current_receipt,
            current_verification_path=args.current_verification,
            candidate_receipt_path=args.candidate_receipt,
            candidate_verification_path=args.candidate_verification,
            latest_state_path=args.latest_state,
        )
    except ReconciliationError as exc:
        print(f"status reconciliation blocked: {exc}")
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
