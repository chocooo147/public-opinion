#!/usr/bin/env python3
"""Build append-only Bilibili historical revisions from immutable captures."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: row is not an object")
            rows.append(row)
    return rows


def normalized_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def row_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("bvid") or row.get("video_id") or "").strip(),
        str(row.get("author_uid") or "").strip(),
        str(row.get("publish_time") or "").strip(),
        normalized_text(row.get("text")),
    )


def parse_publish_date(row: dict[str, Any]) -> date:
    value = str(row.get("publish_time") or "")[:10]
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid comment publish_time: {row.get('publish_time')!r}") from exc


def build_revision(
    *,
    week_id: str,
    base_path: Path,
    supplement_path: Path,
    output_path: Path,
    week_start: date,
    week_end: date,
    backfill_path: Path | None,
    revision_reason: str,
) -> dict[str, Any]:
    base_rows = read_jsonl(base_path)
    supplement_rows = read_jsonl(supplement_path)
    backfill_rows = read_jsonl(backfill_path) if backfill_path else []

    for label, rows in (("base", base_rows), ("supplement", supplement_rows)):
        for index, row in enumerate(rows):
            publish_date = parse_publish_date(row)
            if not week_start <= publish_date <= week_end:
                raise ValueError(
                    f"{label} row {index} falls outside {week_id}: {publish_date}"
                )
            if not normalized_text(row.get("text")):
                raise ValueError(f"{label} row {index} has blank text")

    exact_backfill: dict[tuple[str, str], dict[str, Any]] = {}
    for row in backfill_rows:
        key = (
            str(row.get("bvid") or row.get("video_id") or "").strip(),
            normalized_text(row.get("text")),
        )
        if key[0] and key[1] and row.get("author_name"):
            exact_backfill[key] = row

    author_backfilled = 0
    revised_base: list[dict[str, Any]] = []
    for original in base_rows:
        row = dict(original)
        match = exact_backfill.get(
            (str(row.get("bvid") or "").strip(), normalized_text(row.get("text")))
        )
        if not row.get("author_name") and match:
            row["author_name"] = match.get("author_name", "")
            row["author_uid"] = match.get("author_uid", "")
            row["author_backfill_source"] = str(backfill_path.name)
            row["author_backfill_method"] = "exact_bvid_and_normalized_text_match"
            author_backfilled += 1
        elif not row.get("author_name"):
            row["author_status"] = "unavailable_in_legacy_capture"
        row["data_version"] = output_path.stem
        revised_base.append(row)

    combined: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    duplicates_removed = 0
    for source, rows in (("base_revision", revised_base), ("supplement", supplement_rows)):
        for original in rows:
            row = dict(original)
            key = row_key(row)
            if key in seen:
                duplicates_removed += 1
                continue
            seen.add(key)
            row["week_id"] = week_id
            row["data_version"] = output_path.stem
            row["revision_record_source"] = source
            combined.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in combined),
        encoding="utf-8",
    )
    source_counts = Counter(str(row.get("bvid") or row.get("video_id") or "") for row in combined)
    author_names = {str(row.get("author_name") or "").strip() for row in combined}
    author_names.discard("")
    missing_authors = sum(not str(row.get("author_name") or "").strip() for row in combined)
    manifest = {
        "schema_version": 1,
        "week_id": week_id,
        "status": "revision_generated_not_published",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "revision_reason": revision_reason,
        "previous_data_version": base_path.name,
        "current_data_version": output_path.name,
        "lineage": {
            "base": {"path": str(base_path), "rows": len(base_rows), "sha256": sha256(base_path)},
            "supplement": {"path": str(supplement_path), "rows": len(supplement_rows), "sha256": sha256(supplement_path)},
            "author_backfill_capture": (
                {"path": str(backfill_path), "rows": len(backfill_rows), "sha256": sha256(backfill_path)}
                if backfill_path
                else None
            ),
            "revision": {"path": str(output_path), "rows": len(combined), "sha256": sha256(output_path)},
        },
        "changes": {
            "supplement_rows_added": len(supplement_rows),
            "author_rows_backfilled": author_backfilled,
            "remaining_missing_author_rows": missing_authors,
            "duplicates_removed_during_revision": duplicates_removed,
        },
        "sample": {
            "effective_raw_rows": len(combined),
            "unique_videos": len([key for key in source_counts if key]),
            "unique_authors_with_identity": len(author_names),
            "max_single_video_share": round(max(source_counts.values(), default=0) / len(combined), 6) if combined else 0,
        },
        "supersedes": {
            "artifact": base_path.name,
            "superseded_status": "retained_for_audit_do_not_silently_overwrite",
        },
    }
    manifest_path = output_path.with_suffix(".revision_manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--week-start", type=date.fromisoformat, required=True)
    parser.add_argument("--week-end", type=date.fromisoformat, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--supplement", type=Path, required=True)
    parser.add_argument("--author-backfill", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision-reason", required=True)
    args = parser.parse_args()
    manifest = build_revision(
        week_id=args.week,
        base_path=args.base.resolve(),
        supplement_path=args.supplement.resolve(),
        output_path=args.output.resolve(),
        week_start=args.week_start,
        week_end=args.week_end,
        backfill_path=args.author_backfill.resolve() if args.author_backfill else None,
        revision_reason=args.revision_reason,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
