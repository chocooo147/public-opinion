#!/usr/bin/env python3
"""Atomically promote a validated release to the protected-site document root."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from weekly_release_common import atomic_json, sha256


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--allow-simulated", action="store_true")
    args = parser.parse_args()
    source = args.release_root.resolve() / args.week
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("validated release manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("valid"):
        raise ValueError("release manifest is not valid")
    if manifest.get("week_id") != args.week:
        raise ValueError("release manifest week mismatch")
    if manifest.get("simulation_only") and not args.allow_simulated:
        raise ValueError("simulation release cannot be promoted to production")

    site_root = args.site_root.resolve()
    releases_dir = site_root / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)
    release_fingerprint = sha256(manifest_path)[:12]
    target = releases_dir / f"{args.week}_{release_fingerprint}"
    receipt_path = source / "publish_receipt.json"
    manifest_sha = sha256(manifest_path)
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (
            receipt.get("week_id") == args.week
            and receipt.get("manifest_sha256") == manifest_sha
            and target.is_dir()
        ):
            receipt["idempotent_noop"] = True
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
            return 0
        raise ValueError("publish receipt exists but does not match this manifest")
    existing_week_targets = sorted(releases_dir.glob(f"{args.week}_*"))
    if existing_week_targets:
        raise FileExistsError(
            "a release target already exists for this week without a matching "
            f"receipt: {existing_week_targets}"
        )
    temporary = releases_dir / f".{target.name}.staging"
    if temporary.exists():
        raise FileExistsError(f"stale staging directory exists: {temporary}")
    shutil.copytree(source, temporary, symlinks=False)
    os.replace(temporary, target)
    current = site_root / "current"
    link = site_root / ".current.new"
    if link.exists() or link.is_symlink():
        raise FileExistsError(f"stale promotion link exists: {link}")
    link.symlink_to(target, target_is_directory=True)
    os.replace(link, current)
    receipt = {
        "schema_version": 1,
        "week_id": args.week,
        "simulation_only": manifest["simulation_only"],
        "published_at": datetime.now(timezone.utc).isoformat(),
        "target": target.name,
        "manifest_sha256": manifest_sha,
        "current_resolves_to": str(current.resolve()),
    }
    atomic_json(receipt_path, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
