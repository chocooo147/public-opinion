from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from project_paths import resolve_project_asset
from canonical_rules import (
    load_canonical_rules,
    public_rule_metadata,
    sanitize_dashboard_keywords,
)
from content_integrity import (
    EVENT_RULE_VERSION,
    KEYWORD_RULE_VERSION,
    SENTIMENT_RULE_VERSION,
    extract_keywords,
    generate_events,
)
from heat_v1 import apply_heat_v1_to_week, atomic_json_artifact_sha256
from sentiment_integrity import summarize_sentiment
from representative_content import build_representative_contents


WEEK_ID_RE = re.compile(r"^(?P<year>\d{4})_W(?P<week>\d{2})$")
DISPLAY_WEEK_RE = re.compile(r"^(?P<year>\d{4})-W(?P<week>\d{2})$")
PLATFORMS = ("B站", "小黑盒")
DATA_BOUNDARIES = {
    "B站": "real_bounded_sample",
    "小黑盒": "real_public_search_sample",
    "综合": "mixed_real_observations_incomparable_units",
}
SIMULATION_BOUNDARIES = {
    "B站": "simulated_fixture",
    "小黑盒": "simulated_fixture",
    "综合": "simulated_fixture_incomparable_units",
}
CANONICAL_TOPIC_NAMES_EN = {
    "APEX-T001": "Ranked Play & Matchmaking",
    "APEX-T002": "Season Updates & Gameplay Systems",
    "APEX-T003": "Esports & Streamers",
    "APEX-T004": "Legend Abilities & Weapon Balance",
    "APEX-T005": "Skins, Cosmetics & Monetization",
    "APEX-T006": "Collaboration Events & Experience",
    "APEX-T007": "Creator Video Feedback & Settings Help",
    "APEX-T008": "Legend & Weapon Strength",
    "APEX-T009": "Cosmetics & Control Experience",
    "APEX-T010": "Competitive Esports & Streamer Discussion",
    "APEX-T011": "Version, Ranked & Esports Discussion",
    "APEX-T012": "Cosmetic Appeal & Official Operations",
    "APEX-T013": "Weapon & Legend Strength",
}
STATUS_ZH = {
    "new": "新生",
    "rising": "上升",
    "persistent": "稳定延续",
    "declining": "回落",
}
STATUS_EN = {
    "new": "New",
    "rising": "Rising",
    "persistent": "Stable",
    "declining": "Declining",
}


def load_production_policy(project_root: Path) -> dict[str, Any]:
    path = project_root / "config/weekly_production_policy.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["_path"] = path.as_posix()
    payload["_sha256"] = sha256(path)
    return payload


def verify_policy_asset_hashes(
    project_root: Path, policy: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Verify pinned registry/mapping assets without changing model state."""

    verified: dict[str, dict[str, Any]] = {}
    for name in ("topic_registry", "topic_mapping"):
        path_key = f"{name}_path"
        hash_key = f"{name}_sha256"
        path = resolve_project_asset(project_root, policy["model_gate"][path_key])
        expected = str(policy["model_gate"].get(hash_key) or "")
        actual = sha256(path)
        if not expected or actual != expected:
            raise ValueError(
                f"pinned {name} hash mismatch: {actual} != {expected or 'missing'}"
            )
        verified[name] = {
            "path": policy["model_gate"][path_key],
            "sha256": actual,
        }
    return verified


def file_fingerprint(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def clean_and_deduplicate(
    payload: dict[str, Any],
    *,
    platform: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a derived, reviewable clean layer without modifying raw input."""
    cleaned = copy.deepcopy(payload)
    source_rows = list(cleaned.get("records") or [])
    effective: list[dict[str, Any]] = []
    technical_records: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    blank_rows = 0
    duplicate_rows = 0
    technical_rows = 0
    for row in source_rows:
        text = re.sub(r"\s+", " ", str(row.get("text") or "")).strip()
        if not text:
            blank_rows += 1
            continue
        url = str(row.get("url") or row.get("source_url") or "").strip()
        text_id = str(row.get("text_id") or row.get("comment_id") or "").strip()
        key = (platform, text_id) if text_id else (platform, url, text)
        if key in seen:
            duplicate_rows += 1
            continue
        seen.add(key)
        row["text"] = text
        technical = bool(
            re.search(
                r"(?:采集失败|登录失效|验证码|captcha|timeout|traceback|http\s*[45]\d\d)",
                text,
                flags=re.I,
            )
        )
        row["technical_issue_flag"] = int(technical)
        technical_rows += int(technical)
        if technical:
            technical_records.append(row)
            continue
        effective.append(row)
    cleaned["records"] = effective
    cleaned["technical_records"] = technical_records
    cleaned.setdefault("meta", {}).update(
        {
            "raw_rows": len(source_rows),
            "effective_rows": len(effective),
            "blank_rows_removed": blank_rows,
            "duplicate_rows_removed": duplicate_rows,
            "technical_issue_rows": technical_rows,
            "cleaning_status": "derived_non_destructive_v1",
        }
    )
    return cleaned, {
        "raw_rows": len(source_rows),
        "effective_rows": len(effective),
        "blank_rows_removed": blank_rows,
        "duplicate_rows_removed": duplicate_rows,
        "technical_issue_rows": technical_rows,
    }


def sample_quality(
    payload: dict[str, Any],
    *,
    platform: str,
    policy: dict[str, Any],
    simulated: bool,
) -> dict[str, Any]:
    records = list(payload.get("records") or [])
    source_keys = [
        str(row.get("bvid") or row.get("post_id") or row.get("url") or "")
        for row in records
    ]
    authors = [
        str(
            row.get("author_id")
            or row.get("mid")
            or row.get("uid")
            or row.get("author")
            or row.get("author_name")
            or ""
        )
        for row in records
    ]
    source_counts = Counter(key for key in source_keys if key)
    effective = len(records)
    outliers = sum(bool(row.get("is_outlier")) for row in records)
    low_strength = sum(bool(row.get("low_confidence_flag")) for row in records)
    mapped = sum(
        bool(row.get("canonical_topic_id")) and not bool(row.get("is_outlier"))
        for row in records
    )
    thresholds = policy.get("bilibili_sample_gate", {})
    checks: dict[str, bool | None] = {
        "effective_rows": effective >= int(thresholds.get("minimum_effective_top_level_comments", 100)),
        "independent_sources": len(source_counts) >= int(thresholds.get("minimum_unique_videos", 10)),
        "independent_authors": (
            len({author for author in authors if author})
            >= int(thresholds.get("minimum_unique_authors", 50))
            if any(authors)
            else None
        ),
        "max_single_source_share": (
            max(source_counts.values(), default=0) / effective
            <= float(thresholds.get("maximum_single_video_share", 0.3))
            if effective
            else False
        ),
        "outlier_ratio": (
            outliers / effective
            <= float(thresholds.get("maximum_outlier_rate", 0.4))
            if effective
            else False
        ),
        "low_assignment_strength_ratio": (
            low_strength / effective
            <= float(thresholds.get("maximum_low_assignment_strength_rate", 0.55))
            if effective
            else False
        ),
    }
    if platform != "B站":
        checks = {"effective_rows_nonempty": effective > 0}
    passed = simulated or all(value is True for value in checks.values())
    return {
        "platform": platform,
        "raw_rows": int(payload.get("meta", {}).get("raw_rows") or effective),
        "effective_rows": effective,
        "mapped_rows": mapped,
        "independent_source_count": len(source_counts),
        "independent_author_count": len({author for author in authors if author}) if any(authors) else None,
        "author_identity_available": any(authors),
        "max_single_source_share": round(max(source_counts.values(), default=0) / effective, 6) if effective else 0.0,
        "outlier_count": outliers,
        "outlier_ratio": round(outliers / effective, 6) if effective else 0.0,
        "low_assignment_strength_count": low_strength,
        "low_assignment_strength_ratio": round(low_strength / effective, 6) if effective else 0.0,
        "confidence_semantics": "HDBSCAN cluster membership strength; not calibrated classification correctness probability.",
        "checks": checks,
        "production_gate_passed": passed,
        "low_sample_week": not passed,
        "simulation_exempt": simulated,
    }


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def week_dates(week_id: str) -> tuple[date, date]:
    match = WEEK_ID_RE.fullmatch(week_id)
    if not match:
        raise ValueError(f"invalid week id: {week_id}")
    start = date.fromisocalendar(
        int(match.group("year")),
        int(match.group("week")),
        1,
    )
    return start, start + timedelta(days=6)


def display_week_id(week_id: str) -> str:
    match = WEEK_ID_RE.fullmatch(week_id)
    if not match:
        raise ValueError(f"invalid week id: {week_id}")
    return f"{match.group('year')}-W{match.group('week')}"


def storage_week_id(display_id: str) -> str:
    match = DISPLAY_WEEK_RE.fullmatch(display_id)
    if not match:
        raise ValueError(f"invalid display week id: {display_id}")
    return f"{match.group('year')}_W{match.group('week')}"


def week_number(week_id: str) -> int:
    match = WEEK_ID_RE.fullmatch(week_id)
    if not match:
        raise ValueError(f"invalid week id: {week_id}")
    return int(match.group("week"))


def next_week_id(week_id: str) -> str:
    start, _ = week_dates(week_id)
    next_start = start + timedelta(days=7)
    year, week, _ = next_start.isocalendar()
    return f"{year}_W{week:02d}"


def period_label(start: date, end: date) -> str:
    return f"{start.month}.{start.day}—{end.month}.{end.day}"


def newest_dashboard(
    project_root: Path,
    *,
    before_week_id: str | None = None,
) -> Path:
    candidates: list[tuple[tuple[int, int], Path]] = []
    for path in project_root.glob("dashboard_data_apex_W*_W*.json"):
        match = re.search(r"_W(\d{2})\.json$", path.name)
        if not match:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            default = storage_week_id(payload["meta"]["default_week_id"])
            if before_week_id and week_dates(default)[0] >= week_dates(before_week_id)[0]:
                continue
            candidates.append(
                ((int(default[:4]), week_number(default)), path)
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    if not candidates:
        raise FileNotFoundError(
            "no valid dashboard_data_apex_W*_W*.json found before target week"
        )
    return max(candidates, key=lambda item: item[0])[1]


def validate_collection(
    payload: dict[str, Any],
    *,
    platform: str,
    week_id: str,
    start: date,
    end: date,
    allow_simulated: bool,
) -> None:
    meta = payload.get("meta") or {}
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError(f"{platform} collection has no records list")
    if meta.get("week_id") != week_id:
        raise ValueError(
            f"{platform} week mismatch: {meta.get('week_id')} != {week_id}"
        )
    if meta.get("date_range") != [start.isoformat(), end.isoformat()]:
        raise ValueError(f"{platform} date range does not match natural week")
    if meta.get("simulation_only") and not allow_simulated:
        raise ValueError(f"{platform} simulated input is forbidden in production")
    if not records:
        raise ValueError(f"{platform} collection is empty")
    for index, record in enumerate(records):
        if record.get("week_id") != week_id:
            raise ValueError(f"{platform} record {index} has wrong week")
        if record.get("platform") != platform:
            raise ValueError(f"{platform} record {index} has wrong platform")
        publish_text = str(record.get("publish_time") or "")[:10]
        try:
            publish_date = date.fromisoformat(publish_text)
        except ValueError as exc:
            raise ValueError(
                f"{platform} record {index} has invalid publish_time"
            ) from exc
        if not start <= publish_date <= end:
            raise ValueError(
                f"{platform} record {index} leaks outside target week"
            )


def _apply_sentiment_models(
    project_root: Path,
    payload: dict[str, Any],
    *,
    platform: str,
) -> dict[str, Any]:
    records = payload["records"]
    meta = payload.setdefault("meta", {})
    if meta.get("simulation_only"):
        return payload
    if platform != "B站":
        meta.update(
            {
                "sentiment_model": "SnowNLP_0.12.3",
                "sentiment_role": "baseline_only_not_formal_truth",
                "sentiment_domain_transfer_forbidden": True,
            }
        )
        return payload
    policy = load_production_policy(project_root)
    model_path = resolve_project_asset(
        project_root, policy["model_gate"]["domain_sentiment_model_path"]
    )
    manifest_path = resolve_project_asset(
        project_root, policy["model_gate"]["domain_sentiment_manifest_path"]
    )
    if not model_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("domain sentiment deployment artifact is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256(model_path) != manifest.get("model_sha256"):
        raise ValueError("domain sentiment model hash differs from its manifest")
    import pickle

    with model_path.open("rb") as handle:
        model = pickle.load(handle)
    texts = [str(row.get("text") or "") for row in records]
    predictions = model.predict(texts)
    probabilities = model.predict_proba(texts)
    classes = [str(label) for label in model.classes_]
    label_map = {"积极": "positive", "中性": "neutral", "负面": "negative"}
    threshold = float(manifest["validation"].get("review_threshold", 0.35))
    for row, prediction, distribution in zip(records, predictions, probabilities):
        row.setdefault("snownlp_score", row.get("sentiment_score"))
        row.setdefault("snownlp_label", row.get("sentiment_label"))
        row.setdefault("snownlp_model", row.get("sentiment_model") or "SnowNLP")
        row.setdefault("snownlp_status", row.get("sentiment_status") or "model_only_unvalidated")
        confidence = max(float(value) for value in distribution)
        row.update(
            {
                "sentiment_label": label_map[str(prediction)],
                "sentiment_score": round(confidence, 8),
                "sentiment_confidence": round(confidence, 8),
                "sentiment_probabilities": {
                    label_map[label]: round(float(value), 8)
                    for label, value in zip(classes, distribution)
                },
                "sentiment_review_required": int(confidence < threshold),
                "sentiment_model": manifest["model"],
                "sentiment_model_version": manifest["version"],
                "sentiment_status": "auxiliary_primary_independent_review_required",
                "sentiment_formal_reporting_qualified": False,
            }
        )
    meta.update(
        {
            "sentiment_model": manifest["model"],
            "sentiment_model_version": manifest["version"],
            "sentiment_model_sha256": manifest["model_sha256"],
            "sentiment_review_threshold": threshold,
            "sentiment_review_required_rows": sum(
                int(row["sentiment_review_required"]) for row in records
            ),
            "sentiment_status": "auxiliary_primary_independent_review_required",
            "sentiment_formal_reporting_qualified": False,
            "snownlp_role": "retained_baseline_only_not_formal_truth",
        }
    )
    return payload


def apply_frozen_model(
    project_root: Path,
    payload: dict[str, Any],
    *,
    platform: str,
) -> dict[str, Any]:
    """Apply the read-only topic model and the current SnowNLP baseline.

    ``assignment_confidence`` is HDBSCAN membership strength. It must never be
    exposed as a calibrated probability that the assigned topic is correct.
    """
    records = payload["records"]
    policy = load_production_policy(project_root)
    model_path = resolve_project_asset(
        project_root, policy["model_gate"]["bertopic_model_path"]
    )
    manifest_path = resolve_project_asset(
        project_root, policy["model_gate"]["bertopic_manifest_path"]
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256(model_path) != manifest.get("model_sha256"):
        raise ValueError("frozen BERTopic model hash differs from its manifest")
    complete = all(
        "canonical_topic_id" in row
        and "sentiment_label" in row
        and "sentiment_score" in row
        for row in records
    )
    if complete:
        for row in records:
            if int(row.get("model_topic_id", -1)) == -1:
                row["assignment_confidence"] = 0.0
                row["is_outlier"] = 1
            row["low_confidence_flag"] = int(
                float(row.get("assignment_confidence") or 0.0) < 0.5
            )
        payload["meta"].update(
            {
                "model_application": "collector_output_already_modelled_hash_verified",
                "bertopic_model_version": manifest.get("model_version"),
                "bertopic_model_sha256": manifest.get("model_sha256"),
                "confidence_semantics": (
                    "HDBSCAN cluster membership strength; topic -1 forced to 0.0; "
                    "not calibrated classification correctness probability."
                ),
            }
        )
        return _apply_sentiment_models(project_root, payload, platform=platform)

    import csv
    import pickle

    mapping_path = resolve_project_asset(
        project_root, policy["model_gate"]["topic_mapping_path"]
    )
    with model_path.open("rb") as handle:
        model = pickle.load(handle)
    with mapping_path.open(encoding="utf-8-sig", newline="") as handle:
        mapping = {
            int(row["model_topic_id"]): row
            for row in csv.DictReader(handle)
            if str(row.get("model_topic_id") or "").strip()
        }
    texts = [str(row.get("text") or "").strip() for row in records]
    if any(not text for text in texts):
        raise ValueError(f"{platform} raw collection contains blank text")
    topics, probabilities = model.transform(texts)
    try:
        from snownlp import SnowNLP
    except ImportError as exc:
        raise RuntimeError("SnowNLP is required for weekly production") from exc
    for row, topic, probability, text in zip(
        records,
        topics,
        probabilities,
        texts,
    ):
        topic = int(topic)
        confidence = 0.0 if topic == -1 else float(probability or 0.0)
        mapped = mapping.get(topic, {})
        score = float(SnowNLP(text).sentiments)
        label = "negative" if score < 0.35 else "positive" if score > 0.65 else "neutral"
        row.update(
            {
                "model_topic_id": topic,
                "canonical_topic_id": mapped.get("canonical_topic_id", ""),
                "canonical_topic_name": mapped.get("canonical_topic_name", ""),
                "operation": "retain" if mapped else "review",
                "assignment_confidence": round(confidence, 6),
                "is_outlier": int(topic == -1),
                "low_confidence_flag": int(confidence < 0.5),
                "review_flag": int(topic == -1 or not mapped),
                "possible_wrong_classification": 0,
                "sentiment_score": round(score, 8),
                "sentiment_label": label,
                "sentiment_model": "SnowNLP",
                "sentiment_status": "model_only_unvalidated",
                "sample_scope": (
                    "logged_in_visible_comments_bounded_sample"
                    if platform == "B站"
                    else "public_search_visible_posts_only"
                ),
                "metrics_source": (
                    "bilibili_real_bounded_sample"
                    if platform == "B站"
                    else "heybox_public_search_visible_sample"
                ),
            }
        )
    payload["meta"].update(
        {
            "model_application": "frozen_bertopic_transform_and_snownlp",
            "model_status": "frozen_exploratory_model_only",
            "bertopic_model_version": manifest.get("model_version"),
            "bertopic_model_sha256": manifest.get("model_sha256"),
            "snownlp_role": "baseline_only_not_formal_truth",
            "confidence_semantics": (
                "HDBSCAN cluster membership strength; topic -1 forced to 0.0; "
                "not calibrated classification correctness probability."
            ),
        }
    )
    return _apply_sentiment_models(project_root, payload, platform=platform)


def _clamp(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))


def _sentiment(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Return count-backed sentiment rates without defaulting missing data to 0."""
    return summarize_sentiment(records)


def _keywords(records: Iterable[dict[str, Any]], limit: int = 15) -> list[str]:
    stop = {
        "apex",
        "玩家",
        "游戏",
        "这个",
        "那个",
        "感觉",
        "还是",
        "就是",
        "可以",
        "没有",
        "一个",
    }
    counts: Counter[str] = Counter()
    for record in records:
        text = str(record.get("text") or "").lower()
        counts.update(
            token
            for token in re.findall(r"[a-z0-9]{2,}|[\u4e00-\u9fff]{2,4}", text)
            if token not in stop
        )
    return [token for token, _ in counts.most_common(limit)]


def _keyword_stats(
    records: list[dict[str, Any]],
    limit: int = 30,
) -> list[dict[str, Any]]:
    return extract_keywords(records)["qualified"][:limit]


def _platform_metric(
    records: list[dict[str, Any]],
    previous: dict[str, Any] | None,
    *,
    platform: str,
    simulated: bool,
) -> dict[str, Any]:
    count = len(records)
    previous_count = int((previous or {}).get("count") or 0)
    wow = (
        None
        if previous is None
        else (
            100.0
            if previous_count == 0 and count
            else 0.0
            if previous_count == 0
            else round((count - previous_count) / previous_count * 100, 1)
        )
    )
    sentiment = _sentiment(records)
    likes = sum(int(record.get("likes") or 0) for record in records)
    comments = sum(int(record.get("comments") or 0) for record in records)
    prior_trend = list((previous or {}).get("trend") or [])
    trend = (prior_trend + [count])[-5:]
    negative = sentiment["negative_rate"]
    positive = sentiment["positive_rate"]
    valid_count = int(sentiment["sentiment_valid_count"])
    consensus = (
        _clamp(50 + abs(float(positive) - float(negative)) * 0.35)
        if positive is not None and negative is not None
        else None
    )
    is_bilibili = platform == "B站"
    metrics_source = (
        "simulated_fixture"
        if simulated
        else "bilibili_real_bounded_sample"
        if is_bilibili
        else "heybox_public_search_visible_sample"
    )
    source_ids = {
        str(r.get("bvid") or r.get("post_id") or r.get("url") or "")
        for r in records
        if r.get("bvid") or r.get("post_id") or r.get("url")
    }
    author_ids = {
        str(
            r.get("author_id")
            or r.get("mid")
            or r.get("uid")
            or r.get("author")
            or r.get("author_name")
        )
        for r in records
        if r.get("author_id")
        or r.get("mid")
        or r.get("uid")
        or r.get("author")
        or r.get("author_name")
    }
    # Sentiment cannot depress risk when evidence is tiny.  Below five valid
    # predictions it contributes nothing; at five-to-nine it is downweighted.
    sentiment_weight = float(sentiment["sentiment_risk_weight"])
    growth_component = min(45.0, max(0.0, float(wow or 0)) * 0.2)
    volume_component = min(25.0, count / 20 * 25.0)
    source_component = min(15.0, len(source_ids) / 5 * 15.0)
    sentiment_component = (
        float(negative) * 0.65 * sentiment_weight
        if negative is not None
        else 0.0
    )
    disagreement_component = (
        (100 - float(consensus)) * 0.15 * sentiment_weight
        if consensus is not None
        else 0.0
    )
    risk = _clamp(
        sentiment_component
        + disagreement_component
        + growth_component
        + volume_component
        + source_component
    )
    source_data_version = next(
        (
            str(record.get("source_data_version") or record.get("data_version"))
            for record in records
            if record.get("source_data_version") or record.get("data_version")
        ),
        "",
    )
    representative_contents = build_representative_contents(
        records,
        platform=platform,
        source_data_version=source_data_version,
    )
    metric = {
        "count": count,
        "video_count": len(source_ids),
        "creator_count": len(author_ids) if author_ids else None,
        "comment_count": count if is_bilibili else comments,
        "likes_count": likes,
        **sentiment,
        "wow": wow,
        "trend": trend,
        "video_coverage_score": _clamp(count / 40 * 100),
        "creator_coverage_score": _clamp(count / 30 * 100),
        "consensus_score": consensus,
        "heat_score": None,
        "heat_rule_status": "pending_canonical_heat_v1_calculation",
        "heat_score_status": "pending_canonical_heat_v1_calculation",
        "risk_score": risk,
        "metrics_source": metrics_source,
        "simulated": simulated,
        "estimated": True,
        "simulation_seed": "weekly_e2e_fixture_v1" if simulated else None,
        "core_fields_real": [] if simulated else [
            "count",
            "comment_count",
            "video_count",
            "trend",
            "wow",
        ],
        "estimated_fields": [
            "negative_rate",
            "sentiment",
            "heat_score",
            "consensus_score",
            "risk_score",
        ],
        "data_type": "simulated" if simulated else "real_sample",
        "sample_limited": True,
        "count_unit": "comments" if is_bilibili else "visible_posts",
        "sentiment_model": (
            "fixture"
            if simulated
            else sentiment["sentiment_model"]
        ),
        "sentiment_model_version": (
            "fixture" if simulated else sentiment["sentiment_model_version"]
        ),
        "sentiment_status": (
            "simulation_only"
            if simulated
            else sentiment["sentiment_status"]
        ),
        "sentiment_estimated": True,
        "risk_status": (
            "sentiment_low_sample"
            if valid_count < 5
            else "sentiment_limited_weight"
            if valid_count < 10
            else "model_only_derived"
        ),
        "risk_components": {
            "sentiment": round(sentiment_component, 3),
            "disagreement": round(disagreement_component, 3),
            "growth": round(growth_component, 3),
            "volume": round(volume_component, 3),
            "source_coverage": round(source_component, 3),
        },
        "risk_score_estimated": True,
        "representative_contents": representative_contents,
        "representative_content_count": len(representative_contents),
    }
    if not is_bilibili:
        metric.update(
            {
                "sample_scope": "public_search_visible_posts_only",
                "coverage_note": (
                    "Simulation fixture; no platform claim."
                    if simulated
                    else "Search-visible posts only; comment bodies were not collected."
                ),
                "representative_posts": [
                    {"text": r.get("text", ""), "url": r.get("url", "")}
                    for r in records[:3]
                ],
            }
        )
    return metric


def _combined_metric(
    bilibili: dict[str, Any],
    heybox: dict[str, Any],
    *,
    simulated: bool,
) -> dict[str, Any]:
    count = int(bilibili["count"]) + int(heybox["count"])
    valid_count = int(bilibili["sentiment_valid_count"]) + int(
        heybox["sentiment_valid_count"]
    )

    def weighted_by_valid(key: str) -> float | None:
        if not valid_count:
            return None
        terms = []
        for metric in (bilibili, heybox):
            value = metric.get(key)
            weight = int(metric.get("sentiment_valid_count") or 0)
            if value is not None and weight:
                terms.append(float(value) * weight)
        if not terms:
            return None
        return round(
            sum(terms) / valid_count,
            3,
        )

    def weighted_by_count(key: str) -> float:
        if not count:
            return 0.0
        return round(
            (
                float(bilibili.get(key) or 0) * int(bilibili["count"])
                + float(heybox.get(key) or 0) * int(heybox["count"])
            )
            / count,
            3,
        )

    class_counts = {
        key: int(bilibili.get(key) or 0) + int(heybox.get(key) or 0)
        for key in ("positive_count", "neutral_count", "negative_count")
    }

    def rate(count_key: str) -> float | None:
        return round(class_counts[count_key] / valid_count * 100, 2) if valid_count else None

    b_trend = list(bilibili.get("trend") or [])
    h_trend = list(heybox.get("trend") or [])
    size = max(len(b_trend), len(h_trend))
    b_trend = [0] * (size - len(b_trend)) + b_trend
    h_trend = [0] * (size - len(h_trend)) + h_trend
    representative_contents = sorted(
        list(bilibili.get("representative_contents") or [])
        + list(heybox.get("representative_contents") or []),
        key=lambda item: (
            -int(item.get("topic_text_count") or 0),
            str(item.get("platform") or ""),
            str(item.get("content_id") or item.get("url") or ""),
        ),
    )[:3]
    return {
        "negative": rate("negative_count"),
        "positive": rate("positive_count"),
        "neutral": rate("neutral_count"),
        "negative_rate": rate("negative_count"),
        "positive_rate": rate("positive_count"),
        "neutral_rate": rate("neutral_count"),
        "sentiment": weighted_by_valid("sentiment"),
        "sentiment_valid_count": valid_count,
        "sentiment_invalid_count": int(bilibili.get("sentiment_invalid_count") or 0)
        + int(heybox.get("sentiment_invalid_count") or 0),
        **class_counts,
        "low_sample_status": valid_count < 5,
        "sentiment_sample_band": (
            "unavailable" if valid_count == 0 else "low_under_5" if valid_count < 5 else "limited_5_to_9" if valid_count < 10 else "adequate_10_plus"
        ),
        "sentiment_status": "sentiment_data_unavailable" if valid_count == 0 else "mixed_platform_model_output",
        "sentiment_model": "mixed_platform_models" if valid_count else None,
        "sentiment_model_version": "see_platform_metrics" if valid_count else None,
        "heat_score": None,
        "consensus_score": weighted_by_valid("consensus_score"),
        "risk_score": weighted_by_count("risk_score"),
        "count": count,
        "video_count": int(bilibili["video_count"]) + int(heybox["video_count"]),
        "creator_count": (
            int(bilibili.get("creator_count") or 0)
            + int(heybox.get("creator_count") or 0)
        ),
        "comment_count": int(bilibili["comment_count"])
        + int(heybox["comment_count"]),
        "likes_count": int(bilibili["likes_count"]) + int(heybox["likes_count"]),
        "wow": bilibili.get("wow"),
        "trend": [a + b for a, b in zip(b_trend, h_trend)],
        "metrics_source": (
            "simulated_fixture_incomparable_units"
            if simulated
            else "mixed_real_observations_incomparable_units"
        ),
        "simulated": simulated,
        "estimated": True,
        "simulation_seed": "weekly_e2e_fixture_v1" if simulated else None,
        "sample_limited": True,
        "unit_warning": (
            "B站评论与小黑盒公开搜索可见帖子使用不同单位；综合观察值"
            "仅用于界面探索，不可作为跨平台总量。"
        ),
        "representative_contents": representative_contents,
        "representative_content_count": len(representative_contents),
    }


def _deterministic_generated_at(*payloads: dict[str, Any], fallback: date) -> str:
    timestamps: list[datetime] = []
    for payload in payloads:
        for row in payload.get("records") or []:
            value = str(row.get("collected_at") or "").strip()
            if not value:
                continue
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            timestamps.append(parsed.astimezone(timezone.utc))
    if timestamps:
        return max(timestamps).isoformat()
    return f"{fallback.isoformat()}T23:59:59+08:00"


def build_dashboard(
    baseline: dict[str, Any],
    bilibili_payload: dict[str, Any],
    heybox_payload: dict[str, Any],
    *,
    week_id: str,
    start: date,
    end: date,
    simulated: bool,
    sample_quality_by_platform: dict[str, dict[str, Any]] | None = None,
    business_rules: dict[str, Any] | None = None,
    heat_source_artifact_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    business_rules = business_rules or load_canonical_rules(
        Path(__file__).resolve().parents[1]
    )
    sample_quality_by_platform = sample_quality_by_platform or {}
    b_quality = sample_quality_by_platform.get("B站", {})
    low_sample = bool(b_quality.get("low_sample_week")) and not simulated
    prior_weeks = copy.deepcopy(baseline["weeks"])
    display_id = display_week_id(week_id)
    if any(week.get("week_id") == display_id for week in prior_weeks):
        raise ValueError(f"dashboard already contains {display_id}")
    previous_week = prior_weeks[-1]
    previous_topics = {topic["id"]: topic for topic in previous_week["topics"]}
    registry: dict[str, dict[str, Any]] = {}
    for week in prior_weeks:
        for topic in week.get("topics", []):
            registry[topic["id"]] = topic

    records = {
        "B站": [
            row
            for row in bilibili_payload["records"]
            if row.get("canonical_topic_id") and not row.get("is_outlier")
        ],
        "小黑盒": [
            row
            for row in heybox_payload["records"]
            if row.get("canonical_topic_id") and not row.get("is_outlier")
        ],
    }
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for platform, platform_records in records.items():
        for row in platform_records:
            grouped[(platform, str(row["canonical_topic_id"]))].append(row)
    active_ids = sorted(
        {
            topic_id
            for (_, topic_id), rows in grouped.items()
            if rows
        }
    )
    minimum_topics = int(
        business_rules["data_topics"]["qualification"][
            "minimum_active_topic_count"
        ]
    )
    if len(active_ids) < minimum_topics:
        raise ValueError(
            f"fewer than {minimum_topics} evidence-qualified topics: "
            f"{len(active_ids)}"
        )

    topics: list[dict[str, Any]] = []
    evolution: list[dict[str, Any]] = []
    for topic_id in active_ids:
        template = copy.deepcopy(
            registry.get(topic_id)
            or {
                "id": topic_id,
                "chain": topic_id,
                "name": topic_id,
                "name_en": topic_id,
                "descriptor_keywords": [],
            }
        )
        previous = previous_topics.get(topic_id)
        b_rows = grouped.get(("B站", topic_id), [])
        h_rows = grouped.get(("小黑盒", topic_id), [])
        previous_b = (previous or {}).get("platform_metrics", {}).get("B站")
        previous_h = (previous or {}).get("platform_metrics", {}).get("小黑盒")
        b_metric = _platform_metric(
            b_rows,
            previous_b,
            platform="B站",
            simulated=simulated,
        )
        h_metric = _platform_metric(
            h_rows,
            previous_h,
            platform="小黑盒",
            simulated=simulated,
        )
        combined = _combined_metric(b_metric, h_metric, simulated=simulated)
        previous_count = int((previous or {}).get("count") or 0)
        current_count = int(b_metric["count"])
        wow = (
            100.0
            if previous_count == 0 and current_count
            else 0.0
            if previous_count == 0
            else round((current_count - previous_count) / previous_count * 100, 1)
        )
        keyword_stats = {
            "B站": _keyword_stats(b_rows),
            "小黑盒": _keyword_stats(h_rows),
        }
        combined_keywords = _keyword_stats(b_rows + h_rows)
        status_code = (
            "new"
            if previous is None
            else "rising"
            if wow > 10
            else "declining"
            if wow < -10
            else "persistent"
        )
        template.update(
            {
                "id": topic_id,
                "chain": topic_id,
                "name": (
                    b_rows[0].get("canonical_topic_name")
                    if b_rows
                    else h_rows[0].get("canonical_topic_name")
                    if h_rows
                    else template.get("name", topic_id)
                ),
                "name_en": CANONICAL_TOPIC_NAMES_EN.get(topic_id, topic_id),
                "keywords": [row["keyword"] for row in combined_keywords[:15]],
                "platform_keyword_stats": {
                    **keyword_stats,
                    "综合": combined_keywords,
                },
                "platform_metrics": {"B站": b_metric, "小黑盒": h_metric},
                "combined_metrics": combined,
                "count": current_count,
                "comment_count": current_count,
                "video_count": int(b_metric["video_count"]),
                "creator_count": b_metric.get("creator_count"),
                "share": 0,
                "sentiment": b_metric["sentiment"],
                "negative": b_metric["negative_rate"],
                "negative_rate": b_metric["negative_rate"],
                "sentiment_valid_count": b_metric["sentiment_valid_count"],
                "negative_count": b_metric["negative_count"],
                "low_sample_status": b_metric["low_sample_status"],
                "wow": wow,
                "trend": list(b_metric["trend"]),
                "heat_score": None,
                "consensus_score": (
                    int(b_metric["consensus_score"])
                    if b_metric["consensus_score"] is not None
                    else None
                ),
                "risk": int(b_metric["risk_score"]),
                "status": STATUS_ZH[status_code],
                "status_code": status_code,
                "status_en": STATUS_EN[status_code],
                "first_seen": (
                    template.get("first_seen")
                    or display_id
                ),
                "weeks": int((template.get("weeks") or 0)) + 1,
                "cumulative": int((template.get("cumulative") or 0)) + current_count,
                "quotes": [
                    str(row.get("text") or "")
                    for row in (b_rows + h_rows)[:3]
                ],
                "representative_contents": list(combined.get("representative_contents") or []),
                "representative_content_count": int(combined.get("representative_content_count") or 0),
                "representative_videos": list(b_metric.get("representative_contents") or []),
                "metrics_source": (
                    "simulated_fixture"
                    if simulated
                    else "bilibili_real_bounded_sample"
                ),
                "data_type": "simulated" if simulated else "real_sample",
                "estimated": True,
                "core_fields_real": [] if simulated else [
                    "count",
                    "comment_count",
                    "video_count",
                    "trend",
                    "wow",
                ],
                "sentiment_source": (
                    "simulation_fixture"
                    if simulated
                    else str(bilibili_payload["meta"].get("sentiment_model") or "SnowNLP_baseline_only")
                ),
                "sentiment_status": b_metric["sentiment_status"],
                "sentiment_estimated": True,
                "risk_status": b_metric["risk_status"],
                "risk_score_estimated": True,
                "trend_interpretation_eligible": not low_sample,
                "data_provenance": {
                    "B站": {
                        "data_type": "simulated" if simulated else "real_sample",
                        "metrics_source": b_metric["metrics_source"],
                        "sample_limited": True,
                    },
                    "小黑盒": {
                        "data_type": "simulated" if simulated else "real_sample",
                        "metrics_source": h_metric["metrics_source"],
                        "sample_limited": True,
                    },
                    "综合": {
                        "data_type": "simulated" if simulated else "mixed",
                        "metrics_source": combined["metrics_source"],
                    },
                },
            }
        )
        topics.append(template)
        evolution.append(
            {
                "source_week": storage_week_id(previous_week["week_id"]),
                "target_week": week_id,
                "canonical_topic_id": topic_id,
                "source_count": previous_count,
                "target_count": current_count,
                "change_rate": round(wow / 100, 4),
                "evolution_status": template["status"],
            }
        )

    total_bilibili = sum(topic["count"] for topic in topics)
    for topic in topics:
        topic["share"] = (
            round(topic["count"] / total_bilibili, 4) if total_bilibili else 0
        )
    b_all = records["B站"]
    h_all = records["小黑盒"]
    sentiment = _sentiment(b_all)
    b_week_sentiment = _platform_metric(
        b_all, None, platform="B站", simulated=simulated
    )
    h_week_sentiment = _platform_metric(
        h_all, None, platform="小黑盒", simulated=simulated
    )
    combined_week_sentiment = _combined_metric(
        b_week_sentiment, h_week_sentiment, simulated=simulated
    )
    event_result = generate_events(b_all + h_all, week_id=week_id)
    if not str(event_result.get("status") or "").startswith("success_"):
        raise ValueError("current-week event generation failed")
    b_count = len(b_all)
    h_count = len(h_all)
    observed = b_count + h_count
    current_week = {
        "week_id": display_id,
        "label": period_label(start, end),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "topics": topics,
        "events": event_result["events"],
        "event_generation": {
            "status": event_result["status"],
            "candidate_count": event_result["candidate_count"],
            "qualified_count": event_result["qualified_count"],
            "rule_version": EVENT_RULE_VERSION,
        },
        "kpis": {
            "total_volume": b_count,
            "topic_count": len(topics),
            "new_topic_count": len(
                [topic for topic in topics if topic["id"] not in previous_topics]
            ),
            "new_topic_status": "frozen_registry_comparison",
            "continuing_topic_count": len(
                [topic for topic in topics if topic["id"] in previous_topics]
            ),
            "new_topic_ids": [
                topic["id"] for topic in topics if topic["id"] not in previous_topics
            ],
            "continuing_topic_ids": [
                topic["id"] for topic in topics if topic["id"] in previous_topics
            ],
            "total_video_count": sum(
                1
                for value in {
                    str(row.get("bvid") or row.get("url") or "")
                    for row in b_all
                    if row.get("bvid") or row.get("url")
                }
            ),
            "total_creator_count": b_quality.get("independent_author_count"),
            "sentiment_status": (
                "simulation_only"
                if simulated
                else str(bilibili_payload["meta"].get("sentiment_status") or "model_only_unvalidated")
            ),
            "risk_status": (
                "suppressed_low_sample" if low_sample else "model_only_derived"
            ),
            "sample_status": (
                "simulation_fixture"
                if simulated
                else "low_sample_week_publication_blocked"
                if low_sample
                else "bounded_sample_gate_passed_not_platform_census"
            ),
            "low_sample_week": low_sample,
            "sample_quality": b_quality,
        },
        "platform_sentiment_metrics": {
            "B站": {
                key: b_week_sentiment.get(key)
                for key in (
                    "comment_count", "sentiment_valid_count", "sentiment_invalid_count",
                    "positive_count", "neutral_count", "negative_count",
                    "positive_rate", "neutral_rate", "negative_rate",
                    "positive", "neutral", "negative", "sentiment",
                    "sentiment_model", "sentiment_model_version", "sentiment_status",
                    "low_sample_status", "sentiment_sample_band",
                )
            },
            "小黑盒": {
                key: h_week_sentiment.get(key)
                for key in (
                    "comment_count", "sentiment_valid_count", "sentiment_invalid_count",
                    "positive_count", "neutral_count", "negative_count",
                    "positive_rate", "neutral_rate", "negative_rate",
                    "positive", "neutral", "negative", "sentiment",
                    "sentiment_model", "sentiment_model_version", "sentiment_status",
                    "low_sample_status", "sentiment_sample_band",
                )
            },
            "综合": {
                key: combined_week_sentiment.get(key)
                for key in (
                    "comment_count", "sentiment_valid_count", "sentiment_invalid_count",
                    "positive_count", "neutral_count", "negative_count",
                    "positive_rate", "neutral_rate", "negative_rate",
                    "positive", "neutral", "negative", "sentiment",
                    "sentiment_model", "sentiment_model_version", "sentiment_status",
                    "low_sample_status", "sentiment_sample_band",
                )
            },
        },
        "sentiment": {
            "week_id": week_id,
            "text_count": str(b_count),
            "sentiment_valid_count": str(sentiment["sentiment_valid_count"]),
            "positive_count": str(sentiment["positive_count"]),
            "neutral_count": str(sentiment["neutral_count"]),
            "negative_count": str(sentiment["negative_count"]),
            "positive_rate": (
                f"{sentiment['positive_rate'] / 100:.6f}"
                if sentiment["positive_rate"] is not None else None
            ),
            "neutral_rate": (
                f"{sentiment['neutral_rate'] / 100:.6f}"
                if sentiment["neutral_rate"] is not None else None
            ),
            "negative_rate": (
                f"{sentiment['negative_rate'] / 100:.6f}"
                if sentiment["negative_rate"] is not None else None
            ),
            "avg_sentiment_score": (
                f"{sentiment['sentiment']:.6f}"
                if sentiment["sentiment"] is not None else None
            ),
            "sentiment_model": (
                "fixture"
                if simulated
                else str(bilibili_payload["meta"].get("sentiment_model") or "SnowNLP")
            ),
            "sentiment_version": (
                "simulation"
                if simulated
                else str(bilibili_payload["meta"].get("sentiment_model_version") or "0.12.3")
            ),
            "threshold_low": "0.35",
            "threshold_high": "0.65",
            "sentiment_source": (
                "simulation_fixture"
                if simulated
                else str(bilibili_payload["meta"].get("sentiment_model") or "SnowNLP_baseline_only")
            ),
            "sentiment_status": (
                "simulation_only"
                if simulated
                else str(bilibili_payload["meta"].get("sentiment_status") or "model_only_unvalidated")
            ),
        },
        "formal_sentiment_source": {
            "status": "not_qualified",
            "reason": "bounded exploratory sample",
        },
        "platforms": {
            "B站": round(b_count / observed * 100, 2) if observed else 0,
            "小黑盒": round(h_count / observed * 100, 2) if observed else 0,
        },
        "keyword_stats": {
            "B站": _keyword_stats(b_all),
            "小黑盒": _keyword_stats(h_all),
            "综合": _keyword_stats(b_all + h_all),
        },
        "keyword_meta": {
            "B站": {
                "document_total": b_count,
                "scope": "simulated_fixture"
                if simulated
                else "real_bilibili_bounded_sample_mapped_comments",
            },
            "小黑盒": {
                "document_total": h_count,
                "scope": "simulated_fixture"
                if simulated
                else "real_public_search_visible_posts_sample",
            },
            "综合": {
                "document_total": observed,
                "scope": (
                    "simulated_fixture_incomparable_units"
                    if simulated
                    else "mixed_real_text_observations_sample_limited"
                ),
            },
            "rule_version": KEYWORD_RULE_VERSION,
            "quality_gate": "passed_only_minimum_two_traceable_texts_with_valid_topic",
        },
        "data_provenance": SIMULATION_BOUNDARIES if simulated else DATA_BOUNDARIES,
        "sample_quality": sample_quality_by_platform,
        "low_sample_week": low_sample,
        "trend_interpretation_eligible": not low_sample,
        "evolution": evolution,
    }
    if week_id >= business_rules["heat"]["effective_from_week"]:
        apply_heat_v1_to_week(
            current_week,
            previous_week,
            bilibili_payload,
            heybox_payload,
            policy=business_rules["_heat_policy"],
            policy_hash=business_rules["_heat_policy_sha256"],
            source_artifact_hashes=heat_source_artifact_hashes
            or {
                "B站": atomic_json_artifact_sha256(bilibili_payload),
                "小黑盒": atomic_json_artifact_sha256(heybox_payload),
            },
        )
    else:
        current_week["heat_version_status"] = "legacy_week_not_recalculated"
        for topic in current_week["topics"]:
            topic["heat_score"] = None
            topic["heat_status"] = "legacy_week_not_recalculated"
            for metric in (topic.get("platform_metrics") or {}).values():
                metric["heat_score"] = None
                metric["heat_status"] = "legacy_week_not_recalculated"
                metric["heat_score_status"] = "legacy_week_not_recalculated"
            combined = topic.get("combined_metrics") or {}
            combined["heat_score"] = None
            combined["heat_status"] = "legacy_week_not_recalculated"
            combined["heat_score_status"] = "legacy_week_not_recalculated"
    weeks = (prior_weeks + [current_week])[-5:]
    boundaries = SIMULATION_BOUNDARIES if simulated else DATA_BOUNDARIES
    result = copy.deepcopy(baseline)
    result["weeks"] = weeks
    result["meta"].update(
        {
            "generated_at": _deterministic_generated_at(
                bilibili_payload, heybox_payload, fallback=end
            ),
            "default_week_id": display_id,
            "platform_status": boundaries,
            "keyword_rule_version": KEYWORD_RULE_VERSION,
            "event_rule_version": EVENT_RULE_VERSION,
            "sentiment_rule_version": SENTIMENT_RULE_VERSION,
            "week_boundary": {
                "latest_complete_week": week_id,
                "current_open_week": next_week_id(week_id),
                "current_open_week_status": "excluded_from_complete_week_dashboard",
            },
            "notice": (
                f"{weeks[0]['week_id'].split('-')[-1]}—{display_id.split('-')[-1]}"
                "为最近五个完整自然周。"
                + (
                    "当前产物为隔离模拟联调，不得作为真实数据发布。"
                    if simulated
                    else "B站与小黑盒均为有限真实样本，两平台观察单位不可比。"
                )
            ),
            "formal_report_mode": (
                "simulation_fixture"
                if simulated
                else "model_only_exploratory_bounded_sample"
            ),
            "qualified_for_formal_reporting": False,
            "qualified_for_formal_auxiliary_reporting": False,
            "simulation_only": simulated,
            "low_sample_week": low_sample,
            "publication_gate_passed": simulated or not low_sample,
            "sample_quality": sample_quality_by_platform,
            "canonical_rules": public_rule_metadata(business_rules),
            "heat_version_boundary": {
                "legacy_through_week": business_rules["heat"]["legacy_through_week"].replace("_", "-"),
                "canonical_from_week": business_rules["heat"]["effective_from_week"].replace("_", "-"),
                "legacy_recalculated": False,
                "cross_version_scores_directly_comparable": False,
            },
        }
    )
    result["meta"][f"bilibili_w{week_number(week_id):02d}_sample"] = (
        bilibili_payload["meta"]
    )
    result["meta"][f"heybox_w{week_number(week_id):02d}_sample"] = (
        heybox_payload["meta"]
    )
    sanitize_dashboard_keywords(result, business_rules)
    return result


def patch_site_html(
    source: str,
    *,
    dashboard: dict[str, Any],
    dashboard_filename: str,
    report_filename: str,
    preview_filename: str,
    report_markdown_filename: str,
    bilibili_filename: str,
    heybox_filename: str,
) -> str:
    # The publishing boundary must not trust a caller to have attached current
    # rule metadata or applied visible-keyword exclusions.  Rebind both from
    # the canonical policy immediately before embedding the dashboard.
    project_root = Path(__file__).resolve().parents[1]
    business_rules = load_canonical_rules(project_root)
    dashboard = copy.deepcopy(dashboard)
    dashboard.setdefault("meta", {})["canonical_rules"] = public_rule_metadata(
        business_rules
    )
    sanitize_dashboard_keywords(dashboard, business_rules)
    old_display = str(
        json.loads(
            re.search(
                r"const REAL_DASHBOARD_DATA = (\{.*?\});\s*\n",
                source,
                flags=re.S,
            ).group(1)
        )["meta"]["default_week_id"]
    )
    old_storage = storage_week_id(old_display)
    new_display = dashboard["meta"]["default_week_id"]
    new_storage = storage_week_id(new_display)
    old_label = old_display.split("-")[-1]
    new_label = new_display.split("-")[-1]
    previous_new_label = dashboard["weeks"][-2]["week_id"].split("-")[-1]
    old_dashboard = json.loads(
        re.search(
            r"const REAL_DASHBOARD_DATA = (\{.*?\});\s*\n",
            source,
            flags=re.S,
        ).group(1)
    )
    old_period_label = old_dashboard["weeks"][-1]["label"]

    # Current-week prose and paths are promoted first. Historical report labels
    # are repaired afterwards, and embedded JSON is injected last so retained
    # historical week IDs are never rewritten.
    source = source.replace(old_storage, new_storage)
    source = source.replace(old_display, new_display)
    source = source.replace(old_label, new_label)
    source = re.sub(
        r"下载 W\d{2} 历史周报",
        f"下载 {previous_new_label} 历史周报",
        source,
    )
    source = re.sub(
        r"Download W\d{2} historical report",
        f"Download {previous_new_label} historical report",
        source,
    )
    source = re.sub(
        r"dashboard_data_apex_W\d{2}_W\d{2}\.json",
        dashboard_filename,
        source,
    )
    source = re.sub(
        r"outputs/bilibili_apex_\d{4}_W\d{2}\.json",
        f"outputs/{bilibili_filename}",
        source,
    )
    source = re.sub(
        r"outputs/heybox_apex_\d{4}_W\d{2}_public_search\.json",
        f"outputs/{heybox_filename}",
        source,
    )
    source = re.sub(
        r"reports/APEX_CHINA_W\d{2}_Weekly_Community_Report\.preview\.json",
        f"reports/{preview_filename}",
        source,
    )
    source = re.sub(
        r'(<a[^>]*id="downloadW\d{2}Report"[^>]*href=")[^"]+("[^>]*>)',
        rf'\1reports/{report_filename}\2',
        source,
        count=1,
    )
    source = re.sub(
        r'downloadW\d{2}HistoricalReport',
        f'download{previous_new_label}HistoricalReport',
        source,
    )
    source = re.sub(
        r'(<a[^>]*id="downloadW\d{2}HistoricalReport"[^>]*href=")[^"]+("[^>]*>)',
        rf'\1reports/APEX_CHINA_{previous_new_label}_Weekly_Community_Report.xlsx\2',
        source,
        count=1,
    )
    source = re.sub(
        r"reports/APEX_CHINA_W\d{2}_Weekly_Community_Report\.md",
        f"reports/{report_markdown_filename}",
        source,
    )
    start = date.fromisoformat(dashboard["weeks"][-1]["start"])
    end = date.fromisoformat(dashboard["weeks"][-1]["end"])
    source = source.replace(old_period_label, period_label(start, end))
    payload = json.dumps(dashboard, ensure_ascii=False, separators=(",", ":"))
    source, count = re.subn(
        r"const REAL_DASHBOARD_DATA = \{.*?\};\s*\n",
        f"const REAL_DASHBOARD_DATA = {payload};\n",
        source,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise ValueError("could not replace embedded dashboard data")
    public_rules = json.dumps(
        dashboard["meta"]["canonical_rules"],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    source, rule_count = re.subn(
        r"const EMBEDDED_CANONICAL_RULE_METADATA = \{.*?\};\s*\n",
        f"const EMBEDDED_CANONICAL_RULE_METADATA = {public_rules};\n",
        source,
        count=1,
        flags=re.S,
    )
    if rule_count != 1:
        raise ValueError("could not replace embedded canonical rule metadata")
    source = re.sub(
        r"const CURRENT_REPORT_PREVIEW_PATH='[^']+';",
        f"const CURRENT_REPORT_PREVIEW_PATH='reports/{preview_filename}';",
        source,
        count=1,
    )
    source = re.sub(
        r"const CURRENT_REPORT_XLSX_PATH='[^']+';",
        f"const CURRENT_REPORT_XLSX_PATH='reports/{report_filename}';",
        source,
        count=1,
    )
    source = re.sub(
        r"link\.download='APEX_CHINA_W\d{2}_Weekly_Community_Report\.xlsx'",
        f"link.download='{report_filename}'",
        source,
        count=1,
    )
    return source


def copy_public_assets(project_root: Path, release_dir: Path) -> None:
    for directory in ("assets", "templates"):
        source = project_root / directory
        if source.is_dir():
            shutil.copytree(
                source,
                release_dir / directory,
                dirs_exist_ok=True,
            )
    reports_dir = release_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    for pattern in (
        "APEX_CHINA_W*_Weekly_Community_Report.xlsx",
        "APEX_CHINA_W*_Weekly_Community_Report.md",
        "APEX_CHINA_W*_Weekly_Community_Report.preview.json",
    ):
        for path in (project_root / "reports").glob(pattern):
            shutil.copy2(path, reports_dir / path.name)
