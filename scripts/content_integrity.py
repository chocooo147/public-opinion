#!/usr/bin/env python3
"""Traceable event and keyword generation for APEX weekly dashboard data."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Iterable


KEYWORD_RULE_VERSION = "apex_keyword_quality_v2.0.0"
EVENT_RULE_VERSION = "apex_event_evidence_v1.0.0"
SENTIMENT_RULE_VERSION = "apex_sentiment_count_contract_v2.1.0"


KEYWORD_RULES: tuple[dict[str, Any], ...] = (
    {"normalized": "S30赛季", "entity_type": "season", "patterns": (r"\bs\s*[- ]?30\b", r"30\s*赛季", r"赛季\s*30", r"第\s*30\s*赛季", r"诸神烙印")},
    {"normalized": "S29赛季", "entity_type": "season", "patterns": (r"\bs\s*[- ]?29\b", r"29\s*赛季", r"赛季\s*29", r"第\s*29\s*赛季")},
    {"normalized": "R-99", "entity_type": "weapon", "patterns": (r"(?<![a-z0-9])r\s*[- ]?99(?![a-z0-9])",)},
    {"normalized": "CAR冲锋枪", "entity_type": "weapon", "patterns": (r"(?<![a-z])c\.?a\.?r\.?(?![a-z])", r"car\s*冲锋枪")},
    {"normalized": "RE-45", "entity_type": "weapon", "patterns": (r"(?<![a-z0-9])re\s*[- ]?45(?![a-z0-9])",)},
    {"normalized": "EVA-8", "entity_type": "weapon", "patterns": (r"(?<![a-z0-9])eva\s*[- ]?8(?![a-z0-9])",)},
    {"normalized": "30-30", "entity_type": "weapon", "patterns": (r"(?<!\d)30\s*[- ]?30(?!\d)", r"三零三零")},
    {"normalized": "R-301", "entity_type": "weapon", "patterns": (r"(?<![a-z0-9])r\s*[- ]?301(?![a-z0-9])", r"(?<!\d)301(?!\d)")},
    {"normalized": "武器平衡", "entity_type": "gameplay_issue", "patterns": (r"(?:武器|枪械|r99|car|re45|eva8).{0,12}(?:削弱|加强|平衡|伤害|强度|容错)", r"(?:削弱|加强|平衡).{0,12}(?:武器|枪械|r99|car|re45|eva8)")},
    {"normalized": "补给箱改动", "entity_type": "gameplay_change", "patterns": (r"(?:补给箱|蓝红箱|黄金箱|神话箱|箱子).{0,14}(?:改|砍|移除|废除|刷新|掉落)", r"(?:改|砍|移除|废除).{0,14}(?:补给箱|蓝红箱|黄金箱|神话箱|箱子)")},
    {"normalized": "战利品调整", "entity_type": "gameplay_change", "patterns": (r"(?:战利品|物资|配件|资源).{0,14}(?:改|砍|削|刷新|掉落|减少|调整)", r"(?:改|砍|削|减少|调整).{0,14}(?:战利品|物资|配件|资源)")},
    {"normalized": "复活机制", "entity_type": "gameplay_system", "patterns": (r"复活(?:信标|机制|队友|重生)", r"重生机制")},
    {"normalized": "联动活动", "entity_type": "live_service_event", "patterns": (r"赛博朋克.{0,8}联动", r"联动(?:活动|皮肤|上线)")},
    {"normalized": "排位环境", "entity_type": "community_issue", "patterns": (r"(?:排位|单排|钻排|铂金).{0,18}(?:外挂|炸鱼|匹配|队友|公平|环境)", r"(?:外挂|炸鱼|匹配|公平).{0,18}(?:排位|单排|钻排|铂金)")},
    {"normalized": "反作弊", "entity_type": "community_risk", "patterns": (r"外挂", r"作弊", r"举报.{0,8}(?:封|外挂|作弊)")},
    {"normalized": "服务器稳定性", "entity_type": "technical_issue", "patterns": (r"服务器", r"(?:掉线|延迟|卡顿|排队).{0,8}(?:对局|游戏|服务器)")},
    {"normalized": "赛事表现", "entity_type": "esports", "patterns": (r"\b(?:plq|algs|enc|ewc)\b", r"(?:赛事|比赛|门票|三连鸡)")},
    {"normalized": "手柄与设置", "entity_type": "player_help", "patterns": (r"(?:手柄|视角|灵敏度|设置)",)},
)


EVENT_RULES: tuple[dict[str, Any], ...] = (
    {
        "rule_id": "s30_gameplay_loot_changes",
        "title": "S30赛季武器与战利品调整",
        "summary": "玩家围绕S30赛季的枪械强度、物资来源与补给箱机制展开集中讨论；相关反馈同时涉及战斗节奏、发育效率和版本期待。",
        "title_en": "S30 Weapon and Loot Changes",
        "summary_en": "Players concentrated on S30 weapon strength, resource availability, and supply-bin changes, linking them to combat pace, gearing efficiency, and expectations for the new season.",
        "event_type": "game_update",
        "patterns": (r"\bs\s*[- ]?30\b", r"30\s*赛季", r"赛季\s*30", r"诸神烙印", r"补给箱", r"战利品", r"物资.{0,12}(?:砍|削|减少|改)", r"(?:r99|car|re45|eva8).{0,12}(?:削|改|强度|伤害)"),
    },
    {
        "rule_id": "ranked_fairness_and_cheating",
        "title": "排位公平与作弊投诉",
        "summary": "排位玩家将外挂、疑似炸鱼和举报封禁结果联系到竞技公平，讨论集中在对局可信度与继续参与排位的意愿。",
        "title_en": "Ranked Fairness and Cheating Complaints",
        "summary_en": "Ranked players connected cheating, suspected smurfing, and ban outcomes to competitive fairness, match credibility, and their willingness to keep playing ranked.",
        "event_type": "community_risk",
        "patterns": (r"外挂", r"作弊", r"炸鱼", r"举报.{0,10}(?:封|外挂|作弊)", r"公平竞技"),
    },
    {
        "rule_id": "creator_return_discussion",
        "title": "内容创作者回归讨论",
        "summary": "评论集中提到内容创作者重新更新或回归，但需达到独立内容覆盖门槛后才可作为关键事件展示。",
        "title_en": "Creator Return Discussion",
        "summary_en": "Comments noted a creator's return, but the discussion must span independent content sources before it can be shown as a key event.",
        "event_type": "creator_activity",
        "patterns": (r"天国的.{0,8}复活", r"突然复活", r"终于复活", r"你.{0,4}复活了"),
    },
    {
        "rule_id": "competitive_result_discussion",
        "title": "赛事晋级与战队表现",
        "summary": "赛事观众讨论晋级门票、连续获胜与选手表现；只有跨独立内容形成覆盖时才进入关键事件。",
        "title_en": "Qualification and Team Performance",
        "summary_en": "Esports viewers discussed qualification, consecutive wins, and player performance; the candidate is displayed only when evidence spans independent content sources.",
        "event_type": "esports",
        "patterns": (r"\b(?:enc|plq|algs|ewc)\b", r"门票", r"三连鸡", r"晋级"),
    },
    {
        "rule_id": "collaboration_monetization_reaction",
        "title": "联动皮肤与商业化反馈",
        "summary": "玩家将联动皮肤销售与同期平衡调整联系起来讨论；证据不足时仅保留为候选。",
        "title_en": "Collaboration Skin and Monetization Feedback",
        "summary_en": "Players linked collaboration-skin sales with concurrent balance changes; the item remains a candidate when evidence coverage is insufficient.",
        "event_type": "live_service_event",
        "patterns": (r"联动(?:皮|活动|上线)", r"赛博朋克", r"神话皮"),
    },
)


STOPWORDS = {
    "不是", "现在", "感觉", "这个", "那个", "还是", "就是", "可以", "没有", "一个",
    "时候", "然后", "其实", "真的", "很多", "什么", "怎么", "好像", "一直", "比较",
    "huge", "lz", "nb", "复活了", "时间", "那个赛季", "对比现在", "这次的改",
}


def _text_id(row: dict[str, Any]) -> str:
    existing = row.get("text_id") or row.get("comment_id") or row.get("post_id")
    if existing:
        return str(existing)
    value = f"{row.get('platform')}|{row.get('url')}|{row.get('text')}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _content_id(row: dict[str, Any]) -> str:
    return str(row.get("bvid") or row.get("post_id") or row.get("url") or _text_id(row))


def _platform(row: dict[str, Any]) -> str:
    return str(row.get("platform") or ("B站" if row.get("bvid") else "小黑盒"))


def _analysis_text(row: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", str(row.get("text") or "")).strip()


def _compile(patterns: Iterable[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


def extract_keywords(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in records if row.get("canonical_topic_id") and _analysis_text(row)]
    candidates: list[dict[str, Any]] = []
    recognized_spans: dict[str, set[str]] = defaultdict(set)
    for rule in KEYWORD_RULES:
        compiled = _compile(rule["patterns"])
        matched: list[dict[str, Any]] = []
        occurrence_count = 0
        aliases: Counter[str] = Counter()
        for row in rows:
            text = _analysis_text(row)
            hits = [match for regex in compiled for match in regex.finditer(text)]
            if not hits:
                continue
            matched.append(row)
            occurrence_count += len(hits)
            for hit in hits:
                alias = hit.group(0).strip()
                aliases[alias] += 1
                recognized_spans[_text_id(row)].add(alias.casefold())
        text_ids = sorted({_text_id(row) for row in matched})
        content_ids = sorted({_content_id(row) for row in matched})
        topic_ids = sorted({str(row["canonical_topic_id"]) for row in matched})
        platforms = sorted({_platform(row) for row in matched})
        reasons: list[str] = []
        if len(text_ids) < 2:
            reasons.append("text_coverage_under_2")
        if not topic_ids:
            reasons.append("no_valid_topic")
        if not text_ids:
            reasons.append("no_traceable_evidence")
        quality_status = "passed" if not reasons else "excluded"
        candidate = {
            "keyword": rule["normalized"],
            "normalized_keyword": rule["normalized"],
            "entity_type": rule["entity_type"],
            "occurrence_count": occurrence_count,
            "text_coverage_count": len(text_ids),
            "content_coverage_count": len(content_ids),
            "platforms": platforms,
            "topic_ids": topic_ids,
            "event_driven": rule["entity_type"] in {"season", "live_service_event", "esports"},
            "quality_status": quality_status,
            "exclusion_reasons": reasons,
            "evidence_text_ids": text_ids,
            "content_ids": content_ids,
            "aliases": [alias for alias, _ in aliases.most_common()],
            "score": round(len(text_ids) * 10 + len(content_ids) * 3 + len(topic_ids) * 2, 3),
            # Compatibility aliases retained for historical consumers.
            "occurrences": occurrence_count,
            "document_count": len(text_ids),
            "document_coverage": round(len(text_ids) / len(rows), 6) if rows else 0,
        }
        candidates.append(candidate)

    qualified = sorted(
        (row for row in candidates if row["quality_status"] == "passed"),
        key=lambda row: (
            -row["text_coverage_count"],
            -row["content_coverage_count"],
            -row["occurrence_count"],
            row["normalized_keyword"],
        ),
    )

    numeric: dict[str, set[str]] = defaultdict(set)
    stopword_hits: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        text = _analysis_text(row)
        text_id = _text_id(row)
        for token in re.findall(r"(?<![A-Za-z])\d+(?![A-Za-z])", text):
            if any(
                re.search(rf"(?<!\d){re.escape(token)}(?!\d)", alias)
                for alias in recognized_spans.get(text_id, set())
            ):
                continue
            numeric[token].add(text_id)
        lowered = text.casefold()
        for token in STOPWORDS:
            if token.casefold() in lowered:
                stopword_hits[token].add(text_id)
    filter_log = [
        {
            "raw_keyword": token,
            "normalized_keyword": None,
            "text_coverage_count": len(ids),
            "action": "excluded",
            "reason": "pure_numeric_without_confirmed_game_entity_context",
        }
        for token, ids in sorted(numeric.items(), key=lambda item: (-len(item[1]), item[0]))
    ] + [
        {
            "raw_keyword": token,
            "normalized_keyword": None,
            "text_coverage_count": len(ids),
            "action": "excluded",
            "reason": "stopword_or_low_business_interpretability",
        }
        for token, ids in sorted(stopword_hits.items(), key=lambda item: (-len(item[1]), item[0]))
    ]
    for row in qualified:
        for alias in row["aliases"]:
            if alias != row["normalized_keyword"]:
                filter_log.append(
                    {
                        "raw_keyword": alias,
                        "normalized_keyword": row["normalized_keyword"],
                        "text_coverage_count": row["text_coverage_count"],
                        "action": "normalized",
                        "reason": "domain_entity_alias_normalization",
                    }
                )
    return {
        "rule_version": KEYWORD_RULE_VERSION,
        "input_text_count": len(rows),
        "qualified": qualified,
        "candidates": candidates,
        "filter_log": filter_log,
        "status": "success",
    }


def _record_date(row: dict[str, Any]) -> str | None:
    value = str(row.get("publish_time") or row.get("collected_at") or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        match = re.match(r"(\d{4}-\d{2}-\d{2})", value)
        return match.group(1) if match else None


def generate_events(records: Iterable[dict[str, Any]], *, week_id: str) -> dict[str, Any]:
    rows = [row for row in records if row.get("canonical_topic_id") and _analysis_text(row)]
    candidates: list[dict[str, Any]] = []
    for rule in EVENT_RULES:
        compiled = _compile(rule["patterns"])
        matched = [row for row in rows if any(regex.search(_analysis_text(row)) for regex in compiled)]
        text_ids = sorted({_text_id(row) for row in matched})
        content_ids = sorted({_content_id(row) for row in matched})
        topic_ids = sorted({str(row["canonical_topic_id"]) for row in matched})
        platforms = sorted({_platform(row) for row in matched})
        dates = sorted(filter(None, (_record_date(row) for row in matched)))
        comment_count = sum(_platform(row) == "B站" for row in matched)
        reasons: list[str] = []
        if len(text_ids) < 2:
            reasons.append("evidence_text_coverage_under_2")
        if len(content_ids) < 2:
            reasons.append("independent_content_coverage_under_2")
        if not topic_ids:
            reasons.append("no_valid_topic")
        if not dates:
            reasons.append("event_date_unavailable")
        qualified = not reasons
        event_id = "EVT-" + hashlib.sha256(f"{week_id}|{rule['rule_id']}".encode()).hexdigest()[:12].upper()
        candidates.append(
            {
                "event_id": event_id,
                "week_id": week_id.replace("_W", "-W"),
                "title": rule["title"],
                "summary": rule["summary"],
                "title_en": rule["title_en"],
                "summary_en": rule["summary_en"],
                "event_date": dates[-1] if dates else None,
                "platforms": platforms,
                "topic_ids": topic_ids,
                "content_ids": content_ids,
                "evidence_text_ids": text_ids,
                "comment_count": comment_count,
                "content_count": len(content_ids),
                "impact_score": min(100, len(text_ids) * 5 + len(content_ids) * 8 + len(platforms) * 8 + len(topic_ids) * 3),
                "event_type": rule["event_type"],
                "event_status": "qualified" if qualified else "excluded",
                "data_quality_status": "passed" if qualified else "excluded_insufficient_evidence",
                "exclusion_reasons": reasons,
                "rule_id": rule["rule_id"],
            }
        )
    qualified_events = sorted(
        (row for row in candidates if row["event_status"] == "qualified"),
        key=lambda row: (-row["impact_score"], row["event_id"]),
    )
    return {
        "rule_version": EVENT_RULE_VERSION,
        "status": "success_with_qualified_events" if qualified_events else "success_no_qualified_events",
        "candidate_count": len(candidates),
        "qualified_count": len(qualified_events),
        "events": qualified_events,
        "candidates": candidates,
        "excluded": [row for row in candidates if row["event_status"] == "excluded"],
    }
