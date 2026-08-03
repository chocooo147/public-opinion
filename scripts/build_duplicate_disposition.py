#!/usr/bin/env python3
"""Build a conservative, reference-aware duplicate disposition register.

The register is intentionally a plan, not a deletion script.  Every path that
could eventually be removed must first be moved by a separate, reversible
quarantine operation after an end-to-end reproduction succeeds.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any


TEXT_SUFFIXES = {
    ".cjs", ".css", ".csv", ".html", ".ini", ".js", ".json", ".jsonl",
    ".md", ".mjs", ".py", ".sh", ".toml", ".ts", ".txt", ".yaml", ".yml",
}
SCRIPT_SUFFIXES = {".cjs", ".js", ".mjs", ".py", ".sh", ".ts"}
SENTINELS = {".gitkeep", ".nojekyll"}
ANOMALY_TOKENS = ("low_confidence", "outlier", "possible_misclassification")
HISTORICAL_TOKENS = (
    "weekly_community_report", "report_input", "dashboard_data", "manifest",
    "quality_report", "validation", "release_audit", "preview", "assignments",
)


def _read_groups(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("duplicate-groups input must be a JSON list")
    return payload


def _iter_searchable(root: Path, output_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if ".git" in relative.parts or "quarantine" in relative.parts:
            continue
        if path.is_relative_to(output_dir):
            continue
        try:
            if path.stat().st_size > 8 * 1024 * 1024:
                continue
        except OSError:
            continue
        files.append(path)
    return files


def _references(
    root: Path,
    searchable: list[Path],
    duplicate_paths: list[str],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    script_refs = {path: [] for path in duplicate_paths}
    manifest_refs = {path: [] for path in duplicate_paths}
    needles = {
        path: (path, Path(path).name)
        for path in duplicate_paths
        if Path(path).name not in SENTINELS
    }
    for source in searchable:
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative_source = source.relative_to(root).as_posix()
        for target, (full, name) in needles.items():
            if relative_source == target:
                continue
            if full not in text and name not in text:
                continue
            if source.suffix.lower() in SCRIPT_SUFFIXES:
                script_refs[target].append(relative_source)
            if "manifest" in source.name.casefold() or source.suffix.lower() == ".json":
                manifest_refs[target].append(relative_source)
    return script_refs, manifest_refs


def _is_code(path: str) -> bool:
    candidate = Path(path)
    return candidate.suffix.lower() in SCRIPT_SUFFIXES or candidate.name == "__init__.py"


def _canonical(paths: list[str]) -> str:
    def score(path: str) -> tuple[int, int, str]:
        lower = path.casefold()
        parts = Path(path).parts
        value = 100
        if path.startswith("data/raw/") or path.startswith("data/training/"):
            value = 0
        elif path.startswith("models/"):
            value = 1
        elif path.startswith("work/public-opinion/") and _is_code(path):
            value = 2
        elif path.startswith("work/public-opinion/config/"):
            value = 3
        elif path.startswith("work/public-opinion/"):
            value = 5
        elif path.startswith("outputs/") or path.startswith("reports/"):
            value = 7
        if "backup" in lower or "old" in lower or "tmp" in lower:
            value += 20
        return value, len(parts), path

    return min(paths, key=score)


def _disposition(paths: list[str], canonical: str) -> tuple[str, str]:
    names = [Path(path).name.casefold() for path in paths]
    if all(Path(path).name in SENTINELS for path in paths):
        return (
            "keep_all_location_bound",
            "Location sentinels are semantically distinct despite identical empty content.",
        )
    if any(any(token in name for token in ANOMALY_TOKENS) for name in names):
        return (
            "hold_investigation",
            "Anomaly exports require filter, set-relation, and export-logic review before any move.",
        )
    joined = " ".join(path.casefold() for path in paths)
    if any(token in joined for token in HISTORICAL_TOKENS):
        return (
            "retain_historical_lineage",
            "Identical content participates in week/release/QA lineage; consolidate only after manifest lineage is explicit.",
        )
    public_paths = [path for path in paths if path.startswith("work/public-opinion/")]
    root_paths = [path for path in paths if not path.startswith("work/public-opinion/")]
    if public_paths and root_paths and any(_is_code(path) for path in paths):
        return (
            "quarantine_noncanonical_after_reproduction",
            "work/public-opinion is the active code root; noncanonical mirrors may be quarantined after reference migration and full reproduction.",
        )
    if public_paths and root_paths and any(path.startswith("config/") for path in paths):
        return (
            "quarantine_noncanonical_after_reproduction",
            "Public-worktree configuration is canonical; root mirror may be quarantined after references are migrated.",
        )
    if canonical.startswith("models/") and any(path.startswith("work/public-opinion/models/") for path in paths):
        return (
            "quarantine_noncanonical_after_reproduction",
            "Models belong in the configured external model root; deployment mirrors may be quarantined after model-load reproduction.",
        )
    return (
        "manual_review_retain",
        "No deletion-safe rule was established; retain pending explicit owner and reference review.",
    )


def build(root: Path, groups_path: Path, output_dir: Path) -> list[dict[str, Any]]:
    groups = _read_groups(groups_path)
    all_paths = [path for group in groups for path in group["paths"]]
    searchable = _iter_searchable(root, output_dir)
    script_refs, manifest_refs = _references(root, searchable, all_paths)
    rows: list[dict[str, Any]] = []
    for group in groups:
        paths = list(group["paths"])
        canonical = _canonical(paths)
        action, reason = _disposition(paths, canonical)
        copies = [path for path in paths if path != canonical]
        rows.append(
            {
                "duplicate_group": group["duplicate_group"],
                "sha256": group["sha256"],
                "count": len(paths),
                "canonical_path": canonical,
                "other_copies": copies,
                "referencing_scripts": sorted(
                    {ref for path in paths for ref in script_refs[path]}
                ),
                "manifest_references": sorted(
                    {ref for path in paths for ref in manifest_refs[path]}
                ),
                "action": action,
                "reason": reason,
                "quarantine_candidates": (
                    copies if action == "quarantine_noncanonical_after_reproduction" else []
                ),
            }
        )
    return rows


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "duplicate_disposition_register.json"
    csv_path = output_dir / "duplicate_disposition_register.csv"
    md_path = output_dir / "duplicate_disposition_register.md"
    json_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "duplicate_group", "sha256", "count", "canonical_path",
            "other_copies", "referencing_scripts", "manifest_references",
            "action", "reason", "quarantine_candidates",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "other_copies": json.dumps(row["other_copies"], ensure_ascii=False),
                    "referencing_scripts": json.dumps(row["referencing_scripts"], ensure_ascii=False),
                    "manifest_references": json.dumps(row["manifest_references"], ensure_ascii=False),
                    "quarantine_candidates": json.dumps(row["quarantine_candidates"], ensure_ascii=False),
                }
            )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    lines = [
        "# Duplicate disposition register", "",
        f"- Duplicate groups: {len(rows)}",
        f"- Generated from SHA256 groups; no file was deleted by this step.",
        "- Any quarantine candidate remains conditional on reference migration and a successful full reproduction.",
        "", "## Action summary", "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in sorted(counts.items()))
    lines.extend(["", "## Per-group disposition", ""])
    for row in rows:
        lines.extend(
            [
                f"### {row['duplicate_group']}", "",
                f"- SHA256: `{row['sha256']}`",
                f"- Canonical: `{row['canonical_path']}`",
                f"- Other copies: {', '.join(f'`{p}`' for p in row['other_copies']) or 'none'}",
                f"- Referencing scripts: {', '.join(f'`{p}`' for p in row['referencing_scripts']) or 'none found'}",
                f"- Manifest references: {', '.join(f'`{p}`' for p in row['manifest_references']) or 'none found'}",
                f"- Action: `{row['action']}`",
                f"- Reason: {row['reason']}",
                "",
            ]
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output_dir = args.output_dir.resolve()
    rows = build(root, args.groups.resolve(), output_dir)
    write_outputs(rows, output_dir)
    print(json.dumps({"groups": len(rows), "output_dir": str(output_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
