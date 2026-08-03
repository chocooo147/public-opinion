from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


REPRESENTATIVE_CONTENT_RULE_VERSION = "apex_representative_content_v1.0.0"
BVID_RE = re.compile(r"^BV[0-9A-Za-z]{10}$")
AVID_RE = re.compile(r"^(?:av|AV)\d+$")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _platform_code(platform: str) -> str:
    value = _clean(platform).lower()
    if value in {"b站", "bilibili", "bili"}:
        return "bilibili"
    if value in {"小黑盒", "heybox", "xiaoheihe"}:
        return "heybox"
    return value


def _content_id(row: dict[str, Any], platform: str) -> str:
    if platform == "bilibili":
        value = _clean(
            row.get("bvid")
            or row.get("video_id")
            or row.get("platform_content_id")
            or row.get("content_id")
        )
        if value:
            return value
        match = re.search(r"/video/(BV[0-9A-Za-z]{10}|av\d+)", _clean(row.get("url") or row.get("source_url")), re.I)
        return match.group(1) if match else ""
    value = _clean(
        row.get("post_id")
        or row.get("platform_content_id")
        or row.get("content_id")
    )
    if value:
        return value
    match = re.search(r"/link/(\d+)", _clean(row.get("url") or row.get("source_url")))
    if match:
        return match.group(1)
    return _clean(row.get("text_id") or row.get("comment_id"))


def valid_content_id(value: Any, platform: str) -> bool:
    content_id = _clean(value)
    code = _platform_code(platform)
    if code == "bilibili":
        return bool(BVID_RE.fullmatch(content_id) or AVID_RE.fullmatch(content_id))
    return bool(content_id and content_id.lower() not in {"undefined", "null", "nan"})


def valid_source_url(value: Any, platform: str) -> bool:
    url = _clean(value)
    if not url or any(token in url.lower() for token in ("undefined", "null", "nan")):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.netloc.lower().split(":", 1)[0]
    code = _platform_code(platform)
    if code == "bilibili":
        return host == "b23.tv" or host == "bilibili.com" or host.endswith(".bilibili.com")
    if code == "heybox":
        return host == "xiaoheihe.cn" or host.endswith(".xiaoheihe.cn")
    return False


def _evidence_id(row: dict[str, Any]) -> str:
    value = _clean(row.get("text_id") or row.get("comment_id"))
    if value:
        return value
    return hashlib.sha256(_clean(row.get("text")).encode("utf-8")).hexdigest()[:24]


def load_bilibili_metadata(apex_root: Path) -> dict[str, dict[str, str]]:
    """Load only traceable metadata from immutable raw JSONL captures."""
    result: dict[str, dict[str, str]] = {}
    raw_root = apex_root / "data/raw/bilibili"
    for path in sorted(raw_root.rglob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeDecodeError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(row, dict):
                continue
            bvid = _content_id(row, "bilibili")
            if not valid_content_id(bvid, "bilibili"):
                continue
            content_metadata_row = (
                path.name.startswith(("videos_", "search_cards_"))
                or bool(row.get("video_author_name") or row.get("creator_type") or row.get("video_publish_time"))
            )
            candidate = {
                "content_id": bvid,
                "title": _clean(row.get("video_title") or row.get("title") or row.get("content_title")),
                "url": _clean(row.get("source_url") or row.get("url")),
                "author_name": _clean(
                    row.get("video_author_name")
                    or (row.get("author_name") if content_metadata_row else "")
                ),
                "publish_time": _clean(row.get("video_publish_time") or row.get("content_publish_time")),
            }
            current = result.setdefault(bvid, {key: "" for key in candidate})
            current["content_id"] = bvid
            for key in ("title", "url", "author_name", "publish_time"):
                value = candidate[key]
                if value and (not current.get(key) or (key == "title" and len(value) > len(current[key]))):
                    current[key] = value
    return result


def enrich_bilibili_records(
    rows: Iterable[dict[str, Any]],
    metadata: dict[str, dict[str, str]],
) -> None:
    for row in rows:
        bvid = _content_id(row, "bilibili")
        source = metadata.get(bvid)
        if not source:
            continue
        row.setdefault("bvid", bvid)
        if not _clean(row.get("title") or row.get("video_title") or row.get("content_title")) and source.get("title"):
            row["video_title"] = source["title"]
        if not _clean(row.get("url") or row.get("source_url")) and source.get("url"):
            row["source_url"] = source["url"]
        if not _clean(row.get("author_name")) and source.get("author_name"):
            row["content_author_name"] = source["author_name"]
        if not _clean(row.get("video_publish_time")) and source.get("publish_time"):
            row["video_publish_time"] = source["publish_time"]


def build_representative_contents(
    rows: Iterable[dict[str, Any]],
    *,
    platform: str,
    source_data_version: str = "",
    limit: int = 3,
) -> list[dict[str, Any]]:
    code = _platform_code(platform)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        content_id = _content_id(row, code)
        url = _clean(row.get("source_url") or row.get("url"))
        if code == "bilibili" and not valid_content_id(content_id, code):
            continue
        if code == "heybox" and not (valid_content_id(content_id, code) or valid_source_url(url, code)):
            continue
        grouped[content_id or url].append(row)

    topic_total = len({_evidence_id(row) for group in grouped.values() for row in group})
    candidates: list[dict[str, Any]] = []
    for _, group in grouped.items():
        first = group[0]
        content_id = _content_id(first, code)
        evidence_ids = sorted({_evidence_id(row) for row in group})
        title = ""
        author_name = ""
        publish_time = ""
        url = ""
        for row in group:
            title = title or _clean(
                row.get("video_title")
                or row.get("content_title")
                or row.get("post_title")
                or row.get("title")
                or (row.get("text") if code == "heybox" else "")
            )
            author_name = author_name or _clean(
                row.get("content_author_name") or row.get("author_name") or row.get("author")
            )
            publish_time = publish_time or _clean(
                row.get("video_publish_time")
                or row.get("content_publish_time")
                or (row.get("publish_time") if code == "heybox" else "")
            )
            candidate_url = _clean(row.get("source_url") or row.get("url"))
            if not url and valid_source_url(candidate_url, code):
                url = candidate_url
        versions = Counter(
            _clean(row.get("source_data_version") or row.get("data_version"))
            for row in group
            if _clean(row.get("source_data_version") or row.get("data_version"))
        )
        version = versions.most_common(1)[0][0] if versions else source_data_version
        topic_text_count = len(evidence_ids)
        candidates.append(
            {
                "platform": code,
                "content_type": "video" if code == "bilibili" else "post",
                "content_id": content_id,
                "title": title[:200],
                "url": url,
                "source_url": url,
                "author_name": author_name,
                "publish_time": publish_time,
                "topic_text_count": topic_text_count,
                "topic_comment_count": topic_text_count,
                "topic_share": round(topic_text_count / topic_total, 6) if topic_total else 0.0,
                "source_data_version": version,
                "evidence_text_ids": evidence_ids,
                "quality_status": "passed",
            }
        )
    candidates.sort(key=lambda item: (-item["topic_text_count"], item["content_id"], item["url"]))
    return candidates[: max(0, limit)]


def validate_representative_contents(items: Any) -> list[str]:
    if not isinstance(items, list):
        return ["representative_contents_not_array"]
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(items):
        prefix = f"item_{index}"
        if not isinstance(item, dict):
            errors.append(f"{prefix}:not_object")
            continue
        platform = _platform_code(item.get("platform", ""))
        content_id = _clean(item.get("content_id"))
        title = _clean(item.get("title"))
        url = _clean(item.get("url") or item.get("source_url"))
        if not (title or content_id or url):
            errors.append(f"{prefix}:empty_object")
        if platform not in {"bilibili", "heybox"}:
            errors.append(f"{prefix}:invalid_platform")
        if platform == "bilibili" and not valid_content_id(content_id, platform):
            errors.append(f"{prefix}:invalid_bilibili_content_id")
        if url and not valid_source_url(url, platform):
            errors.append(f"{prefix}:invalid_url")
        count = item.get("topic_text_count")
        if isinstance(count, bool) or not isinstance(count, (int, float)) or count != count:
            errors.append(f"{prefix}:invalid_topic_text_count")
        if not item.get("evidence_text_ids"):
            errors.append(f"{prefix}:missing_evidence")
        key = (platform, content_id or url)
        if key in seen:
            errors.append(f"{prefix}:duplicate_content")
        seen.add(key)
    return errors
