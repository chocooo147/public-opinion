#!/usr/bin/env python3
"""B站公开页面 APEX 舆情试采集器。

不使用官方 API；不绕过登录、验证码或访问控制。原始 JSONL 仅追加写入，
统一 CSV、状态和报告均使用独立文件。需要 Python Playwright 才能进行实时采集。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, urljoin
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from project_paths import configured_root  # noqa: E402

FIELDS = [
    "text_id", "publish_time", "publish_time_raw", "week_id", "week_start", "week_end",
    "platform", "source_type", "text", "title", "author_name", "author_uid", "bvid", "comment_id",
    "parent_id", "likes", "comments", "shares", "views", "danmaku", "favorites", "coins",
    "url", "query_keyword", "is_mobile_game_keyword", "collected_at", "raw_file", "content_hash",
    "duplicate_reason", "suspected_duplicate",
]


class SafetyStop(RuntimeError):
    pass


def resolve_browser_runtime(config: dict, environ: dict[str, str] | None = None) -> dict:
    """Resolve cloud-safe browser settings without storing machine paths in project config."""
    env = os.environ if environ is None else environ
    resolved = dict(config)
    profile_dir = env.get("APEX_BROWSER_PROFILE", "").strip()
    executable_path = env.get("APEX_BROWSER_EXECUTABLE", "").strip()
    headless = env.get("APEX_HEADLESS", "").strip().casefold()
    if profile_dir:
        resolved["browser_profile_dir"] = profile_dir
    if executable_path:
        resolved["browser_executable_path"] = executable_path
    if headless:
        if headless not in {"1", "true", "yes", "0", "false", "no"}:
            raise ValueError("APEX_HEADLESS 仅接受 true/false、yes/no 或 1/0。")
        resolved["headless"] = headless in {"1", "true", "yes"}
    return resolved


def load_json_yaml(path: Path) -> dict:
    """项目配置采用 JSON 兼容 YAML，避免引入额外依赖。"""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def last_complete_week(now: datetime, timezone_name: str = "Asia/Shanghai") -> tuple[datetime, datetime, str]:
    tz = ZoneInfo(timezone_name)
    local_now = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
    this_monday = (local_now - timedelta(days=local_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start = this_monday - timedelta(days=7)
    end = this_monday - timedelta(microseconds=1)
    iso_year, iso_week, _ = start.isocalendar()
    return start, end, f"{iso_year}_W{iso_week:02d}"


def week_bounds(week_id: str, timezone_name: str) -> tuple[datetime, datetime, str]:
    match = re.fullmatch(r"(?P<year>\d{4})_W(?P<week>\d{2})", week_id)
    if not match:
        raise ValueError("--week 必须使用 YYYY_Www 格式")
    start_date = datetime.fromisocalendar(
        int(match.group("year")), int(match.group("week")), 1
    )
    tz = ZoneInfo(timezone_name)
    start = start_date.replace(tzinfo=tz)
    return start, start + timedelta(days=7) - timedelta(microseconds=1), week_id


def assign_week(value: datetime, timezone_name: str = "Asia/Shanghai") -> tuple[str, str, str]:
    tz = ZoneInfo(timezone_name)
    local = value.astimezone(tz) if value.tzinfo else value.replace(tzinfo=tz)
    start = (local - timedelta(days=local.weekday())).date()
    end = start + timedelta(days=6)
    iso_year, iso_week, _ = start.isocalendar()
    return f"{iso_year}_W{iso_week:02d}", start.isoformat(), end.isoformat()


def normalize_text(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def content_hash(text: str) -> str:
    normalized = re.sub(r"[\W_]+", "", normalize_text(text).casefold(), flags=re.UNICODE)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def parse_count(value: str | int | None) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().replace(",", "")
    multiplier = 1
    if text.endswith("万"):
        multiplier, text = 10000, text[:-1]
    elif text.lower().endswith("k"):
        multiplier, text = 1000, text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return None


def extract_bvid(value: str) -> str:
    match = re.search(r"BV[0-9A-Za-z]{10}", value or "")
    return match.group(0) if match else ""


def extract_json_object(source: str, marker: str) -> dict:
    search_from = 0
    while True:
        pos = source.find(marker, search_from)
        if pos < 0:
            return {}
        cursor = pos + len(marker)
        while cursor < len(source) and source[cursor].isspace():
            cursor += 1
        if cursor >= len(source) or source[cursor] != "=":
            search_from = pos + len(marker)
            continue
        start = source.find("{", cursor + 1)
        if start < 0:
            return {}
        depth, quoted, escaped = 0, False, False
        for index in range(start, len(source)):
            char = source[index]
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(source[start:index + 1])
                    except json.JSONDecodeError:
                        break
                    return parsed if isinstance(parsed, dict) else {}
        search_from = pos + len(marker)


def parse_search_html(source: str, keyword: str) -> list[dict]:
    records, seen = [], set()
    pattern = re.compile(r'<a[^>]+href=["\'](?P<href>(?:https?:)?//www\.bilibili\.com/video/[^"\']+)["\'][^>]*(?:title=["\'](?P<title>[^"\']*)["\'])?', re.I)
    for match in pattern.finditer(source):
        url = match.group("href")
        if url.startswith("//"):
            url = "https:" + url
        bvid = extract_bvid(url)
        if bvid and bvid not in seen:
            records.append({"bvid": bvid, "url": f"https://www.bilibili.com/video/{bvid}", "title": normalize_text(match.group("title") or ""), "query_keyword": keyword})
            seen.add(bvid)
    return records


def parse_video_state(state: dict, url: str, keyword: str) -> dict:
    video = state.get("videoData", {}) if isinstance(state, dict) else {}
    stat = video.get("stat", {}) or {}
    owner = video.get("owner", {}) or {}
    return {
        "bvid": video.get("bvid") or extract_bvid(url),
        "url": url,
        "title": normalize_text(video.get("title", "")),
        "description": normalize_text(video.get("desc", "")),
        "author_name": normalize_text(owner.get("name", "")),
        "publish_epoch": video.get("pubdate"),
        "views": stat.get("view"), "danmaku": stat.get("danmaku"), "comments": stat.get("reply"),
        "favorites": stat.get("favorite"), "coins": stat.get("coin"), "shares": stat.get("share"),
        "likes": stat.get("like"), "query_keyword": keyword,
    }


def parse_video_html(source: str, url: str, keyword: str) -> dict:
    state = extract_json_object(source, "__INITIAL_STATE__")
    parsed = parse_video_state(state, url, keyword)
    title_match = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']*)', source, re.I)
    desc_match = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']*)', source, re.I)
    parsed["title"] = normalize_text(parsed["title"] or (title_match.group(1) if title_match else ""))
    parsed["description"] = normalize_text(parsed["description"] or (desc_match.group(1) if desc_match else ""))
    return parsed


def detect_safety_block(title: str, body: str) -> None:
    text = f"{title}\n{body}".casefold()
    if any(token in text for token in ("验证码", "安全验证", "captcha", "访问过于频繁", "请求被拦截")):
        raise SafetyStop("检测到验证码、安全验证或访问限制，采集已停止。")
    if any(token in text for token in ("登录后", "请先登录", "扫码登录")):
        raise SafetyStop("页面要求登录，请在浏览器内自行完成登录后再重新运行。")


def deduplicate(rows: list[dict], threshold: float = .90, window_minutes: int = 10) -> tuple[list[dict], list[dict]]:
    kept, filtered = [], []
    seen_bvid, seen_comment, seen_text, seen_hash = set(), set(), set(), set()
    author_history: dict[str, list[tuple[datetime | None, str]]] = defaultdict(list)
    for original in rows:
        row = dict(original)
        text = normalize_text(row.get("text", ""))
        hsh = row.get("content_hash") or content_hash(text)
        reason = ""
        comment_key = (row.get("bvid", ""), row.get("comment_id", ""))
        if row.get("source_type") in ("video_title", "video_description") and row.get("bvid") and (row["bvid"], row["source_type"]) in seen_bvid:
            reason = "duplicate_bvid_source"
        elif row.get("comment_id") and comment_key in seen_comment:
            reason = "duplicate_comment_id"
        elif text and text in seen_text:
            reason = "exact_text_duplicate"
        elif hsh and hsh in seen_hash:
            reason = "normalized_hash_duplicate"
        if not text:
            reason = reason or "empty_text"
        if reason:
            row["duplicate_reason"] = reason
            filtered.append(row)
            continue
        key = (row.get("bvid", ""), row.get("source_type", ""))
        if row.get("bvid") and row.get("source_type") in ("video_title", "video_description"):
            seen_bvid.add(key)
        if row.get("comment_id"):
            seen_comment.add(comment_key)
        seen_text.add(text)
        if hsh:
            seen_hash.add(hsh)
        suspected = False
        author = row.get("author_name", "")
        try:
            current_time = datetime.fromisoformat(row.get("publish_time", ""))
        except (ValueError, TypeError):
            current_time = None
        if author and text:
            for old_time, old_text in author_history[author]:
                within = not current_time or not old_time or abs((current_time - old_time).total_seconds()) <= window_minutes * 60
                if within and SequenceMatcher(None, text, old_text).ratio() >= threshold:
                    suspected = True
                    break
            author_history[author].append((current_time, text))
        row["suspected_duplicate"] = int(suspected)
        row["duplicate_reason"] = ""
        kept.append(row)
    return kept, filtered


def select_candidates_round_robin(
    candidates_by_keyword: dict[str, list[dict]],
    keywords: list[str],
    limit: int,
) -> list[dict]:
    """Select a bounded, deterministic candidate pool without first-query monopoly."""
    selected: list[dict] = []
    seen: set[str] = set()
    max_depth = max((len(candidates_by_keyword.get(keyword, [])) for keyword in keywords), default=0)
    for index in range(max_depth):
        for keyword in keywords:
            candidates = candidates_by_keyword.get(keyword, [])
            if index >= len(candidates):
                continue
            item = candidates[index]
            bvid = str(item.get("bvid") or "")
            if not bvid or bvid in seen:
                continue
            selected.append(item)
            seen.add(bvid)
            if len(selected) >= limit:
                return selected
    return selected


def filter_excluded(rows: list[dict], exclude_terms: list[str]) -> tuple[list[dict], list[dict]]:
    kept, filtered = [], []
    terms = [(term, term.casefold().replace(" ", "")) for term in exclude_terms]
    for original in rows:
        row = dict(original)
        haystack = f"{row.get('title', '')} {row.get('text', '')}".casefold().replace(" ", "")
        matched = next((raw for raw, normalized in terms if normalized and normalized in haystack), "")
        if matched:
            row["duplicate_reason"] = f"excluded_term:{matched}"
            filtered.append(row)
        else:
            kept.append(row)
    return kept, filtered


def append_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number} 不是 JSON 对象")
            records.append(record)
    return records


def write_csv_new(path: Path, rows: list[dict]) -> Path:
    candidate, number = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
        number += 1
    candidate.parent.mkdir(parents=True, exist_ok=True)
    with candidate.open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return candidate


@dataclass
class Paths:
    videos: Path
    comments: Path
    csv: Path
    log: Path
    checkpoint: Path


class Collector:
    def __init__(
        self,
        keywords: dict,
        config: dict,
        start: datetime,
        end: datetime,
        week_id: str,
        artifact_dir: Path | None = None,
    ):
        self.keywords, self.config, self.start, self.end, self.week_id = keywords, config, start, end, week_id
        self.artifact_dir = artifact_dir
        raw = artifact_dir or configured_root(ROOT, "data_root") / "raw" / "bilibili"
        log = (
            raw / f"bilibili_apex_{week_id}.log"
            if artifact_dir
            else ROOT / "logs" / f"bilibili_apex_{week_id}.log"
        )
        self.report_path = (
            raw / f"bilibili_apex_{week_id}_report.md"
            if artifact_dir
            else ROOT / "reports" / "bilibili_apex_pilot_report.md"
        )
        self.paths = Paths(raw / f"videos_{week_id}.jsonl", raw / f"comments_{week_id}.jsonl", raw / f"bilibili_apex_{week_id}.csv", log, raw / f"checkpoint_{week_id}.json")
        self.collected_at = datetime.now(timezone.utc).astimezone().isoformat()
        self.stats = Counter()
        self.failures: list[str] = []
        self.paths.log.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=self.paths.log, level=logging.INFO, encoding="utf-8", format="%(asctime)s %(levelname)s %(message)s")

    def _sleep(self):
        low, high = self.config["page_delay_seconds"]
        time.sleep(random.uniform(float(low), float(high)))

    def _row(self, source_type: str, text: str, video: dict, comment: dict | None = None) -> dict:
        comment = comment or {}
        if source_type == "top_level_comment":
            epoch = comment.get("publish_epoch")
            publish_text = str(comment.get("publish_time") or "").strip()
            if epoch:
                dt = datetime.fromtimestamp(int(epoch), ZoneInfo(self.config["timezone"]))
            elif publish_text:
                dt = datetime.fromisoformat(publish_text)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=ZoneInfo(self.config["timezone"]))
            else:
                raise ValueError("一级评论缺少自身发布时间，禁止回退到视频发布时间")
            author_name = normalize_text(comment.get("author_name", ""))
            if not author_name:
                raise ValueError("一级评论缺少自身作者，禁止回退到视频作者")
        else:
            epoch = video.get("publish_epoch")
            dt = datetime.fromtimestamp(int(epoch), ZoneInfo(self.config["timezone"])) if epoch else None
            author_name = normalize_text(video.get("author_name", ""))
        wid, ws, we = assign_week(dt, self.config["timezone"]) if dt else ("", "", "")
        clean = normalize_text(text)
        comment_id = str(comment.get("comment_id") or "")
        identity = (
            f"{video.get('bvid', '')}:{comment_id}"
            if source_type == "top_level_comment" and comment_id
            else f"{video.get('bvid','')}:{source_type}"
        )
        return {
            "text_id": f"bilibili:{identity}", "publish_time": dt.isoformat() if dt else "",
            "publish_time_raw": str(epoch or ""), "week_id": wid, "week_start": ws, "week_end": we,
            "platform": "B站", "source_type": source_type, "text": clean, "title": video.get("title", ""),
            "author_name": author_name, "author_uid": str(comment.get("author_uid", "")), "bvid": video.get("bvid", ""),
            "comment_id": comment_id, "parent_id": str(comment.get("parent_id", "")),
            "likes": comment.get("likes") if comment else video.get("likes"), "comments": video.get("comments"),
            "shares": video.get("shares"), "views": video.get("views"), "danmaku": video.get("danmaku"),
            "favorites": video.get("favorites"), "coins": video.get("coins"), "url": video.get("url", ""),
            "query_keyword": video.get("query_keyword", ""),
            "is_mobile_game_keyword": int(video.get("query_keyword") in self.keywords.get("mobile_keywords", [])),
            "collected_at": self.collected_at,
            "raw_file": str(self.paths.comments if source_type == "top_level_comment" else self.paths.videos),
            "content_hash": content_hash(clean),
            "duplicate_reason": "", "suspected_duplicate": 0,
        }

    def run_live(self) -> tuple[list[dict], list[dict]]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return self.run_live_node()
        all_keywords = self.keywords["core_keywords"] + self.keywords["experience_keywords"]
        checkpoint = {
            "completed_keywords": [],
            "completed_bvids": [],
            "discovered_candidates_by_keyword": {},
            "discovery_stats_by_keyword": {},
        }
        if self.paths.checkpoint.exists():
            checkpoint.update(json.loads(self.paths.checkpoint.read_text(encoding="utf-8")))
        candidates_by_keyword = checkpoint.get("discovered_candidates_by_keyword")
        if not isinstance(candidates_by_keyword, dict):
            candidates_by_keyword = {}
        checkpoint["discovered_candidates_by_keyword"] = candidates_by_keyword
        discovery_stats_by_keyword = checkpoint.get("discovery_stats_by_keyword")
        if not isinstance(discovery_stats_by_keyword, dict):
            discovery_stats_by_keyword = {}
        checkpoint["discovery_stats_by_keyword"] = discovery_stats_by_keyword
        for keyword, keyword_stats in discovery_stats_by_keyword.items():
            if (
                keyword in checkpoint["completed_keywords"]
                and isinstance(candidates_by_keyword.get(keyword), list)
                and isinstance(keyword_stats, dict)
            ):
                self.stats["discovery_requests"] += int(keyword_stats.get("requests", 0))
                self.stats["search_video_hits"] += int(keyword_stats.get("hits", 0))
        completed_bvids = set(checkpoint["completed_bvids"])
        existing_videos = {
            video.get("bvid"): video
            for video in read_jsonl(self.paths.videos)
            if video.get("bvid")
        }
        completed_comments = [
            comment
            for comment in read_jsonl(self.paths.comments)
            if comment.get("bvid") in completed_bvids
        ]
        self.stats["videos_read"] = len(completed_bvids.intersection(existing_videos))
        self.stats["videos_with_comments_collected"] = len({
            comment.get("bvid") for comment in completed_comments if comment.get("bvid")
        })
        self.stats["comments_collected"] = len(completed_comments)
        rows: list[dict] = []
        for comment in completed_comments:
            bvid = comment.get("bvid")
            if bvid not in completed_bvids or bvid not in existing_videos:
                continue
            try:
                row = self._row(
                    "top_level_comment",
                    comment.get("text", ""),
                    existing_videos[bvid],
                    comment,
                )
            except ValueError:
                self.stats["comments_missing_exact_metadata"] += 1
                continue
            if row["week_id"] == self.week_id:
                rows.append(row)
        with sync_playwright() as p:
            browser = None
            context = None
            executable_path = self.config.get("browser_executable_path") or None
            channel = None if executable_path else (self.config.get("browser_channel") or None)
            launch_options = {
                "headless": bool(self.config["headless"]),
                "args": ["--disable-dev-shm-usage"],
            }
            if executable_path:
                launch_options["executable_path"] = executable_path
            elif channel:
                launch_options["channel"] = channel
            profile_dir = self.config.get("browser_profile_dir")
            if profile_dir:
                Path(profile_dir).mkdir(parents=True, exist_ok=True)
                context = p.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    locale="zh-CN",
                    timezone_id=self.config["timezone"],
                    **launch_options,
                )
                page = context.pages[0] if context.pages else context.new_page()
            else:
                browser = p.chromium.launch(**launch_options)
                context = browser.new_context(locale="zh-CN", timezone_id=self.config["timezone"])
                page = context.new_page()
            try:
                for keyword in all_keywords:
                    if (
                        keyword in checkpoint["completed_keywords"]
                        and isinstance(candidates_by_keyword.get(keyword), list)
                        and isinstance(discovery_stats_by_keyword.get(keyword), dict)
                    ):
                        continue
                    keyword_candidates: dict[str, dict] = {}
                    keyword_requests = 0
                    keyword_hits = 0
                    for page_no in range(1, int(self.config["max_search_pages_per_keyword"]) + 1):
                        page.goto(f"https://search.bilibili.com/video?keyword={quote(keyword)}&page={page_no}", wait_until="domcontentloaded", timeout=45000)
                        detect_safety_block(page.title(), page.locator("body").inner_text(timeout=10000))
                        found = parse_search_html(page.content(), keyword)
                        keyword_requests += 1
                        keyword_hits += len(found)
                        self.stats["discovery_requests"] += 1
                        self.stats["search_video_hits"] += len(found)
                        for item in found:
                            keyword_candidates.setdefault(item["bvid"], item)
                        self._sleep()
                    candidates_by_keyword[keyword] = list(keyword_candidates.values())
                    discovery_stats_by_keyword[keyword] = {
                        "requests": keyword_requests,
                        "hits": keyword_hits,
                    }
                    if keyword not in checkpoint["completed_keywords"]:
                        checkpoint["completed_keywords"].append(keyword)
                    self.paths.checkpoint.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
                candidates = select_candidates_round_robin(
                    candidates_by_keyword,
                    all_keywords,
                    int(self.config["max_videos"]),
                )
                self.stats["candidate_videos_discovered"] = len({
                    item.get("bvid")
                    for items in candidates_by_keyword.values()
                    if isinstance(items, list)
                    for item in items
                    if item.get("bvid")
                })
                self.stats["candidate_videos_selected"] = len(candidates)
                for hit in candidates:
                    bvid = hit["bvid"]
                    if bvid in checkpoint["completed_bvids"]:
                        continue
                    try:
                        page.goto(hit["url"], wait_until="domcontentloaded", timeout=45000)
                        body = page.locator("body").inner_text(timeout=10000)
                        detect_safety_block(page.title(), body)
                        state = page.evaluate("() => globalThis.__INITIAL_STATE__ || {}")
                        video = parse_video_state(state, hit["url"], hit["query_keyword"])
                        if not video.get("title") or not video.get("publish_epoch"):
                            video = parse_video_html(page.content(), hit["url"], hit["query_keyword"])
                        if bvid not in existing_videos:
                            append_jsonl(self.paths.videos, [video])
                            existing_videos[bvid] = video
                        self.stats["videos_read"] += 1
                        visible_comments = self._extract_visible_comments(page)
                        if visible_comments:
                            self.stats["videos_with_comments_collected"] += 1
                            self.stats["comments_collected"] += len(visible_comments[: int(self.config["max_comments_per_video"])])
                        for comment in visible_comments[: int(self.config["max_comments_per_video"])]:
                            comment["bvid"] = bvid
                        append_jsonl(
                            self.paths.comments,
                            visible_comments[: int(self.config["max_comments_per_video"])],
                        )
                        for comment in visible_comments[: int(self.config["max_comments_per_video"])]:
                            try:
                                row = self._row("top_level_comment", comment.get("text", ""), video, comment)
                            except ValueError as exc:
                                self.stats["comments_missing_exact_metadata"] += 1
                                logging.warning("跳过无法精确归周的评论 %s: %s", bvid, exc)
                                continue
                            if row["week_id"] == self.week_id:
                                rows.append(row)
                        checkpoint["completed_bvids"].append(bvid)
                        self.paths.checkpoint.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
                        if len(rows) >= int(self.config["target_max_valid_texts"]):
                            break
                    except SafetyStop:
                        raise
                    except Exception as exc:
                        message = f"{bvid}: {type(exc).__name__}: {exc}"
                        self.failures.append(message)
                        logging.exception("页面解析失败 %s", bvid)
                    self._sleep()
            finally:
                if context is not None:
                    context.close()
                if browser is not None:
                    browser.close()
        included, excluded = filter_excluded(rows, self.keywords.get("exclude_terms", []))
        valid, duplicates = deduplicate(included, float(self.config["similarity_threshold"]), int(self.config["similarity_window_minutes"]))
        return valid, excluded + duplicates

    def _extract_visible_comments(self, page) -> list[dict]:
        script = """() => {
          const root=document.querySelector('bili-comments')?.shadowRoot;
          return [...(root?.querySelectorAll('bili-comment-thread-renderer')||[])].map((thread,index)=>{
            const renderer=thread.shadowRoot?.querySelector('bili-comment-renderer');
            const sr=renderer?.shadowRoot;
            const user=sr?.querySelector('bili-comment-user-info')?.shadowRoot?.querySelector('#user-name');
            const rich=sr?.querySelector('bili-rich-text')?.shadowRoot?.querySelector('#contents');
            const actions=sr?.querySelector('bili-comment-action-buttons-renderer')?.shadowRoot;
            return {comment_id:renderer?.getAttribute('data-id')||`visible-${index}`,parent_id:'0',
              text:(rich?.textContent||'').trim(),publish_time:(actions?.querySelector('#pubdate')?.textContent||'').trim(),
              author_name:(user?.textContent||'').trim(),author_uid:user?.getAttribute('data-user-profile-id')||'',
              likes:(actions?.querySelector('#like #count')?.textContent||'').trim()};
          }).filter(x=>x.text);
        }"""
        page.mouse.wheel(0, 1600)
        page.wait_for_timeout(1800)
        comments = page.evaluate(script)
        for _ in range(int(self.config.get("retry_count", 0))):
            if comments:
                break
            page.mouse.wheel(0, 1600)
            page.wait_for_timeout(int(float(self.config.get("retry_backoff_seconds", 0)) * 1000))
            detect_safety_block(page.title(), page.locator("body").inner_text(timeout=10000))
            comments = page.evaluate(script)
        return comments

    def run_live_node(self) -> tuple[list[dict], list[dict]]:
        configured_node = os.environ.get("APEX_NODE_EXECUTABLE", "").strip()
        candidates = [
            Path(configured_node) if configured_node else Path(""),
            Path(shutil.which("node") or ""),
        ]
        node = next((p for p in candidates if str(p) and p.is_file()), None)
        modules_text = os.environ.get("APEX_NODE_MODULES", "").strip()
        modules = Path(modules_text) if modules_text else ROOT / "node_modules"
        worker = ROOT / "crawler" / "bilibili_playwright_worker.cjs"
        if node is None or not modules.is_dir() or not worker.is_file():
            raise RuntimeError("未找到可用的 Node Playwright 运行时。")
        temp_dir = self.artifact_dir or ROOT / "work"
        temp_dir.mkdir(parents=True, exist_ok=True)
        token = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        request_path = temp_dir / f"bilibili_worker_request_{token}.json"
        result_path = temp_dir / f"bilibili_worker_result_{token}.json"
        request_path.write_text(json.dumps({
            "keywords": self.keywords, "config": self.config,
            "start_epoch": self.start.timestamp(), "end_epoch": self.end.timestamp(),
        }, ensure_ascii=False), encoding="utf-8")
        env = dict(__import__("os").environ)
        env["NODE_PATH"] = str(modules)
        completed = subprocess.run(
            [str(node), str(worker), "--input", str(request_path), "--output", str(result_path)],
            cwd=ROOT, env=env, text=True, capture_output=True, timeout=1800,
        )
        if completed.returncode != 0 or not result_path.exists():
            raise RuntimeError(f"Node Playwright 后端失败：{completed.stderr.strip() or completed.stdout.strip()}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.stats.update(result.get("stats", {}))
        self.failures.extend(result.get("failures", []))
        append_jsonl(self.paths.videos, result.get("videos", []))
        append_jsonl(self.paths.comments, result.get("comments", []))
        if result.get("stop_reason"):
            raise SafetyStop(result["stop_reason"])
        videos = {v.get("bvid"): v for v in result.get("videos", [])}
        rows = []
        for comment in result.get("comments", []):
            video = videos.get(comment.get("bvid"), {"bvid": comment.get("bvid", "")})
            try:
                row = self._row("top_level_comment", comment.get("text", ""), video, comment)
            except ValueError:
                self.stats["comments_missing_exact_metadata"] += 1
                continue
            if row["week_id"] == self.week_id:
                rows.append(row)
        included, excluded = filter_excluded(rows, self.keywords.get("exclude_terms", []))
        valid, duplicates = deduplicate(included, float(self.config["similarity_threshold"]), int(self.config["similarity_window_minutes"]))
        return valid, excluded + duplicates


def main() -> int:
    parser = argparse.ArgumentParser(description="B站 APEX 公开舆情试采集（严格自然周）")
    parser.add_argument("--dry-run", action="store_true", help="只显示目标周和配置，不访问网页")
    parser.add_argument("--parse-html", type=Path, help="仅解析本地视频 HTML，用于少量页面测试")
    parser.add_argument("--url", default="https://www.bilibili.com/video/BV0000000000")
    parser.add_argument("--keyword", default="Apex英雄")
    parser.add_argument("--week", help="目标完整自然周，格式 YYYY_Www；默认最近完整周")
    parser.add_argument("--artifact-dir", type=Path, help="隔离保存本次运行的 checkpoint、原始文件、CSV、日志和报告")
    args = parser.parse_args()
    keywords = load_json_yaml(ROOT / "config" / "bilibili_apex_keywords.yaml")
    try:
        config = resolve_browser_runtime(load_json_yaml(ROOT / "config" / "bilibili_apex_collector.yaml"))
    except ValueError as exc:
        parser.error(str(exc))
    start, end, week_id = (
        week_bounds(args.week, config["timezone"])
        if args.week
        else last_complete_week(datetime.now(ZoneInfo(config["timezone"])), config["timezone"])
    )
    print(f"目标自然周：{week_id} {start.isoformat()} 至 {end.isoformat()}")
    if args.dry_run:
        print(f"关键词数：{len(keywords['core_keywords']) + len(keywords['experience_keywords'])}；目标有效文本：{config['target_min_valid_texts']}—{config['target_max_valid_texts']}")
        return 0
    if args.parse_html:
        parsed = parse_video_html(args.parse_html.read_text(encoding="utf-8"), args.url, args.keyword)
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
        return 0
    collector = Collector(keywords, config, start, end, week_id, artifact_dir=args.artifact_dir)
    stop_reason = ""
    try:
        valid, filtered = collector.run_live()
    except (SafetyStop, RuntimeError) as exc:
        stop_reason = str(exc)
        logging.error(stop_reason)
        valid, filtered = [], []
        print(stop_reason, file=sys.stderr)
    csv_path = write_csv_new(collector.paths.csv, valid)
    generate_report(collector.report_path, collector, valid, filtered, csv_path, stop_reason)
    return 2 if stop_reason else 0


def tokens(text: str) -> list[str]:
    items = re.findall(r"[a-z][a-z0-9]{1,}|[\u4e00-\u9fff]{2,}", text.casefold())
    return [x for item in items for x in ([item] if len(item) <= 4 or re.match(r"[a-z]", item) else [item[i:i+2] for i in range(len(item)-1)])]


def generate_report(path: Path, collector: Collector, valid: list[dict], filtered: list[dict], csv_path: Path, stop_reason: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_day = Counter(r.get("publish_time", "")[:10] or "[缺失]" for r in valid)
    by_type = Counter(r.get("source_type", "") for r in valid)
    by_keyword = Counter(r.get("query_keyword", "") for r in valid)
    high = Counter(word for r in valid for word in tokens(r.get("text", ""))).most_common(30)
    rng = random.Random(int(collector.config["random_seed"]))
    samples = rng.sample(valid, min(30, len(valid)))
    rejected = rng.sample(filtered, min(20, len(filtered)))
    total = len(valid) + len(filtered)
    empty = sum(not normalize_text(r.get("text", "")) for r in valid + filtered)
    missing_time = sum(not r.get("publish_time") for r in valid + filtered)
    suitable = len(valid) >= int(collector.config["target_min_valid_texts"]) and not stop_reason
    used = sorted(set(r.get("query_keyword", "") for r in valid + filtered if r.get("query_keyword")))
    lines = [
        "# B站《Apex英雄》公开舆情试采集报告", "",
        f"- 目标自然周：{collector.week_id}（{collector.start.isoformat()} 至 {collector.end.isoformat()}）",
        f"- 实际采集时间：{collector.collected_at}", f"- 使用关键词：{', '.join(used) if used else '尚未成功执行页面采集'}",
        f"- Discovery 请求数：{collector.stats['discovery_requests']}",
        f"- 搜索结果命中数：{collector.stats['search_video_hits']}",
        f"- 唯一候选视频数：{collector.stats['candidate_videos_discovered']}；按现有上限选取：{collector.stats['candidate_videos_selected']}",
        f"- 成功读取视频数量：{collector.stats['videos_read']}；采到可见评论的视频数：{collector.stats['videos_with_comments_collected']}；可见评论数：{collector.stats['comments_collected']}",
        f"- 有效文本：{len(valid)}；过滤文本：{len(filtered)}；去重前：{total}；重复/过滤率：{(len(filtered)/total if total else 0):.2%}",
        f"- 空文本率：{(empty/total if total else 0):.2%}；发布时间缺失率：{(missing_time/total if total else 0):.2%}",
        f"- 安全停止或运行限制：{stop_reason or '无'}", f"- 统一 CSV：`{csv_path}`", "",
        "## 文本数量与分布", "", "### 每日文本量", "",
    ]
    lines += [f"- {day}: {count}" for day, count in sorted(by_day.items())] or ["- 暂无数据"]
    lines += ["", "### 来源类型", ""] + ([f"- {key}: {value}（{value/len(valid):.2%}）" for key, value in by_type.items()] if valid else ["- 暂无数据"])
    lines += ["", "### 关键词命中量", ""] + ([f"- {key}: {value}" for key, value in by_keyword.most_common()] if by_keyword else ["- 暂无数据"])
    lines += ["", "## 前30个高频词", "", ", ".join(f"{word}({count})" for word, count in high) or "暂无数据"]
    lines += ["", "## 随机30条有效文本", ""] + ([f"- [{r.get('source_type')}] {r.get('text')}" for r in samples] if samples else ["- 暂无数据"])
    lines += ["", "## 随机20条过滤文本", ""] + ([f"- [{r.get('duplicate_reason')}] {r.get('text')}" for r in rejected] if rejected else ["- 暂无数据"])
    lines += ["", "## 页面与访问情况", "", f"- 解析失败：{len(collector.failures)} 次", f"- 登录、验证码或限流：{stop_reason or '未检测到'}"]
    lines += ["", "## 扩展判断", "", f"- 是否适合扩大到8个自然周：{'是，但仍需用户确认后执行' if suitable else '否'}"]
    lines += ["- 判断依据：" + ("已达到试采数量且未触发访问限制。" if suitable else "尚未达到100条有效文本，或采集环境/访问状态需要先解决。")]
    lines += ["", "## 下一步建议", "", "- 首先复核 apex手游 的单独标记和端游/手游混淆比例。", "- 根据过滤样本补充 APEX 同名排除词。", "- 评论时间若页面未公开显示，应保留为空，不推断。", "- 只有用户确认后才把范围扩大到最近8个完整自然周。", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
