#!/usr/bin/env python3
"""Create a versioned Heat v1.0 dashboard candidate without changing history."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from canonical_rules import load_canonical_rules, public_rule_metadata
from heat_v1 import recalculate_dashboard_heat_v1, sha256_file
from validate_heat_v1 import validate_heat_v1_dashboard
from weekly_release_common import atomic_json


def _object_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _without_heat_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_heat_fields(item)
            for key, item in value.items()
            if not str(key).startswith("heat_")
        }
    if isinstance(value, list):
        return [_without_heat_fields(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--week", required=True)
    parser.add_argument("--dashboard", type=Path, required=True)
    parser.add_argument("--bilibili", type=Path, required=True)
    parser.add_argument("--heybox", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    rules = load_canonical_rules(root)
    dashboard = json.loads(args.dashboard.read_text(encoding="utf-8"))
    bilibili = json.loads(args.bilibili.read_text(encoding="utf-8"))
    heybox = json.loads(args.heybox.read_text(encoding="utf-8"))
    source_hashes = {
        "B站": sha256_file(args.bilibili),
        "小黑盒": sha256_file(args.heybox),
    }
    effective = rules["heat"]["effective_from_week"].replace("_", "-")
    legacy_hashes_before = {
        str(week["week_id"]): _object_hash(week)
        for week in dashboard.get("weeks") or []
        if str(week.get("week_id")) < effective
    }
    recalculated = recalculate_dashboard_heat_v1(
        dashboard,
        bilibili,
        heybox,
        target_week_id=args.week,
        policy=rules["_heat_policy"],
        policy_hash=rules["_heat_policy_sha256"],
        source_artifact_hashes=source_hashes,
    )
    recalculated.setdefault("meta", {})["canonical_rules"] = public_rule_metadata(
        rules
    )
    legacy_hashes_after = {
        str(week["week_id"]): _object_hash(week)
        for week in recalculated.get("weeks") or []
        if str(week.get("week_id")) < effective
    }
    history_untouched = legacy_hashes_before == legacy_hashes_after
    validation = validate_heat_v1_dashboard(
        recalculated,
        bilibili,
        heybox,
        target_week_id=args.week,
        business_rules=rules,
        source_artifact_hashes=source_hashes,
    )
    target_display = args.week.replace("_", "-")
    target = next(
        week for week in recalculated["weeks"] if week["week_id"] == target_display
    )
    source_target = next(
        week for week in dashboard["weeks"] if week["week_id"] == target_display
    )
    w32_non_heat_hash_before = _object_hash(_without_heat_fields(source_target))
    w32_non_heat_hash_after = _object_hash(_without_heat_fields(target))
    w32_non_heat_untouched = w32_non_heat_hash_before == w32_non_heat_hash_after
    topic_results = []
    for topic in target["topics"]:
        topic_results.append(
            {
                "topic_id": topic["id"],
                "B站": {
                    "heat_score": topic["platform_metrics"]["B站"]["heat_score"],
                    "status": topic["platform_metrics"]["B站"]["heat_status"],
                    "eligibility": topic["platform_metrics"]["B站"][
                        "heat_eligibility_status"
                    ],
                    "missing_components": topic["platform_metrics"]["B站"][
                        "heat_missing_components"
                    ],
                },
                "小黑盒": {
                    "heat_score": topic["platform_metrics"]["小黑盒"]["heat_score"],
                    "heat_display": topic["platform_metrics"]["小黑盒"][
                        "heat_display"
                    ],
                    "status": topic["platform_metrics"]["小黑盒"]["heat_status"],
                    "eligibility": topic["platform_metrics"]["小黑盒"][
                        "heat_eligibility_status"
                    ],
                    "missing_components": topic["platform_metrics"]["小黑盒"][
                        "heat_missing_components"
                    ],
                },
                "综合": {
                    "heat_score": topic["combined_metrics"]["heat_score"],
                    "status": topic["combined_metrics"]["heat_status"],
                    "platform_weights": topic["combined_metrics"][
                        "heat_platform_weights"
                    ],
                    "heat_platform_coverage": topic["combined_metrics"][
                        "heat_platform_coverage"
                    ],
                },
            }
        )
    summary = {
        "schema_version": 1,
        "week_id": args.week,
        "rule_version": rules["heat"]["rule_version"],
        "rule_sha256": rules["_heat_policy_sha256"],
        "platform_eligibility_policy": rules["_heat_policy"][
            "platform_eligibility"
        ],
        "source_artifact_sha256": source_hashes,
        "source_dashboard_sha256": sha256_file(args.dashboard),
        "legacy_week_hashes_before": legacy_hashes_before,
        "legacy_week_hashes_after": legacy_hashes_after,
        "w25_w31_untouched": history_untouched,
        "w32_non_heat_hash_before": w32_non_heat_hash_before,
        "w32_non_heat_hash_after": w32_non_heat_hash_after,
        "w32_non_heat_untouched": w32_non_heat_untouched,
        "independent_validation": validation,
        "w32_recalculation_status": (
            "PASS" if validation["release_ready"] else "BLOCKED"
        ),
        "w32_heat_v1_ready": bool(validation["release_ready"]),
        "topic_results": topic_results,
    }
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    dashboard_name = f"dashboard_{args.week}_heat_v1_candidate.json"
    atomic_json(output_dir / dashboard_name, recalculated)
    atomic_json(output_dir / f"{args.week}_HEAT_V1_RECALCULATION.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return (
        0
        if history_untouched
        and w32_non_heat_untouched
        and validation["recalculation_match"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
