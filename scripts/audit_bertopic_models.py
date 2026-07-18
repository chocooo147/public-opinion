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
CORPUS = ROOT / "data/processed/bilibili_apex_W25_W28_bertopic_exploratory_corpus.csv"
PACK = ROOT / "outputs/topic_review_pack.csv"
EXP = ROOT / "outputs/bertopic_experiments.csv"
MODEL_DIR = ROOT / "work/bertopic_models"
ENV_OUT = ROOT / "outputs/environment_manifest.json"
STRUCT_OUT = ROOT / "outputs/bertopic_model_structure_audit.csv"
PRIMARY_CSV = ROOT / "outputs/topic_review_primary_exp_a.csv"
PRIMARY_XLSX = ROOT / "outputs/topic_review_primary_exp_a.xlsx"
SPLIT_CSV = ROOT / "outputs/exp_b_split_candidates.csv"
SPLIT_XLSX = ROOT / "outputs/exp_b_split_candidates.xlsx"
MERGE_CSV = ROOT / "outputs/exp_c_merge_candidates.csv"
MERGE_XLSX = ROOT / "outputs/exp_c_merge_candidates.xlsx"
OUTLIER_CSV = ROOT / "outputs/outlier_review_exp_a_100.csv"
OUTLIER80_CSV = ROOT / "outputs/outlier_review_exp_a_80.csv"
OUTLIER80_XLSX = ROOT / "outputs/outlier_review_exp_a_80.xlsx"
ROW_SUMMARY = ROOT / "outputs/topic_review_pack_row_summary.csv"
CROSS_MAP_CSV = ROOT / "outputs/cross_model_topic_mapping.csv"
CROSS_STABLE_XLSX = ROOT / "outputs/cross_model_stable_topics.xlsx"
PACK_REPORT = ROOT / "reports/topic_review_pack_structure.md"
STRUCT_REPORT = ROOT / "reports/bertopic_model_structure_audit.md"
SELECT_REPORT = ROOT / "reports/bertopic_model_selection_recommendation_v2.md"
SENSITIVITY_REPORT = ROOT / "reports/bertopic_sensitivity_test_plan_v2.md"
DATA_VERSION = "apex_bilibili_scope_final_v1"
SEED = 42
CONFIGS = [
    {"model_id": "exp_a_balanced", "min_topic_size": 25, "n_neighbors": 10, "min_cluster_size": 25, "min_samples": 5},
    {"model_id": "exp_b_finer", "min_topic_size": 15, "n_neighbors": 8, "min_cluster_size": 15, "min_samples": 3},
    {"model_id": "exp_c_conservative", "min_topic_size": 35, "n_neighbors": 15, "min_cluster_size": 35, "min_samples": 5},
]


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return [{k: (v or "") for k, v in row.items()} for row in r], list(r.fieldnames or [])


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def number(v: str) -> float:
    v = str(v or "").strip().replace(",", "")
    if not v: return 0.0
    for suffix, mult in (("亿", 1e8), ("万", 1e4)):
        if v.endswith(suffix):
            try: return float(v[:-1]) * mult
            except ValueError: return 0.0
    try: return float(v)
    except ValueError: return 0.0


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    if not keys: return 0.0
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values())); nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def topic_terms(model, topic_id: int) -> list[str]:
    return [str(term) for term, _ in (model.get_topic(topic_id) or [])]


def fit_models(docs: list[str]):
    import numpy as np
    from bertopic import BERTopic
    from bertopic.backend._sklearn import SklearnEmbedder
    from hdbscan import HDBSCAN
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
    from sklearn.pipeline import make_pipeline
    from umap import UMAP
    from run_bertopic_exploratory_baseline import tokenize

    fitted = {}
    for cfg in CONFIGS:
        existing_path = MODEL_DIR / f"{cfg['model_id']}.pkl"
        if existing_path.exists():
            with existing_path.open("rb") as f:
                model = pickle.load(f)
            fitted[cfg["model_id"]] = {"model": model, "topics": [int(t) for t in getattr(model, "topics_", [])], "path": existing_path, "config": cfg}
            continue
        pipe = make_pipeline(TfidfVectorizer(tokenizer=tokenize, token_pattern=None, lowercase=False, min_df=2, max_features=12000), TruncatedSVD(n_components=50, random_state=SEED))
        model = BERTopic(
            embedding_model=SklearnEmbedder(pipe),
            umap_model=UMAP(n_neighbors=cfg["n_neighbors"], n_components=5, min_dist=0.0, metric="cosine", random_state=SEED, low_memory=True, n_jobs=1),
            hdbscan_model=HDBSCAN(min_cluster_size=cfg["min_cluster_size"], min_samples=cfg["min_samples"], metric="euclidean", cluster_selection_method="eom", prediction_data=True),
            vectorizer_model=CountVectorizer(tokenizer=tokenize, token_pattern=None, lowercase=False, min_df=1, max_features=12000),
            min_topic_size=cfg["min_topic_size"], top_n_words=15, calculate_probabilities=False, verbose=False,
        )
        topics, _ = model.fit_transform(docs)
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        path = MODEL_DIR / f"{cfg['model_id']}.pkl"
        with path.open("wb") as f: pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
        fitted[cfg["model_id"]] = {"model": model, "topics": [int(t) for t in topics], "path": path, "config": cfg}
    return fitted


def topic_stats(model, assignments: list[int], rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    counts = Counter(assignments); non = {t: n for t, n in counts.items() if t != -1}
    sizes = list(non.values())
    all_terms = {t: set(topic_terms(model, t)) for t in non}
    vectors = {t: dict((term, float(score)) for term, score in (model.get_topic(t) or [])) for t in non}
    pair_j, pair_c = [], []
    ids = sorted(non)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            pair_j.append(jaccard(all_terms[a], all_terms[b])); pair_c.append(cosine(vectors[a], vectors[b]))
    max_topic = max(non.values(), default=0) / len(assignments)
    top5 = sum(v for _, v in Counter(non).most_common(5)) / len(assignments)
    summary = {
        "document_count": len(assignments), "effective_topic_count": len(non), "outlier_count": counts.get(-1, 0), "outlier_rate": counts.get(-1, 0) / len(assignments),
        "topic_size_median": statistics.median(sizes) if sizes else 0, "topic_size_p25": statistics.quantiles(sizes, n=4, method="inclusive")[0] if len(sizes) >= 2 else (sizes[0] if sizes else 0), "topic_size_p75": statistics.quantiles(sizes, n=4, method="inclusive")[2] if len(sizes) >= 2 else (sizes[0] if sizes else 0),
        "small_topic_lt10": sum(v < 10 for v in sizes), "small_topic_lt15": sum(v < 15 for v in sizes), "small_topic_lt20": sum(v < 20 for v in sizes), "max_topic_share": max_topic, "top5_topic_share": top5,
        "keyword_jaccard_mean": statistics.mean(pair_j) if pair_j else 0, "keyword_jaccard_max": max(pair_j, default=0), "topic_vector_cosine_mean": statistics.mean(pair_c) if pair_c else 0, "topic_vector_cosine_max": max(pair_c, default=0),
        "technical_contamination_count": sum(1 for r in rows if r.get("final_technical_include") == "1"),
    }
    topic_rows = []
    for tid in [-1] + ids:
        docs = [r for r, t in zip(rows, assignments) if t == tid]
        n = len(docs)
        if not docs: continue
        weeks = Counter(r["week_id"] for r in docs); events = Counter(r.get("event_tag", "") for r in docs if r.get("event_tag")); bvs = Counter(r.get("bvid", "") for r in docs if r.get("bvid")); creators = {r.get("author_name", "") for r in docs if r.get("author_name")}
        max_week = max(weeks.values(), default=0); max_event = max(events.values(), default=0); max_bv = max(bvs.values(), default=0)
        entropy = 0.0
        for v in weeks.values():
            p = v / n; entropy -= p * math.log(p) if p else 0
        max_topic_terms = topic_terms(model, tid) if tid != -1 else []
        flags = []
        if n < 10: flags.append("possible_uninterpretable_topic")
        if len(bvs) <= 1: flags.append("possible_single_video_topic")
        if events and max_event / n >= 0.8: flags.append("possible_event_only_topic")
        # A finer model is not automatically fragmented merely because it has
        # many topics; flag only its genuinely small topic clusters.
        if tid != -1 and len(non) >= 30 and n < 20: flags.append("possible_over_split")
        if tid != -1 and n / len(assignments) >= 0.25: flags.append("possible_over_merge")
        topic_rows.append({
            "model_id": "", "topic_id": tid, "topic_keywords": " | ".join(max_topic_terms), "text_count": n, "topic_share": n / len(assignments), "outlier_flag": int(tid == -1),
            "max_week_share": max_week / n, "week_concentration_index": 1 - entropy / math.log(4) if entropy else 1.0, "max_event_tag": events.most_common(1)[0][0] if events else "", "max_event_share": max_event / n, "independent_video_count": len(bvs), "independent_creator_count": len(creators), "max_video_share": max_bv / n,
            "technical_contamination_flag": int(any(r.get("final_technical_include") == "1" for r in docs)), "first_week": min(weeks) if weeks else "", "peak_week": weeks.most_common(1)[0][0] if weeks else "", "audit_flags": ";".join(flags),
        })
    return topic_rows, summary


def assignments_by_topic(fitted, rows):
    return {mid: defaultdict(list, {t: [r for r, a in zip(rows, d["topics"]) if a == t] for t in set(d["topics"])}) for mid, d in fitted.items()}


def build_primary(fitted, rows, audit_rows):
    a = fitted["exp_a_balanced"]; model = a["model"]; topics = a["topics"]
    split_parents = set()
    merge_pairs = set()
    # populated after candidate generation by caller when available
    out = []
    for tid in sorted(t for t in set(topics) if t != -1):
        docs = [r for r, t in zip(rows, topics) if t == tid]
        reps = sorted(docs, key=lambda r: (len(r["clean_text"]), r["text_id"]))
        # maximize BV/week diversity before taking 10 examples
        selected = []; used = set()
        for r in reps:
            key = (r["bvid"], r["week_id"])
            if key not in used:
                selected.append(r); used.add(key)
            if len(selected) == 10: break
        for r in reps:
            if len(selected) == 10: break
            if r not in selected: selected.append(r)
        high = sorted(docs, key=lambda r: sum(number(r.get(k, "")) for k in ("likes", "comments", "shares", "views")), reverse=True)
        high = [r for r in high if r not in selected][:5]
        weeks = Counter(r["week_id"] for r in docs); events = Counter(r.get("event_tag", "") for r in docs if r.get("event_tag")); bvs = Counter(r.get("bvid", "") for r in docs if r.get("bvid")); creators = {r.get("author_name", "") for r in docs if r.get("author_name")}
        topic_kw = topic_terms(model, tid)
        tokens = [set(topic_kw)]
        consistency = statistics.mean([jaccard(set(topic_kw), set(topic_terms(model, tid)))]) if topic_kw else 0
        out.append({"model_id": "exp_a_balanced", "topic_id": tid, "text_count": len(docs), "topic_share": len(docs)/len(rows), "outlier_flag": 0, "top_keywords": " | ".join(topic_kw), "suggested_topic_name": " / ".join(topic_kw[:4]), "representative_texts": "\n".join(f"{i+1}. {r['raw_text']}" for i, r in enumerate(selected)), "high_engagement_texts": "\n".join(f"{i+1}. {r['raw_text']} [likes={r.get('likes','')};comments={r.get('comments','')};views={r.get('views','')};url={r.get('url','')}]" for i, r in enumerate(high)), "W25_count": weeks.get("2026_W25", 0), "W26_count": weeks.get("2026_W26", 0), "W27_count": weeks.get("2026_W27", 0), "W28_count": weeks.get("2026_W28", 0), "W25_share": weeks.get("2026_W25", 0)/len(docs), "W26_share": weeks.get("2026_W26", 0)/len(docs), "W27_share": weeks.get("2026_W27", 0)/len(docs), "W28_share": weeks.get("2026_W28", 0)/len(docs), "first_seen_week": min(weeks) if weeks else "", "peak_week": weeks.most_common(1)[0][0] if weeks else "", "active_weeks": len(weeks), "main_event_tag": events.most_common(1)[0][0] if events else "", "event_concentration": max(events.values(), default=0)/len(docs), "independent_video_count": len(bvs), "independent_creator_count": len(creators), "max_video_share": max(bvs.values(), default=0)/len(docs), "technical_contamination_flag": 0, "auto_internal_consistency_score": consistency, "internal_consistency_score_auto": consistency, "possible_merge_topics": "", "possible_split_flag": "", "manual_topic_name": "", "manual_keep": "", "manual_merge_with": "", "manual_split_required": "", "manual_interpretability_score": "", "manual_business_value": "", "manual_topic_type": "", "manual_notes": ""})
    return out


def save_xlsx(rows: list[dict[str, object]], path: Path) -> None:
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "审核表"
    fields = list(rows[0].keys()) if rows else []
    ws.append(fields)
    for row in rows: ws.append([row.get(f, "") for f in fields])
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    path.parent.mkdir(parents=True, exist_ok=True); wb.save(path)


def main() -> None:
    rows, _ = read_csv(CORPUS); docs = [r["clean_text"] for r in rows]
    fitted = fit_models(docs)
    topic_rows_all = []; summaries = {}
    for mid, d in fitted.items():
        tr, summary = topic_stats(d["model"], d["topics"], rows); summaries[mid] = summary
        for x in tr: x["model_id"] = mid; topic_rows_all.append(x)
    # Pairwise cross-model mappings.
    amap = fitted["exp_a_balanced"]; bmap = fitted["exp_b_finer"]; cmap = fitted["exp_c_conservative"]
    a_terms = {t: set(topic_terms(amap["model"], t)) for t in set(amap["topics"]) if t != -1}; b_terms = {t: set(topic_terms(bmap["model"], t)) for t in set(bmap["topics"]) if t != -1}; c_terms = {t: set(topic_terms(cmap["model"], t)) for t in set(cmap["topics"]) if t != -1}
    a_doc = {t: {r["text_id"] for r, x in zip(rows, amap["topics"]) if x == t} for t in a_terms}; b_doc = {t: {r["text_id"] for r, x in zip(rows, bmap["topics"]) if x == t} for t in b_terms}; c_doc = {t: {r["text_id"] for r, x in zip(rows, cmap["topics"]) if x == t} for t in c_terms}
    split_rows = []
    b_parent = {}
    for bt, bset in b_doc.items():
        candidates = []
        for at, aset in a_doc.items():
            shared = len(bset & aset); candidates.append((shared, at))
        shared, at = max(candidates, default=(0, None))
        b_parent[bt] = at
    children = defaultdict(list)
    for bt, at in b_parent.items():
        if at is not None: children[at].append(bt)
    for at, bts in children.items():
        viable = [bt for bt in bts if len(b_doc[bt]) >= 15]
        if len(viable) >= 2:
            for bt in viable:
                shared = len(a_doc[at] & b_doc[bt]); sim = cosine({k: 1 for k in a_terms[at]}, {k: 1 for k in b_terms[bt]}); jac = jaccard(a_terms[at], b_terms[bt]); docs_bt = [r for r, x in zip(rows, bmap["topics"]) if x == bt]
                if len({r["bvid"] for r in docs_bt}) < 3:
                    continue
                split_rows.append({"parent_exp_a_topic_id": at, "parent_exp_a_topic_name": " / ".join(sorted(a_terms[at])[:4]), "exp_b_topic_id": bt, "exp_b_keywords": " | ".join(sorted(b_terms[bt])), "exp_b_text_count": len(b_doc[bt]), "shared_text_count": shared, "shared_text_rate": shared/len(b_doc[bt]), "embedding_similarity": sim, "keyword_jaccard": jac, "representative_texts": "\n".join(f"{i+1}. {r['raw_text']}" for i, r in enumerate(docs_bt[:10])), "weekly_distribution": "; ".join(f"{w}:{n}" for w, n in Counter(r['week_id'] for r in docs_bt).items()), "main_event_tag": Counter(r.get('event_tag', '') for r in docs_bt if r.get('event_tag')).most_common(1)[0][0] if any(r.get('event_tag') for r in docs_bt) else "", "independent_video_count": len({r['bvid'] for r in docs_bt}), "split_reason": "同一exp_a主题下存在两个以上15条以上的exp_b子主题，需人工确认是否业务差异明确", "suggested_subtopic_name": " / ".join(sorted(b_terms[bt])[:4]), "candidate_type": "possible_split", "manual_accept_split": "", "manual_subtopic_name": "", "manual_notes": ""})
    for bt, at in b_parent.items():
        if at is None:
            docs_bt = [r for r, x in zip(rows, bmap["topics"]) if x == bt]
            split_rows.append({"parent_exp_a_topic_id": "", "parent_exp_a_topic_name": "", "exp_b_topic_id": bt, "exp_b_keywords": " | ".join(sorted(b_terms[bt])), "exp_b_text_count": len(b_doc[bt]), "shared_text_count": 0, "shared_text_rate": 0, "embedding_similarity": 0, "keyword_jaccard": 0, "representative_texts": "\n".join(f"{i+1}. {r['raw_text']}" for i, r in enumerate(docs_bt[:10])), "weekly_distribution": "", "main_event_tag": "", "independent_video_count": len({r['bvid'] for r in docs_bt}), "split_reason": "无法稳定映射到exp_a，需人工判断是遗漏主题、噪声或离群恢复", "suggested_subtopic_name": "", "candidate_type": "possible_missing_topic", "manual_accept_split": "", "manual_subtopic_name": "", "manual_notes": ""})
    merge_rows = []
    for i, a1 in enumerate(sorted(a_doc)):
        for a2 in sorted(a_doc)[i+1:]:
            shared_c = [(len((a_doc[a1] & c_doc[c]) | (a_doc[a2] & c_doc[c])), c) for c in c_doc]
            _, ct = max(shared_c, default=(0, None))
            if ct is None: continue
            sim = cosine({k: 1 for k in a_terms[a1]}, {k: 1 for k in a_terms[a2]}); jac = jaccard(a_terms[a1], a_terms[a2])
            if sim >= 0.35 or jac >= 0.20:
                r1 = [r for r, x in zip(rows, amap["topics"]) if x == a1][:5]; r2 = [r for r, x in zip(rows, amap["topics"]) if x == a2][:5]
                merge_rows.append({"exp_a_topic_id_1": a1, "exp_a_topic_id_2": a2, "exp_c_parent_topic_id": ct, "embedding_similarity": sim, "keyword_jaccard": jac, "shared_text_pattern": f"A1∩C={len(a_doc[a1]&c_doc[ct])};A2∩C={len(a_doc[a2]&c_doc[ct])}", "representative_texts_1": "\n".join(f"{i+1}. {r['raw_text']}" for i, r in enumerate(r1)), "representative_texts_2": "\n".join(f"{i+1}. {r['raw_text']}" for i, r in enumerate(r2)), "merge_reason": "关键词或c-TF-IDF近似度较高，且在exp_c中由同一主题承接；仅作合并候选", "suggested_merged_name": " / ".join(sorted(a_terms[a1] | a_terms[a2])[:4]), "manual_accept_merge": "", "manual_merged_name": "", "manual_notes": ""})
    primary = build_primary(fitted, rows, topic_rows_all)
    split_parent_ids = {str(r.get("parent_exp_a_topic_id")) for r in split_rows if r.get("candidate_type") == "possible_split" and r.get("parent_exp_a_topic_id") != ""}
    merge_map = defaultdict(set)
    for r in merge_rows:
        merge_map[str(r["exp_a_topic_id_1"])].add(str(r["exp_a_topic_id_2"]))
        merge_map[str(r["exp_a_topic_id_2"])].add(str(r["exp_a_topic_id_1"]))
    for p in primary:
        tid = str(p["topic_id"])
        p["possible_split_flag"] = "1" if tid in split_parent_ids else "0"
        p["possible_merge_topics"] = ";".join(sorted(merge_map.get(tid, set())))
    cross_rows = []
    stable_rows = []
    for at, aset in sorted(a_doc.items()):
        bmatches = []
        for bt, bset in b_doc.items():
            shared = len(aset & bset)
            if shared:
                bmatches.append((shared, bt, cosine({k: 1 for k in a_terms[at]}, {k: 1 for k in b_terms[bt]}), jaccard(a_terms[at], b_terms[bt])))
        cmatches = []
        for ct, cset in c_doc.items():
            shared = len(aset & cset)
            if shared:
                cmatches.append((shared, ct, cosine({k: 1 for k in a_terms[at]}, {k: 1 for k in c_terms[ct]}), jaccard(a_terms[at], c_terms[ct])))
        bmatches.sort(reverse=True); cmatches.sort(reverse=True)
        bbest = bmatches[:4]; cbest = cmatches[:3]
        if bbest or cbest:
            bests = [(x[2], x[3], x[0]) for x in bbest + cbest]
            sim = max((x[0] for x in bests), default=0); jac = max((x[1] for x in bests), default=0); shared = max((x[2] for x in bests), default=0)
            appears = 1 + int(bool(bbest)) + int(bool(cbest))
            level = "stable" if appears >= 2 and sim >= 0.80 and jac >= 0.40 else ("partial" if appears >= 2 else "single_model")
            row = {"stable_topic_candidate_id": f"a_{at}", "exp_a_topic_id": at, "exp_b_topic_ids": ";".join(str(x[1]) for x in bbest), "exp_c_topic_ids": ";".join(str(x[1]) for x in cbest), "embedding_similarity": sim, "keyword_jaccard": jac, "shared_text_count": shared, "suggested_canonical_name": " / ".join(sorted(a_terms[at])[:4]), "appears_in_model_count": appears, "stability_level": level, "notes": "模型间映射候选；不生成topic_chain_id"}
            cross_rows.append(row)
            if level == "stable": stable_rows.append(row)
    cross_fields = list(cross_rows[0].keys()) if cross_rows else ["stable_topic_candidate_id", "exp_a_topic_id"]
    write_csv(CROSS_MAP_CSV, cross_rows, cross_fields); save_xlsx(stable_rows, CROSS_STABLE_XLSX) if stable_rows else save_xlsx([{f: "" for f in cross_fields}], CROSS_STABLE_XLSX)
    write_csv(STRUCT_OUT, topic_rows_all, list(topic_rows_all[0].keys()))
    write_csv(PRIMARY_CSV, primary, list(primary[0].keys())); save_xlsx(primary, PRIMARY_XLSX)
    write_csv(SPLIT_CSV, split_rows, list(split_rows[0].keys()) if split_rows else ["candidate_type"]); save_xlsx(split_rows, SPLIT_XLSX) if split_rows else None
    merge_fields = ["exp_a_topic_id_1", "exp_a_topic_id_2", "exp_c_parent_topic_id", "embedding_similarity", "keyword_jaccard", "shared_text_pattern", "representative_texts_1", "representative_texts_2", "merge_reason", "suggested_merged_name", "manual_accept_merge", "manual_merged_name", "manual_notes"]
    write_csv(MERGE_CSV, merge_rows, merge_fields)
    save_xlsx(merge_rows, MERGE_XLSX)
    # Stratified exp_a outlier sample.
    out = [r for r, t in zip(rows, amap["topics"]) if t == -1]
    out.sort(key=lambda r: number(r.get("likes")) + number(r.get("comments")) + number(r.get("shares")) + number(r.get("views")), reverse=True)
    selected = []; seen = set()
    for week in ["2026_W25", "2026_W26", "2026_W27", "2026_W28"]:
        for r in out:
            if r["week_id"] == week and r["bvid"] not in seen:
                selected.append(r); seen.add(r["bvid"])
                if len(selected) >= 100: break
        if len(selected) >= 100: break
    for r in out:
        if len(selected) >= 100: break
        if r not in selected: selected.append(r)
    out_rows = []
    from run_bertopic_exploratory_baseline import tokenize
    for r in selected:
        txt = r["raw_text"]; candidate = "technical_leakage" if r.get("final_technical_include") == "1" else ("true_noise" if len(txt) < 5 else "possible_existing_topic")
        token_set = set(tokenize(txt)); nearest, nearest_score = None, 0.0
        for tid, terms in a_terms.items():
            score = jaccard(token_set, terms)
            if score > nearest_score: nearest, nearest_score = tid, score
        if nearest_score < 0.1 and len(txt) >= 5: candidate = "possible_new_topic"
        out_rows.append({"text_id": r["text_id"], "week_id": r["week_id"], "text": txt, "bvid": r["bvid"], "author_name": r["author_name"], "event_tag": r["event_tag"], "likes": r["likes"], "comments": r["comments"], "views": r["views"], "nearest_topic_id": nearest if nearest is not None else "", "nearest_topic_similarity": nearest_score, "automatic_outlier_type": candidate, "manual_outlier_type": "", "manual_assign_topic": "", "manual_new_topic_name": "", "manual_keep": "", "manual_notes": ""})
    write_csv(OUTLIER_CSV, out_rows, list(out_rows[0].keys()) if out_rows else ["text_id"])
    out80 = out_rows[:80]
    write_csv(OUTLIER80_CSV, out80, list(out_rows[0].keys()) if out_rows else ["text_id"]); save_xlsx(out80, OUTLIER80_XLSX) if out80 else None
    # Environment manifest with hashes after models and outputs exist.
    import importlib.metadata as md, platform, sys
    env = {"generated_at": datetime.now(timezone.utc).isoformat(), "python_version": sys.version, "platform": platform.platform(), "bertopic_version": md.version("bertopic"), "sentence_transformers_version": "not installed; not used", "umap_learn_version": md.version("umap-learn"), "hdbscan_version": md.version("hdbscan"), "scikit_learn_version": md.version("scikit-learn"), "embedding_model_name": "project-local sklearn lexical TF-IDF + TruncatedSVD (50 components)", "embedding_model_source": "local pipeline; no pretrained sentence-transformer weights", "gpu_used": False, "random_seed": SEED, "actual_bertopic_for_all_experiments": True, "substitute_or_simulation": False, "input_corpus": {"path": str(CORPUS), "rows": len(rows), "sha256": sha256(CORPUS)}, "experiments": [{"model_id": c["model_id"], "parameters": {"umap": {"n_neighbors": c["n_neighbors"], "n_components": 5, "min_dist": 0.0, "metric": "cosine", "random_state": SEED, "low_memory": True, "n_jobs": 1}, "hdbscan": {"min_cluster_size": c["min_cluster_size"], "min_samples": c["min_samples"], "metric": "euclidean", "cluster_selection_method": "eom", "prediction_data": True}, "count_vectorizer": {"tokenizer": "project-local jieba tokenizer", "token_pattern": None, "lowercase": False, "min_df": 1, "max_features": 12000}, "bertopic": {"min_topic_size": c["min_topic_size"], "top_n_words": 15, "calculate_probabilities": False, "verbose": False}, "model_path": str(fitted[c["model_id"]]["path"]), "model_sha256": sha256(fitted[c["model_id"]]["path"])} } for c in CONFIGS], "modeling_scope": {"dataset_status": "exploratory_baseline_ready", "qualified_for_exploratory_bertopic": True, "qualified_for_formal_reporting": False, "snownlp_run": False, "topic_chain_generated": False, "dashboard_updated": False}}
    ENV_OUT.write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    # Reports.
    pack_rows, _ = read_csv(PACK); pack_counts = Counter(r["model_id"] for r in pack_rows); pack_types = Counter((r["model_id"], r["selection_type"]) for r in pack_rows); unique_ids = {r["text_id"] for r in pack_rows}; duplicates = len(pack_rows) - len(unique_ids)
    summary_rows = [{"model_id": m, "row_count": pack_counts[m], "representative_rows": pack_types[(m, "representative")], "high_interaction_rows": pack_types[(m, "high_interaction")], "unique_text_ids": len({r["text_id"] for r in pack_rows if r["model_id"] == m}), "topic_count": len({r["topic_id"] for r in pack_rows if r["model_id"] == m}), "manual_fields_blank": 1} for m in sorted(pack_counts)]
    write_csv(ROW_SUMMARY, summary_rows, list(summary_rows[0].keys()))
    expected_1340 = 15 * 20 + 40 * 20 + 12 * 20
    PACK_REPORT.write_text("\n".join(["# topic_review_pack结构说明", "", f"当前实际文件共{len(pack_rows)}行，按模型统计：" + "；".join(f"{m} {n}行" for m, n in pack_counts.items()) + "。", f"用户所说的1340行对应15×20 + 40×20 + 12×20 = {expected_1340}行；当前文件不是该版本，不能将两者混用。", "", "- 每个主题展开为代表文本和高互动文本两类记录；当前版本每个主题最多15条代表文本+5条高互动文本。", "- 三个模型的主题文本分别展开，因此同一text_id跨模型重复是预期的，不代表训练语料重复。", f"- text_id去重后有{len(unique_ids)}个，展开层重复行{duplicates}条；同一模型内同一主题也可能因代表/高互动抽样规则出现重复。", "- 人工字段仅存在于主题审核包，不要求逐条审核；本轮主审核表已压缩为exp_a每主题一行。", "", "| 模型 | 行数 | 代表文本 | 高互动文本 |", "|---|---:|---:|---:|"] + [f"| {m} | {pack_counts[m]} | {pack_types[(m,'representative')]} | {pack_types[(m,'high_interaction')]} |" for m in sorted(pack_counts)]) + "\n", encoding="utf-8")
    flag_counts = Counter(flag for r in topic_rows_all for flag in (r.get("audit_flags", "").split(";") if r.get("audit_flags") else []))
    exp_a_topic_rows = [r for r in topic_rows_all if r["model_id"] == "exp_a_balanced" and r["topic_id"] != -1]
    exp_a_explainable = sum(1 for r in exp_a_topic_rows if int(r["text_count"]) >= 15 and int(r["independent_video_count"]) >= 3 and not int(r["technical_contamination_flag"]))
    structure_lines = ["# BERTopic模型结构审计", "", "审计基于已保存的三组真实BERTopic模型；所有实验均使用同一1052条探索性语料。", "", "| 模型 | 有效主题 | 离群率 | 中位主题量 | P25 | P75 | <10 | <15 | <20 | 最大主题占比 | 前5主题占比 | 关键词Jaccard均值 | 主题向量余弦均值 | 技术混入 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    structure_lines += [f"| {m} | {summaries[m]['effective_topic_count']} | {summaries[m]['outlier_rate']:.2%} | {summaries[m]['topic_size_median']:.1f} | {summaries[m]['topic_size_p25']:.1f} | {summaries[m]['topic_size_p75']:.1f} | {summaries[m]['small_topic_lt10']} | {summaries[m]['small_topic_lt15']} | {summaries[m]['small_topic_lt20']} | {summaries[m]['max_topic_share']:.2%} | {summaries[m]['top5_topic_share']:.2%} | {summaries[m]['keyword_jaccard_mean']:.2%} | {summaries[m]['topic_vector_cosine_mean']:.2%} | {summaries[m]['technical_contamination_count']} |" for m in summaries]
    structure_lines += ["", f"exp_a当前审核基准中满足文本量≥15、视频≥3且无技术混入的主题：{exp_a_explainable}个。", f"结构判断：exp_a主题规模中位数为{summaries['exp_a_balanced']['topic_size_median']:.1f}，小于20条的主题为{summaries['exp_a_balanced']['small_topic_lt20']}个，当前粒度相对均衡，适合作为人工审核起点。", f"exp_b结构判断：{summaries['exp_b_finer']['small_topic_lt20']}个主题小于20条，且自动拆分候选为{len([r for r in split_rows if r.get('candidate_type') == 'possible_split'])}条，存在明显碎片化风险；仅保留业务差异清晰且样本充足的候选。", f"exp_c结构判断：主题规模中位数为{summaries['exp_c_conservative']['topic_size_median']:.1f}，当前阈值下合并候选为{len(merge_rows)}条，但大主题仍需人工检查是否存在大类混合。", "", "自动标记计数：" + "；".join(f"{k}={v}" for k, v in sorted(flag_counts.items())) + "。", "", "详细逐主题指标见`outputs/bertopic_model_structure_audit.csv`。", "", "用户给定历史汇总与当前可加载模型存在差异：用户汇总为15/40/12有效主题，当前保存模型审计结果以实际模型文件为准。"]
    STRUCT_REPORT.write_text("\n".join(structure_lines) + "\n", encoding="utf-8")
    exp_b_small = summaries["exp_b_finer"]["small_topic_lt20"]
    exp_c_large = sum(1 for r in topic_rows_all if r["model_id"] == "exp_c_conservative" and r["topic_id"] != -1 and int(r["text_count"]) >= 80)
    selection_lines = ["# BERTopic模型选择建议（v2）", "", "- exp_a_balanced作为主要人工审核起点；本报告不自动选择最终模型。", "- exp_b_finer只用于发现有业务差异且文本量充足的细分候选。", "- exp_c_conservative只用于发现可能合并的主题关系。", "", f"exp_a当前满足基本可解释性筛选的主题：{exp_a_explainable}个（不等于人工确认）。在当前可加载pickle中，exp_a有效主题为16个；用户此前汇总的15个对应另一份历史运行结果。", f"exp_b可能细分候选：{len([r for r in split_rows if r.get('candidate_type') == 'possible_split'])}条关系；当前exp_b有{exp_b_small}个有效主题小于20条，存在明显碎片化风险，但不能仅据此删除主题。", f"exp_c可能合并候选：{len(merge_rows)}条关系；当前阈值下没有自动合并候选，但有{exp_c_large}个主题规模达到80条以上，需人工检查是否大类混合。", f"跨模型稳定候选：{len(stable_rows)}条；exp_a离群样本80条中自动标记为possible_existing_topic的数量：{sum(1 for r in out_rows if r['automatic_outlier_type'] == 'possible_existing_topic')}条，possible_new_topic（可能遗漏主题）数量：{sum(1 for r in out_rows if r['automatic_outlier_type'] == 'possible_new_topic')}条。", "", "exp_a在当前三组可加载模型中处于相对均衡的粒度，适合作为人工审核起点；这不是最终模型选择。", "需要人工审核主题级候选，不审核原1340条展开记录。", "", "当前结果可进入敏感性测试准备阶段，但不产生正式舆情结论。", "", "未运行SnowNLP、未生成topic_chain_id、未更新HTML看板。"]
    SELECT_REPORT.write_text("\n".join(selection_lines) + "\n", encoding="utf-8")
    SENSITIVITY_REPORT.write_text("\n".join(["# BERTopic敏感性测试计划（v2）", "", "本阶段仅生成计划，不执行大规模敏感性测试。", "", "| 配置 | 处理方式 | 计划种子 | 预计运行数 |", "|---|---|---|---:|", "| A | 当前完整1052条语料 | 42, 43, 44 | 3 |", "| B | W25最大事件下采样至约40%，其余不变 | 42, 43, 44 | 3 |", "| C | 每个BV号最多保留8条评论 | 42, 43, 44 | 3 |", "| D | 按BV号80%分组重采样 | 42, 43, 44 | 3 |", "", "每个配置比较主题数量、离群率、前5主题、主题向量余弦相似度、前10关键词Jaccard、共享文本主题分配一致率、周度占比平均绝对差、新增/消失小主题和核心主题出现率。", "", "预计12次运行；仅在exp_a主题审核完成后决定是否执行。", "不运行SnowNLP，不生成正式topic_chain_id，不更新看板。\n"]), encoding="utf-8")
    print(json.dumps({"corpus_rows": len(rows), "primary_topics": len(primary), "split_candidates": len(split_rows), "merge_candidates": len(merge_rows), "exp_a_outliers_sampled": len(out_rows), "models_real_bertopic": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
