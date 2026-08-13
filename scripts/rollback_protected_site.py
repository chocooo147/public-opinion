#!/usr/bin/env python3
"""Atomically restore the previous immutable site target after verify failure."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from weekly_release_common import atomic_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--site-root", type=Path, required=True)
    args = parser.parse_args()
    release_dir = args.release_root.resolve() / args.week
    receipt = json.loads((release_dir / "publish_receipt.json").read_text(encoding="utf-8"))
    site_root = args.site_root.resolve()
    current = site_root / "current"
    if not current.is_symlink() or current.resolve().name != receipt["target"]:
        raise ValueError("rollback refused because current no longer points to the failed target")
    rollback_name = receipt.get("rollback_target")
    if not rollback_name:
        raise ValueError("rollback receipt does not contain a previous target")
    rollback_target = site_root / "releases" / str(rollback_name)
    if not rollback_target.is_dir():
        raise FileNotFoundError("rollback target is missing")
    link = site_root / ".current.rollback"
    if link.exists() or link.is_symlink():
        raise FileExistsError("stale rollback link exists")
    link.symlink_to(rollback_target, target_is_directory=True)
    os.replace(link, current)
    result = {
        "schema_version": 1,
        "week_id": args.week,
        "failed_target": receipt["target"],
        "restored_target": rollback_name,
        "rolled_back_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(release_dir / "rollback_receipt.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
