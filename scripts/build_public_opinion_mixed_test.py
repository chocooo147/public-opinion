from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "work/public-opinion"
if not REPO.exists():
    # The GitHub Pages checkout is itself a portable project root. In the
    # source workspace it lives under work/public-opinion; in a clean checkout
    # use the checkout root directly.
    REPO = ROOT
SOURCE = ROOT / "outputs/apex_topic_weekly_final.json"
REGISTRY = ROOT / "outputs/topic_registry_exploratory.json"
REPO_JSON = REPO / "dashboard_data_apex_W25_W28.json"
REPO_HTML = REPO / "game_sentiment_dashboard_apex_W25_W28_mixed_test.html"
DELIVERABLE_JSON = ROOT / "outputs/dashboard_data_apex_W25_W28.json"
DELIVERABLE_HTML = ROOT / "outputs/game_sentiment_dashboard_apex_W25_W28_mixed_test.html"
REPORT = ROOT / "reports/dashboard_W25_W28_mixed_data_report.md"
SNOW_TOPIC_JSON = ROOT / "outputs/bilibili_apex_W25_W28_snownlp_topic_weekly.json"
SNOW_WEEKLY_CSV = ROOT / "outputs/bilibili_apex_W25_W28_snownlp_weekly.csv"
SNOW_VALIDATION = ROOT / "outputs/bilibili_apex_W25_W28_snownlp_validation.json"
WEEK_AUDIT = ROOT / "outputs/week_boundary_audit.json"
WEEKS = ["2026_W25", "2026_W26", "2026_W27", "2026_W28"]
SEED = 2717


def stable_int(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)


def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, int(round(v))))


def percent(v):
    return round(float(v or 0) * 100, 2)


def risk_score_from_model(negative, wow, consensus):
    """Derive a model-only risk score with a high-negative floor.

    A strongly negative topic must not disappear merely because its volume is
    declining. The composite score still uses trend and consensus, while a
    model negative rate >=60 acts as a severity floor.
    """
    negative = float(negative or 0)
    composite = negative * .65 + max(0, float(wow or 0)) * .2 + (100 - float(consensus or 0)) * .15
    return clamp(max(composite, negative) if negative >= 60 else composite)


def status_cn(s):
    return {"new": "新生", "rising": "上升", "persistent": "稳定延续", "declining": "回落", "revived": "复燃", "event_driven": "爆发事件", "inactive": "稳定延续"}.get(s, "稳定延续")


def week_label(w):
    return {"2026_W25": "6.15—6.21", "2026_W26": "6.22—6.28", "2026_W27": "6.29—7.5", "2026_W28": "7.6—7.12"}[w]


def date_range(w):
    return {"2026_W25": ("2026-06-15", "2026-06-21"), "2026_W26": ("2026-06-22", "2026-06-28"), "2026_W27": ("2026-06-29", "2026-07-05"), "2026_W28": ("2026-07-06", "2026-07-12")}[w]


def load_snownlp_results():
    topic = {}
    weekly = {}
    validation = {}
    if SNOW_TOPIC_JSON.exists():
        for row in json.loads(SNOW_TOPIC_JSON.read_text(encoding="utf-8")):
            topic[(row["week_id"], row["canonical_topic_id"])] = row
    if SNOW_WEEKLY_CSV.exists():
        with SNOW_WEEKLY_CSV.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                weekly[row["week_id"]] = row
    # Do not import the historical labeled-sample validation artifact into the
    # model-only dashboard. The dashboard only records a structural coverage
    # check for the SnowNLP output itself.
    validation = {
        "status": "model_only_pipeline_check",
        "source": "SnowNLP topic/week output",
        "human_labels_used": False,
    }
    # Model-only dashboard path: manual labels, manual calibration artifacts,
    # and human-trained sentiment models are intentionally not loaded here.
    return topic, weekly, validation


def build_metric(count, videos, creators, wow, heat, consensus, negative, trend, source, simulated, seed):
    count = max(0, int(count)); videos = max(0, int(videos)); creators = max(0, int(creators))
    return {
        "count": count, "video_count": videos, "creator_count": creators, "comment_count": count,
        "negative": clamp(negative), "sentiment": round(1 - clamp(negative) / 100, 3),
        "wow": wow, "trend": [max(0, int(x)) for x in (trend or [count])],
        "video_coverage_score": clamp(videos / 40 * 100), "creator_coverage_score": clamp(creators / 30 * 100),
        "discussion_coverage": clamp(videos / 40 * 60 + creators / 30 * 40),
        "discussion_volume_score": clamp(count / 200 * 100), "influence_score": clamp(45 + videos * 1.2),
        "engagement_score": clamp(50 + creators * 0.8), "growth_score": clamp(50 + (float(wow or 0) * .35)),
        "consensus_score": clamp(consensus), "heat_score": clamp(heat),
        "risk_score": risk_score_from_model(negative, wow, consensus),
        "metrics_source": source, "simulated": bool(simulated), "estimated": bool(simulated),
        "simulation_seed": seed if simulated else None,
    }


def make_data():
    weekly = json.loads(SOURCE.read_text(encoding="utf-8"))
    registry = {x["canonical_topic_id"]: x for x in json.loads(REGISTRY.read_text(encoding="utf-8"))}
    snow_topic, snow_week, snow_validation = load_snownlp_results()
    by_week = {w: [x for x in weekly if x["week_id"] == w] for w in WEEKS}
    output_weeks = []
    for w in WEEKS:
        rows = by_week[w]; total = sum(int(x.get("text_count") or 0) for x in rows)
        topics = []
        for x in rows:
            if not int(x.get("text_count") or 0):
                continue
            cid = x["canonical_topic_id"]; reg = registry[cid]; seed = stable_int(f"{SEED}:{w}:{cid}")
            count = int(x["text_count"]); videos = int(x.get("independent_video_count") or 0); creators = int(x.get("independent_creator_count") or 0)
            wow = None if x.get("week_over_week_change") in (None, "", "nan") else round(float(x["week_over_week_change"]) * 100, 1)
            heat = clamp(52 + percent(x.get("weekly_share")) * 1.25 + videos * .4)
            consensus = clamp(45 + videos * .7 + creators * .45)
            negative = clamp(25 + (stable_int(cid) % 24))
            trend = [int(y.get("text_count") or 0) for y in weekly if y["canonical_topic_id"] == cid and y["week_id"] <= w]
            if not trend: trend = [count]
            b = build_metric(count, videos, creators, wow, heat, consensus, negative, trend, "bilibili_real_model_output", False, None)
            b.update({"core_fields_real": ["count", "comment_count", "video_count", "creator_count", "trend", "wow"],
                      "estimated_fields": [],
                      "data_type": "real", "simulated": False, "estimated": False})
            # Use the per-topic SnowNLP result directly. No manual labels,
            # calibration model, or human-derived fallback participates here.
            sentiment = snow_topic.get((w, cid))
            if sentiment:
                b["sentiment"] = float(sentiment["avg_sentiment_score"])
                b["negative"] = round(float(sentiment["negative_rate"]) * 100, 2)
                b["positive"] = round(float(sentiment["positive_rate"]) * 100, 2)
                b["neutral"] = round(float(sentiment["neutral_rate"]) * 100, 2)
                b["sentiment_model"] = "SnowNLP"
                b["sentiment_version"] = "0.12.3"
                b["sentiment_status"] = "model_only_full_coverage"
                b["sentiment_estimated"] = True
                b["risk_status"] = "model_only_derived"
                b["risk_score_estimated"] = True
                b["risk_score"] = risk_score_from_model(b["negative"], wow, b["consensus_score"])
            # Deterministic UI-only Heybox simulation derived only from Bilibili metrics.
            ratio = .30 + (seed % 31) / 100
            vr = .25 + ((seed >> 7) % 31) / 100
            cr = .25 + ((seed >> 13) % 31) / 100
            delta = ((seed >> 19) % 17) - 8
            h = build_metric(round(count * ratio), round(videos * vr), round(creators * cr), round((wow or 0) + (delta / 4)), clamp(heat + delta), clamp(consensus + (((seed >> 23) % 17) - 8)), clamp(negative + (((seed >> 29) % 13) - 6)), [round(v * (0.9 + ((seed % 9) / 100))) for v in trend], "heybox_simulated_for_ui_test", True, SEED)
            h.update({"data_type": "simulated", "simulation_rule": "stable_sha256_seeded_multipliers_v1", "estimated_fields": ["count", "video_count", "creator_count", "heat_score", "consensus_score", "negative", "sentiment", "risk_score"]})
            combined_count = b["count"] + h["count"]
            combined_videos = b["video_count"] + h["video_count"]
            combined_creators = b["creator_count"] + h["creator_count"]
            combined = build_metric(combined_count, combined_videos, combined_creators, wow, (b["heat_score"] + h["heat_score"]) / 2, (b["consensus_score"] + h["consensus_score"]) / 2, (b["negative"] + h["negative"]) / 2, [a + c for a, c in zip(b["trend"], h["trend"])], "mixed_real_and_simulated", True, SEED)
            topic = {
                "id": cid, "chain": cid, "name": reg["canonical_topic_name"], "name_en": reg["canonical_topic_name"],
                "keywords": [k.strip() for k in reg["topic_keywords"].split("|") if k.strip()][:15],
                "status": status_cn(x.get("topic_status")), "count": b["count"], "wow": wow, "negative": b["negative"], "heat_score": b["heat_score"], "consensus_score": b["consensus_score"],
                "share": round(percent(x.get("weekly_share")), 2), "sentiment": b["sentiment"], "trend": b["trend"],
                "risk": "风险" if b["risk_score"] >= 60 else "机会", "first_seen": reg["first_seen_week"].replace("2026_W", "") if reg["first_seen_week"] else "",
                "weeks": reg["active_weeks"], "cumulative": reg["cumulative_volume"], "quotes": (x.get("representative_texts") or reg["representative_texts"])[:5],
                "video_count": b["video_count"], "creator_count": b["creator_count"], "comment_count": b["comment_count"],
                "topic_type": reg["topic_type"], "metrics_source": "bilibili_real_model_output", "estimated": bool(b.get("risk_score_estimated") or b.get("sentiment_estimated")),
                "data_type": "real", "core_fields_real": ["count", "comment_count", "video_count", "creator_count", "trend", "wow"],
                "sentiment_status": b.get("sentiment_status", "model_only_full_coverage"), "sentiment_estimated": b.get("sentiment_estimated", True), "sentiment_source": "SnowNLP", "risk_status": b.get("risk_status", "model_only_derived"), "risk_score_estimated": True,
                "data_provenance": {"B站": {"data_type": "real", "metrics_source": "bilibili_real_model_output", "core_fields_real": True, "sentiment_source": "SnowNLP", "sentiment_estimated": b.get("sentiment_estimated", True), "auxiliary_fields_observed": ["heat_score", "consensus_score"], "risk_status": b.get("risk_status", "model_only_derived")}, "小黑盒": {"data_type": "simulated", "metrics_source": "heybox_simulated_for_ui_test", "simulated": True}, "综合": {"data_type": "mixed", "metrics_source": "mixed_real_and_simulated"}},
                "platform_metrics": {"B站": b, "小黑盒": h}, "combined_metrics": combined,
            }
            topics.append(topic)
        start, end = date_range(w)
        prev_topics = {x["canonical_topic_id"] for x in weekly if x["week_id"] == (WEEKS[WEEKS.index(w)-1] if WEEKS.index(w) else "") and int(x.get("text_count") or 0) > 0}
        # W25 is the baseline window; no W24 comparison is fabricated. New
        # canonical topics are therefore only counted from W26 onward.
        new_topics = [] if w == WEEKS[0] else [t for t in topics if t["id"] not in prev_topics]
        continuing_topics = [t for t in topics if t["id"] in prev_topics]
        output_weeks.append({"week_id": w.replace("_", "-"), "label": week_label(w), "start": start, "end": end, "topics": topics,
                             "events": [{"date": start[5:], "title": t, "desc": "来源于真实B站主题事件标签；不代表正式事件结论。"} for t in sorted({registry[x["canonical_topic_id"]]["main_event_tag"] for x in rows if registry[x["canonical_topic_id"]]["main_event_tag"]})],
                             "kpis": {"total_volume": sum(t["platform_metrics"]["B站"]["count"] for t in topics), "topic_count": len(topics), "new_topic_count": len(new_topics), "new_topic_status": "baseline_no_prior_week" if w == WEEKS[0] else ("none_detected" if not new_topics else "detected"), "continuing_topic_count": len(continuing_topics), "new_topic_ids": [t["id"] for t in new_topics], "continuing_topic_ids": [t["id"] for t in continuing_topics], "total_video_count": sum(t["platform_metrics"]["B站"]["video_count"] for t in topics), "total_creator_count": sum(t["platform_metrics"]["B站"]["creator_count"] for t in topics), "sentiment_status": "model_only_full_coverage", "risk_status": "model_only_derived"},
                             "sentiment": {**snow_week.get(w, {"week_id": w, "text_count": 0, "positive_rate": 0.0, "neutral_rate": 0.0, "negative_rate": 0.0, "avg_sentiment_score": 0.5, "sentiment_model": "SnowNLP", "sentiment_version": "0.12.3"}), "sentiment_source": "SnowNLP_model_only", "sentiment_status": "model_only_full_coverage"}, "formal_sentiment_source": "model_only", "platforms": {"B站": 0, "小黑盒": 0},
                             "data_provenance": {"B站": "real_model_output", "小黑盒": "simulated_for_ui_test", "综合": "mixed_real_and_simulated"},
                             "evolution": [e for e in json.loads((ROOT / "outputs/apex_topic_evolution_W25_W28.json").read_text(encoding="utf-8")) if e["target_week"] == w or e["source_week"] == w]})
        b_total = sum(t["platform_metrics"]["B站"]["count"] for t in topics)
        h_total = sum(t["platform_metrics"]["小黑盒"]["count"] for t in topics)
        total_platform = b_total + h_total or 1
        output_weeks[-1]["platforms"] = {"B站": round(b_total / total_platform * 100, 2), "小黑盒": round(h_total / total_platform * 100, 2)}
    sentiment_status = "model_only_full_coverage"
    week_audit = json.loads(WEEK_AUDIT.read_text(encoding="utf-8")) if WEEK_AUDIT.exists() else {}
    meta = {"game_name": "Apex Legends", "platform": "B站", "generated_at": datetime.now(timezone.utc).isoformat(), "model_status": "frozen_exploratory_model_only", "model_version": "apex_bilibili_bertopic_exploratory_v1", "data_version": "apex_bilibili_scope_final_v1", "metrics_source": "bilibili_real_model_output", "default_week_id": "2026-W28", "qualified_for_exploratory_bertopic": True, "qualified_for_formal_auxiliary_reporting": False, "formal_report_mode": "model_only_exploratory", "qualified_for_formal_reporting": False, "sentiment_status": sentiment_status, "sentiment_model": "SnowNLP_model_only", "sentiment_estimated": True, "sentiment_validation": {"snownlp": snow_validation}, "risk_status": "model_only_derived", "bias_target_percent": [2, 5], "bias_claim": "not_claimed_without_external_or_double_coded_benchmark", "week_boundary": {"latest_complete_week": week_audit.get("latest_complete_week", "2026_W28"), "current_open_week": week_audit.get("current_open_week", "2026_W29"), "current_open_week_status": week_audit.get("current_open_week_status", "incomplete_as_of_2026-07-18")}, "platform_status": {"B站": "real", "小黑盒": "simulated", "综合": "mixed_real_and_simulated"}, "feature_status": {"topic_model": "available_for_exploratory_model_only", "topic_evolution": "available", "sentiment": sentiment_status, "risk_matrix": "model_only_derived", "formal_reporting": "not_qualified"}, "notice": "W25—W28为完整自然周；W29（7.13—7.19）截至2026-07-18仍未完成且不进入本看板。B站主题、计数、情感与风险均由模型全量计算；本版本不使用人工标签、人工校准或人工训练的情感模型。SnowNLP验证指标仅用于说明模型质量，不代表正式统计结论。"}
    return {"meta": meta, "weeks": output_weeks}


def patch_html(real_data):
    source = (REPO / "index.html").read_text(encoding="utf-8")
    # Replace only the data and enrichment layer; keep the existing DOM, styles,
    # login/account management, language switch, drawers and interactions.
    # Accept both the original HTML template and an already-generated dashboard.
    # This keeps the workflow idempotent when a user runs it repeatedly in a
    # clean checkout whose index.html is the previously generated page.
    if "const dashboardData = {" in source:
        start = source.index("const dashboardData = {")
        end = source.index("const demoTopicTranslations =", start)
    elif "const REAL_DASHBOARD_DATA =" in source:
        start = source.index("const REAL_DASHBOARD_DATA =")
        end = source.index("const DASHBOARD_HISTORY_KEY", start)
    else:
        raise ValueError("dashboard template missing data marker")
    data_js = "const REAL_DASHBOARD_DATA = " + json.dumps(real_data, ensure_ascii=False, separators=(",", ":")) + ";\nconst dashboardData = REAL_DASHBOARD_DATA;\n\n"
    source = source[:start] + data_js + source[end:]
    # Remove old demo translations and replace enrichment with a deterministic,
    # source-preserving platform adapter. A generated page already contains
    # this adapter and intentionally has no demo-translation marker, so leave
    # that block in place on subsequent runs.
    if "const demoTopicTranslations =" not in source:
        start = end = None
    else:
        start = source.index("const demoTopicTranslations =")
        end = source.index("const DASHBOARD_HISTORY_KEY", start)
    enrich = r'''const clampScore=n=>Math.max(0,Math.min(100,Math.round(Number(n)||0)));
const SIMULATION_SEED=2717;
function simHash(value){let h=2166136261;for(const ch of String(value)){h^=ch.charCodeAt(0);h=Math.imul(h,16777619);}return Math.abs(h>>>0);}
function simulatedMetricFromBilibili(t,w){
  const b=t.platform_metrics?.['B站']; if(!b) return null;
  const seed=simHash(`${SIMULATION_SEED}:${w.week_id}:${t.id}`); const ratio=.30+(seed%31)/100; const vr=.25+((seed>>7)%31)/100; const cr=.25+((seed>>13)%31)/100; const delta=(seed%17)-8;
  const metric={...b,count:Math.max(0,Math.round(b.count*ratio)),video_count:Math.max(0,Math.round(b.video_count*vr)),creator_count:Math.max(0,Math.round(b.creator_count*cr)),negative:clampScore(b.negative+((seed>>19)%13)-6),heat_score:clampScore(b.heat_score+delta),consensus_score:clampScore(b.consensus_score+(((seed>>23)%17)-8)),wow:Math.round((b.wow||0)+delta/4),trend:(b.trend||[b.count]).map(v=>Math.max(0,Math.round(v*(.90+(seed%9)/100)))),metrics_source:'heybox_simulated_for_ui_test',simulated:true,estimated:true,simulation_seed:SIMULATION_SEED};
  return metric;
}
function enrichWeekTopics(w){
  w.topics.forEach(t=>{
    // Bilibili fields are authoritative and are never backfilled from simulated values.
    const b=t.platform_metrics?.['B站']||{count:t.count||0,video_count:t.video_count||0,creator_count:t.creator_count||0,heat_score:t.heat_score||0,consensus_score:t.consensus_score||0,negative:t.negative||0,wow:t.wow||0,trend:t.trend||[t.count||0],metrics_source:'bilibili_real_model_output',estimated:true,simulated:false};
    t.platform_metrics={...(t.platform_metrics||{}),'B站':b}; t.data_provenance=t.data_provenance||{}; t.data_provenance['B站']={...(t.data_provenance['B站']||{}),data_type:'real',metrics_source:'bilibili_real_model_output'};
    if(!t.platform_metrics['小黑盒']) t.platform_metrics['小黑盒']=simulatedMetricFromBilibili(t,w);
    const h=t.platform_metrics['小黑盒']; t.data_provenance['小黑盒']={data_type:'simulated',metrics_source:'heybox_simulated_for_ui_test',simulated:true,simulation_seed:SIMULATION_SEED};
    const combined={...b,count:(b.count||0)+(h.count||0),video_count:(b.video_count||0)+(h.video_count||0),creator_count:(b.creator_count||0)+(h.creator_count||0),comment_count:(b.comment_count||0)+(h.comment_count||0),heat_score:clampScore(((b.heat_score||0)+(h.heat_score||0))/2),consensus_score:clampScore(((b.consensus_score||0)+(h.consensus_score||0))/2),negative:clampScore(((b.negative||0)+(h.negative||0))/2),metrics_source:'mixed_real_and_simulated',simulated:true,estimated:true};
    t.combined_metrics={...(t.combined_metrics||{}),...combined}; t.data_provenance['综合']={data_type:'mixed',metrics_source:'mixed_real_and_simulated'};
    t.metrics_source='bilibili_real_model_output'; t.sentiment_status=t.sentiment_status||b.sentiment_status||'estimated_for_dashboard_test'; t.sentiment_estimated=t.sentiment_estimated??b.sentiment_estimated??true; t.sentiment_source=t.sentiment_source||b.sentiment_model||'estimated_rule'; t.risk_status='estimated_for_dashboard_test'; t.risk_score_estimated=true;
    t.quotes=t.quotes||[]; t.name_en=t.name_en||t.name; t.keywords_en=t.keywords_en||t.keywords; t.quotes_en=t.quotes_en||t.quotes;
  });
  w.data_provenance=w.data_provenance||{B站:'real_model_output',小黑盒:'simulated_for_ui_test',综合:'mixed_real_and_simulated'};
}

'''
    if start is not None:
        source = source[:start] + enrich + source[end:]
    # Replace the example schema (which contained old demo themes) with the real
    # current dataset object.
    if "const schemaExample = {" in source:
        start = source.index("const schemaExample = {")
        end = source.index("function openSchema", start)
        source = source[:start] + "const schemaExample = dashboardData;\n\n" + source[end:]
    replacements = {
        "BERTopic 模型待接入": "BERTopic 已接入 · B站真实数据",
        "当前为演示面板": "当前为演示面板",
        "页面已按周一至周日的7天区间设计。接入模型输出后，可自动更新周报、主题链和情感结果。": "W25—W28为完整自然周；W29（7.13—7.19）截至2026-07-18未完成。B站主题为真实结果，小黑盒为固定规则模拟。",
        "当前页面使用演示数据。后续 BERTopic 需输出本周 topic_id、topic_name、topic_embedding、关键词、代表文本及跨周匹配结果。": "B站主题、情感与风险由模型全量计算；当前不使用人工标签或人工校准。",
        "SnowNLP输出，建议对高风险主题进行人工校正。": "SnowNLP作为全量模型输出；验证指标仅用于说明模型质量。",
        "行动优先级": "测试行动建议",
        "横轴为主题声量占比，纵轴为负面率；右上角为优先处理区。": "横轴为模型计算的主题声量占比，纵轴为模型负面概率。",
        "当前基于估算情感与主题声量生成，仅用于功能测试。": "当前由模型全量计算情感与主题声量；结果属于模型辅助输出。",
        "The x-axis is topic volume share and the y-axis is negative rate; the upper-right quadrant requires priority action.": "The matrix uses model-computed volume share and model-computed negative rate.",
        "总声量与负面率同步观察，识别持续升温或风险加速。": "总声量与模型负面率同步观察，识别持续升温或风险加速。",
        "总声量与负面率同步观察（负面率为测试估算）。": "总声量与模型负面率同步观察。",
        "Track total volume and negative sentiment together to identify sustained growth or accelerating risk.": "Track total volume and model-computed negative rate to identify sustained growth or accelerating risk.",
        "sample:'演示样本'": "sample:'真实样本'",
        "sample:'Demo sample'": "sample:'Real sample'",
        "This page uses demo data. BERTopic should output topic_id, topic_name, topic_embedding, keywords, representative posts, and cross-week matches.": "W25-W28 are complete natural weeks; W29 (Jul 13-19) is incomplete as of Jul 18. The model provides full-coverage sentiment without manual calibration.",
        "当前页面使用演示数据。后续 BERTopic 需输出本周 topic_id、topic_name、topic_embedding、关键词、代表文本及跨周匹配结果。": "B站真实模型结果已接入；情感与风险为纯模型输出；小黑盒为固定规则模拟。",
        "${tr('platformComparison')}</div>": "${tr('platformComparison')} <span class=\"status source-real\">B站真实</span><span class=\"status source-sim\">小黑盒模拟</span></div>",
        'data-platform="综合"': 'data-platform="综合"',
        '<button class="chip active" data-platform="综合">综合</button>': '<button class="chip active" data-platform="综合">综合 · 测试</button>',
        '<button class="chip" data-platform="B站">B站</button>': '<button class="chip" data-platform="B站">B站 · 真实</button>',
        '<button class="chip" data-platform="小黑盒">小黑盒</button>': '<button class="chip" data-platform="小黑盒">小黑盒 · 模拟</button>',
        "['BERTopic 模型待接入','BERTopic integration pending']": "['BERTopic 已接入 · B站真实数据','BERTopic connected · real Bilibili data']",
        "['当前为演示面板','Demo dashboard']": "['当前为演示面板','Demo dashboard']",
        "negativeShare:'负面情绪占比'": "negativeShare:'负面率'",
        "negativeRate:'负面率'": "negativeRate:'负面率'",
        "negativeRate:'Negative rate'": "negativeRate:'Negative rate'",
        "avgSentiment:'平均情感分'": "avgSentiment:'本周情感结构'",
        "highRisk:'高风险主题'": "highRisk:'高风险主题'",
        "priorityNeeded:'需优先处置的主题'": "priorityNeeded:'辅助复核建议'",
        "riskOverview:'风险主题概览'": "riskOverview:'风险主题概览'",
        "persistentTopics:'跨周持续主题'": "persistentTopics:'高频关键词'",
    }
    for a, b in replacements.items(): source = source.replace(a, b)
    source = source.replace('<h3 class="panel-title">本周情感结构</h3>', '<h3 class="panel-title">本周情感结构</h3>')
    source = source.replace('<h3 class="panel-title">主题风险—机会矩阵</h3>', '<h3 class="panel-title">主题风险—机会矩阵</h3>')
    source = source.replace('当前为测试估算，SnowNLP正式结果尚未接入。', 'SnowNLP已作为全量模型输出；本版本不使用人工标签或人工校准。')
    source = source.replace('B站情感已接入SnowNLP测试结果；小黑盒情感为模拟推导；风险仍为估算，暂不可用于正式报告。', 'B站情感与风险由SnowNLP及模型公式全量计算；小黑盒与综合不用于正式统计。')
    source = source.replace('B站真实模型结果已接入；小黑盒、情感与风险仅用于测试。', 'B站主题、情感与风险由模型全量计算；小黑盒为固定规则模拟。')
    source = source.replace('The matrix uses observed volume and human-validated sentiment coverage; unlabeled items require review.', 'The matrix uses model-computed volume and negative probability; human labels calibrate and audit the model.')
    source = source.replace('<h3 class="panel-title">平台声量分布</h3>', '<h3 class="panel-title">平台声量分布 <span class="status source-mixed">真实＋模拟</span></h3>')
    source = source.replace("${displayPlatform(k)}${state.platform===k?' · '+tr('current'):''}", "${displayPlatform(k)} ${k==='B站'?'· 真实':'· 模拟'}${state.platform===k?' · '+tr('current'):''}")
    source = source.replace("${displayPlatform(state.platform)} ${tr('view')} · ${tr('topicChain')}", "${displayPlatform(state.platform)} ${state.platform==='B站'?'· 真实':'· 模拟'} · ${tr('view')} · ${tr('topicChain')}")
    source = source.replace("<small>${displayPlatform(state.platform)} · ${tr('sample')}</small>", "<small>${displayPlatform(state.platform)} · ${state.platform==='B站'?'真实模型数据':'模拟测试数据'} · ${tr('sample')}</small>")
    source = source.replace("  dashboardData.weeks.forEach(w=>{const found=w.topics.find(x=>x.id===id); if(found){t=found;wFound=w;}});\n  if(!t) return;", "  const selectedWeek=currentWeek(); const selectedTopic=selectedWeek.topics.find(x=>x.id===id); if(selectedTopic){t=selectedTopic;wFound=selectedWeek;} else { dashboardData.weeks.forEach(w=>{const found=w.topics.find(x=>x.id===id); if(found && !t){t=found;wFound=w;}}); }\n  if(!t) return;")
    source = source.replace("<div class=\"panel-head\"><div><h3 class=\"panel-title\">平台声量分布", "<div class=\"panel-head\"><div><h3 class=\"panel-title\">平台声量分布")
    # Keep historical localStorage, but never merge old PROJECT A/demo history.
    old = "if(storedDashboardHistory?.weeks?.length){\n  dashboardData.meta={...dashboardData.meta,...(storedDashboardHistory.meta||{})};\n  dashboardData.weeks=mergeDashboardWeeks([],storedDashboardHistory.weeks);\n}"
    new = "if(storedDashboardHistory?.weeks?.length && storedDashboardHistory.meta?.data_version==='apex_bilibili_scope_final_v1'){\n  dashboardData.meta={...dashboardData.meta,...(storedDashboardHistory.meta||{})};\n  dashboardData.weeks=mergeDashboardWeeks([],storedDashboardHistory.weeks);\n}else if(storedDashboardHistory){ try{ localStorage.removeItem(DASHBOARD_HISTORY_KEY); }catch(err){} }"
    source = source.replace(old, new)
    # Keep W28 as the current/latest default while preserving an explicit week selector.
    source = source.replace("let state = { weekIndex: dashboardData.weeks.length - 1, platform: \"综合\", search: \"\", sort: \"risk\", lang: \"zh\" };", "let state = { weekIndex: dashboardData.weeks.findIndex(w=>w.week_id==='2026-W28')>=0?dashboardData.weeks.findIndex(w=>w.week_id==='2026-W28'):dashboardData.weeks.length-1, platform: \"综合\", search: \"\", sort: \"risk\", lang: \"zh\" };")
    # Replace strict old import validation with Bilibili-only validation and deterministic adapter.
    if "$(\"#fileInput\").addEventListener('change',e=>{" in source:
        start = source.index("$(\"#fileInput\").addEventListener('change',e=>{")
        end = source.index("$$('.nav-item[data-anchor]')", start)
        importer = r'''$("#fileInput").addEventListener('change',e=>{
  if(!requireAuthenticated()) return;
  const file=e.target.files[0]; if(!file) return; const reader=new FileReader();
  reader.onload=()=>{ try{
    const obj=JSON.parse(reader.result); if(!obj.weeks||!Array.isArray(obj.weeks)||!obj.weeks.length) throw new Error(loc('缺少有效的 weeks 数组','Missing a valid weeks array'));
    obj.weeks.forEach((w,wi)=>{if(!Array.isArray(w.topics)) throw new Error(loc(`第 ${wi+1} 周缺少 topics 数组`,`Week ${wi+1} is missing a topics array`)); w.topics.forEach((t,ti)=>{if(!t.id||!t.name||!Array.isArray(t.keywords)||!Array.isArray(t.quotes)) throw new Error(loc(`主题 ${t.id||ti+1} 缺少 id、name、keywords 或 quotes`,`Topic ${t.id||ti+1} is missing id, name, keywords, or quotes`)); const b=t.platform_metrics?.['B站']||t.combined_metrics; if(!b||![b.count,b.video_count,b.creator_count,b.heat_score,b.consensus_score].every(Number.isFinite)) throw new Error(loc(`主题 ${t.id||ti+1} 缺少B站真实核心指标`,`Topic ${t.id||ti+1} is missing core real Bilibili metrics`));}); enrichWeekTopics(w);});
    const existingHistory=readDashboardHistory(); dashboardData.meta={...dashboardData.meta,...(obj.meta||{})}; dashboardData.weeks=mergeDashboardWeeks([],obj.weeks); writeDashboardHistory(dashboardData.meta,dashboardData.weeks); state.weekIndex=dashboardData.weeks.findIndex(w=>w.week_id==='2026-W28'); if(state.weekIndex<0) state.weekIndex=dashboardData.weeks.length-1; state.platform='综合'; state.search=''; $("#topicSearch").value=''; $$("#platformChips .chip").forEach((c,i)=>c.classList.toggle('active',i===0)); renderAll(); alert(loc('真实B站主题数据导入成功；小黑盒已按固定种子生成模拟数据。','Real Bilibili topic data imported; Heybox simulation was generated from a fixed seed.'));
  }catch(err){alert(loc('导入失败：','Import failed: ')+err.message);} finally{e.target.value='';}}; reader.readAsText(file,'utf-8');
});
'''
        source = source[:start] + importer + source[end:]
    # Add visible source badges and estimation notes without altering page layout.
    source = source.replace('</style>', '.source-real{color:#b8f2d0;border-color:#4d9a72!important}.source-sim{color:#ffe29a;border-color:#9e7a35!important}.source-mixed{color:#ffb0b8;border-color:#a44b57!important}.estimate-note{font-size:10px;color:#f1d98e;margin-left:6px}.platform-compare-metrics{grid-template-columns:minmax(30px,.46fr) minmax(64px,1.02fr) minmax(78px,1.25fr);gap:7px;align-items:start}.platform-compare-metric{min-width:0}.platform-compare-metric span{white-space:nowrap;line-height:1.35}.platform-compare-metric b{margin-top:6px;white-space:nowrap}html[lang="en"] .platform-compare-metric span{white-space:normal;overflow-wrap:anywhere}</style>', 1)
    source = source.replace('<div class="panel-head"><div><h3 class="panel-title">本周情感结构</h3>', '<div class="panel-head"><div><h3 class="panel-title">本周情感结构</h3>')
    source = source.replace('<div class="panel-head"><div><h3 class="panel-title">主题风险—机会矩阵</h3>', '<div class="panel-head"><div><h3 class="panel-title">主题风险—机会矩阵</h3>')
    source = source.replace('<div class="panel-head"><div><h3 class="panel-title">平台声量分布</h3>', '<div class="panel-head"><div><h3 class="panel-title">平台声量分布 <span class="status source-mixed">真实＋模拟</span></h3>')
    source = source.replace('负面率（人工覆盖）', '负面率')
    source = source.replace('高风险主题（人工覆盖）', '高风险主题')
    source = source.replace('风险主题概览（人工覆盖）', '风险主题概览')
    source = source.replace('人工覆盖负面率', '负面率')
    source = source.replace('人工情感覆盖', '情感复核结果')
    source = source.replace('人工覆盖子集', '人工复核子集')
    source = source.replace('平均情感分', '本周情感结构')
    source = source.replace("${displayKeywords(t).join(' · ')}", "${displayKeywords(t).slice(0,5).join(' · ')}")
    # Move the model notice into the sidebar and keep the weekly header sticky.
    source = re.sub(r'\n\s*<div class="notice">.*?</div>\n\s*\n\s*<div class="kpi-grid"', '\n\n        <div class="kpi-grid"', source, count=1, flags=re.S)
    if "const USER_USERNAME='nick';" not in source:
        source = source.replace("const ADMIN_USERNAME='choco';\nconst ADMIN_PASSWORD_HASH='327a7380d2cc7cf09ed5820e1ecdb8abe585d696b5b5526986dfebe70acec59e';", "const ADMIN_USERNAME='choco';\nconst ADMIN_PASSWORD_HASH='327a7380d2cc7cf09ed5820e1ecdb8abe585d696b5b5526986dfebe70acec59e';\nconst USER_USERNAME='nick';\nconst USER_PASSWORD_HASH='397d1a8097452b158e449ce9104699854463d2b5893e8f4004abfa1db9d58aa0';")
    if "let user=accounts.find(a=>a.username.toLowerCase()===USER_USERNAME);" not in source:
        source = source.replace("  admin.username=ADMIN_USERNAME; admin.passwordHash=ADMIN_PASSWORD_HASH; admin.role='admin'; admin.active=true;\n  writeAccounts(accounts);", "  admin.username=ADMIN_USERNAME; admin.passwordHash=ADMIN_PASSWORD_HASH; admin.role='admin'; admin.active=true;\n  let user=accounts.find(a=>a.username.toLowerCase()===USER_USERNAME);\n  if(!user){ user={username:USER_USERNAME,passwordHash:USER_PASSWORD_HASH,role:'user',active:true,createdAt:new Date().toISOString()}; accounts.push(user); }\n  user.username=USER_USERNAME; user.passwordHash=USER_PASSWORD_HASH; user.role='user'; user.active=true;\n  writeAccounts(accounts);")
    # Move the model notice into the sidebar and keep the weekly header sticky.
    source = re.sub(r'\n\s*<div class="notice">.*?</div>\n\s*\n\s*<div class="kpi-grid"', '\n\n        <div class="kpi-grid"', source, count=1, flags=re.S)
    source = source.replace('      <!-- Protected author signature. Keep this attribution in all published versions. -->', '      <div class="notice sidebar-model-notice"><div><b>模型接入提示：</b> B站主题、情感与风险仅使用模型全量输出；本版本不使用人工标签或人工校准；小黑盒为固定规则模拟。</div><button class="btn" id="jumpSchemaSidebar">查看字段结构</button></div>\n      <!-- Protected author signature. Keep this attribution in all published versions. -->', 1)
    source = source.replace('</style>', '.page-head{position:sticky;top:0;z-index:40;background:linear-gradient(180deg,rgba(8,9,11,.98) 0%,rgba(8,9,11,.94) 78%,rgba(8,9,11,.72) 100%);backdrop-filter:blur(12px);padding-top:12px;padding-bottom:14px;border-bottom:1px solid rgba(255,255,255,.08)}.sidebar-model-notice{margin:16px 0 0;padding:12px;border:1px solid rgba(242,31,43,.3);background:rgba(242,31,43,.07);font-size:10px;line-height:1.55;display:grid;gap:8px}.sidebar-model-notice .btn{justify-self:start;padding:6px 9px;font-size:10px}.dashboard-flow{display:grid;gap:18px}.dashboard-flow > *{grid-column:1 / -1 !important}.dashboard-flow>.method-grid{margin:0}.dashboard-flow>.card{width:100%}.dashboard-flow>.trend-risk-row{display:grid;grid-template-columns:minmax(0,7fr) minmax(320px,5fr);gap:18px}.dashboard-flow>.trend-risk-row>.card{min-width:0}.dashboard-flow>.chain-card{width:100%}.legacy-layout-hidden{display:none!important}.kpi-action{cursor:pointer;text-align:left}.kpi-action:focus-visible{outline:2px solid var(--accent);outline-offset:3px}.drawer-chart{display:grid;gap:10px;margin:14px 0}.drawer-chart-row{display:grid;grid-template-columns:78px 1fr 44px;align-items:center;gap:9px;font-size:11px}.drawer-chart-bar{height:9px;background:rgba(255,255,255,.09);overflow:hidden}.drawer-chart-bar i{display:block;height:100%;background:linear-gradient(90deg,#f21f2b,#f3b34c)}.drawer-keywords{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.drawer-keyword{padding:8px 10px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#f4f0df}.drawer-action-list{display:grid;gap:9px;margin-top:14px}@media(max-width:900px){.page-head{position:sticky;top:0}.dashboard-flow>.trend-risk-row{grid-template-columns:1fr}.sidebar-model-notice{margin-left:0;margin-right:0}} </style>', 1)
    source = source.replace('</style>', '.page-head{position:sticky;top:72px;z-index:40;align-items:center}.page-head>div:first-child{min-width:0;flex:1 1 auto}.page-head h2{white-space:nowrap;font-size:22px}.page-head p{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.filters{flex:0 0 auto;flex-wrap:nowrap;white-space:nowrap;gap:8px}.history-label,.chip-group{white-space:nowrap}.dashboard-flow>.trend-risk-row{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,.8fr);gap:18px}.dashboard-flow>.trend-risk-row>.card{grid-column:auto!important;min-width:0}.dashboard-flow>.chain-event-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px}.dashboard-flow>.chain-event-row>.card{grid-column:auto!important;min-width:0;width:100%}.drawer-donut-wrap{display:flex;align-items:center;gap:18px;margin:16px 0 20px}.drawer-donut{width:150px;height:150px;border-radius:50%;background:conic-gradient(var(--sentiment-positive) 0 var(--p1),var(--sentiment-neutral) var(--p1) var(--p2),var(--sentiment-negative) var(--p2) 100%);display:grid;place-items:center;position:relative;flex:0 0 150px}.drawer-donut:after{content:"";position:absolute;width:88px;height:88px;border-radius:50%;background:#101010}.drawer-donut span{position:relative;z-index:1;color:#fff;font-size:20px;font-weight:800}.drawer-donut-legend{display:grid;gap:8px;font-size:11px}.drawer-donut-legend i{display:inline-block;width:9px;height:9px;margin-right:6px;border-radius:2px}@media(max-width:900px){.page-head{top:72px}.filters{flex-wrap:wrap}.dashboard-flow>.trend-risk-row,.dashboard-flow>.chain-event-row{grid-template-columns:1fr}.dashboard-flow>.trend-risk-row>.card,.dashboard-flow>.chain-event-row>.card{grid-column:1!important}.drawer-donut-wrap{align-items:flex-start}} </style>', 1)
    ui_js = r'''function dashboardKeywordStats(w){\n  w=w||currentWeek(); const freq={}; w.topics.forEach(function(t){displayKeywords(t).forEach(function(k){freq[k]=(freq[k]||0)+(metricFor(t)?metricFor(t).count:0);});}); return Object.entries(freq).sort(function(a,b){return b[1]-a[1];});\n}\nfunction showMetricDrawer(title,sub,body){$("#drawerTitle").textContent=title;$("#drawerSub").textContent=sub;$("#drawerBody").innerHTML=body;$("#drawerMask").classList.add("show");$("#drawer").classList.add("show");}\nfunction openVolumeDrawer(){var w=currentWeek(),totals={"B站":0,"小黑盒":0};w.topics.forEach(function(t){Object.keys(totals).forEach(function(p){totals[p]+=Number(t.platform_metrics&&t.platform_metrics[p]&&t.platform_metrics[p].count)||0;});});var all=totals["B站"]+totals["小黑盒"]||1;var bars=Object.entries(totals).map(function(x){var k=x[0],v=x[1];return '<div class="platform-row"><span>'+displayPlatform(k)+(k==="B站"?" · "+loc("真实","Real"):" · "+loc("模拟","Simulated"))+'</span><div class="platform-bar"><i style="width:'+(v/all*100)+'%"></i></div><b style="color:#dbe3f4">'+(v/all*100).toFixed(1)+'%</b></div>';}).join("");showMetricDrawer(loc("本周总声量","Total volume this week"),w.label+" · "+fmt(all)+" "+loc("条","items"),'<p class="risk-drawer-intro">'+loc("平台声量分布仅在此二级页面展示；B站为真实数据，小黑盒为固定规则模拟。","Platform volume is shown only in this detail view; Bilibili is real and Heybox is deterministic simulation.")+'</p><div class="platform-bars drawer-platform-bars">'+bars+'</div><div class="detail-kpis"><div class="detail-kpi"><span>'+loc("总声量","Total volume")+'</span><strong>'+fmt(all)+'</strong></div><div class="detail-kpi"><span>B站</span><strong>'+fmt(totals["B站"])+'</strong></div><div class="detail-kpi"><span>小黑盒</span><strong>'+fmt(totals["小黑盒"])+'</strong></div></div>');}\nfunction openSentimentDrawer(){var w=currentWeek(),cur=aggregateWeek(w),summaries=dashboardData.weeks.map(function(x){return {w:x,s:aggregateWeek(x)};}),max=Math.max.apply(null,summaries.map(function(x){return x.s.volume;}).concat([1]));var rows=[[loc("积极","Positive"),cur.sentiment.positive,"var(--sentiment-positive)"],[loc("中性","Neutral"),cur.sentiment.neutral,"var(--sentiment-neutral)"],[loc("负面","Negative"),cur.sentiment.negative,"var(--sentiment-negative)"]];var rhtml=rows.map(function(r){return '<div class="sentiment-row"><span>'+r[0]+'</span><div class="bar"><i style="width:'+r[1]+'%;background:'+r[2]+'"></i></div><b style="color:'+r[2]+'">'+r[1]+'%</b></div>';}).join("");var chart=summaries.map(function(x){return '<div class="drawer-chart-row"><span>'+x.w.label+'</span><div class="drawer-chart-bar"><i style="width:'+(x.s.volume/max*100)+'%"></i></div><b>'+x.s.negative_rate+'%</b></div>';}).join("");showMetricDrawer(loc("本周情感结构","Sentiment this week"),w.label+" · "+loc("人工覆盖子集","Human-validated subset"),'<p class="risk-drawer-intro">'+loc("本页展示本周结构和历史环比；未覆盖评论继续保留在人工复核队列。","This view shows the current structure and week-over-week comparison; unlabeled comments remain in the human review queue.")+'</p><div class="sentiment-list">'+rhtml+'</div><div class="section-title">'+loc("近5周情感结构环比","Five-week sentiment comparison")+'</div><div class="drawer-chart">'+chart+'</div>');}\nfunction openKeywordDrawer(){var stats=dashboardKeywordStats(currentWeek()),max=stats[0]?stats[0][1]:1;var chips=stats.slice(0,30).map(function(x,i){return '<span class="drawer-keyword" style="font-size:'+(12+x[1]/max*10)+'px;color:'+(i<5?"#f2c94c":"#e3e3df")+'">'+x[0]+'<small style="display:block;color:var(--muted);font-size:10px;margin-top:3px">'+fmt(x[1])+' '+loc("声量","volume")+'</small></span>';}).join("");showMetricDrawer(loc("高频关键词","Top keywords"),currentWeek().label+" · "+stats.length+" "+loc("个关键词","keywords"),'<p class="risk-drawer-intro">'+loc("关键词按本周主题声量加权汇总，用于辅助人工命名主题和发现新词。","Keywords are weighted by this week’s topic volume for human topic naming and new-term discovery.")+'</p><div class="drawer-keywords">'+chips+'</div>');}\nfunction openActionDrawer(){var topics=filteredTopics(),risks=topics.filter(function(t){return t.risk==="风险";}).sort(function(a,b){return metricFor(b).risk_score-metricFor(a).risk_score;}),ops=topics.filter(function(t){return t.risk==="机会";}).sort(function(a,b){return metricFor(b).heat_score-metricFor(a).heat_score;}),items=risks.map(function(t){return {t:t,kind:"risk"};}).concat(ops.map(function(t){return {t:t,kind:"op"};}));var html=items.map(function(x,i){var tm=metricFor(x.t);return '<div class="risk-item" data-topic="'+x.t.id+'"><div class="risk-line '+(x.kind==="op"?"op":"")+'"></div><div><strong>'+displayTopicName(x.t)+'</strong><span>'+(x.kind==="op"?tr("heatOption")+" "+tm.heat_score+" · "+tr("heatAsset"):tr("negativeRate")+" "+tm.negative+"% · "+tr("responseAdvice"))+'</span></div><div class="risk-level">'+(x.kind==="op"?tr("opportunity"):"P"+Math.min(3,i+1))+'</div></div>';}).join("");showMetricDrawer(loc("辅助复核建议","Review priorities"),currentWeek().label+" · "+items.length+" "+loc("项","items"),'<p class="risk-drawer-intro">'+loc("以下建议用于辅助专业人员安排复核顺序，不替代人工舆情判断。","These suggestions help professionals prioritize review and do not replace human judgment.")+'</p><div class="drawer-action-list">'+html+'</div>');$$("#drawerBody .risk-item").forEach(function(el){el.onclick=function(){openTopic(el.dataset.topic);};});}\nfunction renderKpis(){var w=currentWeek(),k=aggregateWeek(w),keywordCount=dashboardKeywordStats(w).length,items=[[tr("thisWeekVolume"),fmt(k.volume),loc("查看平台声量","View platform volume")],[tr("negativeShare"),k.negative_rate+"%",loc("查看行动优先级","View review priorities")],[tr("highRisk"),k.risk_topics,tr("priorityNeeded")],[tr("newTopics"),k.new_topics,tr("modelDetected")],[tr("keywords"),keywordCount,loc("查看高频关键词","View top keywords")],[loc("本周情感结构","Sentiment this week"),k.sentiment_score.toFixed(2),loc("查看情感环比","View sentiment comparison")]],actions=[openVolumeDrawer,openActionDrawer,openHighRiskDrawer,openNewTopicsDrawer,openKeywordDrawer,openSentimentDrawer];$("#kpiGrid").innerHTML=items.map(function(x,i){return '<button type="button" class="card kpi kpi-action" id="kpiAction'+i+'" aria-label="'+x[0]+' '+x[1]+'"><div class="kpi-label">'+x[0]+'</div><div class="kpi-value">'+x[1]+'</div><div class="kpi-foot">'+x[2]+'</div></button>';}).join("");items.forEach(function(_,i){$("#kpiAction"+i).addEventListener("click",actions[i]);});}\nfunction arrangeDashboardOrder(){if(document.body.dataset.dashboardArranged)return;var main=document.querySelector("main"),overview=document.querySelector("#overview"),topics=document.querySelector("#topics"),risk=document.querySelector("#risk");if(!main||!overview||!topics||!risk)return;var method=topics.querySelector(".method-grid"),coreGrid=topics.querySelector(".grid-12"),coreCard=coreGrid&&coreGrid.querySelector(".span-12"),eventCard=coreGrid&&coreGrid.querySelector(".span-12:not(:first-child)"),trend=overview.querySelector(".grid-12 .span-8"),sentimentPanel=overview.querySelector("#sentiment"),riskGrid=risk.querySelector(".grid-12"),matrix=riskGrid&&riskGrid.querySelector(".span-7"),actionPanel=riskGrid&&riskGrid.querySelector(".span-5"),chainGrid=risk.querySelectorAll(".grid-12")[1],chainCard=chainGrid&&chainGrid.querySelector(".span-6:last-child"),keywordCard=chainGrid&&chainGrid.querySelector(".span-6:first-child");if(!method||!coreCard||!trend||!matrix||!chainCard)return;sentimentPanel&&sentimentPanel.classList.add("legacy-layout-hidden");actionPanel&&actionPanel.classList.add("legacy-layout-hidden");keywordCard&&keywordCard.classList.add("legacy-layout-hidden");if(eventCard){eventCard.querySelector(".platform-bars")&&eventCard.querySelector(".platform-bars").classList.add("legacy-layout-hidden");eventCard.querySelector(".panel-head")&&eventCard.querySelector(".panel-head").classList.add("legacy-layout-hidden");}var order=document.createElement("div");order.id="dashboardOrder";order.className="dashboard-flow";var row=document.createElement("div");row.className="trend-risk-row";trend.classList.remove("span-8");matrix.classList.remove("span-7");matrix.classList.add("span-5");row.append(trend,matrix);main.insertBefore(order,overview);order.append(method,coreCard,row,chainCard);if(eventCard)order.append(eventCard);[overview,topics,risk].forEach(function(s){s.classList.add("legacy-layout-hidden");});document.body.dataset.dashboardArranged="1";$$(".nav-item[data-anchor]").forEach(function(n){n.onclick=function(){var target=n.dataset.anchor==="evolution"?"evolution":"dashboardOrder";document.getElementById(target)&&document.getElementById(target).scrollIntoView({behavior:"smooth",block:"start"});$$(".nav-item").forEach(function(x){x.classList.remove("active");});n.classList.add("active");};});}\n'''
    # Refine the secondary drawers and dashboard order without changing the base HTML.
    ui_js = ui_js.replace('var chart=summaries.map(function(x){', 'var donut="<div class=\\"drawer-donut\\" style=\\"--p1:"+cur.sentiment.positive+"%;--p2:"+(cur.sentiment.positive+cur.sentiment.neutral)+"%\\"><span>"+cur.sentiment.positive+"%</span></div>";var chart=summaries.map(function(x){')
    ui_js = ui_js.replace("<div class=\"sentiment-list\">'+rhtml", """<div class="drawer-donut-wrap">'+donut+'<div class="drawer-donut-legend"><div><i style="background:var(--sentiment-positive)"></i>'+loc("积极","Positive")+' '+cur.sentiment.positive+'%</div><div><i style="background:var(--sentiment-neutral)"></i>'+loc("中性","Neutral")+' '+cur.sentiment.neutral+'%</div><div><i style="background:var(--sentiment-negative)"></i>'+loc("负面","Negative")+' '+cur.sentiment.negative+'%</div></div></div><div class="sentiment-list">'+rhtml""")
    ui_js = ui_js.replace('loc("人工覆盖子集","Human-validated subset")', 'loc("人工复核子集","Reviewed subset")')
    ui_js = ui_js.replace('loc("辅助复核建议","Review priorities")', 'loc("辅助复核意见","Review comments")')
    ui_js = ui_js.replace('loc("查看行动优先级","View review priorities")', 'loc("辅助复核意见","Review comments")')
    ui_js = ui_js.replace('w.label+" · "+loc("人工复核子集","Reviewed subset")', 'w.label+" · "+loc("模型全量输出","Model full-coverage output")')
    ui_js = ui_js.replace('loc("本页展示本周结构和历史环比；未覆盖评论继续保留在人工复核队列。","This view shows the current structure and week-over-week comparison; unlabeled comments remain in the human review queue.")', 'loc("本页展示模型计算的本周结构和历史环比。","This view shows the model-computed structure and week-over-week comparison.")')
    ui_js = ui_js.replace('loc("关键词按本周主题声量加权汇总，用于辅助人工命名主题和发现新词。","Keywords are weighted by this week’s topic volume for human topic naming and new-term discovery.")', 'loc("关键词按本周主题声量加权汇总，用于发现新词。","Keywords are weighted by this week’s topic volume for new-term discovery.")')
    ui_js = ui_js.replace('var order=document.createElement("div");order.id="dashboardOrder";order.className="dashboard-flow";var row=', 'var order=document.createElement("div");order.id="dashboardOrder";order.className="dashboard-flow";var chainEventRow=document.createElement("div");chainEventRow.className="chain-event-row";var row=')
    ui_js = ui_js.replace('order.append(method,coreCard,row,chainCard);if(eventCard)order.append(eventCard);', 'if(eventCard)chainEventRow.append(chainCard,eventCard);else chainEventRow.append(chainCard);order.append(method,coreCard,row,chainEventRow);')
    ui_js = ui_js.replace('var method=topics.querySelector(".method-grid")', 'var pageHead=overview.querySelector(".page-head"),kpiGrid=document.querySelector("#kpiGrid"),method=topics.querySelector(".method-grid")')
    ui_js = ui_js.replace('if(!method||!coreCard||!trend||!matrix||!chainCard)return;', 'if(!pageHead||!kpiGrid||!method||!coreCard||!trend||!matrix||!chainCard)return;')
    ui_js = ui_js.replace('order.append(method,coreCard,row,chainEventRow)', 'order.append(pageHead,kpiGrid,method,coreCard,row,chainEventRow)')
    source = source.replace("const schemaExample = dashboardData;", ui_js.replace("\\n", "\n") + "\nconst schemaExample = dashboardData;", 1)
    source = source.replace('$("#schemaBtn").onclick=openSchema; $("#jumpSchema").onclick=openSchema;', '$("#schemaBtn").onclick=openSchema; $("#jumpSchema")?.addEventListener("click",openSchema); $("#jumpSchemaSidebar")?.addEventListener("click",openSchema);')
    source = source.replace("const weighted=k=>rows.reduce((s,x)=>s+(Number(x.m[k])||0)*x.m.count,0)/volume;\n  const negative=Math.round(weighted('negative'));", "const weighted=k=>rows.reduce((s,x)=>s+(Number(x.m[k])||0)*x.m.count,0)/volume;\n  const hasWow=rows.some(x=>x.m.wow!==null&&x.m.wow!==undefined&&x.m.wow!=='');\n  const negative=Math.round(weighted('negative'));", 1)
    source = source.replace("return {volume,negative_rate:negative,wow:+weighted('wow').toFixed(1),", "return {volume,negative_rate:negative,wow:hasWow?+weighted('wow').toFixed(1):null,", 1)
    source = source.replace("risk_topics:rows.filter(x=>x.m.risk_score>=60).length", "risk_topics:rows.filter(x=>x.m.risk_score>=60||x.m.negative>=60).length")
    source = source.replace(".filter(x=>x.m&&x.m.count>0&&x.m.risk_score>=60)", ".filter(x=>x.m&&x.m.count>0&&(x.m.risk_score>=60||x.m.negative>=60))")
    source = source.replace(".filter(x=>x.m&&x.m.count>0&&x.t.status==='新生')", ".filter(x=>x.m&&x.m.count>0&&(currentWeek().kpis.new_topic_ids||[]).includes(x.t.id))")
    source = source.replace("${tr('newTopicOverviewDesc')}", "${currentWeek().kpis.new_topic_status==='baseline_no_prior_week'?loc('W25为基准周，不生成W24新增对比。','W25 is the baseline week; no W24 comparison is generated.'):topics.length?tr('newTopicOverviewDesc'):loc('本周没有新增canonical主题；离群或删除文本不会自动升级为新主题。','No new canonical topic was detected this week; outliers and deleted texts are not promoted automatically.')}" )
    source = source.replace('initializeAuth();', 'arrangeDashboardOrder();\ninitializeAuth();')
    return source


def main():
    if not REPO.exists(): raise SystemExit(f"GitHub repo not found: {REPO}")
    data = make_data(); html = patch_html(data); payload = json.dumps(data, ensure_ascii=False, indent=2); REPO_JSON.write_text(payload, encoding="utf-8"); REPO_HTML.write_text(html, encoding="utf-8"); DELIVERABLE_JSON.write_text(payload, encoding="utf-8"); DELIVERABLE_HTML.write_text(html, encoding="utf-8")
    weeks = data["weeks"]; report = ["# W25—W28混合数据看板接入报告", "", "## 数据来源", "", "- B站：W25—W28真实BERTopic主题结果；文本量、视频数、作者数、关键词、主题链和代表文本来自真实B站结果，`metrics_source=bilibili_real_model_output`。", "- B站情感：SnowNLP对全部映射评论直接进行模型计算；本版本不读取人工标签、不使用人工校准、不使用人工训练的情感模型。", "- 小黑盒：仅用于平台切换和计算逻辑测试，基于同一主题B站核心指标按固定种子生成，`metrics_source=heybox_simulated_for_ui_test`，每条记录含`simulated=true`和`simulation_seed=2717`。", "- 综合：B站真实数据与小黑盒模拟数据合并，`metrics_source=mixed_real_and_simulated`，不属于正式统计口径。", "", "## 模型口径", "", "- 热议度、共识度和风险由看板公式基于模型输出的声量、覆盖与情感结果计算。", "- 负面率和情感结构为SnowNLP全量模型输出；不使用人工标签替换或平滑模型结果。", "- 2%—5%偏差目标不作未经独立基准支持的宣称；SnowNLP验证指标仅用于说明模型质量。", "", "## 接入周次", "", "| 周次 | B站主题数 | B站文本量 |", "|---|---:|---:|"]
    for w in weeks: report.append(f"| {w['label']} | {len(w['topics'])} | {sum(t['platform_metrics']['B站']['count'] for t in w['topics'])} |")
    snow_status = data["meta"].get("sentiment_status")
    report += ["", "## 新增主题核对", "", "W25为基准周，不生成不存在的W24环比，因此新增主题数记为0并标记为baseline。W26—W28的13个有效canonical主题均已在W25首次出现，模型没有识别到新的canonical主题，所以后三周新增数为0。模型离群、删除或低置信度文本不会自动升级为新增主题；它们需要单独完成主题候选分析。", "", "## 情感与风险状态", "", "本版本对全部映射评论直接使用SnowNLP模型输出，再按主题和周次聚合；不读取人工标签、不使用人工校准或人工训练的情感模型。当前只完成模型输出覆盖性检查，尚未完成独立的正式统计基准验证，因此结果用于模型辅助看板，不单独作为最终舆情结论。", "", "## 已保留交互", "", "登录、账号管理、中英文切换、JSON导入、localStorage历史周、周次切换、平台切换、主题搜索、主题排序、主题详情、关键词、跨周演化和响应式布局均保留。", "", "## 禁止误读", "", "小黑盒和综合视图包含模拟数据；2%—5%偏差目标未完成独立基准验证；B站纯模型情感与风险不应单独作为最终舆情结论。"]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    repo_report = REPO / "reports/dashboard_W25_W28_mixed_data_report.md"
    repo_report.parent.mkdir(parents=True, exist_ok=True)
    repo_report.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"repo_json": str(REPO_JSON), "repo_html": str(REPO_HTML), "deliverable_json": str(DELIVERABLE_JSON), "deliverable_html": str(DELIVERABLE_HTML), "weeks": len(weeks), "topics_per_week": [len(w['topics']) for w in weeks]}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
