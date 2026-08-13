#!/usr/bin/env python3
"""Canonical APEX Heat v1.0 calculation from real Topic evidence.

This module is the production calculator.  It never substitutes a proxy for a
missing component: an evidenced platform with any unavailable component has a
null Heat score, and the corresponding composite Heat is blocked.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any


PLATFORMS = ("B站", "小黑盒")
ELIGIBLE = "ELIGIBLE"
INELIGIBLE_HEAT_STATUS = "not_applicable_platform_ineligible"
LEGACY_PROXY_FIELDS = (
    "discussion_coverage",
    "discussion_volume_score",
    "influence_score",
    "engagement_score",
    "growth_score",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_json_artifact_sha256(payload: dict[str, Any]) -> str:
    """Hash the exact bytes written by weekly_release_common.atomic_json."""

    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(float(value), digits)


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _quantile_type_7(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot calculate a quantile over an empty cohort")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _normalize_cohort(
    raw_by_topic: dict[str, float],
    *,
    long_tail: bool,
    policy: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return inspectable same-platform/week normalization details."""

    if not raw_by_topic:
        return {}
    values = list(raw_by_topic.values())
    transform = policy["transformation_and_normalization"]
    outlier = transform["outlier_control"]
    q1 = _quantile_type_7(values, float(outlier["lower_quantile"]))
    q3 = _quantile_type_7(values, float(outlier["upper_quantile"]))
    iqr = q3 - q1
    multiplier = float(outlier["iqr_multiplier"])
    lower_fence = q1 - multiplier * iqr
    upper_fence = q3 + multiplier * iqr
    capped = {
        topic_id: _clamp(value, lower_fence, upper_fence)
        for topic_id, value in raw_by_topic.items()
    }
    transformed = {
        topic_id: math.log1p(max(0.0, value)) if long_tail else value
        for topic_id, value in capped.items()
    }
    cohort = list(transformed.values())
    mean = sum(cohort) / len(cohort)
    population_variance = sum((value - mean) ** 2 for value in cohort) / len(cohort)
    population_std = math.sqrt(population_variance)
    z_low, z_high = map(float, transform["standardization"]["z_clip"])
    zero_dispersion = float(
        transform["standardization"]["zero_dispersion_score"]
    )
    result: dict[str, dict[str, Any]] = {}
    for topic_id, raw_value in raw_by_topic.items():
        capped_value = capped[topic_id]
        transformed_value = transformed[topic_id]
        if population_std == 0:
            z_score = 0.0
            clipped_z = 0.0
            score = zero_dispersion
        else:
            z_score = (transformed_value - mean) / population_std
            clipped_z = _clamp(z_score, z_low, z_high)
            score = _clamp(50.0 + clipped_z * (50.0 / 3.0), 0.0, 100.0)
        result[topic_id] = {
            "raw_value": _round(raw_value),
            "outlier_control": {
                "method": outlier["method"],
                "q1": _round(q1),
                "q3": _round(q3),
                "iqr": _round(iqr),
                "lower_fence": _round(lower_fence),
                "upper_fence": _round(upper_fence),
                "capped_value": _round(capped_value),
            },
            "log_transform": "natural_log1p" if long_tail else "not_applicable",
            "transformed_value": _round(transformed_value),
            "standardization": {
                "method": transform["standardization"]["method"],
                "cohort_size": len(cohort),
                "mean": _round(mean),
                "population_std": _round(population_std),
                "z_score": _round(z_score),
                "clipped_z": _round(clipped_z),
            },
            "score": _round(score),
        }
    return result


def _identifier(record: dict[str, Any], fields: list[str]) -> str | None:
    for field in fields:
        value = record.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _mapped_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in payload.get("records") or []
        if row.get("canonical_topic_id") and not row.get("is_outlier")
    ]


def _platform_eligibility(policy: dict[str, Any], platform: str) -> dict[str, Any]:
    eligibility = policy.get("platform_eligibility") or {}
    platform_policy = (eligibility.get("platforms") or {}).get(platform)
    if not isinstance(platform_policy, dict) or not platform_policy.get("status"):
        raise ValueError(f"Heat policy has no eligibility status for {platform}")
    return platform_policy


def _platform_raw_inputs(
    *,
    platform: str,
    topics: list[dict[str, Any]],
    records: list[dict[str, Any]],
    previous_week: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, Any]]]:
    platform_policy = policy["platform_inputs"][platform]
    topic_ids = [str(topic["id"]) for topic in topics]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["canonical_topic_id"])].append(record)

    previous_topics = {
        str(topic["id"]): topic for topic in previous_week.get("topics") or []
    }
    current_total = sum(len(grouped.get(topic_id, [])) for topic_id in topic_ids)
    previous_total = sum(
        int((topic.get("platform_metrics") or {}).get(platform, {}).get("count") or 0)
        for topic in previous_week.get("topics") or []
    )
    raw: dict[str, dict[str, float]] = {
        "discussion_intensity": {},
        "breadth_sources": {},
        "breadth_participants": {},
        "engagement_depth": {},
        "reach": {},
        "momentum": {},
    }
    details: dict[str, dict[str, Any]] = {}

    for topic_id in topic_ids:
        rows = grouped.get(topic_id, [])
        detail: dict[str, Any] = {
            "valid_evidence_count": len(rows),
            "missing_components": [],
        }
        details[topic_id] = detail
        if not rows:
            detail["status"] = "not_applicable_no_platform_evidence"
            continue

        raw["discussion_intensity"][topic_id] = float(len(rows))

        source_fields = list(platform_policy["content_source_id_priority"])
        source_ids = [_identifier(row, source_fields) for row in rows]
        if any(source_id is None for source_id in source_ids):
            detail["missing_components"].append(
                "discussion_breadth.independent_content_sources"
            )
        else:
            raw["breadth_sources"][topic_id] = float(len(set(source_ids)))
        detail["content_source_count"] = len(
            {source_id for source_id in source_ids if source_id is not None}
        )
        detail["content_source_identity_coverage"] = _round(
            sum(source_id is not None for source_id in source_ids) / len(rows)
        )

        participant_fields = list(platform_policy["participant_id_priority"])
        participant_ids = [_identifier(row, participant_fields) for row in rows]
        participant_complete = all(value is not None for value in participant_ids)
        if not participant_complete:
            detail["missing_components"].append(
                "discussion_breadth.independent_participants"
            )
        else:
            raw["breadth_participants"][topic_id] = float(
                len(set(participant_ids))
            )
        detail["participant_count"] = len(
            {value for value in participant_ids if value is not None}
        )
        detail["participant_identity_coverage"] = _round(
            sum(value is not None for value in participant_ids) / len(rows)
        )

        engagement_policy = platform_policy["engagement"]
        engagement_values: list[float] = []
        if platform == "B站":
            for row in rows:
                likes = _finite_number(row.get("likes"))
                if likes is None or likes < 0:
                    engagement_values = []
                    break
                engagement_values.append(likes)
        else:
            for row in rows:
                likes = _finite_number(row.get("likes"))
                comments = _finite_number(row.get("comments"))
                if likes is None or comments is None or likes < 0 or comments < 0:
                    engagement_values = []
                    break
                engagement_values.append(likes + comments)
        if len(engagement_values) != len(rows):
            detail["missing_components"].append("engagement_depth")
        else:
            engagement_raw = sum(engagement_values) / len(engagement_values)
            raw["engagement_depth"][topic_id] = engagement_raw
            detail["engagement_raw"] = _round(engagement_raw)
            detail["engagement_method"] = engagement_policy["method"]
            detail["engagement_record_coverage"] = 1.0

        reach_policy = platform_policy["reach"]
        reach_by_source: dict[str, list[float]] = defaultdict(list)
        for row, source_id in zip(rows, source_ids):
            if source_id is None:
                continue
            observed: float | None = None
            for field in reach_policy["fields"]:
                candidate = _finite_number(row.get(field))
                if candidate is not None and candidate > 0:
                    observed = candidate
                    break
            if observed is not None:
                reach_by_source[source_id].append(observed)
        expected_sources = {value for value in source_ids if value is not None}
        complete_reach = bool(expected_sources) and expected_sources == set(reach_by_source)
        if not complete_reach:
            detail["missing_components"].append("reach")
        else:
            reach_raw = sum(max(values) for values in reach_by_source.values())
            raw["reach"][topic_id] = reach_raw
            detail["reach_raw"] = _round(reach_raw)
        detail["reach_content_source_coverage"] = _round(
            len(reach_by_source) / len(expected_sources) if expected_sources else 0.0
        )
        detail["reach_method"] = reach_policy["method"]

        previous = previous_topics.get(topic_id) or {}
        previous_count = int(
            ((previous.get("platform_metrics") or {}).get(platform) or {}).get("count")
            or 0
        )
        if current_total <= 0 or previous_total <= 0 or previous_count <= 0:
            detail["missing_components"].append("momentum")
            detail["momentum_status"] = "missing_no_reliable_previous_baseline"
        else:
            current_share = len(rows) / current_total
            previous_share = previous_count / previous_total
            relative_change = (current_share - previous_share) / previous_share
            protection = policy["components"]["momentum"]["low_base_protection"]
            protected_change = _clamp(
                relative_change,
                float(protection["minimum"]),
                float(protection["maximum"]),
            )
            raw["momentum"][topic_id] = protected_change
            detail["momentum_status"] = "available"
            detail["momentum"] = {
                "current_count": len(rows),
                "current_platform_total": current_total,
                "current_share": _round(current_share),
                "previous_count": previous_count,
                "previous_platform_total": previous_total,
                "previous_share": _round(previous_share),
                "relative_share_change": _round(relative_change),
                "protected_relative_share_change": _round(protected_change),
            }
        detail["status"] = (
            "blocked_missing_components"
            if detail["missing_components"]
            else "raw_inputs_available"
        )
    return raw, details


def _platform_heat(
    *,
    platform: str,
    topics: list[dict[str, Any]],
    records: list[dict[str, Any]],
    previous_week: dict[str, Any],
    policy: dict[str, Any],
    policy_hash: str,
    source_hash: str,
) -> dict[str, dict[str, Any]]:
    eligibility_policy = policy["platform_eligibility"]
    eligibility = _platform_eligibility(policy, platform)
    eligibility_status = str(eligibility["status"])
    raw, details = _platform_raw_inputs(
        platform=platform,
        topics=topics,
        records=records,
        previous_week=previous_week,
        policy=policy,
    )
    normalized = {
        "discussion_intensity": _normalize_cohort(
            raw["discussion_intensity"], long_tail=True, policy=policy
        ),
        "breadth_sources": _normalize_cohort(
            raw["breadth_sources"], long_tail=True, policy=policy
        ),
        "breadth_participants": _normalize_cohort(
            raw["breadth_participants"], long_tail=True, policy=policy
        ),
        "engagement_depth": _normalize_cohort(
            raw["engagement_depth"], long_tail=True, policy=policy
        ),
        "reach": _normalize_cohort(raw["reach"], long_tail=True, policy=policy),
        "momentum": _normalize_cohort(
            raw["momentum"], long_tail=False, policy=policy
        ),
    }
    formula_weights = policy["formula"]["weights"]
    breadth_weights = policy["components"]["discussion_breadth"]["weights"]
    results: dict[str, dict[str, Any]] = {}
    for topic in topics:
        topic_id = str(topic["id"])
        evidence_count = int(details[topic_id]["valid_evidence_count"])
        eligibility_provenance = {
            "policy_version": eligibility_policy["policy_version"],
            "effective_from_week": eligibility_policy["effective_from_week"],
            "status": eligibility_status,
            "reason": eligibility.get("reason"),
            "restoration_requires_business_approval": bool(
                eligibility.get("restoration_requires_business_approval")
            ),
        }
        if eligibility_status != ELIGIBLE:
            results[topic_id] = {
                "heat_score": None,
                "heat_display": eligibility.get("heat_display") or "N/A",
                "heat_status": INELIGIBLE_HEAT_STATUS,
                "heat_eligibility_status": eligibility_status,
                "heat_eligibility": eligibility_provenance,
                "heat_components": {},
                "heat_missing_components": [
                    eligibility.get("disqualifying_component") or "platform_eligibility"
                ],
                "heat_raw_input_summary": deepcopy(details[topic_id]),
                "heat_provenance": {
                    "rule_version": policy["rule_version"],
                    "rule_sha256": policy_hash,
                    "source_artifact_sha256": source_hash,
                    "valid_evidence_count": evidence_count,
                    "previous_week_id": previous_week.get("week_id"),
                    "platform_eligibility_policy_version": eligibility_policy[
                        "policy_version"
                    ],
                    "platform_eligibility_status": eligibility_status,
                    "included_in_composite": False,
                    "frontend_recalculation_allowed": False,
                    "proxy_used": False,
                },
            }
            continue
        if evidence_count == 0:
            results[topic_id] = {
                "heat_score": None,
                "heat_display": "N/A",
                "heat_status": "not_applicable_no_platform_evidence",
                "heat_eligibility_status": eligibility_status,
                "heat_eligibility": eligibility_provenance,
                "heat_components": {},
                "heat_missing_components": [],
                "heat_provenance": {
                    "rule_version": policy["rule_version"],
                    "rule_sha256": policy_hash,
                    "source_artifact_sha256": source_hash,
                    "valid_evidence_count": 0,
                    "previous_week_id": previous_week.get("week_id"),
                    "platform_eligibility_policy_version": eligibility_policy[
                        "policy_version"
                    ],
                    "platform_eligibility_status": eligibility_status,
                    "included_in_composite": False,
                    "frontend_recalculation_allowed": False,
                    "proxy_used": False,
                },
            }
            continue

        intensity = normalized["discussion_intensity"].get(topic_id)
        breadth_source = normalized["breadth_sources"].get(topic_id)
        breadth_participant = normalized["breadth_participants"].get(topic_id)
        engagement = normalized["engagement_depth"].get(topic_id)
        reach = normalized["reach"].get(topic_id)
        momentum = normalized["momentum"].get(topic_id)
        breadth_score = (
            float(breadth_source["score"])
            * float(breadth_weights["independent_content_source_score"])
            + float(breadth_participant["score"])
            * float(breadth_weights["independent_participant_score"])
            if breadth_source is not None and breadth_participant is not None
            else None
        )
        components = {
            "discussion_intensity": intensity,
            "discussion_breadth": {
                "score": _round(breadth_score),
                "independent_content_sources": breadth_source,
                "independent_participants": breadth_participant,
            },
            "engagement_depth": engagement,
            "reach": reach,
            "momentum": momentum,
        }
        component_scores = {
            "discussion_intensity": intensity.get("score") if intensity else None,
            "discussion_breadth": _round(breadth_score),
            "engagement_depth": engagement.get("score") if engagement else None,
            "reach": reach.get("score") if reach else None,
            "momentum": momentum.get("score") if momentum else None,
        }
        missing = [key for key, value in component_scores.items() if value is None]
        if missing:
            heat_score = None
            status = "blocked_missing_components"
        else:
            heat_score = _round(
                sum(
                    float(component_scores[key]) * float(formula_weights[key])
                    for key in formula_weights
                )
            )
            status = "calculated"
        results[topic_id] = {
            "heat_score": heat_score,
            "heat_display": None if heat_score is not None else "N/A",
            "heat_status": status,
            "heat_eligibility_status": eligibility_status,
            "heat_eligibility": eligibility_provenance,
            "heat_components": components,
            "heat_missing_components": missing,
            "heat_raw_input_summary": deepcopy(details[topic_id]),
            "heat_provenance": {
                "rule_version": policy["rule_version"],
                "rule_sha256": policy_hash,
                "source_artifact_sha256": source_hash,
                "valid_evidence_count": evidence_count,
                "previous_week_id": previous_week.get("week_id"),
                "platform_eligibility_policy_version": eligibility_policy[
                    "policy_version"
                ],
                "platform_eligibility_status": eligibility_status,
                "included_in_composite": heat_score is not None,
                "frontend_recalculation_allowed": False,
                "proxy_used": False,
            },
        }
    return results


def apply_heat_v1_to_week(
    week: dict[str, Any],
    previous_week: dict[str, Any],
    bilibili_payload: dict[str, Any],
    heybox_payload: dict[str, Any],
    *,
    policy: dict[str, Any],
    policy_hash: str,
    source_artifact_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Mutate only the target week with canonical Heat v1.0 fields."""

    source_artifact_hashes = source_artifact_hashes or {
        "B站": canonical_payload_sha256(bilibili_payload),
        "小黑盒": canonical_payload_sha256(heybox_payload),
    }
    topics = week.get("topics") or []
    payloads = {"B站": bilibili_payload, "小黑盒": heybox_payload}
    platform_results: dict[str, dict[str, dict[str, Any]]] = {}
    for platform in PLATFORMS:
        platform_results[platform] = _platform_heat(
            platform=platform,
            topics=topics,
            records=_mapped_records(payloads[platform]),
            previous_week=previous_week,
            policy=policy,
            policy_hash=policy_hash,
            source_hash=source_artifact_hashes[platform],
        )

    aggregation_expression = policy["platform_aggregation"]["weight_expression"]
    eligibility_policy = policy["platform_eligibility"]
    eligibility_by_platform = {
        platform: str(_platform_eligibility(policy, platform)["status"])
        for platform in PLATFORMS
    }
    eligible_platforms = [
        platform
        for platform in PLATFORMS
        if eligibility_by_platform[platform] == ELIGIBLE
    ]
    ineligible_platforms = {
        platform: eligibility_by_platform[platform]
        for platform in PLATFORMS
        if eligibility_by_platform[platform] != ELIGIBLE
    }
    platform_coverage = "partial" if ineligible_platforms else "full"
    for topic in topics:
        topic_id = str(topic["id"])
        platform_metrics = topic.setdefault("platform_metrics", {})
        eligible_evidenced: list[tuple[str, dict[str, Any]]] = []
        for platform in PLATFORMS:
            result = platform_results[platform][topic_id]
            metric = platform_metrics.setdefault(platform, {})
            for legacy_field in LEGACY_PROXY_FIELDS:
                metric.pop(legacy_field, None)
            metric.update(deepcopy(result))
            metric["heat_rule_version"] = policy["rule_version"]
            metric["heat_rule_sha256"] = policy_hash
            metric["heat_score_status"] = result["heat_status"]
            metric["heat_score_estimated"] = False
            metric["heat_score_independently_recalculable"] = (
                result["heat_status"] == "calculated"
            )
            metric["estimated_fields"] = [
                field
                for field in metric.get("estimated_fields") or []
                if field != "heat_score"
            ]
            if (
                result["heat_eligibility_status"] == ELIGIBLE
                and int(result["heat_provenance"]["valid_evidence_count"]) > 0
            ):
                eligible_evidenced.append((platform, result))

        combined = topic.setdefault("combined_metrics", {})
        for legacy_field in LEGACY_PROXY_FIELDS:
            combined.pop(legacy_field, None)
        blocked_platforms = [
            platform
            for platform, result in eligible_evidenced
            if result["heat_score"] is None
        ]
        if not eligible_evidenced:
            composite_score = None
            composite_status = "not_applicable_no_platform_evidence"
            weights: dict[str, float] = {}
        elif blocked_platforms:
            composite_score = None
            composite_status = "blocked_platform_component_missing"
            weights = {}
        else:
            roots = {
                platform: math.sqrt(
                    int(result["heat_provenance"]["valid_evidence_count"])
                )
                for platform, result in eligible_evidenced
            }
            denominator = sum(roots.values())
            weights = {
                platform: value / denominator for platform, value in roots.items()
            }
            composite_score = _round(
                sum(
                    float(result["heat_score"]) * weights[platform]
                    for platform, result in eligible_evidenced
                )
            )
            composite_status = "calculated"
        combined.update(
            {
                "heat_score": composite_score,
                "heat_status": composite_status,
                "heat_score_status": composite_status,
                "heat_rule_version": policy["rule_version"],
                "heat_rule_sha256": policy_hash,
                "heat_platform_weights": {
                    platform: _round(weight) for platform, weight in weights.items()
                },
                "heat_blocked_platforms": blocked_platforms,
                "heat_eligible_platforms": eligible_platforms,
                "heat_ineligible_platforms": ineligible_platforms,
                "heat_platform_coverage": platform_coverage,
                "heat_eligibility_policy_version": eligibility_policy[
                    "policy_version"
                ],
                "heat_aggregation": aggregation_expression,
                "heat_provenance": {
                    "rule_version": policy["rule_version"],
                    "rule_sha256": policy_hash,
                    "platform_eligibility_policy_version": eligibility_policy[
                        "policy_version"
                    ],
                    "heat_platform_coverage": platform_coverage,
                    "eligible_platforms": eligible_platforms,
                    "ineligible_platforms": ineligible_platforms,
                    "frontend_recalculation_allowed": False,
                    "proxy_used": False,
                },
            }
        )
        topic["heat_score"] = composite_score
        topic["heat_status"] = composite_status
        topic["heat_rule_version"] = policy["rule_version"]
        topic["heat_rule_sha256"] = policy_hash

    week["heat_rule_version"] = policy["rule_version"]
    week["heat_rule_sha256"] = policy_hash
    week["heat_version_status"] = "canonical_v1_0"
    week["heat_eligibility_policy_version"] = eligibility_policy["policy_version"]
    week["heat_eligible_platforms"] = eligible_platforms
    week["heat_ineligible_platforms"] = ineligible_platforms
    week["heat_platform_coverage"] = platform_coverage
    return week


def recalculate_dashboard_heat_v1(
    dashboard: dict[str, Any],
    bilibili_payload: dict[str, Any],
    heybox_payload: dict[str, Any],
    *,
    target_week_id: str,
    policy: dict[str, Any],
    policy_hash: str,
    source_artifact_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    result = deepcopy(dashboard)
    display_id = target_week_id.replace("_", "-")
    target_index = next(
        (
            index
            for index, week in enumerate(result.get("weeks") or [])
            if week.get("week_id") == display_id
        ),
        None,
    )
    if target_index is None:
        raise ValueError(f"dashboard has no target week {display_id}")
    if target_index == 0:
        raise ValueError("Heat v1.0 requires the previous complete week")
    apply_heat_v1_to_week(
        result["weeks"][target_index],
        result["weeks"][target_index - 1],
        bilibili_payload,
        heybox_payload,
        policy=policy,
        policy_hash=policy_hash,
        source_artifact_hashes=source_artifact_hashes,
    )
    meta = result.setdefault("meta", {})
    meta["heat_version_boundary"] = {
        "legacy_through_week": policy["legacy_through_week"].replace("_", "-"),
        "canonical_from_week": policy["effective_from_week"].replace("_", "-"),
        "legacy_recalculated": False,
        "cross_version_scores_directly_comparable": False,
    }
    return result
