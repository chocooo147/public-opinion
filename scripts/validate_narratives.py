#!/usr/bin/env python3
"""Fail closed when an APEX weekly preview uses non-editorial narratives."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


TARGET_DRIVER_COUNT = 10
MINIMUM_DRIVER_COUNT = 8


FORBIDDEN = {
    "zh": (
        "在本周有限样本中",
        "被归入",
        "代表性观察涉及",
        "方向来自模型推断",
        "仅用于探索",
        "不代表平台总体情绪",
        "不是经正式验证的统计事实",
    ),
    "en": (
        "Within this bounded weekly sample",
        "were assigned to",
        "Representative evidence",
        "model-derived and exploratory",
        "not a platform-wide sentiment",
        "not a formally validated fact",
    ),
}

ACTOR_ZH = re.compile(r"玩家|观众|社区|帖子|讨论|群体|用户")
REACTION_ZH = re.compile(
    r"认可|欢迎|认为|质疑|讨论|否定|担忧|期待|无法确定|评价|受挫|关注|反感|描述|报告|询问|解释|获得|视为"
)
IMPACT_ZH = re.compile(
    r"帮助|提升|打断|促使|削弱|增加|限制|形成|共识|判断|参与|信任|理解|兴趣|关注|决定|结论|顾虑"
)
ACTOR_EN = re.compile(
    r"\b(players?|viewers?|community|post|discussion|audience|users?)\b",
    re.I,
)
REACTION_EN = re.compile(
    r"\b(welcomed|reported|described|questioned|discussed|debated|rejected|worried|expected|interpreted|struggled|found|recognized|drew|could not determine)\b",
    re.I,
)
IMPACT_EN = re.compile(
    r"\b(helped|encouraged|interrupted|prompted|weakened|increased|limited|understanding|interest|trust|participation|consensus|judgment|verdict|decision|concern)\b",
    re.I,
)
TOPIC_ID = re.compile(r"APEX-T\d{3}")
COUNT_ZH = re.compile(r"\d+\s*(?:条B站评论|篇小黑盒)")
COUNT_EN = re.compile(r"\d+\s+(?:Bilibili comment|Heybox)", re.I)


def sentence_count(text: str, language: str) -> int:
    marks = r"[。！？]" if language == "zh" else r"[.!?]"
    return len([part for part in re.split(marks, text) if part.strip()])


def validate_driver(driver: dict[str, object], index: int) -> list[str]:
    errors: list[str] = []
    topic_zh = str(driver.get("topic_zh") or "")
    topic_en = str(driver.get("topic_en") or "")
    narrative_zh = str(driver.get("narrative_zh") or "").strip()
    narrative_en = str(driver.get("narrative_en") or "").strip()
    label = topic_zh or topic_en or f"driver {index}"

    for topic in (topic_zh, topic_en):
        if TOPIC_ID.search(topic):
            errors.append(f"{label}: visible title contains a canonical topic ID")
            break

    for phrase in FORBIDDEN["zh"]:
        if phrase in narrative_zh:
            errors.append(f"{label}: Chinese narrative contains pipeline boilerplate: {phrase}")
    for phrase in FORBIDDEN["en"]:
        if phrase.lower() in narrative_en.lower():
            errors.append(f"{label}: English narrative contains pipeline boilerplate: {phrase}")

    if COUNT_ZH.search(narrative_zh):
        errors.append(f"{label}: Chinese driver repeats platform sample counts")
    if COUNT_EN.search(narrative_en):
        errors.append(f"{label}: English driver repeats platform sample counts")

    if not 45 <= len(narrative_zh) <= 150:
        errors.append(
            f"{label}: Chinese narrative length {len(narrative_zh)} is outside 45-150 characters"
        )
    word_count = len(re.findall(r"\b[\w’'-]+\b", narrative_en))
    if not 25 <= word_count <= 75:
        errors.append(
            f"{label}: English narrative length {word_count} is outside 25-75 words"
        )

    if sentence_count(narrative_zh, "zh") < 2:
        errors.append(f"{label}: Chinese narrative needs at least two sentences")
    if sentence_count(narrative_en, "en") < 2:
        errors.append(f"{label}: English narrative needs at least two sentences")

    if not ACTOR_ZH.search(narrative_zh):
        errors.append(f"{label}: Chinese narrative lacks a bounded audience or source")
    if not REACTION_ZH.search(narrative_zh):
        errors.append(f"{label}: Chinese narrative lacks an explicit reaction")
    if not IMPACT_ZH.search(narrative_zh):
        errors.append(f"{label}: Chinese narrative lacks an impact or confidence limit")
    if not ACTOR_EN.search(narrative_en):
        errors.append(f"{label}: English narrative lacks a bounded audience or source")
    if not REACTION_EN.search(narrative_en):
        errors.append(f"{label}: English narrative lacks an explicit reaction")
    if not IMPACT_EN.search(narrative_en):
        errors.append(f"{label}: English narrative lacks an impact or confidence limit")

    return errors


def validate_driver_count(
    payload: dict[str, object], drivers: list[object], allow_legacy_reference: bool
) -> list[str]:
    """Require 10 drivers unless an auditable evidence shortage justifies 8 or 9."""

    count = len(drivers)
    errors: list[str] = []
    if count < MINIMUM_DRIVER_COUNT or count > TARGET_DRIVER_COUNT:
        return [
            f"preview must contain {MINIMUM_DRIVER_COUNT}-{TARGET_DRIVER_COUNT} drivers; found {count}"
        ]
    if count == TARGET_DRIVER_COUNT or allow_legacy_reference:
        return errors

    reduction = payload.get("driver_reduction")
    if not isinstance(reduction, dict):
        return [
            f"{count}-driver report requires a driver_reduction audit; 10 drivers are the standard"
        ]

    if reduction.get("target_count") != TARGET_DRIVER_COUNT:
        errors.append("driver_reduction.target_count must be 10")
    if reduction.get("actual_count") != count:
        errors.append("driver_reduction.actual_count must equal the driver list length")
    reason = str(reduction.get("reason") or "").strip()
    if len(reason) < 20:
        errors.append("driver_reduction.reason must give a specific evidence-based explanation")
    if reduction.get("padding_forbidden") is not True:
        errors.append("driver_reduction.padding_forbidden must be true")

    candidates = reduction.get("excluded_candidates")
    missing = TARGET_DRIVER_COUNT - count
    if not isinstance(candidates, list) or len(candidates) < missing:
        errors.append(
            f"driver_reduction.excluded_candidates must document at least {missing} excluded candidate(s)"
        )
    else:
        for index, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict):
                errors.append(f"excluded candidate {index}: expected an object")
                continue
            name = str(candidate.get("candidate") or "").strip()
            exclusion = str(candidate.get("exclusion_reason") or "").strip()
            if not name:
                errors.append(f"excluded candidate {index}: candidate is required")
            if len(exclusion) < 12:
                errors.append(
                    f"excluded candidate {index}: exclusion_reason must explain the evidence failure"
                )

    return errors


def validate_payload(
    payload: dict[str, object], *, allow_legacy_reference: bool = False
) -> list[str]:
    drivers = payload.get("drivers")
    if not isinstance(drivers, list):
        return ["preview must contain a drivers list"]
    errors = validate_driver_count(payload, drivers, allow_legacy_reference)
    for index, driver in enumerate(drivers, start=1):
        if not isinstance(driver, dict):
            errors.append(f"driver {index}: expected an object")
            continue
        errors.extend(validate_driver(driver, index))
    for language in ("zh", "en"):
        key = f"narrative_{language}"
        prefixes = Counter(str(driver.get(key) or "").strip()[:12] for driver in drivers)
        repeated = [prefix for prefix, count in prefixes.items() if prefix and count >= 3]
        if repeated:
            errors.append(
                f"{language}: repeated template opening across at least three drivers: {repeated[0]}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("preview", type=Path)
    parser.add_argument(
        "--allow-legacy-reference",
        action="store_true",
        help="validate a historical pre-rule reference; never use for a new report",
    )
    args = parser.parse_args()
    payload = json.loads(args.preview.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("preview must contain a JSON object")
    errors = validate_payload(
        payload, allow_legacy_reference=args.allow_legacy_reference
    )
    drivers = payload.get("drivers") or []
    result = {
        "preview": str(args.preview),
        "driver_count": len(drivers),
        "valid": not errors,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
