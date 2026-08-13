#!/usr/bin/env python3
"""Merge duplicate decisions with reversible quarantine execution evidence."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--register", type=Path, required=True)
    parser.add_argument("--quarantine-manifest", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()
    register = json.loads(args.register.read_text(encoding="utf-8"))
    quarantine = json.loads(args.quarantine_manifest.read_text(encoding="utf-8"))
    moved = {item["original_path"]: item for item in quarantine["items"]}
    results = []
    for group in register:
        item = dict(group)
        quarantined = [moved[path] for path in group.get("quarantine_candidates", []) if path in moved]
        pending = [path for path in group.get("quarantine_candidates", []) if path not in moved]
        if quarantined:
            status = "quarantined_reversible_with_compatibility_wrapper"
        elif group["action"] == "hold_investigation":
            status = "retained_after_filter_and_set_relation_review"
        elif group["action"] in {"keep_all_location_bound", "retain_historical_lineage", "manual_review_retain"}:
            status = "retained"
        elif pending:
            status = "pending_reference_migration_or_approved_release"
        else:
            status = "no_move_required"
        item.update(
            {
                "execution_status": status,
                "quarantined": [entry["quarantine_path"] for entry in quarantined],
                "pending_candidates": pending,
                "formal_deleted": [],
            }
        )
        results.append(item)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = [
        "duplicate_group", "sha256", "count", "canonical_path", "other_copies",
        "referencing_scripts", "manifest_references", "action", "reason",
        "execution_status", "quarantined", "pending_candidates", "formal_deleted",
    ]
    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in results:
            writer.writerow(
                {
                    key: json.dumps(item[key], ensure_ascii=False)
                    if isinstance(item.get(key), list)
                    else item.get(key, "")
                    for key in fields
                }
            )
    print(json.dumps({"groups": len(results), "status_counts": Counter(item["execution_status"] for item in results)}, ensure_ascii=False, default=dict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
