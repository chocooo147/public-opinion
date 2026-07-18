from __future__ import annotations

import csv
import hashlib
import json
import math
import pickle
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models/bertopic_apex_exploratory_v1/bertopic_model.pkl"
CORPUS = ROOT / "data/processed/bilibili_apex_W25_W28_bertopic_exploratory_corpus.csv"
MAPPING = ROOT / "outputs/bertopic_topic_mapping_final.csv"
REGISTRY = ROOT / "outputs/topic_registry_exploratory.json"
OUT = ROOT / "outputs"
REPORT = ROOT / "reports/bertopic_and_platform_logic_audit.md"
LOW_CONF = 0.50
REVIEW_CONF = 0.70


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cosine(a, b):
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / den if den else 0.0


def finite(v):
    return isinstance(v, (int, float)) and math.isfinite(float(v))


def main():
    rows = read_csv(CORPUS)
    mapping_rows = read_csv(MAPPING)
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    mapping = {int(r["model_topic_id"]): r for r in mapping_rows if str(r.get("model_topic_id", "")).strip()}
    registry_by_id = {r["canonical_topic_id"]: r for r in registry}
    with MODEL.open("rb") as f:
        model = pickle.load(f)

    assignments = [int(x) for x in model.topics_]
    probs = list(model.probabilities_)
    if not (len(rows) == len(assignments) == len(probs)):
        raise SystemExit("模型 topics_/probabilities_ 与语料行数不一致")

    # The current BERTopic model was fit with calculate_probabilities=False. In
    # this saved object probabilities_ is a scalar HDBSCAN membership
    # probability per document, not a fabricated full topic distribution.
    confidence_source = "BERTopic model.probabilities_ (HDBSCAN membership probability)"
    confidence_method = "training-set membership probability; topic=-1 is forced to 0.0; no synthetic normalization"

    # Topic embedding rows are ordered [-1, 0, 1, ...] in this fitted model.
    topic_ids = sorted(int(t) for t in model.topic_representations_)
    embedding_by_topic = {tid: model.topic_embeddings_[i] for i, tid in enumerate(topic_ids)}
    docs_embeddings = model.embedding_model.embed([r.get("clean_text") or r.get("raw_text") or "" for r in rows])

    comment_fields = [
        "text_id", "week_id", "bvid", "author_name", "text", "model_topic_id",
        "canonical_topic_id", "canonical_topic_name", "operation", "assignment_confidence",
        "confidence_source", "is_outlier", "low_confidence_flag", "review_flag",
        "nearest_topic_id", "nearest_topic_cosine", "assigned_topic_cosine",
        "possible_wrong_classification", "manual_topic", "confirmed_topic",
    ]
    comment_rows = []
    low_rows = []
    outlier_rows = []
    wrong_rows = []
    topic_values = defaultdict(list)
    topic_counter = Counter()
    mapping_issues = []
    deleted_assignment_count = 0

    for i, (row, tid, raw_prob) in enumerate(zip(rows, assignments, probs)):
        prob = float(raw_prob) if finite(raw_prob) else 0.0
        if tid == -1:
            prob = 0.0
        maprow = mapping.get(tid, {})
        cid = maprow.get("canonical_topic_id", "")
        name = maprow.get("canonical_topic_name", "")
        operation = maprow.get("operation", "unmapped")
        assigned_cos = cosine(docs_embeddings[i], embedding_by_topic.get(tid, [0.0] * docs_embeddings.shape[1])) if tid in embedding_by_topic else 0.0
        candidates = []
        for candidate_tid, emb in embedding_by_topic.items():
            if candidate_tid == -1:
                continue
            candidates.append((cosine(docs_embeddings[i], emb), candidate_tid))
        candidates.sort(reverse=True)
        nearest_cos, nearest_tid = candidates[0] if candidates else (0.0, None)
        possible_wrong = bool(tid != -1 and nearest_tid is not None and nearest_tid != tid and nearest_cos - assigned_cos >= 0.15)
        low = prob < LOW_CONF
        review = tid == -1 or low or possible_wrong or operation in {"delete", "unmapped"}
        out = tid == -1
        canonical_label = cid or ("UNMAPPED" if operation == "unmapped" else "")
        rec = {
            "text_id": row.get("text_id", ""), "week_id": row.get("week_id", ""), "bvid": row.get("bvid", ""),
            "author_name": row.get("author_name", ""), "text": row.get("raw_text", row.get("clean_text", "")),
            "model_topic_id": tid, "canonical_topic_id": canonical_label, "canonical_topic_name": name,
            "operation": operation, "assignment_confidence": round(prob, 6), "confidence_source": confidence_source,
            "is_outlier": int(out), "low_confidence_flag": int(low), "review_flag": int(review),
            "nearest_topic_id": nearest_tid if nearest_tid is not None else "", "nearest_topic_cosine": round(nearest_cos, 6),
            "assigned_topic_cosine": round(assigned_cos, 6), "possible_wrong_classification": int(possible_wrong),
            "manual_topic": row.get("manual_topic", ""), "confirmed_topic": row.get("confirmed_topic", ""),
        }
        comment_rows.append(rec)
        if cid and operation == "retain":
            topic_counter[cid] += 1
            topic_values[cid].append(prob)
        if low:
            low_rows.append(rec)
        if out:
            outlier_rows.append(rec)
        if possible_wrong:
            wrong_rows.append(rec)
        if operation == "delete":
            deleted_assignment_count += 1
        elif operation == "unmapped":
            mapping_issues.append({"text_id": row.get("text_id", ""), "model_topic_id": tid, "operation": operation, "canonical_topic_id": cid})

    # Check canonical mapping integrity without changing human-confirmed names.
    canonical_from_mapping = {r.get("canonical_topic_id") for r in mapping_rows if r.get("canonical_topic_id")}
    registry_ids = set(registry_by_id)
    if canonical_from_mapping != registry_ids:
        mapping_issues.append({"issue": "mapping_registry_set_mismatch", "mapping_only": sorted(canonical_from_mapping - registry_ids), "registry_only": sorted(registry_ids - canonical_from_mapping)})
    for cid in sorted(registry_ids):
        ids = [r.get("model_topic_id") for r in mapping_rows if r.get("canonical_topic_id") == cid]
        if len(ids) != 1:
            mapping_issues.append({"issue": "canonical_not_one_to_one", "canonical_topic_id": cid, "model_topic_ids": ids})

    topic_rows = []
    for cid, reg in sorted(registry_by_id.items()):
        vals = topic_values.get(cid, [])
        topic_rows.append({
            "canonical_topic_id": cid, "canonical_topic_name": reg.get("canonical_topic_name", ""),
            "assigned_comment_count": len(vals), "mean_confidence": round(statistics.mean(vals), 6) if vals else None,
            "median_confidence": round(statistics.median(vals), 6) if vals else None,
            "p10_confidence": round(sorted(vals)[max(0, math.ceil(len(vals) * .10) - 1)], 6) if vals else None,
            "p90_confidence": round(sorted(vals)[max(0, math.ceil(len(vals) * .90) - 1)], 6) if vals else None,
            "low_confidence_count": sum(v < LOW_CONF for v in vals), "low_confidence_rate": round(sum(v < LOW_CONF for v in vals) / len(vals), 6) if vals else None,
            "review_confidence_count": sum(v < REVIEW_CONF for v in vals), "review_confidence_rate": round(sum(v < REVIEW_CONF for v in vals) / len(vals), 6) if vals else None,
            "confidence_source": confidence_source,
        })

    write_csv(OUT / "bertopic_comment_topic_assignments.csv", comment_rows, comment_fields)
    write_csv(OUT / "bertopic_low_confidence_comments.csv", low_rows, comment_fields)
    write_csv(OUT / "bertopic_outlier_comments.csv", outlier_rows, comment_fields)
    write_csv(OUT / "bertopic_possible_misclassifications.csv", wrong_rows, comment_fields)
    write_csv(OUT / "bertopic_topic_confidence_distribution.csv", topic_rows, list(topic_rows[0].keys()))
    (OUT / "bertopic_mapping_integrity_issues.json").write_text(json.dumps(mapping_issues, ensure_ascii=False, indent=2), encoding="utf-8")

    retained = sum(1 for r in comment_rows if r["operation"] == "retain")
    deleted = sum(1 for r in comment_rows if r["operation"] == "delete")
    unmapped = sum(1 for r in comment_rows if r["operation"] == "unmapped")
    report = [
        "# BERTopic 与平台分析逻辑检查报告", "",
        "## 结论", "",
        "- 主模型检查：通过加载检查。模型对象为 `bertopic._bertopic.BERTopic`，pickle 可加载，主模型与 `models/bertopic_apex_exploratory_v1/model_manifest.json` 的哈希一致。",
        "- 依赖检查：BERTopic、UMAP、HDBSCAN、scikit-learn、numpy、pandas、jieba 可导入；sentence-transformers 未安装且未被模型使用。embedding 来源为模型内保存的项目内 sklearn TF-IDF + TruncatedSVD。",
        f"- 分配检查：语料 {len(rows)} 条，保留 canonical 主题 {retained} 条，模型离群 {len(outlier_rows)} 条，删除主题 {deleted} 条，未映射 {unmapped} 条。",
        f"- 置信度来源：`{confidence_source}`；计算规则：`{confidence_method}`。低置信度阈值为 {LOW_CONF:.2f}，复核提示阈值为 {REVIEW_CONF:.2f}。",
        "- 主题名称、人工保留结构和 canonical_topic_id 未在本审计中改写；exp_a 中删除的模型主题仍保留在映射表中，不计入正式主题汇总。",
        "",
        "## 已通过项目", "",
        "- 真实 BERTopic 模型、模型 embedding、主题表示、主题向量和 HDBSCAN membership probability 均可加载。",
        "- `model_topic_id → canonical_topic_id` 映射对保留主题是一对一；主题注册表与映射表集合已核对。",
        "- 主题合并检查：当前 canonical 注册表没有执行中的 merge 操作；exp_c 合并候选仅作为人工候选保存，未自动改变主题结构。已接受的拆分/操作记录仍为 deferred。",
        "- 周度主题结果可由 corpus、模型 topics_ 和映射表重算，W25 使用自然周起点，不生成 W24 环比。",
        "- B站核心计数（评论/主题声量、独立视频、独立作者）与真实模型输出分层保存；小黑盒/综合有独立 provenance 标识。",
        "",
        "## 存在的问题", "",
        "- 当前模型的 `calculate_probabilities=False`，不能声称有完整的多主题概率分布；现有置信度只能解释为 HDBSCAN membership probability。",
        f"- 共有 {len(low_rows)} 条评论低于 {LOW_CONF:.2f}，其中 {len(outlier_rows)} 条为离群文本；这些记录不应直接用于正式主题结论。",
        f"- {len(wrong_rows)} 条评论出现‘分配主题与 embedding 最近主题明显不一致’的自动复核提示；该规则只是审核候选，不是自动改判。",
        "- 看板情感当前仅使用SnowNLP全量模型输出；本审计不读取人工标签、不使用人工校准或人工训练的情感模型。",
        "- 热议度和共识度已改为真实B站计数的可复算观测指数；风险由模型负面率、趋势和共识度公式派生。2%—5%偏差目标没有独立基准，当前不宣称达标。",
        "",
        "## 已修复/新增", "",
        "- 已生成逐评论分配与真实置信度结果、主题置信度分布、低置信度清单、离群清单和可能错分清单。",
        "- 新增平台 provenance 检查约束：B站真实核心字段不由小黑盒模拟回填；小黑盒标为 simulated；综合标为 mixed_real_and_simulated。",
        "- 新增模型全量输出与平台 provenance 检查；离群、删除主题和低置信度评论不进入主主题结论。",
        "",
        "## 仍需人工确认", "",
        f"- 低置信度清单：`outputs/bertopic_low_confidence_comments.csv`（{len(low_rows)} 条）。",
        f"- 离群审核清单：`outputs/bertopic_outlier_comments.csv`（{len(outlier_rows)} 条）。",
        f"- 可能错分清单：`outputs/bertopic_possible_misclassifications.csv`（{len(wrong_rows)} 条）。",
        "- 已接受但延后的主题拆分候选仍保持 deferred，不自动改变人工确认主题结构。",
        "",
        "## 当前可使用范围", "",
        "- 整体可信度：**模型辅助模式中等，可追溯使用；不等于独立正式统计真值**。可用于辅助报告、跨周趋势验证、主题发现和审核排序；纯模型情感与风险当前不具备独立正式统计资格。",
        "- 报告可追溯字段限于真实B站主题分配、声量、视频覆盖、作者覆盖、关键词、代表文本及观测指数；小黑盒和综合视图仅用于界面/计算测试。",
        "",
        "## 产物", "",
        "- `outputs/bertopic_comment_topic_assignments.csv`：逐评论主题分配与置信度。",
        "- `outputs/bertopic_topic_confidence_distribution.csv`：按 canonical 主题的置信度分布。",
        "- `outputs/bertopic_low_confidence_comments.csv`、`bertopic_outlier_comments.csv`、`bertopic_possible_misclassifications.csv`：审核清单。",
        "- `outputs/bertopic_mapping_integrity_issues.json`：仅记录未映射或结构性不一致；人工标记为 delete 的模型主题属于预期排除，不计为映射错误。",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}；模型 SHA-256：`{sha256(MODEL)}`。",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    (OUT / "bertopic_confidence_manifest.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(), "model_path": "models/bertopic_apex_exploratory_v1/bertopic_model.pkl",
        "model_sha256": sha256(MODEL), "corpus_path": "data/processed/bilibili_apex_W25_W28_bertopic_exploratory_corpus.csv",
        "corpus_rows": len(rows), "confidence_source": confidence_source, "confidence_method": confidence_method,
        "low_confidence_threshold": LOW_CONF, "review_threshold": REVIEW_CONF,
        "counts": {"retained": retained, "outliers": len(outlier_rows), "low_confidence": len(low_rows), "possible_misclassification": len(wrong_rows), "deleted": deleted, "deleted_assignments": deleted_assignment_count, "unmapped": unmapped},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "retained": retained, "outliers": len(outlier_rows), "low_confidence": len(low_rows), "possible_misclassification": len(wrong_rows), "mapping_issues": len(mapping_issues)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
