#!/usr/bin/env python3
"""小黑盒网页端公开搜索结果卡片的有界采集器。

仅读取已登录网页端搜索结果列表中可见的帖子卡片，不进入帖子详情页，
不采集评论正文，也不绕过登录、验证码、限流或其他访问控制。作者身份
仅来自卡片中公开可见的用户主页链接；页面没有可靠 Reach 字段时保持缺失。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from bilibili_apex_collector import (
    SafetyStop,
    content_hash,
    last_complete_week,
    load_json_yaml,
    normalize_text,
    parse_count,
    resolve_browser_runtime,
)

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://www.xiaoheihe.cn"
CARD_SELECTOR = 'a[href^="/app/bbs/link/"]'
DATE_RE = re.compile(r"^(?:(?P<year>\d{4})-)?(?P<month>\d{1,2})-(?P<day>\d{1,2})$")
RELATIVE_DATE_RE = re.compile(r"^(?P<days>\d+)天前$")
LEVEL_RE = re.compile(r"^Lv\.\d+", re.IGNORECASE)
AUTHOR_PROFILE_RE = re.compile(r"^/app/user/profile/(?P<author_uid>\d+)$")

CSV_FIELDS = [
    "text_id",
    "post_id",
    "publish_time",
    "platform",
    "text",
    "title",
    "summary",
    "community",
    "displayed_date",
    "author_name",
    "author_uid",
    "likes",
    "comments",
    "shares",
    "views",
    "url",
    "source_type",
    "query_keyword",
    "collected_at",
    "content_hash",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_safety_block(title: str, body: str) -> None:
    text = f"{title}\n{body}".casefold()
    if any(token in text for token in ("验证码", "安全验证", "captcha", "访问过于频繁", "请求被拦截", "操作频繁")):
        raise SafetyStop("检测到验证码、安全验证或访问限制，小黑盒采集已停止。")


def parse_displayed_date(value: str, now: datetime, start: datetime, end: datetime) -> datetime | None:
    """Resolve only dates that can be placed unambiguously inside the target week."""
    clean = normalize_text(value)
    local_now = now.astimezone(start.tzinfo)
    if clean in {"今天", "刚刚"}:
        candidate = local_now.replace(hour=12, minute=0, second=0, microsecond=0)
        return candidate if start <= candidate <= end else None
    if clean == "昨天":
        candidate = (local_now - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
        return candidate if start <= candidate <= end else None
    relative = RELATIVE_DATE_RE.fullmatch(clean)
    if relative:
        candidate = (local_now - timedelta(days=int(relative.group("days")))).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        return candidate if start <= candidate <= end else None
    match = DATE_RE.fullmatch(clean)
    if not match:
        return None
    years = [int(match.group("year"))] if match.group("year") else [
        start.year - 1,
        start.year,
        start.year + 1,
    ]
    matches: list[datetime] = []
    for year in years:
        try:
            candidate = datetime(
                year,
                int(match.group("month")),
                int(match.group("day")),
                12,
                tzinfo=start.tzinfo,
            )
        except ValueError:
            continue
        if start <= candidate <= end:
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def parse_card_text(
    card_text: str,
    href: str,
    keyword: str,
    author_profile_href: str = "",
) -> dict | None:
    lines = [normalize_text(line) for line in card_text.splitlines()]
    lines = [line for line in lines if line]
    if len(lines) < 6 or not re.fullmatch(r"/app/bbs/link/\d+", href or ""):
        return None
    try:
        date_index = next(
            index
            for index in range(len(lines) - 3, 0, -1)
            if DATE_RE.fullmatch(lines[index])
            or RELATIVE_DATE_RE.fullmatch(lines[index])
            or lines[index] in {"今天", "昨天", "刚刚"}
        )
    except StopIteration:
        return None
    if date_index + 2 >= len(lines):
        return None
    likes = parse_count(lines[date_index + 1])
    comments = parse_count(lines[date_index + 2])
    if likes is None or comments is None:
        return None
    level_index = next((i for i, line in enumerate(lines[:date_index]) if LEVEL_RE.match(line)), -1)
    content_start = level_index + 1 if level_index >= 0 else 1
    content = lines[content_start:date_index - 1]
    if not content:
        return None
    title = content[0]
    summary = " ".join(content[1:])
    post_id = href.rstrip("/").split("/")[-1]
    author_match = AUTHOR_PROFILE_RE.fullmatch(author_profile_href or "")
    return {
        "post_id": post_id,
        "author_name": " ".join(lines[:level_index] if level_index > 0 else lines[:1]),
        "author_uid": author_match.group("author_uid") if author_match else "",
        "title": title,
        "summary": summary,
        "community": lines[date_index - 1],
        "displayed_date": lines[date_index],
        "likes": likes,
        "comments": comments,
        "url": f"{BASE_URL}{href}",
        "query_keyword": keyword,
    }


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in CSV_FIELDS} for row in rows)


def collect(config: dict, keywords: list[str], start: datetime, end: datetime, now: datetime) -> tuple[list[dict], list[dict]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("未安装 Python Playwright，无法执行小黑盒网页采集。") from exc

    visible: list[dict] = []
    selected: dict[str, dict] = {}
    with sync_playwright() as playwright:
        executable_path = config.get("browser_executable_path") or None
        channel = None if executable_path else (config.get("browser_channel") or None)
        profile_dir = config.get("browser_profile_dir")
        if not profile_dir:
            raise RuntimeError("小黑盒采集必须设置 APEX_BROWSER_PROFILE，以使用独立的持久登录环境。")
        launch_options = {
            "headless": bool(config["headless"]),
            "args": ["--disable-dev-shm-usage"],
        }
        if executable_path:
            launch_options["executable_path"] = executable_path
        elif channel:
            launch_options["channel"] = channel
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            locale="zh-CN",
            timezone_id=config["timezone"],
            **launch_options,
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            for keyword in keywords:
                page.goto(
                    f"{BASE_URL}/app/search/list?q={quote_plus(keyword)}",
                    wait_until="domcontentloaded",
                    timeout=45000,
                )
                page.wait_for_timeout(1200)
                body = page.locator("body").inner_text(timeout=10000)
                detect_safety_block(page.title(), body)
                if page.locator('nav img[alt$="头像"]').count() == 0:
                    raise SafetyStop("未检测到小黑盒登录头像；请先完成服务器独立浏览器登录。")
                cards = page.locator(CARD_SELECTOR)
                count = min(cards.count(), int(config["max_cards_per_keyword"]))
                for index in range(count):
                    card = cards.nth(index)
                    author_links = card.locator('a[href^="/app/user/profile/"]')
                    author_profile_href = (
                        author_links.first.get_attribute("href")
                        if author_links.count()
                        else ""
                    )
                    parsed = parse_card_text(
                        card.inner_text(timeout=5000),
                        card.get_attribute("href") or "",
                        keyword,
                        author_profile_href or "",
                    )
                    if not parsed:
                        continue
                    parsed["collected_at"] = now.isoformat()
                    visible.append(parsed)
                    published = parse_displayed_date(parsed["displayed_date"], now, start, end)
                    if not published:
                        continue
                    text = normalize_text(f"{parsed['title']} {parsed['summary']}")
                    selected.setdefault(
                        parsed["post_id"],
                        {
                            "text_id": f"heybox:{parsed['post_id']}",
                            "post_id": parsed["post_id"],
                            "publish_time": published.isoformat(),
                            "platform": "小黑盒",
                            "text": text,
                            "likes": parsed["likes"],
                            "comments": parsed["comments"],
                            "shares": "",
                            "views": "",
                            "url": parsed["url"],
                            "source_type": "post_card",
                            "query_keyword": keyword,
                            "content_hash": content_hash(text),
                            "displayed_date": parsed["displayed_date"],
                            "title": parsed["title"],
                            "summary": parsed["summary"],
                            "community": parsed["community"],
                            "author_name": parsed["author_name"],
                            "author_uid": parsed["author_uid"],
                            "collected_at": now.isoformat(),
                        },
                    )
                    if len(selected) >= int(config["max_total_cards"]):
                        break
                if len(selected) >= int(config["max_total_cards"]):
                    break
                low, high = config["page_delay_seconds"]
                time.sleep(random.uniform(float(low), float(high)))
        finally:
            context.close()
    return visible, list(selected.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="小黑盒 APEX 公开搜索结果卡片有界采集")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keyword", action="append", dest="keywords", help="覆盖默认关键词，可重复")
    parser.add_argument("--max-keywords", type=int)
    parser.add_argument("--max-cards", type=int)
    args = parser.parse_args()

    try:
        config = resolve_browser_runtime(load_json_yaml(ROOT / "config/heybox_public_search_collector.yaml"))
    except ValueError as exc:
        parser.error(str(exc))
    keywords = args.keywords or list(config["keywords"])
    max_keywords = args.max_keywords or int(config["max_keywords"])
    config["max_total_cards"] = args.max_cards or int(config["max_total_cards"])
    keywords = keywords[:max_keywords]
    now = datetime.now(ZoneInfo(config["timezone"]))
    start, end, week_id = last_complete_week(now, config["timezone"])
    print(f"目标自然周：{week_id} {start.isoformat()} 至 {end.isoformat()}")
    print(f"公开搜索关键词：{keywords}；本次最多保留 {config['max_total_cards']} 张帖子卡片")
    if args.dry_run:
        return 0

    run_id = now.strftime("%Y%m%dT%H%M%S")
    raw_path = ROOT / f"data/raw/heybox/{week_id}/visible_cards_{run_id}.jsonl"
    csv_path = ROOT / f"outputs/heybox_public_search_{week_id}_{run_id}.csv"
    manifest_path = ROOT / f"outputs/heybox_public_search_{week_id}_{run_id}_manifest.json"
    try:
        visible, selected = collect(config, keywords, start, end, now)
    except (SafetyStop, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    incomplete_author_ids = [
        row.get("post_id", "")
        for row in selected
        if not row.get("author_name") or not row.get("author_uid")
    ]
    if incomplete_author_ids:
        print(
            "小黑盒帖子作者身份不完整，停止输出 Heat v1.0 输入："
            + ", ".join(incomplete_author_ids),
            file=sys.stderr,
        )
        return 2
    append_jsonl(raw_path, visible)
    write_csv(csv_path, selected)
    manifest = {
        "generated_at": now.isoformat(),
        "week_id": week_id,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "keywords": keywords,
        "visible_cards": len(visible),
        "selected_unique_cards": len(selected),
        "raw_file": str(raw_path.relative_to(ROOT)),
        "raw_sha256": sha256(raw_path),
        "output_file": str(csv_path.relative_to(ROOT)),
        "output_sha256": sha256(csv_path),
        "collection_scope": "Logged-in Xiaoheihe web public-search result cards only; not a platform-wide census.",
        "comment_body_collection": False,
        "detail_page_collection": False,
        "post_author_identity_collection": "visible_author_name_and_profile_uid",
        "post_author_identity_complete": True,
        "reach_collection_status": "missing_no_reliable_visible_web_field",
        "sample_limited": True,
        "formal_reporting_qualified": False,
        "date_rule": "Only cards whose displayed date resolves unambiguously into the last complete Asia/Shanghai natural week.",
        "stop_policy": "Stop immediately on missing login, CAPTCHA, security verification, or rate limiting.",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
