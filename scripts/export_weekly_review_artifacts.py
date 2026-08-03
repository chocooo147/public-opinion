#!/usr/bin/env python3
"""Export review queues and a reconciliation report from a prepared release."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from weekly_release_common import atomic_json, sha256


FIELDS = [
    "text_id", "comment_id", "week_id", "platform", "publish_time", "bvid",
    "author_name", "author_uid", "text", "model_topic_id", "canonical_topic_id",
    "canonical_topic_name", "assignment_confidence", "confidence_source", "is_outlier",
    "low_confidence_flag", "review_flag", "possible_wrong_classification",
    "sentiment_label", "sentiment_confidence", "sentiment_review_required", "url",
]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = FIELDS + sorted({key for row in rows for key in row} - set(FIELDS))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def filtered(
    rows: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]
) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if predicate(row)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    args = parser.parse_args()
    release_dir = args.release_root.resolve() / args.week
    context = json.loads((release_dir / "release_context.json").read_text(encoding="utf-8"))
    platform_path = release_dir / "outputs" / context["files"]["bilibili"]
    payload = json.loads(platform_path.read_text(encoding="utf-8"))
    rows = list(payload.get("records") or [])
    technical = list(payload.get("technical_records") or [])
    outliers = filtered(rows, lambda row: bool(row.get("is_outlier")))
    low_strength = filtered(rows, lambda row: bool(row.get("low_confidence_flag")))
    possible_misclassification = filtered(
        rows,
        lambda row: (
            not bool(row.get("is_outlier"))
            and (
                bool(row.get("possible_wrong_classification"))
                or bool(row.get("review_flag"))
                or bool(row.get("low_confidence_flag"))
                or not bool(row.get("canonical_topic_id"))
            )
        ),
    )
    for row in possible_misclassification:
        reasons = []
        if row.get("low_confidence_flag"):
            reasons.append("low_hdbscan_membership_strength")
        if row.get("review_flag") or not row.get("canonical_topic_id"):
            reasons.append("missing_or_review_canonical_mapping")
        if row.get("possible_wrong_classification"):
            reasons.append("preexisting_possible_wrong_classification_flag")
        row["candidate_reason"] = ";".join(reasons)

    review_dir = release_dir / "review"
    outputs = {
        "cleaned": review_dir / f"bilibili_{args.week}_cleaned.csv",
        "assignments": review_dir / f"bilibili_{args.week}_topic_assignments.csv",
        "outliers": review_dir / f"bilibili_{args.week}_outliers.csv",
        "low_assignment_strength": review_dir / f"bilibili_{args.week}_low_assignment_strength.csv",
        "possible_misclassification": review_dir / f"bilibili_{args.week}_possible_misclassification_candidates.csv",
        "technical_issues": review_dir / f"bilibili_{args.week}_technical_issues.csv",
    }
    write_csv(outputs["cleaned"], rows)
    write_csv(outputs["assignments"], rows)
    write_csv(outputs["outliers"], outliers)
    write_csv(outputs["low_assignment_strength"], low_strength)
    write_csv(outputs["possible_misclassification"], possible_misclassification)
    write_csv(outputs["technical_issues"], technical)

    topic_counts = Counter(
        str(row.get("canonical_topic_id") or "UNMAPPED")
        for row in rows
        if not row.get("is_outlier")
    )
    sentiment_counts = Counter(str(row.get("sentiment_label") or "UNKNOWN") for row in rows)
    non_outliers = len(rows) - len(outliers)
    mapped = sum(bool(row.get("canonical_topic_id")) and not row.get("is_outlier") for row in rows)
    unmapped_non_outliers = non_outliers - mapped
    reconciliation = {
        "raw_to_effective": {
            "raw": int(payload["meta"].get("raw_rows") or 0),
            "blank_removed": int(payload["meta"].get("blank_rows_removed") or 0),
            "duplicates_removed": int(payload["meta"].get("duplicate_rows_removed") or 0),
            "technical_removed": int(payload["meta"].get("technical_issue_rows") or 0),
            "effective": len(rows),
        },
        "topic_assignment": {
            "effective": len(rows),
            "outliers": len(outliers),
            "non_outliers": non_outliers,
            "mapped_non_outliers": mapped,
            "unmapped_non_outliers": unmapped_non_outliers,
            "topic_counts": dict(sorted(topic_counts.items())),
        },
        "review_queues": {
            "outliers": len(outliers),
            "low_assignment_strength": len(low_strength),
            "possible_misclassification_candidates": len(possible_misclassification),
            "technical_issues": len(technical),
        },
        "sentiment": {"effective": len(rows), "counts": dict(sorted(sentiment_counts.items()))},
    }
    checks = {
        "raw_reconciles": (
            reconciliation["raw_to_effective"]["raw"]
            - reconciliation["raw_to_effective"]["blank_removed"]
            - reconciliation["raw_to_effective"]["duplicates_removed"]
            - reconciliation["raw_to_effective"]["technical_removed"]
            == len(rows)
        ),
        "outlier_partition_reconciles": len(outliers) + non_outliers == len(rows),
        "mapping_partition_reconciles": mapped + unmapped_non_outliers == non_outliers,
        "topic_counts_reconcile": sum(topic_counts.values()) == non_outliers,
        "sentiment_counts_reconcile": sum(sentiment_counts.values()) == len(rows),
        "outlier_and_possible_misclassification_are_not_identical": {
            str(row.get("comment_id") or row.get("text_id")) for row in outliers
        } != {
            str(row.get("comment_id") or row.get("text_id"))
            for row in possible_misclassification
        },
    }
    report = {
        "schema_version": 1,
        "week_id": args.week,
        "status": "passed" if all(checks.values()) else "failed",
        "confidence_semantics": payload["meta"].get("confidence_semantics"),
        "sample_quality": context["sample_quality"]["B站"],
        "reconciliation": reconciliation,
        "checks": checks,
        "provenance": {
            "platform_json": {"path": str(platform_path), "sha256": sha256(platform_path)},
            "input_hash": context["input_hashes"]["bilibili"],
            "bertopic_model_version": payload["meta"].get("bertopic_model_version"),
            "bertopic_model_sha256": payload["meta"].get("bertopic_model_sha256"),
            "sentiment_model": payload["meta"].get("sentiment_model"),
            "sentiment_model_version": payload["meta"].get("sentiment_model_version"),
            "sentiment_model_sha256": payload["meta"].get("sentiment_model_sha256"),
            "report_rules": context["report_rules"],
        },
        "artifacts": {
            key: {"path": str(path), "rows": len(list(csv.DictReader(path.open(encoding="utf-8-sig")))), "sha256": sha256(path)}
            for key, path in outputs.items()
        },
    }
    atomic_json(release_dir / "quality_report.json", report)
    markdown = [
        f"# {args.week} revision quality report",
        "",
        f"- Status: {report['status']}",
        f"- Effective Bilibili top-level comments: {len(rows)}",
        f"- Independent videos: {context['sample_quality']['B站']['independent_source_count']}",
        f"- Outliers: {len(outliers)}",
        f"- Low HDBSCAN membership strength: {len(low_strength)}",
        f"- Possible misclassification candidates: {len(possible_misclassification)}",
        "- Confidence is HDBSCAN cluster membership strength, not a calibrated probability that the topic label is correct.",
        "",
    ]
    (release_dir / "quality_report.md").write_text("\n".join(markdown), encoding="utf-8")
    print(json.dumps({"week_id": args.week, "status": report["status"], "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
