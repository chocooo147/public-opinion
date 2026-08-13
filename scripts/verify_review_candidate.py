#!/usr/bin/env python3
"""Verify the deployed Review Candidate without treating it as LIVE."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weekly_release_common import atomic_json, sha256


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--site-root", type=Path, required=True)
    args = parser.parse_args()

    release_dir = args.release_root.resolve() / args.week
    receipt_path = release_dir / "candidate_deploy_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    candidate = args.site_root.resolve() / "candidate"
    current = args.site_root.resolve() / "current"
    errors: list[str] = []
    if not candidate.is_symlink():
        errors.append("review candidate pointer is not an atomic symlink")
    target = candidate.resolve() if candidate.is_symlink() else candidate
    if target.name != receipt.get("target"):
        errors.append("candidate pointer differs from deployment receipt")
    if current.is_symlink() and current.resolve() == target:
        errors.append("review candidate was incorrectly marked LIVE")
    manifest_path = target / "manifest.json"
    if not manifest_path.is_file():
        errors.append("candidate public manifest is missing")
        manifest: dict = {}
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if receipt.get("public_manifest_sha256") != sha256(manifest_path):
            errors.append("candidate public manifest hash mismatch")
        if manifest.get("week_id") != args.week or manifest.get("valid") is not True:
            errors.append("candidate public manifest is invalid")
        for relative, expected in (manifest.get("artifacts") or {}).items():
            path = target / relative
            if not path.is_file() or sha256(path) != expected.get("sha256"):
                errors.append(f"candidate artifact hash mismatch: {relative}")

    result = {
        "schema_version": 1,
        "week_id": args.week,
        "valid": not errors,
        "state": "review_candidate_not_live",
        "target": target.name,
        "public_manifest_sha256": receipt.get("public_manifest_sha256"),
        "artifact_count": len(manifest.get("artifacts") or {}),
        "live_pointer_unchanged": not (
            current.is_symlink() and current.resolve() == target
        ),
        "errors": errors,
    }
    atomic_json(release_dir / "candidate_verification.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
