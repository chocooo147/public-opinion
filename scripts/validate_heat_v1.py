#!/usr/bin/env python3
"""Independent release gate for canonical APEX Heat v1.0."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from canonical_rules import load_canonical_rules
from heat_v1 import (
    LEGACY_PROXY_FIELDS,
    PLATFORMS,
    recalculate_dashboard_heat_v1,
    sha256_file,
)


def _display_week(value: str) -> str:
    return value.replace("_", "-")


def _week_number(value: str) -> tuple[int, int]:
    normalized = value.replace("-", "_")
    year, week = normalized.split("_W", 1)
    return int(year), int(week)


def _close(left: Any, right: Any, tolerance: float = 1e-6) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), abs_tol=tolerance, rel_tol=0)
    return left == right


def _heat_snapshot(topic: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "topic": {
            key: topic.get(key)
            for key in (
                "heat_score",
                "heat_status",
                "heat_rule_version",
                "heat_rule_sha256",
            )
        }
    }
    for platform in PLATFORMS:
        metric = (topic.get("platform_metrics") or {}).get(platform) or {}
        result[platform] = {
            key: metric.get(key)
            for key in (
                "heat_score",
                "heat_display",
                "heat_status",
                "heat_eligibility_status",
                "heat_eligibility",
                "heat_score_status",
                "heat_rule_version",
                "heat_rule_sha256",
                "heat_components",
                "heat_missing_components",
                "heat_raw_input_summary",
                "heat_provenance",
            )
        }
    combined = topic.get("combined_metrics") or {}
    result["综合"] = {
        key: combined.get(key)
        for key in (
            "heat_score",
            "heat_status",
            "heat_score_status",
            "heat_rule_version",
            "heat_rule_sha256",
            "heat_platform_weights",
            "heat_blocked_platforms",
            "heat_eligible_platforms",
            "heat_ineligible_platforms",
            "heat_platform_coverage",
            "heat_eligibility_policy_version",
            "heat_aggregation",
            "heat_provenance",
        )
    }
    return result


def _compare_structure(
    actual: Any,
    expected: Any,
    *,
    path: str,
    errors: list[str],
) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            errors.append(f"{path} is not an object")
            return
        if set(actual) != set(expected):
            errors.append(
                f"{path} keys differ: {sorted(actual)} != {sorted(expected)}"
            )
            return
        for key in expected:
            _compare_structure(
                actual[key], expected[key], path=f"{path}.{key}", errors=errors
            )
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            errors.append(f"{path} list differs")
            return
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            _compare_structure(
                actual_item,
                expected_item,
                path=f"{path}[{index}]",
                errors=errors,
            )
        return
    if not _close(actual, expected):
        errors.append(f"{path} differs: {actual!r} != {expected!r}")


def validate_heat_v1_dashboard(
    dashboard: dict[str, Any],
    bilibili_payload: dict[str, Any],
    heybox_payload: dict[str, Any],
    *,
    target_week_id: str,
    business_rules: dict[str, Any],
    source_artifact_hashes: dict[str, str],
) -> dict[str, Any]:
    policy = business_rules["_heat_policy"]
    policy_hash = business_rules["_heat_policy_sha256"]
    target_display = _display_week(target_week_id)
    errors: list[str] = []
    missing_input_blocks: list[str] = []

    if policy.get("status") != "approved":
        errors.append("Heat policy is not approved")
    eligibility_policy = policy.get("platform_eligibility") or {}
    eligibility_platforms = eligibility_policy.get("platforms") or {}
    required_components = set(eligibility_policy.get("required_components") or [])
    if required_components != set(policy["formula"]["weights"]):
        errors.append("Heat platform eligibility does not require the canonical five components")
    expected_eligibility = {
        platform: (eligibility_platforms.get(platform) or {}).get("status")
        for platform in PLATFORMS
    }
    if expected_eligibility != {
        "B站": "ELIGIBLE",
        "小黑盒": "INELIGIBLE_REACH_UNAVAILABLE",
    }:
        errors.append("Heat platform eligibility status differs from approved policy")
    if _week_number(target_week_id) < _week_number(policy["effective_from_week"]):
        legacy_errors = []
        for week in dashboard.get("weeks") or []:
            if week.get("heat_rule_version") == policy["rule_version"]:
                legacy_errors.append(
                    f"legacy week {week.get('week_id')} was relabeled as Heat v1.0"
                )
        return {
            "rule_version": policy["rule_version"],
            "rule_sha256": policy_hash,
            "target_week_id": target_week_id,
            "status": "not_applicable_legacy_week",
            "recalculation_match": not legacy_errors,
            "release_ready": not legacy_errors,
            "errors": legacy_errors,
            "missing_input_blocks": [],
        }

    weeks = dashboard.get("weeks") or []
    target = next((week for week in weeks if week.get("week_id") == target_display), None)
    if target is None:
        errors.append(f"dashboard has no {target_display}")
        return {
            "rule_version": policy["rule_version"],
            "rule_sha256": policy_hash,
            "recalculation_match": False,
            "release_ready": False,
            "errors": errors,
            "missing_input_blocks": missing_input_blocks,
        }

    boundary = (dashboard.get("meta") or {}).get("heat_version_boundary") or {}
    expected_boundary = {
        "legacy_through_week": _display_week(policy["legacy_through_week"]),
        "canonical_from_week": _display_week(policy["effective_from_week"]),
        "legacy_recalculated": False,
        "cross_version_scores_directly_comparable": False,
    }
    if boundary != expected_boundary:
        errors.append("Heat Legacy/v1.0 version boundary is missing or incorrect")

    expected_eligible_platforms = [
        platform
        for platform in PLATFORMS
        if expected_eligibility.get(platform) == "ELIGIBLE"
    ]
    expected_ineligible_platforms = {
        platform: expected_eligibility[platform]
        for platform in PLATFORMS
        if expected_eligibility.get(platform) != "ELIGIBLE"
    }
    expected_coverage = "partial" if expected_ineligible_platforms else "full"
    if target.get("heat_eligibility_policy_version") != eligibility_policy.get(
        "policy_version"
    ):
        errors.append("target week eligibility policy version is missing or incorrect")
    if target.get("heat_eligible_platforms") != expected_eligible_platforms:
        errors.append("target week eligible platforms differ from policy")
    if target.get("heat_ineligible_platforms") != expected_ineligible_platforms:
        errors.append("target week ineligible platforms differ from policy")
    if target.get("heat_platform_coverage") != expected_coverage:
        errors.append("target week Heat platform coverage is incorrect")

    effective = _week_number(policy["effective_from_week"])
    for week in weeks:
        week_key = _week_number(str(week.get("week_id")))
        if week_key < effective:
            if week.get("heat_rule_version") == policy["rule_version"]:
                errors.append(f"legacy week {week['week_id']} was relabeled as Heat v1.0")
            continue
        if week.get("heat_rule_version") != policy["rule_version"]:
            errors.append(f"{week['week_id']} does not declare Heat v1.0")

    try:
        expected_dashboard = recalculate_dashboard_heat_v1(
            dashboard,
            bilibili_payload,
            heybox_payload,
            target_week_id=target_week_id,
            policy=policy,
            policy_hash=policy_hash,
            source_artifact_hashes=source_artifact_hashes,
        )
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"independent Heat recomputation failed: {exc}")
        expected_dashboard = None

    if expected_dashboard is not None:
        expected_week = next(
            week
            for week in expected_dashboard["weeks"]
            if week["week_id"] == target_display
        )
        expected_topics = {str(topic["id"]): topic for topic in expected_week["topics"]}
        for topic in target.get("topics") or []:
            topic_id = str(topic["id"])
            expected_topic = expected_topics.get(topic_id)
            if expected_topic is None:
                errors.append(f"unexpected Heat topic {topic_id}")
                continue
            _compare_structure(
                _heat_snapshot(topic),
                _heat_snapshot(expected_topic),
                path=f"{target_display}.{topic_id}",
                errors=errors,
            )

            for platform in PLATFORMS:
                metric = (topic.get("platform_metrics") or {}).get(platform) or {}
                eligibility_status = expected_eligibility.get(platform)
                if metric.get("heat_eligibility_status") != eligibility_status:
                    errors.append(
                        f"{target_display}.{topic_id}.{platform} eligibility status differs from policy"
                    )
                for legacy_field in LEGACY_PROXY_FIELDS:
                    if legacy_field in metric:
                        errors.append(
                            f"{target_display}.{topic_id}.{platform} retains legacy proxy field {legacy_field}"
                        )
                provenance = metric.get("heat_provenance") or {}
                if provenance.get("proxy_used") is not False:
                    errors.append(
                        f"{target_display}.{topic_id}.{platform} does not prove proxy_used=false"
                    )
                if (
                    eligibility_status == "ELIGIBLE"
                    and metric.get("heat_status") == "blocked_missing_components"
                ):
                    missing_input_blocks.append(
                        f"{topic_id}.{platform}: "
                        + ", ".join(metric.get("heat_missing_components") or [])
                    )

                if eligibility_status != "ELIGIBLE":
                    if metric.get("heat_score") is not None:
                        errors.append(
                            f"{target_display}.{topic_id}.{platform} ineligible platform has a Heat score"
                        )
                    if metric.get("heat_display") != "N/A":
                        errors.append(
                            f"{target_display}.{topic_id}.{platform} ineligible platform does not display N/A"
                        )
                    if metric.get("heat_status") != "not_applicable_platform_ineligible":
                        errors.append(
                            f"{target_display}.{topic_id}.{platform} ineligible platform has the wrong Heat status"
                        )
                    if provenance.get("included_in_composite") is not False:
                        errors.append(
                            f"{target_display}.{topic_id}.{platform} ineligible platform entered the composite"
                        )
                elif metric.get("heat_status") == "calculated":
                    components = metric.get("heat_components") or {}
                    scores = {
                        "discussion_intensity": (components.get("discussion_intensity") or {}).get("score"),
                        "discussion_breadth": (components.get("discussion_breadth") or {}).get("score"),
                        "engagement_depth": (components.get("engagement_depth") or {}).get("score"),
                        "reach": (components.get("reach") or {}).get("score"),
                        "momentum": (components.get("momentum") or {}).get("score"),
                    }
                    if not all(isinstance(value, (int, float)) for value in scores.values()):
                        errors.append(
                            f"{target_display}.{topic_id}.{platform} calculated Heat lacks a component score"
                        )
                    else:
                        direct = round(
                            sum(
                                float(scores[key]) * float(policy["formula"]["weights"][key])
                                for key in policy["formula"]["weights"]
                            ),
                            int(policy["formula"]["rounding_decimals"]),
                        )
                        if not _close(metric.get("heat_score"), direct):
                            errors.append(
                                f"{target_display}.{topic_id}.{platform} stored Heat does not equal direct component recomputation"
                            )

            combined = topic.get("combined_metrics") or {}
            if combined.get("heat_eligible_platforms") != expected_eligible_platforms:
                errors.append(f"{target_display}.{topic_id}.综合 eligible platforms differ from policy")
            if combined.get("heat_ineligible_platforms") != expected_ineligible_platforms:
                errors.append(f"{target_display}.{topic_id}.综合 ineligible platforms differ from policy")
            if combined.get("heat_platform_coverage") != expected_coverage:
                errors.append(f"{target_display}.{topic_id}.综合 platform coverage is incorrect")
            weights = combined.get("heat_platform_weights") or {}
            if any(platform not in expected_eligible_platforms for platform in weights):
                errors.append(f"{target_display}.{topic_id}.综合 weights include an ineligible platform")
            if any(platform in expected_ineligible_platforms for platform in combined.get("heat_blocked_platforms") or []):
                errors.append(f"{target_display}.{topic_id}.综合 treats an ineligible platform as blocked")
            if combined.get("heat_status") == "calculated":
                if not math.isclose(sum(map(float, weights.values())), 1.0, abs_tol=1e-6):
                    errors.append(f"{target_display}.{topic_id}.综合 eligible platform weights do not sum to 1")
                direct = 0.0
                for platform, weight in weights.items():
                    platform_score = topic["platform_metrics"][platform]["heat_score"]
                    direct += float(platform_score) * float(weight)
                direct = round(direct, int(policy["formula"]["rounding_decimals"]))
                if not _close(combined.get("heat_score"), direct):
                    errors.append(
                        f"{target_display}.{topic_id}.综合 stored Heat does not equal direct platform recomputation"
                    )

    return {
        "rule_version": policy["rule_version"],
        "rule_sha256": policy_hash,
        "target_week_id": target_week_id,
        "recalculation_match": not errors,
        "release_ready": not errors and not missing_input_blocks,
        "errors": errors,
        "missing_input_blocks": sorted(set(missing_input_blocks)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--week", required=True)
    parser.add_argument("--dashboard", type=Path, required=True)
    parser.add_argument("--bilibili", type=Path, required=True)
    parser.add_argument("--heybox", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rules = load_canonical_rules(args.root.resolve())
    dashboard = json.loads(args.dashboard.read_text(encoding="utf-8"))
    bilibili = json.loads(args.bilibili.read_text(encoding="utf-8"))
    heybox = json.loads(args.heybox.read_text(encoding="utf-8"))
    result = validate_heat_v1_dashboard(
        dashboard,
        bilibili,
        heybox,
        target_week_id=args.week,
        business_rules=rules,
        source_artifact_hashes={
            "B站": sha256_file(args.bilibili),
            "小黑盒": sha256_file(args.heybox),
        },
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["recalculation_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
