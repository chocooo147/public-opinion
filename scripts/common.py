from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

RAW_FIELDS = [
    "text_id", "publish_time", "platform", "text", "likes", "comments",
    "shares", "url", "source_type",
]

DERIVED_FIELDS = [
    "publish_datetime", "week_start", "week_end", "week_label", "clean_text",
    "text_length", "is_short", "duplicate_group_size", "is_duplicate",
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_rules(path: Path | None = None) -> dict:
    path = path or project_root() / "config" / "quality_rules.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def timestamp_id() -> str:
    return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")


def clean_whitespace(value: str) -> str:
    value = (value or "").replace("\u3000", " ").replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", value).strip()


def effective_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def normalize_for_duplicate(text: str) -> str:
    return re.sub(r"[\W_]+", "", (text or "").casefold(), flags=re.UNICODE)


def parse_datetime(value: str, timezone_name: str = "Asia/Shanghai") -> datetime | None:
    value = clean_whitespace(value)
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    timezone = ZoneInfo(timezone_name)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def week_fields(dt: datetime | None) -> tuple[str, str, str]:
    if dt is None:
        return "", "", ""
    start = dt.date() - timedelta(days=dt.weekday())
    end = start + timedelta(days=6)
    if start.year == end.year:
        label = f"{start.year}年{start.month}.{start.day}—{end.month}.{end.day}"
    else:
        label = f"{start.year}年{start.month}.{start.day}—{end.year}年{end.month}.{end.day}"
    return start.isoformat(), end.isoformat(), label


def parse_nonnegative_int(value: str) -> tuple[str, bool]:
    value = clean_whitespace(value)
    if value == "":
        return "", True
    try:
        number = int(float(value.replace(",", "")))
    except ValueError:
        return "", False
    return (str(number), True) if number >= 0 else ("", False)


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = [{key: (value or "") for key, value in row.items() if key is not None} for row in reader]
    return fields, rows


def write_csv(path: Path, fields: list[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
