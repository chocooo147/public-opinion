#!/usr/bin/env python3
"""Canonical sentiment validation and aggregation helpers.

Percentages in dashboard JSON are backend products.  The browser must display
these values verbatim and must never infer missing values as zero.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


LABEL_MAP = {
    "positive": "positive",
    "neutral": "neutral",
    "negative": "negative",
    "积极": "positive",
    "正面": "positive",
    "中性": "neutral",
    "负面": "negative",
    "消极": "negative",
}
FAILURE_MARKERS = ("fail", "error", "unavailable", "not_run", "未运行", "失败")


def normalize_sentiment_label(value: Any) -> str | None:
    """Normalize supported English/Chinese labels without inventing a default."""
    if value is None:
        return None
    token = str(value).strip().casefold()
    return LABEL_MAP.get(token)


def validate_sentiment_record(record: dict[str, Any]) -> tuple[bool, str | None, str | None]:
    """Return validity, normalized label and a deterministic exclusion reason."""
    status = str(record.get("sentiment_status") or "").strip().casefold()
    if any(marker in status for marker in FAILURE_MARKERS):
        return False, None, "sentiment_model_failed_or_unavailable"
    model = str(record.get("sentiment_model") or "").strip()
    if not model or model == "no_observations":
        return False, None, "sentiment_model_missing"
    label = normalize_sentiment_label(record.get("sentiment_label"))
    if label is None:
        return False, None, "sentiment_label_missing_or_unmapped"

    probabilities = record.get("sentiment_probabilities")
    if probabilities is not None:
        if not isinstance(probabilities, dict):
            return False, None, "sentiment_probabilities_invalid"
        normalized: dict[str, float] = {}
        for raw_label, raw_value in probabilities.items():
            mapped = normalize_sentiment_label(raw_label)
            if mapped is None:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                return False, None, "sentiment_probability_not_numeric"
            if value < 0 or value > 1:
                return False, None, "sentiment_probability_out_of_range"
            normalized[mapped] = value
        if label not in normalized:
            return False, None, "predicted_label_probability_missing"
        if normalized and abs(sum(normalized.values()) - 1.0) > 0.02:
            return False, None, "sentiment_probabilities_do_not_sum_to_one"
    return True, label, None


def summarize_sentiment(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Create count-backed rates; missing valid evidence stays null."""
    rows = list(records)
    labels: Counter[str] = Counter()
    valid_scores: list[float] = []
    invalid_reasons: Counter[str] = Counter()
    models: set[str] = set()
    versions: set[str] = set()
    statuses: set[str] = set()
    for record in rows:
        valid, label, reason = validate_sentiment_record(record)
        if not valid or label is None:
            invalid_reasons[reason or "unknown"] += 1
            continue
        labels[label] += 1
        models.add(str(record.get("sentiment_model") or ""))
        versions.add(str(record.get("sentiment_model_version") or record.get("sentiment_version") or "unknown"))
        statuses.add(str(record.get("sentiment_status") or "unknown"))
        try:
            valid_scores.append(float(record.get("sentiment_score")))
        except (TypeError, ValueError):
            pass

    valid_count = sum(labels.values())
    counts = {name: int(labels[name]) for name in ("positive", "neutral", "negative")}

    def rate(name: str) -> float | None:
        return round(counts[name] / valid_count * 100, 2) if valid_count else None

    unavailable = valid_count == 0
    return {
        "comment_count": len(rows),
        "sentiment_valid_count": valid_count,
        "sentiment_invalid_count": len(rows) - valid_count,
        "positive_count": counts["positive"],
        "neutral_count": counts["neutral"],
        "negative_count": counts["negative"],
        "positive_rate": rate("positive"),
        "neutral_rate": rate("neutral"),
        "negative_rate": rate("negative"),
        # Backward-compatible aliases. They deliberately remain null if there
        # is no valid evidence.
        "positive": rate("positive"),
        "neutral": rate("neutral"),
        "negative": rate("negative"),
        "sentiment": round(sum(valid_scores) / len(valid_scores), 6) if valid_scores else None,
        "sentiment_model": ",".join(sorted(models)) if models else None,
        "sentiment_model_version": ",".join(sorted(versions)) if versions else None,
        "sentiment_status": (
            "sentiment_data_unavailable"
            if unavailable
            else ",".join(sorted(statuses))
        ),
        "low_sample_status": valid_count < 5,
        "sentiment_sample_band": (
            "unavailable" if unavailable else "low_under_5" if valid_count < 5 else "limited_5_to_9" if valid_count < 10 else "adequate_10_plus"
        ),
        "sentiment_risk_weight": 0.0 if valid_count < 5 else 0.25 if valid_count < 10 else 1.0,
        "invalid_reasons": dict(sorted(invalid_reasons.items())),
    }


def annotate_sentiment_record(record: dict[str, Any]) -> dict[str, Any]:
    """Add audit fields to a copy of one prediction record."""
    row = dict(record)
    valid, label, reason = validate_sentiment_record(row)
    row["sentiment_label_normalized"] = label
    row["sentiment_statistics_included"] = valid
    row["sentiment_statistics_exclusion_reason"] = reason
    return row
