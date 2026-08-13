#!/usr/bin/env python3
"""Load and enforce the versioned APEX business-rule binding."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_canonical_rules(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    policy_path = root / "config/weekly_production_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    binding = policy.get("canonical_business_rules") or {}
    relative = binding.get("path")
    if not relative:
        raise ValueError("weekly policy has no canonical_business_rules binding")
    rules_path = root / str(relative)
    payload = json.loads(rules_path.read_text(encoding="utf-8"))
    actual_hash = sha256(rules_path)
    if actual_hash != binding.get("sha256"):
        raise ValueError(
            "canonical business-rule hash mismatch: "
            f"{actual_hash} != {binding.get('sha256')}"
        )
    if payload.get("policy_version") != binding.get("version"):
        raise ValueError("canonical business-rule version differs from weekly policy")
    heat_binding = payload.get("heat") or {}
    heat_relative = heat_binding.get("policy_path")
    if not heat_relative:
        raise ValueError("canonical business rules have no Heat policy binding")
    heat_path = root / str(heat_relative)
    heat_policy = json.loads(heat_path.read_text(encoding="utf-8"))
    heat_hash = sha256(heat_path)
    if heat_hash != heat_binding.get("policy_sha256"):
        raise ValueError(
            "canonical Heat policy hash mismatch: "
            f"{heat_hash} != {heat_binding.get('policy_sha256')}"
        )
    if heat_policy.get("rule_version") != heat_binding.get("rule_version"):
        raise ValueError("canonical Heat rule version differs from its binding")
    if heat_policy.get("status") != heat_binding.get("status"):
        raise ValueError("canonical Heat status differs from its binding")
    payload["_path"] = str(relative)
    payload["_sha256"] = actual_hash
    payload["_heat_policy"] = heat_policy
    payload["_heat_policy_sha256"] = heat_hash
    return payload


def normalize_keyword(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def forbidden_keyword_set(rules: dict[str, Any]) -> set[str]:
    return {
        normalize_keyword(value)
        for value in rules["keywords"]["forbidden_visible_exact_terms"]
    }


def is_forbidden_keyword(value: Any, rules: dict[str, Any]) -> bool:
    return normalize_keyword(value) in forbidden_keyword_set(rules)


def _filter_keyword_list(values: list[Any], rules: dict[str, Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        candidate = value
        if isinstance(value, dict):
            candidate = value.get("normalized_keyword") or value.get("keyword")
        if is_forbidden_keyword(candidate, rules):
            continue
        result.append(value)
    return result


def sanitize_dashboard_keywords(
    dashboard: dict[str, Any], rules: dict[str, Any]
) -> dict[str, Any]:
    """Remove approved exact exclusions from every visible keyword-bearing path."""

    for week in dashboard.get("weeks") or []:
        stats = week.get("keyword_stats") or {}
        for platform, values in list(stats.items()):
            if isinstance(values, list):
                stats[platform] = _filter_keyword_list(values, rules)
        for topic in week.get("topics") or []:
            for key in ("descriptor_keywords", "keywords"):
                values = topic.get(key)
                if isinstance(values, list):
                    topic[key] = _filter_keyword_list(values, rules)
            platform_stats = topic.get("platform_keyword_stats") or {}
            for platform, values in list(platform_stats.items()):
                if isinstance(values, list):
                    platform_stats[platform] = _filter_keyword_list(values, rules)
    return dashboard


def iter_visible_keywords(dashboard: dict[str, Any]) -> Iterable[tuple[str, Any]]:
    for week in dashboard.get("weeks") or []:
        week_id = str(week.get("week_id") or "unknown")
        for platform, values in (week.get("keyword_stats") or {}).items():
            for index, value in enumerate(values or []):
                candidate = (
                    value.get("normalized_keyword") or value.get("keyword")
                    if isinstance(value, dict)
                    else value
                )
                yield f"{week_id}.keyword_stats.{platform}[{index}]", candidate
        for topic in week.get("topics") or []:
            topic_id = str(topic.get("id") or "unknown")
            for key in ("descriptor_keywords", "keywords"):
                for index, value in enumerate(topic.get(key) or []):
                    yield f"{week_id}.{topic_id}.{key}[{index}]", value
            for platform, values in (topic.get("platform_keyword_stats") or {}).items():
                for index, value in enumerate(values or []):
                    candidate = (
                        value.get("normalized_keyword") or value.get("keyword")
                        if isinstance(value, dict)
                        else value
                    )
                    yield (
                        f"{week_id}.{topic_id}.platform_keyword_stats."
                        f"{platform}[{index}]",
                        candidate,
                    )


def public_rule_metadata(rules: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_version": rules["policy_version"],
        "policy_sha256": rules["_sha256"],
        "data_topics": {
            "rule_version": rules["data_topics"]["rule_version"],
            "description_zh": rules["data_topics"]["public_description_zh"],
            "description_en": rules["data_topics"]["public_description_en"],
        },
        "keywords": {
            "rule_version": rules["keywords"]["rule_version"],
            "description_zh": rules["keywords"]["public_description_zh"],
            "description_en": rules["keywords"]["public_description_en"],
            "forbidden_visible_exact_terms": rules["keywords"][
                "forbidden_visible_exact_terms"
            ],
        },
        "heat": {
            "rule_version": rules["heat"]["rule_version"],
            "status": rules["heat"]["status"],
            "policy_sha256": rules["_heat_policy_sha256"],
            "effective_from_week": rules["heat"]["effective_from_week"],
            "legacy_through_week": rules["heat"]["legacy_through_week"],
            "formula": rules["heat"]["canonical_formula"],
            "weights": rules["heat"]["canonical_weights"],
            "platform_eligibility": rules["heat"]["platform_eligibility"],
            "frontend_recalculation_allowed": False,
            "description_zh": rules["heat"]["public_description_zh"],
            "description_en": rules["heat"]["public_description_en"],
        },
        "weekly_report_drivers": {
            "rule_version": rules["weekly_report_drivers"]["rule_version"],
            "data_topic_match_required": False,
            "provenance_required": True,
        },
    }
