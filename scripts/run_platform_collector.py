#!/usr/bin/env python3
"""Run a live collector and normalize its JSON output to the weekly contract."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weekly_release_common import atomic_json


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_payload(
    path: Path,
    *,
    platform: str,
    week_id: str,
    week_start: str,
    week_end: str,
) -> dict[str, object]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["week_id"] = row.get("week_id") or week_id
        row["platform"] = row.get("platform") or platform
        for field in ("likes", "comments", "shares", "views"):
            value = row.get(field)
            if value in (None, ""):
                row[field] = (
                    None if platform == "小黑盒" and field == "views" else 0
                )
            else:
                try:
                    row[field] = int(float(str(value)))
                except ValueError:
                    row[field] = (
                        None if platform == "小黑盒" and field == "views" else 0
                    )
    return {
        "meta": {
            "week_id": week_id,
            "date_range": [week_start, week_end],
            "raw_input": path.name,
            "raw_sha256": _sha256(path),
            "raw_rows": len(rows),
            "mapped_rows": None,
            "collection_scope": (
                "Logged-in visible Bilibili bounded sample."
                if platform == "B站"
                else (
                    "Logged-in Xiaoheihe public-search visible post cards; "
                    "comment bodies were not collected."
                )
            ),
            "comment_body_collection": False if platform == "小黑盒" else None,
            "formal_reporting_qualified": False,
            "sample_limited": True,
            "simulation_only": False,
        },
        "records": rows,
    }


def _jsonl_payload(
    path: Path,
    *,
    platform: str,
    week_id: str,
    week_start: str,
    week_end: str,
) -> dict[str, object]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL row") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: row is not an object")
            row["week_id"] = week_id
            row["platform"] = platform
            row["url"] = row.get("url") or row.get("source_url") or ""
            for field in ("likes", "comments", "shares", "views"):
                value = row.get(field)
                try:
                    row[field] = (
                        int(float(str(value)))
                        if value not in (None, "")
                        else (
                            None
                            if platform == "小黑盒" and field == "views"
                            else 0
                        )
                    )
                except ValueError:
                    row[field] = (
                        None if platform == "小黑盒" and field == "views" else 0
                    )
            rows.append(row)
    return {
        "meta": {
            "week_id": week_id,
            "date_range": [week_start, week_end],
            "raw_input": path.name,
            "raw_sha256": _sha256(path),
            "raw_rows": len(rows),
            "mapped_rows": None,
            "collection_scope": (
                "Versioned Bilibili visible top-level comment revision; exact "
                "comment publish time enforced."
                if platform == "B站"
                else "Versioned Xiaoheihe public-search visible post revision."
            ),
            "comment_body_collection": False if platform == "小黑盒" else None,
            "formal_reporting_qualified": False,
            "sample_limited": True,
            "simulation_only": False,
            "historical_revision_input": True,
        },
        "records": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument(
        "--fallback",
        type=Path,
        action="append",
        default=[],
        help="Collector-owned output path accepted when target is not written",
    )
    parser.add_argument(
        "--fallback-glob",
        action="append",
        default=[],
        help="Collector-owned CSV/JSON glob; only new or modified files qualify",
    )
    parser.add_argument("--platform", choices=("B站", "小黑盒"), required=True)
    parser.add_argument("--week", required=True)
    parser.add_argument("--week-start", required=True)
    parser.add_argument("--week-end", required=True)
    parser.add_argument(
        "--source-existing",
        type=Path,
        help=(
            "Normalize an existing immutable CSV, JSONL, or contract JSON. "
            "Used for historical revisions; no collector command is executed."
        ),
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if args.source_existing and command:
        raise ValueError("--source-existing cannot be combined with a collector command")
    if not command and not args.source_existing:
        raise ValueError("collector command is required after --")
    args.target.parent.mkdir(parents=True, exist_ok=True)
    if args.source_existing:
        source = args.source_existing.resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        if source.suffix.lower() == ".csv":
            payload = _csv_payload(
                source,
                platform=args.platform,
                week_id=args.week,
                week_start=args.week_start,
                week_end=args.week_end,
            )
        elif source.suffix.lower() == ".jsonl":
            payload = _jsonl_payload(
                source,
                platform=args.platform,
                week_id=args.week,
                week_start=args.week_start,
                week_end=args.week_end,
            )
        else:
            payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
            raise ValueError("existing source must normalize to a records list")
        atomic_json(args.target, payload)
        print(
            json.dumps(
                {
                    "target": str(args.target),
                    "records": len(payload["records"]),
                    "normalized_from": str(source),
                    "historical_revision_input": True,
                },
                ensure_ascii=False,
            )
        )
        return 0
    watched = [args.target, *args.fallback]
    watched.extend(
        path
        for pattern in args.fallback_glob
        for path in Path("/").glob(pattern.lstrip("/"))
        if path.is_file()
    )
    before = {
        str(path.resolve()): (path.stat().st_mtime_ns, path.stat().st_size)
        for path in watched
        if path.is_file()
    }
    completed = subprocess.run(command, check=False)
    if completed.returncode:
        return completed.returncode
    changed = []
    for pattern in args.fallback_glob:
        for path in Path("/").glob(pattern.lstrip("/")):
            if not path.is_file():
                continue
            state = (path.stat().st_mtime_ns, path.stat().st_size)
            if before.get(str(path.resolve())) != state:
                changed.append(path)
    for path in [args.target, *args.fallback]:
        if not path.is_file():
            continue
        state = (path.stat().st_mtime_ns, path.stat().st_size)
        if before.get(str(path.resolve())) != state:
            changed.append(path)
    unique_changed = {str(path.resolve()): path for path in changed}
    source = (
        max(unique_changed.values(), key=lambda path: path.stat().st_mtime_ns)
        if unique_changed
        else None
    )
    if source is None:
        raise FileNotFoundError(
            "collector exited successfully but produced no contract JSON"
        )
    payload = (
        _csv_payload(
            source,
            platform=args.platform,
            week_id=args.week,
            week_start=args.week_start,
            week_end=args.week_end,
        )
        if source.suffix.lower() == ".csv"
        else _jsonl_payload(
            source,
            platform=args.platform,
            week_id=args.week,
            week_start=args.week_start,
            week_end=args.week_end,
        )
        if source.suffix.lower() == ".jsonl"
        else json.loads(source.read_text(encoding="utf-8"))
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("collector output must contain a records list")
    if source.suffix.lower() in {".csv", ".jsonl"}:
        atomic_json(args.target, payload)
    elif source.resolve() != args.target.resolve():
        shutil.copy2(source, args.target)
    print(
        json.dumps(
            {
                "target": str(args.target),
                "records": len(payload["records"]),
                "normalized_from": str(source),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
