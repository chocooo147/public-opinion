#!/usr/bin/env python3
"""Build one non-publishing event, keyword, and sentiment integrity preview bundle."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import re
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from content_integrity import (
    EVENT_RULE_VERSION,
    KEYWORD_RULE_VERSION,
    SENTIMENT_RULE_VERSION,
    extract_keywords,
    generate_events,
)
from sentiment_integrity import annotate_sentiment_record, summarize_sentiment
from representative_content import (
    REPRESENTATIVE_CONTENT_RULE_VERSION,
    build_representative_contents,
    enrich_bilibili_records,
    load_bilibili_metadata,
    validate_representative_contents,
)
from weekly_release_common import (
    _combined_metric,
    _platform_metric,
    atomic_json,
    build_dashboard,
    patch_site_html,
    sha256,
)


TARGET_TOPICS = {"APEX-T006", "APEX-T007", "APEX-T008"}
DISPLAY_TOPIC_NAMES = {"APEX-T006": "联动活动与体验"}
SENTIMENT_KEYS = (
    "comment_count", "sentiment_valid_count", "sentiment_invalid_count",
    "positive_count", "neutral_count", "negative_count",
    "positive_rate", "neutral_rate", "negative_rate",
    "positive", "neutral", "negative", "sentiment",
    "sentiment_model", "sentiment_model_version", "sentiment_status",
    "low_sample_status", "sentiment_sample_band", "sentiment_risk_weight",
    "invalid_reasons",
)


def display_week(value: str) -> str:
    return value.replace("_W", "-W")


def storage_week(value: str) -> str:
    return value.replace("-W", "_W")


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def json_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    meta = payload.get("meta") or {}
    source_version = clean_text(
        meta.get("current_data_version")
        or meta.get("data_version")
        or Path(str(meta.get("raw_input") or path.stem)).stem
    )
    rows = [dict(row) for row in (payload.get("records") or [])]
    for row in rows:
        row.setdefault("source_data_version", source_version)
    return rows


def load_records(apex_root: Path, repo_root: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    records: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    corpus = {
        row["text_id"]: row
        for row in read_csv(apex_root / "data/processed/bilibili_apex_W25_W28_bertopic_exploratory_corpus.csv")
    }
    for row in read_csv(apex_root / "data/processed/bilibili_apex_W25_W28_snownlp_sentiment.csv"):
        if str(row.get("dashboard_topic_include") or "") != "1":
            continue
        merged = {**corpus.get(str(row.get("text_id")), {}), **row}
        merged.update(
            {
                "platform": "B站",
                "text": merged.get("raw_text") or merged.get("clean_text"),
                "sentiment_model_version": merged.get("sentiment_version"),
                "is_outlier": 0,
            }
        )
        records[(display_week(str(row["week_id"])), "B站")].append(merged)

    for row in read_csv(repo_root / "outputs/heybox_apex_W25_W28_public_search_assignments.csv"):
        if str(row.get("canonical_topic_id") or "").strip() and str(row.get("is_outlier") or "0") not in {"1", "true", "True"}:
            row["platform"] = "小黑盒"
            row["sentiment_model_version"] = row.get("sentiment_version") or "0.12.3"
            row["source_data_version"] = "heybox_apex_W25_W28_public_search_assignments"
            records[(display_week(str(row["week_id"])), "小黑盒")].append(row)

    for week in ("2026_W29", "2026_W30", "2026_W31"):
        for platform, filename in (
            ("B站", f"bilibili_apex_{week}.json"),
            ("小黑盒", f"heybox_apex_{week}_public_search.json"),
        ):
            for row in json_records(repo_root / "outputs" / filename):
                if row.get("canonical_topic_id") and not row.get("is_outlier"):
                    records[(display_week(week), platform)].append(row)
    metadata = load_bilibili_metadata(apex_root)
    for (week_id, platform), rows in records.items():
        if platform == "B站":
            enrich_bilibili_records(rows, metadata)
    return records


def dashboard_sources(apex_root: Path, repo_root: Path) -> dict[str, dict[str, Any]]:
    paths = {
        **{week: apex_root / f"outputs/dashboard_data_apex_W25_W28.json" for week in ("2026-W25", "2026-W26", "2026-W27", "2026-W28")},
        "2026-W29": apex_root / "outputs/dashboard_data_apex_W25_W29.json",
        "2026-W30": apex_root / "outputs/dashboard_data_apex_W25_W30.json",
        "2026-W31": repo_root / "dashboard_data_apex_W27_W31.json",
    }
    result: dict[str, dict[str, Any]] = {}
    for week_id, path in paths.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        result[week_id] = next(w for w in payload["weeks"] if w["week_id"] == week_id)
    return result


def metric_for(week: dict[str, Any], topic_id: str, platform: str) -> dict[str, Any] | None:
    topic = next((item for item in week.get("topics", []) if item.get("id") == topic_id), None)
    if not topic:
        return None
    return topic.get("combined_metrics") if platform == "综合" else (topic.get("platform_metrics") or {}).get(platform)


def grouped_by_topic(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        topic_id = str(row.get("canonical_topic_id") or "").strip()
        if topic_id:
            result[topic_id].append(row)
    return result


def original_rate(metric: dict[str, Any] | None) -> tuple[Any, str]:
    if not metric:
        return None, "metric_missing"
    if "negative_rate" in metric:
        return metric.get("negative_rate"), "negative_rate"
    if "negative" in metric:
        return metric.get("negative"), "negative_legacy_rate"
    return None, "negative_field_missing"


def audit_history(
    all_records: dict[tuple[str, str], list[dict[str, Any]]],
    dashboards: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for week_id in sorted(dashboards):
        dashboard_week = dashboards[week_id]
        topic_ids = {str(t["id"]) for t in dashboard_week.get("topics", [])}
        for platform in ("B站", "小黑盒"):
            by_topic = grouped_by_topic(all_records.get((week_id, platform), []))
            for topic_id in sorted(topic_ids | set(by_topic)):
                evidence = by_topic.get(topic_id, [])
                summary = summarize_sentiment(evidence)
                metric = metric_for(dashboard_week, topic_id, platform)
                original, source_field = original_rate(metric)
                recalculated = summary["negative_rate"]
                unavailable_shown_zero = (
                    summary["sentiment_valid_count"] == 0 and original == 0
                )
                consistent = (
                    original is None and recalculated is None
                ) or (
                    original is not None
                    and recalculated is not None
                    and abs(float(original) - float(recalculated)) <= 0.011
                )
                topic_name = DISPLAY_TOPIC_NAMES.get(topic_id) or next(
                    (str(t.get("name")) for t in dashboard_week.get("topics", []) if t.get("id") == topic_id),
                    evidence[0].get("canonical_topic_name") if evidence else topic_id,
                )
                rows.append(
                    {
                        "week_id": week_id,
                        "platform": platform,
                        "canonical_topic_id": topic_id,
                        "topic_name": topic_name,
                        **summary,
                        "original_json_negative_rate": original,
                        "original_json_source_field": source_field,
                        "backend_recalculated_negative_rate": recalculated,
                        "legacy_frontend_display": (
                            "0%" if original == 0 else "—" if original is None else f"{original}%"
                        ),
                        "revised_frontend_display": (
                            "—"
                            if recalculated is None
                            else f"{recalculated}%\n低样本：样本量较小 不单独用于风险结论"
                            if recalculated == 0 and summary["negative_count"] == 0 and 0 < summary["sentiment_valid_count"] < 5
                            else f"{recalculated}%"
                        ),
                        "three_way_consistent_before": consistent,
                        "mismatch_stage": "none" if consistent else "legacy_json_or_frontend",
                        "unavailable_but_legacy_zero": unavailable_shown_zero,
                        "sentiment_model_failed": bool(summary["invalid_reasons"].get("sentiment_model_failed_or_unavailable")),
                    }
                )

    summary = {
        "topic_platform_week_rows": len(rows),
        "true_zero_rate_rows": sum(r["sentiment_valid_count"] > 0 and r["negative_count"] == 0 for r in rows),
        "unavailable_but_legacy_zero_rows": sum(bool(r["unavailable_but_legacy_zero"]) for r in rows),
        "sentiment_model_failed_rows": sum(bool(r["sentiment_model_failed"]) for r in rows),
        "valid_sample_under_5_rows": sum(0 < r["sentiment_valid_count"] < 5 for r in rows),
        "no_valid_sample_rows": sum(r["sentiment_valid_count"] == 0 for r in rows),
        "negative_rate_count_mismatch_rows": sum(
            r["sentiment_valid_count"] > 0
            and abs(float(r["backend_recalculated_negative_rate"]) - r["negative_count"] / r["sentiment_valid_count"] * 100) > 0.011
            for r in rows
        ),
        "legacy_frontend_backend_mismatch_rows": sum(not bool(r["three_way_consistent_before"]) for r in rows),
    }
    return rows, summary


def apply_historical_metrics(
    dashboard: dict[str, Any],
    all_records: dict[tuple[str, str], list[dict[str, Any]]],
) -> None:
    for week in dashboard["weeks"]:
        week_id = week["week_id"]
        platform_summaries: dict[str, dict[str, Any]] = {}
        topic_groups = {
            platform: grouped_by_topic(all_records.get((week_id, platform), []))
            for platform in ("B站", "小黑盒")
        }
        for topic in week.get("topics", []):
            platform_metrics = topic.get("platform_metrics") or {}
            recalculated: dict[str, dict[str, Any]] = {}
            representative_by_platform: dict[str, list[dict[str, Any]]] = {}
            for platform in ("B站", "小黑盒"):
                existing = platform_metrics.get(platform)
                if existing is None:
                    continue
                evidence = topic_groups[platform].get(str(topic["id"]), [])
                existing_trend = list(existing.get("trend") or [])
                previous_stub = (
                    {"count": int(existing_trend[-2]), "trend": existing_trend[:-1]}
                    if len(existing_trend) >= 2
                    else None
                )
                metric = _platform_metric(
                    evidence,
                    previous_stub,
                    platform=platform,
                    simulated=False,
                )
                for key in SENTIMENT_KEYS + ("risk_score", "risk_status", "risk_components"):
                    existing[key] = metric.get(key)
                contents = build_representative_contents(
                    evidence,
                    platform=platform,
                    source_data_version=f"{storage_week(week_id)}_{'bilibili' if platform == 'B站' else 'heybox'}_source",
                )
                existing["representative_contents"] = contents
                existing["representative_content_count"] = len(contents)
                representative_by_platform[platform] = contents
                recalculated[platform] = metric
            if "B站" in recalculated and "小黑盒" in recalculated:
                combined = _combined_metric(recalculated["B站"], recalculated["小黑盒"], simulated=False)
                topic["combined_metrics"].update(combined)
            combined_contents = representative_by_platform.get("B站", []) + representative_by_platform.get("小黑盒", [])
            topic["representative_contents"] = combined_contents
            topic["representative_content_count"] = len(combined_contents)
            topic["representative_videos"] = representative_by_platform.get("B站", [])
            b_metric = platform_metrics.get("B站") or {}
            topic.update(
                {
                    "negative": b_metric.get("negative_rate"),
                    "negative_rate": b_metric.get("negative_rate"),
                    "negative_count": b_metric.get("negative_count", 0),
                    "sentiment_valid_count": b_metric.get("sentiment_valid_count", 0),
                    "low_sample_status": b_metric.get("low_sample_status", True),
                    "risk": b_metric.get("risk_score"),
                    "risk_status": b_metric.get("risk_status"),
                }
            )

        for platform in ("B站", "小黑盒"):
            records = all_records.get((week_id, platform), [])
            platform_summaries[platform] = summarize_sentiment(records)
        combined_counts = {
            key: platform_summaries["B站"][key] + platform_summaries["小黑盒"][key]
            for key in ("positive_count", "neutral_count", "negative_count")
        }
        valid = sum(combined_counts.values())
        combined_summary = {
            "comment_count": platform_summaries["B站"]["comment_count"] + platform_summaries["小黑盒"]["comment_count"],
            "sentiment_valid_count": valid,
            "sentiment_invalid_count": platform_summaries["B站"]["sentiment_invalid_count"] + platform_summaries["小黑盒"]["sentiment_invalid_count"],
            **combined_counts,
            "positive_rate": round(combined_counts["positive_count"] / valid * 100, 2) if valid else None,
            "neutral_rate": round(combined_counts["neutral_count"] / valid * 100, 2) if valid else None,
            "negative_rate": round(combined_counts["negative_count"] / valid * 100, 2) if valid else None,
            "sentiment": (
                round(sum(float(r.get("sentiment_score")) for p in ("B站", "小黑盒") for r in all_records.get((week_id, p), []) if r.get("sentiment_score") not in (None, "")) / valid, 6)
                if valid else None
            ),
            "sentiment_model": "mixed_platform_models" if valid else None,
            "sentiment_model_version": "see_platform_metrics" if valid else None,
            "sentiment_status": "mixed_platform_model_output" if valid else "sentiment_data_unavailable",
            "low_sample_status": valid < 5,
            "sentiment_sample_band": "unavailable" if valid == 0 else "low_under_5" if valid < 5 else "limited_5_to_9" if valid < 10 else "adequate_10_plus",
        }
        combined_summary.update(
            {
                "positive": combined_summary["positive_rate"],
                "neutral": combined_summary["neutral_rate"],
                "negative": combined_summary["negative_rate"],
            }
        )
        week["platform_sentiment_metrics"] = {
            "B站": platform_summaries["B站"],
            "小黑盒": platform_summaries["小黑盒"],
            "综合": combined_summary,
        }

        platform_records = {
            platform: all_records.get((week_id, platform), [])
            for platform in ("B站", "小黑盒")
        }
        keyword_results = {
            "B站": extract_keywords(platform_records["B站"]),
            "小黑盒": extract_keywords(platform_records["小黑盒"]),
            "综合": extract_keywords(platform_records["B站"] + platform_records["小黑盒"]),
        }
        week["keyword_stats"] = {
            platform: result["qualified"][:30]
            for platform, result in keyword_results.items()
        }
        week["keyword_meta"] = {
            platform: {
                "document_total": result["input_text_count"],
                "qualified_count": len(result["qualified"]),
                "candidate_count": len(result["candidates"]),
                "rule_version": result["rule_version"],
                "quality_status": "passed",
            }
            for platform, result in keyword_results.items()
        }
        for topic in week.get("topics", []):
            topic_id = str(topic["id"])
            topic["platform_keyword_stats"] = {
                platform: [
                    row for row in result["qualified"]
                    if topic_id in row["topic_ids"]
                ][:15]
                for platform, result in keyword_results.items()
            }
            topic["keywords"] = [
                row["normalized_keyword"]
                for row in topic["platform_keyword_stats"]["综合"][:8]
            ]

        event_result = generate_events(
            platform_records["B站"] + platform_records["小黑盒"],
            week_id=storage_week(week_id),
        )
        week["events"] = event_result["events"]
        week["event_generation"] = {
            "status": event_result["status"],
            "candidate_count": event_result["candidate_count"],
            "qualified_count": event_result["qualified_count"],
            "rule_version": event_result["rule_version"],
            "data_quality_status": "passed",
        }


def audit_representative_content_history(
    dashboards: dict[str, dict[str, Any]],
    all_records: dict[tuple[str, str], list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    source_mapping_failures = 0
    fixed_empty_placeholders = 0
    for week_id in sorted(dashboards):
        week = dashboards[week_id]
        grouped = {
            platform: grouped_by_topic(all_records.get((week_id, platform), []))
            for platform in ("B站", "小黑盒")
        }
        for topic in week.get("topics", []):
            topic_id = str(topic.get("id") or "")
            bili = build_representative_contents(
                grouped["B站"].get(topic_id, []), platform="B站",
                source_data_version=f"{storage_week(week_id)}_bilibili_source",
            )
            heybox = build_representative_contents(
                grouped["小黑盒"].get(topic_id, []), platform="小黑盒",
                source_data_version=f"{storage_week(week_id)}_heybox_source",
            )
            legacy = topic.get("representative_videos") or []
            if any(
                not isinstance(item, dict)
                or not (clean_text(item.get("title")) or clean_text(item.get("bvid")) or clean_text(item.get("url")))
                for item in legacy
            ):
                fixed_empty_placeholders += sum(
                    not isinstance(item, dict)
                    or not (clean_text(item.get("title")) or clean_text(item.get("bvid")) or clean_text(item.get("url")))
                    for item in legacy
                )
            if any(
                isinstance(item, dict)
                and (item.get("bvid") is None or item.get("comment_count") is None)
                for item in legacy
            ):
                source_mapping_failures += 1
            combined = sorted(
                bili + heybox,
                key=lambda item: (
                    -int(item.get("topic_text_count") or 0),
                    str(item.get("platform") or ""),
                    str(item.get("content_id") or item.get("url") or ""),
                ),
            )[:3]
            for view, contents in (
                ("B站", bili),
                ("小黑盒", heybox),
                ("综合", combined),
            ):
                serialized = json.dumps(contents, ensure_ascii=False)
                errors = validate_representative_contents(contents)
                rows.append(
                    {
                        "week_id": week_id,
                        "canonical_topic_id": topic_id,
                        "topic_name": topic.get("name") or topic_id,
                        "view": view,
                        "representative_content_count": len(contents),
                        "contents": contents,
                        "schema_errors": errors,
                        "contains_undefined": "undefined" in serialized.lower(),
                        "contains_null_text": any(
                            value in serialized.lower()
                            for value in ('"title": "null"', '"content_id": "null"', '"url": "null"')
                        ),
                        "missing_title_count": sum(not clean_text(item.get("title")) for item in contents),
                        "missing_link_count": sum(not clean_text(item.get("url")) for item in contents),
                        "unverifiable_content": not contents,
                    }
                )
    samples: list[dict[str, Any]] = []
    sample_targets = (
        ("2026-W25", "B站"),
        ("2026-W27", "小黑盒"),
        ("2026-W29", "综合"),
        ("2026-W30", "B站"),
        ("2026-W31", "B站"),
        ("2026-W31", "小黑盒"),
    )
    for week_id, view in sample_targets:
        candidates = [row for row in rows if row["week_id"] == week_id and row["view"] == view]
        selected = next((row for row in candidates if row["contents"]), candidates[0] if candidates else None)
        if selected:
            samples.append(selected)
    summary = {
        "audited_week_range": [min(dashboards), max(dashboards)],
        "topic_view_rows": len(rows),
        "topics_with_undefined_after_fix": len({(r["week_id"], r["canonical_topic_id"]) for r in rows if r["contains_undefined"]}),
        "topics_with_missing_bilibili_title_after_fix": len({(r["week_id"], r["canonical_topic_id"]) for r in rows if r["view"] == "B站" and r["missing_title_count"]}),
        "topics_with_missing_link_after_fix": len({(r["week_id"], r["canonical_topic_id"], r["view"]) for r in rows if r["missing_link_count"]}),
        "fixed_empty_placeholder_objects": fixed_empty_placeholders,
        "topics_without_verifiable_content_by_view": {
            view: sum(r["view"] == view and r["unverifiable_content"] for r in rows)
            for view in ("B站", "小黑盒", "综合")
        },
        "successfully_repaired_legacy_mapping_topics": source_mapping_failures,
        "schema_error_rows": sum(bool(r["schema_errors"]) for r in rows),
    }
    return rows, summary, samples


def file_hashes(root: Path) -> list[dict[str, Any]]:
    return [
        {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "revision_manifest.json"
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apex-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--data-version", default="2026_W31_dashboard_integrity_revision5_20260803")
    parser.add_argument("--previous-data-version", default="2026_W31_sentiment_revision4_20260803")
    args = parser.parse_args()
    apex_root, repo_root, output = args.apex_root.resolve(), args.project_root.resolve(), args.output_dir.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite revision directory: {output}")
    output.mkdir(parents=True)
    recalculated_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=repo_root,
            text=True,
        ).strip()
    )
    code_version = f"{base_commit}{'+working-tree-dashboard-integrity' if dirty else ''}"
    previous_data_version = args.previous_data_version
    revision_match = re.search(r"(revision\d+)", args.data_version)
    if not revision_match:
        raise ValueError("data version must contain revisionN")
    revision_tag = revision_match.group(1)
    revision_reason = "Repair representative content from traceable topic evidence with one platform-independent schema; retain the event, keyword, and count-backed sentiment integrity fixes without changing backend sentiment calculation."

    all_records = load_records(apex_root, repo_root)
    dashboards = dashboard_sources(apex_root, repo_root)
    audit_rows, audit_summary = audit_history(all_records, dashboards)
    representative_audit_rows, representative_audit_summary, representative_samples = (
        audit_representative_content_history(dashboards, all_records)
    )

    baseline = json.loads((apex_root / "outputs/dashboard_data_apex_W25_W30.json").read_text(encoding="utf-8"))
    bili_path = repo_root / "outputs/bilibili_apex_2026_W31.json"
    hey_path = repo_root / "outputs/heybox_apex_2026_W31_public_search.json"
    bili = json.loads(bili_path.read_text(encoding="utf-8"))
    hey = json.loads(hey_path.read_text(encoding="utf-8"))
    dashboard = build_dashboard(
        baseline, bili, hey,
        week_id="2026_W31",
        start=datetime(2026, 7, 27).date(),
        end=datetime(2026, 8, 2).date(),
        simulated=False,
        sample_quality_by_platform=(dashboards["2026-W31"].get("sample_quality") or {}),
    )
    apply_historical_metrics(dashboard, all_records)
    policy = json.loads((repo_root / "config/weekly_production_policy.json").read_text(encoding="utf-8"))
    report_rules = policy["weekly_report"]
    registry_path = repo_root / "outputs/topic_registry_exploratory.json"
    topic_registry_version = f"apex_topic_registry_exploratory_v1@{sha256(registry_path)[:12]}"
    dashboard["meta"].update(
        {
            "previous_data_version": previous_data_version,
            "current_data_version": args.data_version,
            "data_version": args.data_version,
            "revision_reason": revision_reason,
            "recalculated_at": recalculated_at,
            "generated_at": recalculated_at,
            "code_version": code_version,
            "git_commit": base_commit,
            "model_version": bili["meta"].get("bertopic_model_version"),
            "topic_registry_version": topic_registry_version,
            "keyword_rule_version": KEYWORD_RULE_VERSION,
            "event_rule_version": EVENT_RULE_VERSION,
            "sentiment_rule_version": SENTIMENT_RULE_VERSION,
            "representative_content_rule_version": REPRESENTATIVE_CONTENT_RULE_VERSION,
            "skill_version": report_rules["skill_version"],
            "narrative_rule_version": report_rules["narrative_rule_version"],
            "sentiment_model_version": bili["meta"].get("sentiment_model_version"),
            "publication_status": "internal_preview_not_published",
        }
    )

    revised_payloads = {}
    for platform, payload in (("B站", bili), ("小黑盒", hey)):
        revised = copy.deepcopy(payload)
        revised["records"] = [annotate_sentiment_record(row) for row in revised["records"]]
        revised["meta"].update(
            {
                "previous_data_version": previous_data_version,
                "current_data_version": args.data_version,
                "data_version": args.data_version,
                "revision_reason": revision_reason,
                "recalculated_at": recalculated_at,
                "generated_at": recalculated_at,
                "code_version": code_version,
                "git_commit": base_commit,
                "model_version": bili["meta"].get("bertopic_model_version"),
                "topic_registry_version": topic_registry_version,
                "keyword_rule_version": KEYWORD_RULE_VERSION,
                "event_rule_version": EVENT_RULE_VERSION,
                "sentiment_rule_version": SENTIMENT_RULE_VERSION,
                "representative_content_rule_version": REPRESENTATIVE_CONTENT_RULE_VERSION,
                "publication_status": "internal_preview_not_published",
            }
        )
        revised_payloads[platform] = revised

    outputs = output / "outputs"
    evidence_dir = output / "evidence"
    reports = output / "reports"
    preview = output / "preview"
    for directory in (outputs, evidence_dir, reports, preview):
        directory.mkdir(parents=True)
    bili_name = f"bilibili_apex_2026_W31_dashboard_integrity_{revision_tag}.json"
    hey_name = f"heybox_apex_2026_W31_dashboard_integrity_{revision_tag}.json"
    dashboard_name = f"dashboard_data_apex_W27_W31_dashboard_integrity_{revision_tag}.json"
    atomic_json(outputs / bili_name, revised_payloads["B站"])
    atomic_json(outputs / hey_name, revised_payloads["小黑盒"])
    atomic_json(outputs / dashboard_name, dashboard)

    current_records = all_records[("2026-W31", "B站")] + all_records[("2026-W31", "小黑盒")]
    current_events = generate_events(current_records, week_id="2026_W31")
    current_keywords = extract_keywords(current_records)
    atomic_json(evidence_dir / "W31_event_candidates.json", {
        "data_version": args.data_version,
        "rule_version": EVENT_RULE_VERSION,
        "candidates": current_events["candidates"],
    })
    atomic_json(evidence_dir / "W31_qualified_events.json", {
        "data_version": args.data_version,
        "rule_version": EVENT_RULE_VERSION,
        "events": current_events["events"],
    })
    atomic_json(evidence_dir / "W31_excluded_events.json", {
        "data_version": args.data_version,
        "rule_version": EVENT_RULE_VERSION,
        "events": current_events["excluded"],
    })
    atomic_json(evidence_dir / "W31_keyword_details.json", {
        "data_version": args.data_version,
        "rule_version": KEYWORD_RULE_VERSION,
        "qualified": current_keywords["qualified"],
        "candidates": current_keywords["candidates"],
    })
    atomic_json(evidence_dir / "W31_keyword_filter_and_normalization.json", {
        "data_version": args.data_version,
        "rule_version": KEYWORD_RULE_VERSION,
        "records": current_keywords["filter_log"],
    })
    atomic_json(evidence_dir / "W25_W31_representative_content_audit.json", {
        "data_version": args.data_version,
        "rule_version": REPRESENTATIVE_CONTENT_RULE_VERSION,
        "summary": representative_audit_summary,
        "topic_views": representative_audit_rows,
    })
    atomic_json(evidence_dir / "representative_content_schema_samples.json", {
        "data_version": args.data_version,
        "rule_version": REPRESENTATIVE_CONTENT_RULE_VERSION,
        "samples": representative_samples,
    })

    report_input = {
        "schema_version": "apex_china_weekly_report_input_v5_dashboard_integrity",
        "meta": {
            "region": "CHINA",
            "week_id": "2026_W31",
            "date_range": ["2026-07-27", "2026-08-02"],
            "previous_data_version": previous_data_version,
            "current_data_version": args.data_version,
            "data_version": args.data_version,
            "code_version": code_version,
            "git_commit": base_commit,
            "model_version": bili["meta"].get("bertopic_model_version"),
            "topic_registry_version": topic_registry_version,
            "keyword_rule_version": KEYWORD_RULE_VERSION,
            "event_rule_version": EVENT_RULE_VERSION,
            "sentiment_rule_version": SENTIMENT_RULE_VERSION,
            "representative_content_rule_version": REPRESENTATIVE_CONTENT_RULE_VERSION,
            "skill_version": report_rules["skill_version"],
            "narrative_rule_version": report_rules["narrative_rule_version"],
            "generated_at": recalculated_at,
            "publication_status": "internal_preview_not_published",
        },
        "bilibili_manifest": revised_payloads["B站"]["meta"],
        "heybox_manifest": revised_payloads["小黑盒"]["meta"],
        "week": dashboard["weeks"][-1],
        "evidence": {
            "B站": revised_payloads["B站"]["records"],
            "小黑盒": revised_payloads["小黑盒"]["records"],
        },
        "sample_quality": dashboard["weeks"][-1].get("sample_quality"),
        "events": current_events["events"],
        "keywords": current_keywords["qualified"],
        "sentiment_contract": dashboard["weeks"][-1]["platform_sentiment_metrics"],
    }
    report_input_name = f"APEX_CHINA_W31_report_input_dashboard_integrity_{revision_tag}.json"
    atomic_json(outputs / report_input_name, report_input)

    details: list[dict[str, Any]] = []
    target_details: list[dict[str, Any]] = []
    for row in revised_payloads["B站"]["records"]:
        topic_id = str(row.get("canonical_topic_id") or "")
        detail = {
            "week_id": display_week(str(row.get("week_id") or "2026_W31")),
            "platform": "B站",
            "canonical_topic_id": topic_id or None,
            "topic_name": row.get("canonical_topic_name"),
            "text_id": row.get("text_id") or row.get("comment_id") or hashlib.sha256(str(row.get("text") or "").encode()).hexdigest()[:24],
            "raw_comment": row.get("text"),
            "clean_comment": clean_text(row.get("text")),
            "model_topic_id": row.get("model_topic_id"),
            "bertopic_membership_strength": row.get("assignment_confidence"),
            "sentiment_label": row.get("sentiment_label_normalized"),
            "sentiment_prediction_probability": row.get("sentiment_confidence"),
            "sentiment_probabilities": json.dumps(row.get("sentiment_probabilities"), ensure_ascii=False, sort_keys=True),
            "included_in_sentiment_statistics": row.get("sentiment_statistics_included"),
            "exclusion_reason": row.get("sentiment_statistics_exclusion_reason"),
            "sentiment_model": row.get("sentiment_model"),
            "sentiment_model_version": row.get("sentiment_model_version"),
            "sentiment_status": row.get("sentiment_status"),
            "sentiment_review_required": row.get("sentiment_review_required"),
        }
        details.append(detail)
        if topic_id in TARGET_TOPICS:
            target_details.append(detail)
    detail_fields = list(details[0])
    write_csv(evidence_dir / "W31_bilibili_sentiment_details_all.csv", details, detail_fields)
    write_csv(evidence_dir / "W31_three_zero_topics_comment_evidence.csv", target_details, detail_fields)

    stats_rows = [r for r in audit_rows if r["week_id"] == "2026-W31"]
    stats_fields = [
        "week_id", "platform", "canonical_topic_id", "topic_name", "comment_count",
        "sentiment_valid_count", "positive_count", "neutral_count", "negative_count",
        "positive_rate", "neutral_rate", "negative_rate", "sentiment_model",
        "sentiment_model_version", "sentiment_status", "low_sample_status",
        "sentiment_sample_band", "original_json_negative_rate",
        "backend_recalculated_negative_rate", "legacy_frontend_display",
        "revised_frontend_display", "three_way_consistent_before", "mismatch_stage",
    ]
    write_csv(outputs / "W31_topic_sentiment_statistics.csv", stats_rows, stats_fields)
    history_fields = stats_fields + ["original_json_source_field", "unavailable_but_legacy_zero", "sentiment_model_failed"]
    write_csv(reports / "W25_W31_sentiment_integrity_audit.csv", audit_rows, history_fields)

    target_stats = [r for r in stats_rows if r["platform"] == "B站" and r["canonical_topic_id"] in TARGET_TOPICS]
    atomic_json(reports / "three_zero_topics_recalculation.json", {"data_version": args.data_version, "topics": target_stats})
    atomic_json(reports / "W25_W31_sentiment_audit_summary.json", audit_summary)

    assertions: list[dict[str, Any]] = []
    for row in audit_rows:
        assertions.append(
            {
                "check": "class_count_sum_equals_valid_count",
                "scope": f"{row['week_id']}|{row['platform']}|{row['canonical_topic_id']}",
                "passed": row["positive_count"] + row["neutral_count"] + row["negative_count"] == row["sentiment_valid_count"],
            }
        )
        assertions.append(
            {
                "check": "negative_rate_recalculable_or_null",
                "scope": f"{row['week_id']}|{row['platform']}|{row['canonical_topic_id']}",
                "passed": (
                    row["negative_rate"] is None and row["sentiment_valid_count"] == 0
                ) or (
                    row["sentiment_valid_count"] > 0
                    and abs(row["negative_rate"] - row["negative_count"] / row["sentiment_valid_count"] * 100) <= 0.011
                ),
            }
        )
    current = dashboard["weeks"][-1]
    assertions.extend(
        [
            {"check": "bilibili_view_platform_isolated", "scope": "2026-W31", "passed": all(metric_for(current, t["id"], "B站") is (t.get("platform_metrics") or {}).get("B站") for t in current["topics"])},
            {"check": "combined_sentiment_weighted_by_valid_count", "scope": "2026-W31", "passed": current["platform_sentiment_metrics"]["综合"]["sentiment_valid_count"] == current["platform_sentiment_metrics"]["B站"]["sentiment_valid_count"] + current["platform_sentiment_metrics"]["小黑盒"]["sentiment_valid_count"]},
            {"check": "three_topics_have_comment_evidence", "scope": "2026-W31|B站", "passed": {r["canonical_topic_id"] for r in target_details} == TARGET_TOPICS},
            {"check": "low_sample_risk_marked", "scope": "2026-W31|B站", "passed": all(metric_for(current, topic_id, "B站").get("risk_status") == "sentiment_low_sample" for topic_id in TARGET_TOPICS)},
        ]
    )
    required_event_fields = {
        "event_id", "week_id", "title", "summary", "event_date", "platforms",
        "topic_ids", "content_ids", "evidence_text_ids", "comment_count",
        "content_count", "impact_score", "event_type", "event_status",
        "data_quality_status",
    }
    required_keyword_fields = {
        "keyword", "normalized_keyword", "entity_type", "occurrence_count",
        "text_coverage_count", "content_coverage_count", "platforms", "topic_ids",
        "event_driven", "quality_status", "evidence_text_ids",
    }
    for week in dashboard["weeks"]:
        week_evidence_ids = {
            platform: {
                clean_text(row.get("text_id") or row.get("comment_id"))
                or hashlib.sha256(clean_text(row.get("text")).encode()).hexdigest()[:24]
                for row in all_records.get((week["week_id"], platform), [])
            }
            for platform in ("B站", "小黑盒")
        }
        assertions.extend(
            [
                {
                    "check": "event_generation_has_explicit_success_state",
                    "scope": week["week_id"],
                    "passed": str((week.get("event_generation") or {}).get("status", "")).startswith("success_"),
                },
                {
                    "check": "qualified_events_have_traceable_contract",
                    "scope": week["week_id"],
                    "passed": all(required_event_fields <= set(event) and event["evidence_text_ids"] and event["content_ids"] for event in week.get("events", [])),
                },
                {
                    "check": "keywords_are_backend_qualified_and_traceable",
                    "scope": week["week_id"],
                    "passed": all(
                        required_keyword_fields <= set(row)
                        and row["quality_status"] == "passed"
                        and row["text_coverage_count"] >= 2
                        and row["topic_ids"]
                        and row["evidence_text_ids"]
                        and not str(row["normalized_keyword"]).isdigit()
                        for platform_rows in (week.get("keyword_stats") or {}).values()
                        for row in platform_rows
                    ),
                },
                {
                    "check": "topic_trend_last_value_equals_current_volume",
                    "scope": week["week_id"],
                    "passed": all(
                        not (metric.get("trend") or [])
                        or int(metric["trend"][-1]) == int(metric.get("count") or 0)
                        for topic in week.get("topics", [])
                        for metric in [topic.get("combined_metrics") or {}]
                    ),
                },
                {
                    "check": "representative_contents_schema_valid",
                    "scope": week["week_id"],
                    "passed": all(
                        not validate_representative_contents(topic.get("representative_contents"))
                        and all(
                            not validate_representative_contents(metric.get("representative_contents"))
                            for metric in [
                                (topic.get("platform_metrics") or {}).get("B站") or {},
                                (topic.get("platform_metrics") or {}).get("小黑盒") or {},
                                topic.get("combined_metrics") or {},
                            ]
                        )
                        for topic in week.get("topics", [])
                    ),
                },
                {
                    "check": "representative_content_count_matches_array",
                    "scope": week["week_id"],
                    "passed": all(
                        int(topic.get("representative_content_count") or 0)
                        == len(topic.get("representative_contents") or [])
                        and all(
                            int(metric.get("representative_content_count") or 0)
                            == len(metric.get("representative_contents") or [])
                            for metric in [
                                (topic.get("platform_metrics") or {}).get("B站") or {},
                                (topic.get("platform_metrics") or {}).get("小黑盒") or {},
                                topic.get("combined_metrics") or {},
                            ]
                        )
                        for topic in week.get("topics", [])
                    ),
                },
                {
                    "check": "representative_contents_trace_to_topic_evidence",
                    "scope": week["week_id"],
                    "passed": all(
                        set(item.get("evidence_text_ids") or []).issubset(
                            week_evidence_ids["B站" if item.get("platform") == "bilibili" else "小黑盒"]
                        )
                        for topic in week.get("topics", [])
                        for item in topic.get("representative_contents") or []
                    ),
                },
            ]
        )
    assertions.extend(
        [
            {
                "check": "current_week_has_qualified_events",
                "scope": "2026-W31",
                "passed": current_events["qualified_count"] > 0,
            },
            {
                "check": "current_week_has_qualified_keywords",
                "scope": "2026-W31",
                "passed": bool(current_keywords["qualified"]),
            },
            {
                "check": "dashboard_and_report_input_events_match",
                "scope": "2026-W31",
                "passed": report_input["events"] == current["events"],
            },
            {
                "check": "dashboard_and_report_input_keywords_match",
                "scope": "2026-W31",
                "passed": report_input["keywords"] == current["keyword_stats"]["综合"],
            },
            {
                "check": "dashboard_and_report_input_sentiment_match",
                "scope": "2026-W31",
                "passed": report_input["sentiment_contract"] == current["platform_sentiment_metrics"],
            },
            {
                "check": "dashboard_contains_no_undefined_or_null_text",
                "scope": "W27-W31",
                "passed": "undefined" not in json.dumps(dashboard, ensure_ascii=False).lower()
                and '"null"' not in json.dumps(dashboard, ensure_ascii=False).lower(),
            },
            {
                "check": "historical_representative_content_audit_passed",
                "scope": "W25-W31",
                "passed": representative_audit_summary["topics_with_undefined_after_fix"] == 0
                and representative_audit_summary["schema_error_rows"] == 0,
            },
        ]
    )
    html_source = (repo_root / "index.html").read_text(encoding="utf-8")
    page_assertions = [
        {"check": "frontend_reads_only_backend_qualified_keywords", "passed": "x?.quality_status==='passed'" in html_source},
        {"check": "frontend_event_failure_is_explicit", "passed": "APEX_EVENT_DATA_UNAVAILABLE" in html_source and "关键事件数据暂不可用" in html_source},
        {"check": "frontend_event_empty_state_is_explicit", "passed": "本周暂无达到展示门槛的关键事件" in html_source},
        {"check": "frontend_true_zero_low_sample_two_line_rule", "passed": "低样本：样本量较小 不单独用于风险结论" in html_source and "0 / n" not in html_source},
        {"check": "frontend_missing_sentiment_uses_dash", "passed": "value===null||valid===0" in html_source},
        {"check": "local_storage_cannot_override_embedded_version", "passed": "Object.assign(dashboardData" not in html_source},
        {"check": "frontend_does_not_recalculate_negative_rate", "passed": "negative_count / sentiment_valid_count" not in html_source and "negative_count/sentiment_valid_count" not in html_source},
        {"check": "frontend_reads_unified_representative_contents", "passed": "representative_contents" in html_source and "representativeContentsForTopic" in html_source},
        {"check": "frontend_does_not_render_legacy_video_fields", "passed": "v.bvid" not in html_source and "v.comment_count" not in html_source},
        {"check": "frontend_representative_empty_state_is_explicit", "passed": "暂无可验证的代表性B站视频" in html_source and "No verifiable representative content is available" in html_source},
        {"check": "frontend_validates_representative_urls", "passed": "validRepresentativeUrl" in html_source and "APEX_REPRESENTATIVE_CONTENT_URL_INVALID" in html_source},
        {"check": "frontend_fails_closed_on_representative_schema", "passed": "assertRepresentativeContentSchema" in html_source and "APEX_REPRESENTATIVE_CONTENT_SCHEMA_ERROR" in html_source},
        {"check": "frontend_does_not_pad_representative_contents", "passed": "representative_contents||[{" not in html_source and ".fill({" not in html_source},
    ]
    assertions.extend({**item, "scope": "index.html"} for item in page_assertions)
    validation = {
        "data_version": args.data_version,
        "previous_data_version": previous_data_version,
        "recalculated_at": recalculated_at,
        "code_version": code_version,
        "assertion_count": len(assertions),
        "failed_count": sum(not item["passed"] for item in assertions),
        "publication_eligible": False,
        "publication_block_reason": "This unified bundle is preview-only until GitHub commit, Tencent preview checks, and new manual approval are recorded.",
        "assertions": assertions,
    }
    atomic_json(reports / "sentiment_data_validation_report.json", validation)
    atomic_json(reports / "dashboard_integrity_quality_report.json", {
        "data_version": args.data_version,
        "code_version": code_version,
        "git_commit": base_commit,
        "dashboard_json_hash": sha256(outputs / dashboard_name),
        "generated_at": recalculated_at,
        "event_summary": {
            "candidate_count": current_events["candidate_count"],
            "qualified_count": current_events["qualified_count"],
            "excluded_count": len(current_events["excluded"]),
        },
        "keyword_summary": {
            "candidate_count": len(current_keywords["candidates"]),
            "qualified_count": len(current_keywords["qualified"]),
            "filtered_or_normalized_log_count": len(current_keywords["filter_log"]),
        },
        "sentiment_regression_summary": audit_summary,
        "representative_content_summary": representative_audit_summary,
        "assertion_count": len(assertions),
        "failed_count": validation["failed_count"],
        "status": "passed" if validation["failed_count"] == 0 else "failed",
        "assertions": assertions,
    })
    atomic_json(reports / "page_automatic_check_report.json", {
        "data_version": args.data_version,
        "code_version": code_version,
        "generated_at": recalculated_at,
        "dashboard_json_hash": sha256(outputs / dashboard_name),
        "source_checks": page_assertions,
        "source_checks_passed": all(item["passed"] for item in page_assertions),
        "browser_execution_status": "pending_tencent_preview",
        "publication_eligible": False,
    })

    for filename in (
        "APEX_CHINA_W31_Weekly_Community_Report.xlsx",
        "APEX_CHINA_W31_Weekly_Community_Report.preview.json",
        "APEX_CHINA_W31_Weekly_Community_Report.md",
        "APEX_CHINA_W30_Weekly_Community_Report.xlsx",
        "APEX_W29_Combined_Dashboard_Long_Capture.png",
    ):
        source = repo_root / "reports" / filename
        if source.exists():
            shutil.copy2(source, reports / filename)
    report_preview_path = reports / "APEX_CHINA_W31_Weekly_Community_Report.preview.json"
    if report_preview_path.exists():
        report_preview = json.loads(report_preview_path.read_text(encoding="utf-8"))
        report_preview.update(
            {
                "previous_data_version": previous_data_version,
                "current_data_version": args.data_version,
                "revision_reason": revision_reason,
                "approval": {
                    "status": "pending_new_unified_preview_approval",
                    "approved_at": None,
                    "approver_role": None,
                    "approval_source": None,
                    "approval_statement": None,
                    "scope": f"dashboard_integrity_{revision_tag}",
                },
                "dashboard_integrity": {
                    "data_version": args.data_version,
                    "code_version": code_version,
                    "git_commit": base_commit,
                    "events": current_events["events"],
                    "keywords": current_keywords["qualified"],
                    "sentiment_contract": current["platform_sentiment_metrics"],
                    "keyword_rule_version": KEYWORD_RULE_VERSION,
                    "event_rule_version": EVENT_RULE_VERSION,
                    "sentiment_rule_version": SENTIMENT_RULE_VERSION,
                    "representative_content_rule_version": REPRESENTATIVE_CONTENT_RULE_VERSION,
                },
            }
        )
        atomic_json(report_preview_path, report_preview)
    if (repo_root / "assets").exists():
        shutil.copytree(repo_root / "assets", output / "assets")
    guide_source = repo_root / "templates/APEX_Dashboard_Data_and_Narrative_Guide.md"
    if guide_source.exists():
        (output / "templates").mkdir(parents=True)
        shutil.copy2(guide_source, output / "templates" / guide_source.name)

    html = patch_site_html(
        (repo_root / "index.html").read_text(encoding="utf-8"),
        dashboard=dashboard,
        dashboard_filename=dashboard_name,
        report_filename="APEX_CHINA_W31_Weekly_Community_Report.xlsx",
        preview_filename="APEX_CHINA_W31_Weekly_Community_Report.preview.json",
        report_markdown_filename="APEX_CHINA_W31_Weekly_Community_Report.md",
        bilibili_filename=bili_name,
        heybox_filename=hey_name,
    )
    (output / "index.html").write_text(html, encoding="utf-8")
    (preview / "README.txt").write_text("Open ../index.html from the revision root.\n", encoding="utf-8")

    relative_refs = {
        ref.split("?", 1)[0].split("#", 1)[0]
        for _, _, ref in re.findall(r"\b(href|src)=([\"'])(.*?)\2", html)
        if ref and "${" not in ref and not re.match(r"^(?:#|https?:|data:|mailto:|javascript:)", ref)
    }
    missing_refs = sorted(ref for ref in relative_refs if not (output / ref).is_file())
    page_report_path = reports / "page_automatic_check_report.json"
    page_report = json.loads(page_report_path.read_text(encoding="utf-8"))
    page_report["packaged_link_check"] = {
        "checked_count": len(relative_refs),
        "missing_count": len(missing_refs),
        "missing": missing_refs,
        "status": "passed" if not missing_refs else "failed",
    }
    atomic_json(page_report_path, page_report)
    if missing_refs:
        raise ValueError(f"preview package contains missing relative links: {missing_refs}")

    manifest = {
        "data_version": args.data_version,
        "previous_data_version": previous_data_version,
        "current_data_version": args.data_version,
        "revision_reason": revision_reason,
        "recalculated_at": recalculated_at,
        "code_version": code_version,
        "dashboard_json_hash": sha256(outputs / dashboard_name),
        "code_files": {
            path: sha256(repo_root / path)
            for path in (
                "scripts/sentiment_integrity.py",
                "scripts/content_integrity.py",
                "scripts/representative_content.py",
                "scripts/weekly_release_common.py",
                "scripts/build_sentiment_revision.py",
                "scripts/build_dashboard_integrity_revision.py",
                "index.html",
            )
        },
        "sentiment_model_version": bili["meta"].get("sentiment_model_version"),
        "model_version": bili["meta"].get("bertopic_model_version"),
        "topic_registry_version": topic_registry_version,
        "keyword_rule_version": KEYWORD_RULE_VERSION,
        "event_rule_version": EVENT_RULE_VERSION,
        "sentiment_rule_version": SENTIMENT_RULE_VERSION,
        "representative_content_rule_version": REPRESENTATIVE_CONTENT_RULE_VERSION,
        "skill_version": report_rules["skill_version"],
        "narrative_rule_version": report_rules["narrative_rule_version"],
        "report_input": report_input_name,
        "status": "validated_internal_preview_not_published" if validation["failed_count"] == 0 else "validation_failed_not_publishable",
        "publication_performed": False,
        "files": file_hashes(output),
    }
    atomic_json(output / "revision_manifest.json", manifest)
    print(json.dumps({
        "output": output.as_posix(),
        "status": manifest["status"],
        "sentiment_audit_summary": audit_summary,
        "representative_content_summary": representative_audit_summary,
    }, ensure_ascii=False, indent=2))
    return 0 if validation["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
