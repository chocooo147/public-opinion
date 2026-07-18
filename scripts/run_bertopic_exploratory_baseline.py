from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/processed/bilibili_apex_W25_W28_final_settlement.csv"
CORPUS = ROOT / "data/processed/bilibili_apex_W25_W28_bertopic_exploratory_corpus.csv"
MANIFEST = ROOT / "outputs/bilibili_apex_W25_W28_dataset_manifest.json"
EXPERIMENTS = ROOT / "outputs/bertopic_experiments.csv"
REVIEW = ROOT / "outputs/topic_review_pack.csv"
WEEKLY = ROOT / "outputs/topic_weekly_distribution.csv"
OUTLIERS = ROOT / "outputs/outlier_review_sample.csv"
BASELINE_REPORT = ROOT / "reports/bertopic_exploratory_baseline_report.md"
RECOMMENDATION = ROOT / "reports/bertopic_model_selection_recommendation.md"

DATA_VERSION = "apex_bilibili_scope_final_v1"
MODEL_VERSION = "bertopic_exploratory_baseline_v1_2026-07-17"
STATUS = "exploratory_baseline_ready"
WEEKS = ["2026_W25", "2026_W26", "2026_W27", "2026_W28"]
TERM_LEXICON = sorted({
    "Apex英雄", "Apex", "排位", "匹配", "外挂", "反作弊", "服务器", "延迟", "掉线", "闪退", "掉帧", "卡顿", "优化",
    "猎杀", "段位", "英雄", "强度", "角色平衡", "武器", "武器平衡", "版本更新", "新赛季", "通行证", "皮肤", "活动",
    "氪金", "联动", "赛博朋克", "赛事", "ALGS", "主播", "玩家", "社区", "官方", "开发", "退款", "差评", "手柄",
    "键鼠", "莫桑比克", "希尔", "复仇", "传家宝", "外卡", "KD", "棒球棒", "技能", "大招", "队友", "单排", "猎杀",
    "商业化", "玩法", "规则", "公平", "沟通", "质量", "排名", "战队", "选手", "赛季", "版本", "皮肤评价",
}, key=len, reverse=True)
STOPWORDS = {"的", "了", "是", "我", "你", "他", "她", "它", "这", "那", "都", "就", "也", "还", "在", "有", "和", "与", "一个", "一下", "什么", "怎么", "然后", "真的", "感觉"}
_JIEBA = None
_JIEBA_READY = False


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    last = None
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            with path.open(encoding=enc, newline="") as f:
                r = csv.DictReader(f)
                return [{k: (v or "") for k, v in row.items()} for row in r], list(r.fieldnames or [])
        except UnicodeDecodeError as exc:
            last = exc
    raise UnicodeError(str(last))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def clean_text(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", text or "")
    text = re.sub(r"[\r\n\t]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    global _JIEBA, _JIEBA_READY
    text = clean_text(text)
    if _JIEBA is None:
        try:
            import jieba
            _JIEBA = jieba
        except ImportError:
            _JIEBA = False
    if _JIEBA and not _JIEBA_READY:
        for term in TERM_LEXICON:
            _JIEBA.add_word(term)
        _JIEBA_READY = True
    if _JIEBA:
        return [tok.lower() for tok in _JIEBA.lcut(text, HMM=False) if len(tok.strip()) > 1 and tok.strip() not in STOPWORDS and not re.fullmatch(r"[\W_]+", tok.strip())]
    tokens: list[str] = []
    i = 0
    while i < len(text):
        matched = None
        for term in TERM_LEXICON:
            if text[i:i + len(term)].lower() == term.lower():
                matched = term
                break
        if matched:
            tokens.append(matched.lower())
            i += len(matched)
            continue
        m = re.match(r"[A-Za-z0-9]+", text[i:])
        if m:
            token = m.group(0).lower()
            if len(token) > 1:
                tokens.append(token)
            i += len(m.group(0))
            continue
        if "\u4e00" <= text[i] <= "\u9fff":
            if i + 1 < len(text) and "\u4e00" <= text[i + 1] <= "\u9fff":
                tokens.append(text[i:i + 2])
                i += 2
            else:
                i += 1
            continue
        i += 1
    return tokens


def numeric(value: str) -> float:
    value = str(value or "").strip().replace(",", "")
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        mult = 1.0
        if value.endswith("万"):
            mult, value = 10000.0, value[:-1]
        elif value.endswith("亿"):
            mult, value = 100000000.0, value[:-1]
        try:
            return float(value) * mult
        except ValueError:
            return 0.0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def row_count(path: Path) -> int | None:
    if path.suffix != ".csv":
        return None
    with path.open(encoding="utf-8-sig", newline="") as f:
        return max(0, sum(1 for _ in csv.DictReader(f)))


def build_corpus() -> tuple[list[dict[str, str]], list[str]]:
    rows, source_fields = read_csv(INPUT)
    selected = [
        r for r in rows
        if r.get("source_type") == "top_level_comment"
        and r.get("final_training_include") == "1"
        and clean_text(r.get("text", ""))
    ]
    fields = [
        "text_id", "publish_time", "week_id", "week_start", "week_end", "platform", "source_type",
        "raw_text", "clean_text", "title", "bvid", "author_name", "creator_type", "query_keyword",
        "event_tag", "is_event_driven", "likes", "comments", "shares", "views", "final_analysis_scope",
        "final_new_media_include", "final_technical_include", "final_scope_source", "content_hash", "dedup_key",
        "manual_topic", "confirmed_topic", "manual_sentiment", "data_version", "dataset_status",
        "qualified_for_exploratory_bertopic", "qualified_for_formal_reporting",
    ]
    out = []
    for r in selected:
        x = {k: r.get(k, "") for k in fields}
        x["raw_text"] = r.get("text", "")
        x["clean_text"] = clean_text(r.get("text", ""))
        x["data_version"] = DATA_VERSION
        x["dataset_status"] = STATUS
        x["qualified_for_exploratory_bertopic"] = "true"
        x["qualified_for_formal_reporting"] = "false"
        out.append(x)
    write_csv(CORPUS, out, fields)
    return out, fields


def run_models(corpus_rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    # Use a local sklearn lexical embedding to avoid downloading a sentence-transformer model.
    import numpy as np
    from bertopic import BERTopic
    from bertopic.backend._sklearn import SklearnEmbedder
    from hdbscan import HDBSCAN
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
    from sklearn.pipeline import make_pipeline
    from umap import UMAP

    docs = [r["clean_text"] for r in corpus_rows]
    configs = [
        {"model_id": "exp_a_balanced", "min_topic_size": 25, "n_neighbors": 10, "min_cluster_size": 25, "min_samples": 5},
        {"model_id": "exp_b_finer", "min_topic_size": 15, "n_neighbors": 8, "min_cluster_size": 15, "min_samples": 3},
        {"model_id": "exp_c_conservative", "min_topic_size": 35, "n_neighbors": 15, "min_cluster_size": 35, "min_samples": 5},
    ]
    experiment_rows: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    weekly_rows: list[dict[str, object]] = []
    outlier_rows: list[dict[str, object]] = []
    model_cache: dict[str, tuple[object, list[int]]] = {}

    for cfg in configs:
        pipe = make_pipeline(
            TfidfVectorizer(tokenizer=tokenize, token_pattern=None, lowercase=False, min_df=2, max_features=12000),
            TruncatedSVD(n_components=50, random_state=42),
        )
        embedding_model = SklearnEmbedder(pipe)
        umap_model = UMAP(
            n_neighbors=cfg["n_neighbors"], n_components=5, min_dist=0.0, metric="cosine",
            random_state=42, low_memory=True, n_jobs=1,
        )
        hdbscan_model = HDBSCAN(
            min_cluster_size=cfg["min_cluster_size"], min_samples=cfg["min_samples"],
            metric="euclidean", cluster_selection_method="eom", prediction_data=True,
        )
        vectorizer = CountVectorizer(tokenizer=tokenize, token_pattern=None, lowercase=False, min_df=1, max_features=12000)
        model = BERTopic(
            embedding_model=embedding_model,
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            vectorizer_model=vectorizer,
            min_topic_size=cfg["min_topic_size"],
            top_n_words=15,
            calculate_probabilities=False,
            verbose=False,
        )
        topics, _ = model.fit_transform(docs)
        topics = [int(t) for t in topics]
        model_cache[cfg["model_id"]] = (model, topics)
        counts = Counter(topics)
        non_outlier = {k: v for k, v in counts.items() if k != -1}
        topic_count = len(non_outlier)
        outlier_rate = counts.get(-1, 0) / len(topics) if topics else 0
        max_topic_share = max(non_outlier.values(), default=0) / len(topics) if topics else 0
        info = model.get_topic_info()
        keyword_by_topic: dict[int, list[str]] = {}
        for topic_id in sorted(non_outlier):
            terms = [term for term, _ in (model.get_topic(topic_id) or [])]
            keyword_by_topic[topic_id] = terms[:15]
        all_terms = [term for terms in keyword_by_topic.values() for term in terms]
        repetition = sum(1 for term, n in Counter(all_terms).items() if n > 1) / len(set(all_terms)) if all_terms else 0
        experiment_rows.append({
            "model_id": cfg["model_id"], "model_status": "completed", "embedding_backend": "sklearn_lexical_tfidf_svd",
            "min_topic_size": cfg["min_topic_size"], "n_neighbors": cfg["n_neighbors"],
            "min_cluster_size": cfg["min_cluster_size"], "min_samples": cfg["min_samples"],
            "documents": len(docs), "topic_count": topic_count, "outlier_count": counts.get(-1, 0),
            "outlier_rate": outlier_rate, "max_topic_share": max_topic_share,
            "keyword_repetition_rate": repetition, "topic_keyword_overlap_count": sum(1 for n in Counter(all_terms).values() if n > 1),
            "notes": "探索性模型；不等同于正式舆情结论",
        })

        week_topic_counts = Counter((r["week_id"], t) for r, t in zip(corpus_rows, topics) if t != -1)
        week_totals = Counter(r["week_id"] for r in corpus_rows)
        for (week, topic_id), n in sorted(week_topic_counts.items()):
            weekly_rows.append({"model_id": cfg["model_id"], "week_id": week, "topic_id": topic_id, "text_count": n, "share_of_week": n / week_totals[week]})

        topic_rows: dict[int, list[dict[str, str]]] = defaultdict(list)
        for r, topic_id in zip(corpus_rows, topics):
            if topic_id != -1:
                topic_rows[topic_id].append(r)
            else:
                outlier_rows.append({"model_id": cfg["model_id"], "text_id": r["text_id"], "week_id": r["week_id"], "text": r["raw_text"], "bvid": r["bvid"], "event_tag": r["event_tag"], "outlier_reason": "BERTopic assigned -1"})
        for topic_id, rows in sorted(topic_rows.items()):
            terms = keyword_by_topic.get(topic_id, [])
            suggested = " / ".join(terms[:4])
            reps = sorted(rows, key=lambda r: (len(r["clean_text"]), r["text_id"]))[:15]
            interaction = sorted(rows, key=lambda r: sum(numeric(r.get(k, "")) for k in ("likes", "comments", "shares", "views")), reverse=True)[:5]
            primary_events = Counter(r.get("event_tag", "") for r in rows if r.get("event_tag", ""))
            main_event = primary_events.most_common(1)[0][0] if primary_events else ""
            for selection, selected_rows in (("representative", reps), ("high_interaction", interaction)):
                for rank, r in enumerate(selected_rows, 1):
                    review_rows.append({
                        "model_id": cfg["model_id"], "topic_id": topic_id, "topic_text_count": len(rows),
                        "topic_share": len(rows) / len(docs), "topic_keywords": " | ".join(terms),
                        "suggested_topic_name": suggested, "main_event_tag": main_event,
                        "selection_type": selection, "selection_rank": rank, "text_id": r["text_id"],
                        "week_id": r["week_id"], "text": r["raw_text"], "bvid": r["bvid"],
                        "author_name": r["author_name"], "creator_type": r["creator_type"],
                        "event_tag": r["event_tag"], "likes": r["likes"], "comments": r["comments"],
                        "shares": r["shares"], "views": r["views"], "manual_topic_name": "",
                        "manual_keep": "", "manual_merge_with": "", "manual_split_required": "",
                        "manual_interpretability_score": "", "manual_notes": "",
                    })
    return experiment_rows, review_rows, weekly_rows, outlier_rows


def write_manifest(corpus_rows: list[dict[str, str]], output_paths: list[Path]) -> None:
    inputs = [INPUT]
    files = []
    for path in [CORPUS, MANIFEST, EXPERIMENTS, REVIEW, WEEKLY, OUTLIERS, BASELINE_REPORT, RECOMMENDATION] + output_paths:
        if path.exists():
            files.append({"path": str(path), "rows": row_count(path), "sha256": sha256_file(path)})
    manifest = {
        "data_version": DATA_VERSION,
        "model_version": MODEL_VERSION,
        "dataset_status": STATUS,
        "qualified_for_exploratory_bertopic": True,
        "qualified_for_formal_reporting": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_files": [{"path": str(p), "sha256": sha256_file(p)} for p in inputs],
        "output_files": files,
        "final_training_text_count": len(corpus_rows),
        "known_limitations": [
            "W25最大单一事件占比43.02%，高于业务参考线40%",
            "W27独立视频27个",
            "W28独立视频24个",
            "当前仅锁定为探索性基线输入，不具备正式报告资格",
        ],
        "modeling": {"bertopic_trained": True, "snownlp_run": False, "dashboard_updated": False, "topic_chain_generated": False},
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def write_reports(experiments: list[dict[str, object]], weekly: list[dict[str, object]], review: list[dict[str, object]], outliers: list[dict[str, object]], corpus_rows: list[dict[str, str]]) -> None:
    # 选择仅用于人工审核排序：同时惩罚离群、关键词重复和单一主题支配，避免“零离群但单主题吞并”的退化模型。
    best = min(experiments, key=lambda r: float(r["outlier_rate"]) + float(r["keyword_repetition_rate"]) + float(r["max_topic_share"]))
    best_id = best["model_id"]
    best_weekly = [r for r in weekly if r["model_id"] == best_id]
    stable = []
    for topic_id in sorted({r["topic_id"] for r in best_weekly}):
        weeks = {r["week_id"] for r in best_weekly if r["topic_id"] == topic_id and float(r["share_of_week"]) >= 0.01}
        if len(weeks) >= 3:
            stable.append(str(topic_id))
    name_by_topic = {}
    size_by_topic = {}
    for r in review:
        if r["model_id"] == best_id:
            name_by_topic.setdefault(str(r["topic_id"]), r["suggested_topic_name"])
            size_by_topic.setdefault(str(r["topic_id"]), int(r["topic_text_count"]))
    stable_labels = [f"{tid}:{name_by_topic.get(tid, '')}" for tid in stable]
    small_topics = [f"{tid}:{name_by_topic.get(tid, '')}" for tid, n in sorted(size_by_topic.items()) if n < 10]
    event_driven = []
    for topic_id in sorted({r["topic_id"] for r in review if r["model_id"] == best_id}):
        rows = [r for r in review if r["model_id"] == best_id and r["topic_id"] == topic_id]
        if rows and rows[0]["main_event_tag"] and sum(1 for r in rows if r["event_tag"] == rows[0]["main_event_tag"]) / len(rows) >= 0.6:
            event_driven.append(f"{topic_id}:{rows[0]['main_event_tag']}")
    lines = [
        "# Apex英雄B站W25—W28探索性BERTopic基线报告", "",
        f"- 数据版本：`{DATA_VERSION}`；状态：`{STATUS}`。",
        f"- 训练评论：{len(corpus_rows)}条；采用四周合并全局模型。",
        "- qualified_for_exploratory_bertopic=true；qualified_for_formal_reporting=false。",
        "- 本报告仅用于主题层人工审核，不生成正式舆情结论。", "",
        "## 已知限制", "",
        "- W25最大单一事件占比43.02%，高于业务参考线40%，可能放大该事件相关主题。",
        "- W27独立视频27个、W28独立视频24个，来源覆盖较窄，可能降低跨UP主泛化能力。",
        "- 技术问题、广告、无关游戏和低信息文本已在训练纳入规则中排除。", "",
        "## 三组实验", "", "| 模型 | 主题数 | 离群数 | 离群率 | 最大主题占比 | 关键词重复率 |", "|---|---:|---:|---:|---:|---:|"]
    for e in experiments:
        lines.append(f"| {e['model_id']} | {e['topic_count']} | {e['outlier_count']} | {float(e['outlier_rate']):.2%} | {float(e['max_topic_share']):.2%} | {float(e['keyword_repetition_rate']):.2%} |")
    lines += ["", f"## 暂定人工审核优先模型：`{best_id}`", "", "- 该选择仅按离群率、主题集中度和关键词重复程度的组合指标排序，不代表正式模型定型。", f"- 跨至少3周出现的暂定稳定主题（ID/关键词）：{'; '.join(stable_labels) if stable_labels else '暂无'}。", f"- 可能由单一事件驱动的暂定主题：{', '.join(event_driven) if event_driven else '当前自动事件集中检测未识别，W25高事件占比仍需人工核对'}。", f"- 文本量较少、需要重点人工核对或后续定向补采的主题：{'; '.join(small_topics) if small_topics else '暂无'}。", "", "## 后续人工审核", "", "- 请优先审核topic_review_pack.csv中的suggested_topic_name、代表文本和高互动文本。", "- 需要人工决定主题保留、合并、拆分及可解释性评分。", "- 当前不建议在主题层审核完成前直接扩大到8周；审核后再评估是否扩大。", "", "本轮未运行SnowNLP，未生成正式topic_chain_id，未更新HTML看板。"]
    BASELINE_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    rec_lines = ["# BERTopic探索性模型选择建议", "", f"当前暂定审核模型：`{best_id}`。", "", "## 建议", "", "1. 先人工审核主题包，不直接将主题名称用于正式周报。", "2. 对W25事件偏高、W27/W28来源较窄造成的主题偏差进行人工标注。", "3. 若主题层审核显示合并/拆分需求，再进行一次参数调整。", "4. 主题审核前暂不扩大到8周；审核完成后再决定。", "", "## 跨周与事件提示", "", f"- 暂定跨周稳定主题（ID/关键词）：{'; '.join(stable_labels) if stable_labels else '暂无'}。", f"- 暂定事件驱动主题：{', '.join(event_driven) if event_driven else '暂无；W25事件占比限制仍需人工关注'}。", f"- 低样本主题：{'; '.join(small_topics) if small_topics else '暂无'}。", f"- 离群审核样本已输出{min(len(outliers), 100)}条。", "", "本报告不运行SnowNLP、不生成topic_chain_id、不更新看板。"]
    RECOMMENDATION.write_text("\n".join(rec_lines) + "\n", encoding="utf-8")


def main() -> None:
    corpus_rows, corpus_fields = build_corpus()
    experiments, review, weekly, outliers = run_models(corpus_rows)
    exp_fields = list(experiments[0].keys()) if experiments else ["model_id", "model_status"]
    review_fields = list(review[0].keys()) if review else ["model_id", "topic_id"]
    weekly_fields = list(weekly[0].keys()) if weekly else ["model_id", "week_id", "topic_id"]
    outlier_fields = list(outliers[0].keys()) if outliers else ["model_id", "text_id", "week_id", "text"]
    write_csv(EXPERIMENTS, experiments, exp_fields)
    write_csv(REVIEW, review, review_fields)
    write_csv(WEEKLY, weekly, weekly_fields)
    write_csv(OUTLIERS, outliers[:100], outlier_fields)
    write_reports(experiments, weekly, review, outliers, corpus_rows)
    write_manifest(corpus_rows, [])
    print(json.dumps({"status": STATUS, "corpus_rows": len(corpus_rows), "experiments": len(experiments), "review_rows": len(review), "weekly_rows": len(weekly), "outlier_rows": min(len(outliers), 100)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
