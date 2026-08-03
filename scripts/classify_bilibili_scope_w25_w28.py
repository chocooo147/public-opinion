from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from project_paths import configured_root  # noqa: E402

DATA_ROOT = configured_root(ROOT, "data_root")
OUTPUT_ROOT = configured_root(ROOT, "historical_output_root")
RULE_VERSION = "bilibili_apex_scope_split_v1_2026-07-17"
MIN_NEW_MEDIA_COMMENTS = 250

INPUTS = {
    "W25": DATA_ROOT / "processed/bilibili_apex_2026_W25_rectified_v2.csv",
    "W26": DATA_ROOT / "processed/bilibili_apex_2026_W26_rectified_v2.csv",
    "W27": DATA_ROOT / "processed/bilibili_apex_2026_W27_supplement_merged.csv",
    "W28": DATA_ROOT / "processed/bilibili_apex_2026_W28_merged.csv",
}

LATEST_AUDITS = {
    "W25": Path(os.environ.get("APEX_W25_SCOPE_AUDIT", OUTPUT_ROOT / "manual_audit/bilibili_apex_2026_W25_reaudit_v2_comments_50.csv")),
    "W26": Path(os.environ.get("APEX_W26_SCOPE_AUDIT", OUTPUT_ROOT / "manual_audit/bilibili_apex_2026_W26_reaudit_v2_comments_50.csv")),
    "W27": Path(os.environ.get("APEX_W27_SCOPE_AUDIT", OUTPUT_ROOT / "manual_audit/bilibili_apex_2026_W27_audit_50.csv")),
    "W28": Path(os.environ.get("APEX_W28_SCOPE_AUDIT", OUTPUT_ROOT / "manual_audit/bilibili_apex_2026_W28_round2_audit_final.csv")),
}

OUTPUT_CLASSIFIED = DATA_ROOT / "processed/bilibili_apex_W25_W28_scope_classified.csv"
OUTPUT_NEW_MEDIA = OUTPUT_ROOT / "bilibili_apex_W25_W28_new_media_pool.csv"
OUTPUT_TECHNICAL = OUTPUT_ROOT / "bilibili_apex_W25_W28_technical_issue_pool.csv"
OUTPUT_REVIEW = OUTPUT_ROOT / "manual_audit/bilibili_apex_W25_W28_scope_review.csv"
OUTPUT_REPORT = ROOT / "reports/bilibili_apex_W25_W28_scope_adjustment_report.md"

MANUAL_FIELDS = (
    "manual_relevant",
    "manual_user_opinion",
    "manual_content_role",
    "manual_topic",
    "manual_sentiment",
    "manual_noise_reason",
    "manual_keep",
    "manual_notes",
)

SCOPE_FIELDS = (
    "analysis_scope",
    "new_media_include",
    "technical_issue_include",
    "technical_pool_include",
    "issue_category",
    "issue_attribution",
    "attribution_confidence",
    "routing_team",
    "scope_exclusion_reason",
    "manual_scope_review",
    "scope_review_reason",
    "scope_classification_basis",
    "scope_rule_conflict",
    "manual_auto_scope_mismatch",
    "training_include_original",
    "scope_rule_version",
    "scope_audit_source",
)

OTHER_GAME_PATTERNS = re.compile(
    r"守望先锋|overwatch|求生之路|empulse|暴雪是不是把apex|apexclient|比apex还逆天",
    re.I,
)

OFFICIAL_VALUE_PATTERNS = (
    re.compile(r"(?:官方|重生|ea|运营).{0,15}(?:不回应|不回复|装死|态度|沟通|道歉|公告|解释|处理|不管|不修|摆烂)", re.I),
    re.compile(r"(?:不回应|不回复|装死|态度|沟通|道歉|公告|解释|处理|不管|不修|摆烂).{0,15}(?:官方|重生|ea|运营)", re.I),
    re.compile(r"退款|退钱|差评|品牌|信任|口碑|全网|热搜|舆论|传播|全网笑话|大范围|大量玩家|集体退游|退游潮", re.I),
    re.compile(r"(?:年年|长期|每次更新都).{0,8}(?:bug|卡顿|掉帧|闪退|崩溃|启动|服务器|延迟)", re.I),
    re.compile(r"玩(?:个|这)?游戏.{0,8}(?:自己修|还要修).{0,5}(?:bug|错误|故障)", re.I),
    re.compile(r"(?:破游戏|垃圾游戏|这游戏真烂|屎山代码)", re.I),
)

OFFICIAL_OR_BRAND = re.compile(r"官方|重生|ea|运营|品牌|信任|口碑|退款|退钱|差评|全网|热搜|舆论|传播|笑话", re.I)
CRITIQUE = re.compile(r"态度|装死|不回应|不回复|不修|不管|摆烂|离谱|逆天|垃圾|烂|失望|恶心|退游|退款|差评|信任|没用|一点用都没有|屎山", re.I)
HELP_OR_DIAGNOSIS = re.compile(
    r"怎么办|怎么解决|如何解决|求助|求方法|解决办法|教程|修复|排查|设置|配置|参数|报错|错误代码|代码|重装|更新驱动|驱动更新|验证文件|校验文件|启动项|注册表|bios|请问|有没有办法|什么情况|咋回事|进不去|打不开",
    re.I,
)
RESOLUTION_EVIDENCE = re.compile(r"(?:更新|回退|重装|关闭|开启|修改|调整).{0,10}(?:驱动|设置|分辨率|画质|bios|超线程|启动项|注册表|权限|路径).{0,12}(?:正常|好了|解决|修复|不再)", re.I)
NONTECH_TOPIC = re.compile(
    r"皮肤|外观|通行证|抽奖|活动|联动|赛博朋克|排位|匹配|猎杀|段位|英雄|角色|武器|平衡|赛事|algs|主播|选手|战队|上分|阵容|伤害|手感|剧情|语音",
    re.I,
)

CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("launch_error", re.compile(r"启动失败|启动错误|无法启动|进不去游戏|无法进入游戏|打不开游戏|卡在启动|卡在正在停止|反作弊未运行|eac.{0,8}(?:错误|报错|失败)", re.I)),
    ("crash", re.compile(r"闪退|崩溃|黑屏|蓝屏|卡死|死机|未响应|退回桌面", re.I)),
    ("frame_drop", re.compile(r"掉帧|抽帧|跳帧|帧数低|帧率低|帧率不稳|帧不稳|帧数暴跌|low帧|fps.{0,6}(?:低|掉|不稳)", re.I)),
    ("driver", re.compile(r"显卡驱动|驱动程序|n卡驱动|a卡驱动|驱动更新|更新驱动|回退驱动", re.I)),
    ("graphics_setting", re.compile(r"画质设置|分辨率|渲染比例|纹理设置|垂直同步|图像设置|画面设置", re.I)),
    ("system_environment", re.compile(r"系统环境|管理员权限|权限问题|windows|环境变量|系统版本|注册表|文件权限", re.I)),
    ("compatibility", re.compile(r"兼容性|硬件兼容|外设兼容|设备兼容|不兼容", re.I)),
    ("installation", re.compile(r"安装路径|安装失败|无法安装|重装游戏|校验文件|验证文件|文件缺失|安装目录", re.I)),
    ("hardware", re.compile(r"显存|cpu|gpu|显卡|处理器|内存占用|硬件|温度|功耗", re.I)),
    ("network", re.compile(r"丢包|网络波动|网络延迟|高延迟|延迟.{0,3}高|掉线|断线|无法重连|连接ea服务器|服务器延迟|服务器连接|ping.{0,6}(?:高|跳)|\d+pin", re.I)),
    ("performance", re.compile(r"卡顿|卡顿严重|(?:太|很|特别|非常|巨|好)卡(?:了|啊|呀|！|!|$)|游戏卡|性能问题|占用异常|cpu占用|gpu占用|发热|优化后|负优化", re.I)),
    ("bug", re.compile(r"bug|漏洞|程序异常|游戏异常", re.I)),
)

TECHNICAL_TOPIC_WORDS = re.compile(r"服务器与性能|技术|卡顿|掉帧|帧率|启动|闪退|崩溃|驱动|硬件|网络|bug", re.I)
NONTECH_TOPIC_WORDS = re.compile(r"皮肤|外观|活动|商业化|排位|匹配|英雄|武器|平衡|赛事|主播|外挂|反作弊|版本|赛季", re.I)


def clean_row(row: dict[str, str | None]) -> dict[str, str]:
    return {key: (value or "").strip() for key, value in row.items()}


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            with path.open(encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                return [clean_row(row) for row in reader], list(reader.fieldnames or [])
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"无法识别CSV编码：{path}")


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str], replace: bool) -> None:
    if path.exists() and not replace:
        raise FileExistsError(f"拒绝覆盖已有输出：{path}；如需重建请显式传入 --replace-scope")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w" if replace else "x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, text: str, replace: bool) -> None:
    if path.exists() and not replace:
        raise FileExistsError(f"拒绝覆盖已有输出：{path}；如需重建请显式传入 --replace-scope")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def binary(value: str) -> int | None:
    value = (value or "").strip()
    if value in {"1", "1.0", "true", "True", "是"}:
        return 1
    if value in {"0", "0.0", "false", "False", "否"}:
        return 0
    return None


def week_id(week: str) -> str:
    return f"2026_W{week[1:]}"


def overlay_latest_audit(week: str, rows: list[dict[str, str]]) -> int:
    path = LATEST_AUDITS.get(week)
    if path is None or not path.exists():
        return 0
    reviewed, _ = read_csv(path)
    reviewed = [row for row in reviewed if row.get("source_type") == "top_level_comment"]
    by_id = {row.get("text_id", ""): row for row in rows}
    matched = 0
    for source in reviewed:
        target = by_id.get(source.get("text_id", ""))
        if target is None:
            continue
        for field in MANUAL_FIELDS:
            target[field] = source.get(field, "")
        target["manual_review_status"] = "reviewed_reaudit_v2_completed"
        target["scope_audit_source"] = str(path)
        matched += 1
    if matched != len(reviewed):
        raise ValueError(f"{week}最新复核表仅匹配{matched}/{len(reviewed)}条")
    return matched


def category_from(text: str) -> str:
    for category, pattern in CATEGORY_PATTERNS:
        if pattern.search(text or ""):
            return category
    return ""


def parent_category_from(title: str) -> str:
    """Only use a parent title when it is clearly a fault/help context.

    A gameplay highlight containing words such as "高延迟" or a skin title
    containing "bug" is not enough to route every child comment to technical.
    """
    category = category_from(title)
    if not category:
        return ""
    technical_framing = re.search(
        r"解决|教程|指南|问题|错误|报错|无法|进不去|启动失败|闪退|崩溃|黑屏|卡顿|掉帧|帧数|帧率|驱动|兼容|安装|卡死|卡bug|负优化|占用异常|服务器.{0,6}(?:烂|故障|连接|延迟)",
        title,
        re.I,
    )
    if technical_framing:
        return category
    return ""


def parent_relevant(row: dict[str, str]) -> bool:
    existing = binary(row.get("parent_video_relevant", ""))
    if existing is not None:
        return existing == 1
    title = row.get("title", "")
    if OTHER_GAME_PATTERNS.search(title):
        return False
    if re.search(r"n卡驱动|显卡驱动", title, re.I) and not re.search(r"apex|英雄", title, re.I):
        return False
    return True


def base_candidate(row: dict[str, str]) -> bool:
    existing = binary(row.get("candidate_training_include", ""))
    if existing is not None:
        return existing == 1
    return (
        row.get("source_type") == "top_level_comment"
        and parent_relevant(row)
        and binary(row.get("rule_filtered", "")) != 1
        and binary(row.get("deduplication_valid", "")) != 0
        and row.get("week_assignment_confidence", "").lower() != "low"
        and not row.get("filter_reason", "")
    )


def attribution(text: str, title: str, category: str) -> tuple[str, str, str]:
    combined = f"{text} {title}"
    hardware_text = re.sub(r"显卡驱动|n卡驱动|a卡驱动|驱动程序", "", combined, flags=re.I)
    causes: list[str] = []
    evidence: list[str] = []
    if re.search(r"驱动|n卡|a卡", combined, re.I):
        causes.append("driver_environment")
        evidence.append("显式提到显卡驱动环境")
    if re.search(r"bios|超线程|启动项|注册表|画质设置|分辨率|渲染比例|客户端参数", combined, re.I):
        causes.append("user_setting")
        evidence.append("显式提到本地设置或客户端参数")
    if re.search(r"显卡|显存|cpu|gpu|处理器|内存|硬件", hardware_text, re.I):
        causes.append("user_hardware")
        evidence.append("显式提到玩家硬件")
    if re.search(r"系统环境|windows|管理员权限|权限问题|安装路径|环境变量", combined, re.I):
        causes.append("system_environment")
        evidence.append("显式提到系统或权限环境")
    causes = list(dict.fromkeys(causes))
    if len(causes) > 1:
        return "mixed", "medium" if RESOLUTION_EVIDENCE.search(text) else "low", "；".join(evidence)
    if len(causes) == 1:
        confidence = "high" if RESOLUTION_EVIDENCE.search(text) else "medium"
        return causes[0], confidence, evidence[0]
    if category:
        return "unknown", "low", "单条评论不足以可靠归因到游戏客户端或服务器"
    return "", "", ""


def classify_scope(row: dict[str, str]) -> dict[str, str]:
    text = row.get("text", "")
    title = row.get("title", "")
    query = row.get("query_keyword", "")
    direct_category = category_from(text)
    parent_category = parent_category_from(title)
    official_value = any(pattern.search(text) for pattern in OFFICIAL_VALUE_PATTERNS)
    official_critique = bool(OFFICIAL_OR_BRAND.search(text) and CRITIQUE.search(text))
    new_media_value = official_value or official_critique
    help_signal = bool(HELP_OR_DIAGNOSIS.search(text))
    nontech_signal = bool(NONTECH_TOPIC.search(text))
    parent_is_relevant = parent_relevant(row)
    old_candidate = base_candidate(row)
    existing_filtered = binary(row.get("rule_filtered", "")) == 1 or bool(row.get("filter_reason", ""))

    rule_conflict = 0
    basis: list[str] = []
    primary_new_media = False

    if not parent_is_relevant:
        scope = "unclear"
        category = direct_category or parent_category or ""
        basis.append("父视频已判定非Apex主题，不能进入任一Apex分析池")
    elif direct_category and new_media_value:
        scope = "mixed"
        category = direct_category
        primary_new_media = True
        rule_conflict = 1
        basis.append("评论同时描述技术问题，并讨论官方回应、品牌信任、退款或传播影响")
    elif direct_category:
        scope = "technical"
        category = direct_category
        basis.append("评论正文主要描述技术故障、配置排查或解决方法")
    elif parent_category and help_signal:
        scope = "technical"
        category = parent_category
        basis.append("父视频为技术问题场景，评论正文为求助、排查或解决方法")
    elif parent_category and new_media_value:
        scope = "mixed"
        category = parent_category
        primary_new_media = True
        rule_conflict = 1
        basis.append("技术问题父视频下，评论重点转向官方态度、品牌或传播影响")
    elif parent_category and not nontech_signal:
        scope = "unclear"
        category = parent_category
        basis.append("父视频具有技术问题主题，但评论正文缺少足够上下文")
    else:
        scope = "new_media"
        category = ""
        basis.append("评论主要讨论玩法、运营、商业化、赛事、社区或品牌相关内容")

    attr, attr_confidence, attr_basis = attribution(text, title, category)
    if attr_basis:
        basis.append(attr_basis)

    manual_topic = row.get("confirmed_topic") or row.get("manual_topic", "")
    manual_mismatch = 0
    if manual_topic:
        if scope == "new_media" and TECHNICAL_TOPIC_WORDS.search(manual_topic):
            manual_mismatch = 1
        elif scope == "technical" and NONTECH_TOPIC_WORDS.search(manual_topic):
            manual_mismatch = 1

    if scope == "technical":
        new_media_include = 0
        technical_issue_include = 1
        routing_team = "technical_support"
        exclusion_reason = "主要为技术故障、硬件/驱动/设置或本地排查，不计入新媒体模型和指标"
    elif scope == "mixed":
        new_media_include = 1 if (primary_new_media and old_candidate and not existing_filtered) else 0
        technical_issue_include = 1
        routing_team = "manual_review"
        exclusion_reason = "" if new_media_include else "混合型文本当前重点仍为故障本身，等待人工范围复核"
    elif scope == "new_media":
        new_media_include = 1 if (old_candidate and not existing_filtered) else 0
        technical_issue_include = 0
        routing_team = "new_media" if new_media_include else "community_operation"
        exclusion_reason = "" if new_media_include else "已被既有清洗、父视频、去重或时间规则排除"
    else:
        new_media_include = 0
        technical_issue_include = 0 if not parent_is_relevant else (1 if category else 0)
        routing_team = "manual_review"
        exclusion_reason = "范围或上下文不足，等待人工判断"

    technical_pool_include = int(technical_issue_include == 1 and scope in {"technical", "mixed"})
    dedup_valid = binary(row.get("deduplication_valid", ""))
    if dedup_valid is None:
        dedup_valid = 1
    week_conf = row.get("week_assignment_confidence", "").lower()
    parent_flag = int(parent_is_relevant)
    rule_filtered = int(existing_filtered)
    candidate_flag = int(old_candidate)
    training_include = int(
        row.get("source_type") == "top_level_comment"
        and candidate_flag == 1
        and new_media_include == 1
        and scope in {"new_media", "mixed"}
        and rule_filtered != 1
        and parent_flag == 1
        and dedup_valid == 1
        and week_conf != "low"
    )

    review_reasons: list[str] = []
    if scope in {"mixed", "unclear"}:
        review_reasons.append(f"analysis_scope={scope}")
    if attr_confidence == "low":
        review_reasons.append("技术问题归因置信度低")
    if rule_conflict:
        review_reasons.append("技术规则与新媒体价值规则同时命中")
    if manual_mismatch:
        review_reasons.append("既有人工主题与自动范围判断不一致")

    return {
        "analysis_scope": scope,
        "new_media_include": str(new_media_include),
        "technical_issue_include": str(technical_issue_include),
        "technical_pool_include": str(technical_pool_include),
        "issue_category": category,
        "issue_attribution": attr,
        "attribution_confidence": attr_confidence,
        "routing_team": routing_team,
        "scope_exclusion_reason": exclusion_reason,
        "manual_scope_review": "",
        "scope_review_reason": "；".join(review_reasons),
        "scope_classification_basis": "；".join(basis),
        "scope_rule_conflict": str(rule_conflict),
        "manual_auto_scope_mismatch": str(manual_mismatch),
        "training_include": str(training_include),
        "candidate_training_include": str(candidate_flag),
        "parent_video_relevant": str(parent_flag),
        "rule_filtered": str(rule_filtered),
        "deduplication_valid": str(dedup_valid),
        "scope_rule_version": RULE_VERSION,
    }


def topic_label(row: dict[str, str]) -> str:
    for field in ("confirmed_topic", "manual_topic", "candidate_topic", "auto_topic", "event_tag", "query_keyword"):
        value = row.get(field, "").strip()
        if value:
            return value
    return "未分类"


def total_variation(before: list[dict[str, str]], after: list[dict[str, str]]) -> float:
    before_counts = Counter(topic_label(row) for row in before)
    after_counts = Counter(topic_label(row) for row in after)
    if not before_counts or not after_counts:
        return 0.0
    keys = set(before_counts) | set(after_counts)
    return 0.5 * sum(
        abs(before_counts[key] / len(before) - after_counts[key] / len(after))
        for key in keys
    )


def top_counts(rows: list[dict[str, str]], field: str, limit: int = 5) -> str:
    counts = Counter(row.get(field, "") or "未分类" for row in rows)
    return "、".join(f"{key} {value}" for key, value in counts.most_common(limit)) or "无"


def render_report(all_rows: list[dict[str, str]], audit_matches: dict[str, int]) -> str:
    lines = [
        "# B站 Apex英雄 W25—W28 分析范围调整报告",
        "",
        "> 本报告仅完成新媒体舆情与技术问题的双口径路由。原始文件未修改；未训练BERTopic，未运行SnowNLP，未生成主题链，也未更新看板。",
        "",
        "## 口径说明",
        "",
        "- 统计对象：四周现有 `top_level_comment`，标题和简介仅作为父视频上下文。",
        "- 新媒体池：满足既有候选清洗规则，且 `new_media_include=1`、`analysis_scope` 为 `new_media` 或 `mixed`。",
        "- 技术池：`technical_issue_include=1` 且 `analysis_scope` 为 `technical` 或 `mixed`。技术记录仍保留在完整处理表中。",
        "- 技术归因：没有充分证据时统一为 `unknown`，不根据单条评论自动归因为 `game_client` 或 `server_side`。",
        "- mixed、unclear、低归因置信度、规则冲突及人工/自动判断不一致记录进入独立人工范围复核表。",
        "- 每周BERTopic最低样本量沿用本项目已验证门槛：250条新媒体一级评论。当前结论为范围复核前的候选状态。",
        "",
        "## 逐周数量与资格",
        "",
        "| 周次 | 原始一级评论 | 既有候选评论 | 新媒体语料池 | 技术问题池 | mixed | unclear | 技术排除率* | 待人工判断 | 新媒体样本≥250 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    summaries: dict[str, dict[str, object]] = {}
    for week in ("W25", "W26", "W27", "W28"):
        week_rows = [row for row in all_rows if row.get("week_id") == week_id(week)]
        candidates = [row for row in week_rows if row.get("candidate_training_include") == "1"]
        new_media = [row for row in week_rows if row.get("training_include") == "1"]
        technical = [row for row in week_rows if row.get("technical_pool_include") == "1"]
        mixed = [row for row in week_rows if row.get("analysis_scope") == "mixed"]
        unclear = [row for row in week_rows if row.get("analysis_scope") == "unclear"]
        excluded_technical = [
            row for row in candidates
            if row.get("analysis_scope") in {"technical", "mixed"} and row.get("new_media_include") == "0"
        ]
        review = [row for row in week_rows if row.get("scope_review_reason")]
        exclusion_rate = len(excluded_technical) / len(candidates) if candidates else 0
        tvd = total_variation(candidates, new_media)
        before_top = Counter(topic_label(row) for row in candidates).most_common(1)
        after_top = Counter(topic_label(row) for row in new_media).most_common(1)
        before_topic = before_top[0][0] if before_top else "无"
        after_topic = after_top[0][0] if after_top else "无"
        changed = tvd >= 0.10 or before_topic != after_topic
        summaries[week] = {
            "rows": week_rows,
            "candidates": candidates,
            "new_media": new_media,
            "technical": technical,
            "mixed": mixed,
            "unclear": unclear,
            "review": review,
            "exclusion_rate": exclusion_rate,
            "tvd": tvd,
            "changed": changed,
            "before_topic": before_topic,
            "after_topic": after_topic,
        }
        lines.append(
            f"| 2026-{week} | {len(week_rows)} | {len(candidates)} | {len(new_media)} | {len(technical)} | "
            f"{len(mixed)} | {len(unclear)} | {exclusion_rate:.2%} | {len(review)} | "
            f"{'通过' if len(new_media) >= MIN_NEW_MEDIA_COMMENTS else '未通过'} |"
        )

    lines.extend([
        "",
        "* 技术排除率 = 既有候选评论中，因主要属于technical或故障优先的mixed而不进入新媒体池的数量 ÷ 既有候选评论数。",
        "",
        "## 技术问题类别与归因",
        "",
    ])
    for week in ("W25", "W26", "W27", "W28"):
        summary = summaries[week]
        technical = summary["technical"]
        assert isinstance(technical, list)
        week_rows = summary["rows"]
        assert isinstance(week_rows, list)
        low_confidence = sum(row.get("attribution_confidence") == "low" for row in week_rows)
        rule_conflicts = sum(row.get("scope_rule_conflict") == "1" for row in week_rows)
        manual_mismatches = sum(row.get("manual_auto_scope_mismatch") == "1" for row in week_rows)
        lines.extend([
            f"### 2026-{week}",
            "",
            f"- 主要技术类别：{top_counts(technical, 'issue_category')}",
            f"- 主要归因类型：{top_counts(technical, 'issue_attribution')}",
            f"- 需要人工范围判断：{len(summary['review'])}条，其中mixed {len(summary['mixed'])}条、unclear {len(summary['unclear'])}条、低归因置信度 {low_confidence}条、规则冲突 {rule_conflicts}条、人工/自动判断不一致 {manual_mismatches}条；同一记录可重复命中。",
            "",
        ])

    lines.extend([
        "## 样本量与补采判断",
        "",
    ])
    needs_supplement: list[str] = []
    for week in ("W25", "W26", "W27", "W28"):
        new_count = len(summaries[week]["new_media"])
        gap = max(0, MIN_NEW_MEDIA_COMMENTS - new_count)
        if gap:
            needs_supplement.append(f"2026-{week}")
            lines.append(f"- 2026-{week}：未满足，当前{new_count}条，至少缺{gap}条非技术类有效一级评论。")
        else:
            lines.append(f"- 2026-{week}：满足，当前{new_count}条新媒体一级评论。")
    if needs_supplement:
        lines.append(f"- 可能需要定向补采非技术类评论的周次：{'、'.join(needs_supplement)}。补采应等待范围人工复核完成后再决定。")
    else:
        lines.append("- 四周当前均无需因本次范围剥离而补采；仍需先完成人工范围复核。")

    lines.extend([
        "",
        "## 对主题结构的影响",
        "",
        "这里比较范围调整前的既有候选主题分布与调整后的新媒体池主题分布。总变差距离（TVD）达到10%，或首要主题发生变化，记为“显著”。这是结构诊断，不是正式舆情结论。",
        "",
        "| 周次 | 调整前首要主题 | 调整后首要主题 | 主题分布TVD | 是否显著改变 |",
        "|---|---|---|---:|---|",
    ])
    for week in ("W25", "W26", "W27", "W28"):
        summary = summaries[week]
        lines.append(
            f"| 2026-{week} | {summary['before_topic']} | {summary['after_topic']} | "
            f"{summary['tvd']:.2%} | {'是' if summary['changed'] else '否'} |"
        )

    lines.extend([
        "",
        "## 人工复核衔接",
        "",
        f"- W25最新50条复核结果成功匹配：{audit_matches.get('W25', 0)}/50。",
        f"- W26最新50条复核结果成功匹配：{audit_matches.get('W26', 0)}/50。",
        f"- W27既有复核表中的一级评论成功匹配：{audit_matches.get('W27', 0)}/40。",
        f"- W28既有最终复核表中的一级评论成功匹配：{audit_matches.get('W28', 0)}/80。",
        "- `manual_scope_review`保持空白，等待人工填写；既有人工主题和判断仅用于识别自动范围冲突，不被改写为新的范围结论。",
        f"- 待审核文件：`{OUTPUT_REVIEW.relative_to(ROOT)}`。",
        "",
        "## 停止状态",
        "",
        "本阶段已停止。未训练BERTopic、未运行SnowNLP、未生成正式主题链、未更新HTML看板；待mixed、unclear及低置信度记录完成人工范围审核后，再重新计算最终训练资格。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="重建W25—W28新媒体/技术问题双口径数据池")
    parser.add_argument("--replace-scope", action="store_true", help="允许重建本脚本自己的派生输出")
    args = parser.parse_args()

    all_rows: list[dict[str, str]] = []
    fields: list[str] = []
    audit_matches: dict[str, int] = {}
    input_counts: dict[str, int] = {}

    for week in ("W25", "W26", "W27", "W28"):
        rows, input_fields = read_csv(INPUTS[week])
        rows = [row for row in rows if row.get("source_type") == "top_level_comment"]
        input_counts[week] = len(rows)
        for field in input_fields:
            if field not in fields:
                fields.append(field)
        audit_matches[week] = overlay_latest_audit(week, rows)
        for row in rows:
            row["week_id"] = week_id(week)
            row.setdefault("scope_audit_source", "")
            row["training_include_original"] = row.get("training_include", "")
            row.update(classify_scope(row))
            all_rows.append(row)

    if input_counts != {"W25": 334, "W26": 301, "W27": 282, "W28": 284}:
        raise ValueError(f"四周输入评论量与已审计基线不一致：{input_counts}")

    for field in (*SCOPE_FIELDS, "candidate_training_include", "parent_video_relevant", "rule_filtered", "deduplication_valid"):
        if field not in fields:
            fields.append(field)
    if "training_include" not in fields:
        fields.append("training_include")

    review_rows = [row for row in all_rows if row.get("scope_review_reason")]
    new_media_rows = [row for row in all_rows if row.get("training_include") == "1"]
    technical_rows = [row for row in all_rows if row.get("technical_pool_include") == "1"]

    if len({row.get("text_id") for row in all_rows}) != len(all_rows):
        raise ValueError("四周合并后text_id不唯一，拒绝输出")
    if any(row.get("source_type") != "top_level_comment" for row in all_rows):
        raise ValueError("范围分类表意外包含非一级评论")
    if any(row.get("manual_scope_review") for row in review_rows):
        raise ValueError("manual_scope_review必须保持空白")
    if any(row.get("analysis_scope") not in {"new_media", "technical", "mixed", "unclear"} for row in all_rows):
        raise ValueError("analysis_scope存在非法值")
    if any(row.get("issue_attribution") in {"game_client", "server_side"} for row in all_rows):
        raise ValueError("自动分类不得将单条评论直接归因为game_client或server_side")

    write_csv(OUTPUT_CLASSIFIED, all_rows, fields, args.replace_scope)
    write_csv(OUTPUT_NEW_MEDIA, new_media_rows, fields, args.replace_scope)
    write_csv(OUTPUT_TECHNICAL, technical_rows, fields, args.replace_scope)
    write_csv(OUTPUT_REVIEW, review_rows, fields, args.replace_scope)
    write_text(OUTPUT_REPORT, render_report(all_rows, audit_matches), args.replace_scope)

    print(f"classified={len(all_rows)} new_media={len(new_media_rows)} technical={len(technical_rows)} review={len(review_rows)}")
    for week in ("W25", "W26", "W27", "W28"):
        rows = [row for row in all_rows if row.get("week_id") == week_id(week)]
        print(
            week,
            "raw", len(rows),
            "candidate", sum(row.get("candidate_training_include") == "1" for row in rows),
            "new_media", sum(row.get("training_include") == "1" for row in rows),
            "technical", sum(row.get("technical_pool_include") == "1" for row in rows),
            "mixed", sum(row.get("analysis_scope") == "mixed" for row in rows),
            "unclear", sum(row.get("analysis_scope") == "unclear" for row in rows),
            "review", sum(bool(row.get("scope_review_reason")) for row in rows),
        )


if __name__ == "__main__":
    main()
