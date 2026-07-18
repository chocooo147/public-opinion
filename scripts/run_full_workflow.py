from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pickle
import subprocess
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
OUT = ROOT / "outputs"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_stage(name: str, cmd: list[str], log_lines: list[str]):
    shown = []
    for item in cmd:
        if item == sys.executable:
            shown.append("<python>")
            continue
        try:
            shown.append(str(Path(item).resolve().relative_to(ROOT)))
        except (ValueError, OSError):
            shown.append(item)
    log_lines.append(f"[{datetime.now(timezone.utc).isoformat()}] START {name}: {' '.join(shown)}")
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    log_lines.extend(line.replace(str(ROOT), ".") for line in proc.stdout.splitlines())
    if proc.stderr:
        log_lines.extend(f"STDERR {x.replace(str(ROOT), '.')}" for x in proc.stderr.splitlines())
    log_lines.append(f"[{datetime.now(timezone.utc).isoformat()}] END {name}: rc={proc.returncode}")
    if proc.returncode:
        raise RuntimeError(f"阶段 {name} 失败，退出码 {proc.returncode}")


def predict_input(input_path: Path, output_path: Path, log_lines: list[str]):
    """Predict an optional new-week cleaned CSV with the frozen model.

    This never appends to the frozen corpus or overwrites raw data. The output
    is a review candidate file; a human must decide whether it can enter the
    next frozen corpus/version.
    """
    model_path = ROOT / "models/bertopic_apex_exploratory_v1/bertopic_model.pkl"
    mapping_path = ROOT / "outputs/bertopic_topic_mapping_final.csv"
    with model_path.open("rb") as f:
        model = pickle.load(f)
    with input_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    with mapping_path.open(encoding="utf-8-sig", newline="") as f:
        mapping = {int(r["model_topic_id"]): r for r in csv.DictReader(f) if str(r.get("model_topic_id", "")).strip()}
    texts = [r.get("clean_text") or r.get("text") or "" for r in rows]
    topics, probabilities = model.transform(texts)
    fields = ["text_id", "week_id", "text", "model_topic_id", "canonical_topic_id", "canonical_topic_name", "assignment_confidence", "confidence_source", "is_outlier", "low_confidence_flag", "new_topic_candidate", "scope_status"]
    result = []
    for row, tid, prob in zip(rows, topics, probabilities):
        tid = int(tid); confidence = 0.0 if tid == -1 else float(prob or 0.0); m = mapping.get(tid, {})
        week_id = row.get("week_id", "")
        if not week_id and row.get("week_start"):
            week_start = date.fromisoformat(row["week_start"])
            iso_year, iso_week, _ = week_start.isocalendar()
            week_id = f"{iso_year}_W{iso_week:02d}"
        result.append({"text_id": row.get("text_id", ""), "week_id": week_id, "text": row.get("text", row.get("clean_text", "")), "model_topic_id": tid, "canonical_topic_id": m.get("canonical_topic_id", ""), "canonical_topic_name": m.get("canonical_topic_name", ""), "assignment_confidence": round(confidence, 6), "confidence_source": "BERTopic model.transform probabilities_ (HDBSCAN membership probability)", "is_outlier": int(tid == -1), "low_confidence_flag": int(confidence < 0.5), "new_topic_candidate": int(tid == -1 or not m.get("canonical_topic_id")), "scope_status": row.get("final_analysis_scope") or row.get("analysis_scope") or "needs_scope_review"})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(result)
    log_lines.append(f"new_week_prediction_rows={len(result)}; raw_input_sha256={sha256(input_path)}")


def validate_outputs():
    dashboard_path = ROOT / "work/public-opinion/dashboard_data_apex_W25_W28.json"
    if not dashboard_path.exists():
        dashboard_path = ROOT / "dashboard_data_apex_W25_W28.json"
    data = json.loads(dashboard_path.read_text(encoding="utf-8"))
    assert [w["week_id"] for w in data["weeks"]] == ["2026-W25", "2026-W26", "2026-W27", "2026-W28"]
    assert data["meta"]["default_week_id"] == "2026-W28"
    assert data["meta"]["week_boundary"]["latest_complete_week"] == "2026_W28"
    assert data["meta"]["week_boundary"]["current_open_week"] == "2026_W29"
    assert data["meta"]["qualified_for_formal_auxiliary_reporting"] is False
    assert data["meta"]["sentiment_status"] == "model_only_full_coverage"
    assert data["meta"]["sentiment_model"] == "SnowNLP_model_only"
    assert data["meta"]["risk_status"] == "model_only_derived"
    heybox_real_sample = data["meta"].get("platform_status", {}).get("小黑盒") == "real_public_search_sample"
    assert data["weeks"][0]["kpis"]["new_topic_status"] == "baseline_no_prior_week"
    for idx, week in enumerate(data["weeks"]):
        assert week["kpis"]["total_volume"] == sum(t["platform_metrics"]["B站"]["count"] for t in week["topics"])
        assert week["kpis"]["new_topic_count"] == len(week["kpis"]["new_topic_ids"])
        assert set(week["kpis"]["new_topic_ids"]).issubset({t["id"] for t in week["topics"]})
        for topic in week["topics"]:
            b = topic["platform_metrics"]["B站"]; h = topic["platform_metrics"]["小黑盒"]; c = topic["combined_metrics"]
            assert b["data_type"] == "real" and not b["simulated"] and b["metrics_source"] == "bilibili_real_model_output"
            if heybox_real_sample:
                assert h["data_type"] == "real_sample" and not h["simulated"] and h["metrics_source"] == "heybox_public_search_visible_sample"
                assert c["metrics_source"] == "mixed_real_and_real_sample_incomparable_units" and not c["simulated"] and c["sample_limited"]
            else:
                assert h["data_type"] == "simulated" and h["simulated"] and h["metrics_source"] == "heybox_simulated_for_ui_test"
                assert c["metrics_source"] == "mixed_real_and_simulated" and c["simulated"]
            assert c["count"] == b["count"] + h["count"]
            assert b["sentiment_model"] == "SnowNLP"
            assert b["sentiment_status"] == "model_only_full_coverage"
            assert b["risk_status"] == "model_only_derived"
            assert "human_label_count" not in topic
        if idx == 0:
            assert all(topic["wow"] is None for topic in week["topics"]), "W25 must not contain a fabricated W24 comparison"
    return {"weeks": len(data["weeks"]), "topics_per_week": [len(w["topics"]) for w in data["weeks"]], "dashboard_json_sha256": sha256(dashboard_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="APEX 一键可复现流程：清洗/质检、冻结模型预测、审计、看板与一致性检查")
    parser.add_argument("--input", type=Path, help="可选新一周原始CSV；只读并输出候选预测，不覆盖冻结语料")
    parser.add_argument("--skip-clean", action="store_true", help="跳过可选原始CSV清洗")
    args = parser.parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True); OUT.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_lines = [f"run_id={run_id}", "project_root=.", "raw_data_policy=append-only; original model/data/html are not overwritten"]
    try:
        run_stage("environment", [sys.executable, "scripts/check_environment.py"], log_lines)
        raw_dir = ROOT / "data/raw"
        if raw_dir.exists() and any(raw_dir.rglob("*.csv")):
            run_stage("week_boundary_audit", [sys.executable, "scripts/audit_week_boundaries.py"], log_lines)
        else:
            log_lines.append("week_boundary_audit=skipped; no local raw CSV supplied, packaged week_boundary_audit.json retained")
        run_stage("bertopic_environment_verification", [sys.executable, "scripts/verify_bertopic_environment.py"], log_lines)
        if args.input and not args.skip_clean:
            cleaned = OUT / f"new_week_cleaned_{run_id}.csv"
            run_stage("clean_and_quality", [sys.executable, "scripts/run_pipeline.py", "--input", str(args.input), "--output", str(cleaned)], log_lines)
            # run_pipeline prints its own quality-report location; use the clean result for prediction.
            predict_input(cleaned, OUT / f"new_week_topic_predictions_{run_id}.csv", log_lines)
        frozen_corpus = ROOT / "data/processed/bilibili_apex_W25_W28_bertopic_exploratory_corpus.csv"
        if frozen_corpus.exists():
            run_stage("assignment_audit", [sys.executable, "scripts/audit_bertopic_assignments.py"], log_lines)
            run_stage("bertopic_model_audit", [sys.executable, "scripts/audit_bertopic_models.py"], log_lines)
        else:
            log_lines.append("frozen_corpus_audit=skipped; packaged dashboard/model manifest remains loadable, provide local processed corpus to run comment-level audit")
        log_lines.append("sentiment_mode=model_only; manual review, calibration, and human-trained sentiment stages are not consumed")
        run_stage("dashboard_build", [sys.executable, "scripts/build_public_opinion_mixed_test.py"], log_lines)
        validation = validate_outputs(); log_lines.append(json.dumps(validation, ensure_ascii=False))
        run_stage("release_check", [sys.executable, "scripts/check_release.py"], log_lines)
        input_display = None
        if args.input:
            try: input_display = str(args.input.resolve().relative_to(ROOT))
            except (ValueError, OSError): input_display = "<external-input>"
        (OUT / "workflow_last_run.json").write_text(json.dumps({"run_id": run_id, "status": "passed", "validation": validation, "input": input_display}, ensure_ascii=False, indent=2), encoding="utf-8")
        log_lines.append("status=passed")
        print(json.dumps({"run_id": run_id, "status": "passed", "validation": validation}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        log_lines.append(f"status=failed error={type(exc).__name__}: {exc}"); log_lines.extend(traceback.format_exc().splitlines())
        (OUT / "workflow_last_run.json").write_text(json.dumps({"run_id": run_id, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"流程失败：{exc}", file=sys.stderr)
        return 1
    finally:
        (LOG_DIR / f"workflow_{run_id}.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
