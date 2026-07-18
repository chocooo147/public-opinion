from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = (2.0, 5.0)


def main() -> int:
    parser = argparse.ArgumentParser(description="用独立/双人复核基准评估热议度、共识度、风险偏差")
    parser.add_argument("--benchmark", type=Path, help="字段：week_id,canonical_topic_id,heat_reference,consensus_reference,risk_reference")
    args = parser.parse_args()
    result = {"status": "blocked_no_benchmark", "bias_target_percent": list(TARGET), "message": "必须提供独立或双人复核基准；没有基准不能声称2%—5%偏差。"}
    if args.benchmark:
        benchmark = args.benchmark if args.benchmark.is_absolute() else ROOT / args.benchmark
        metrics = {(r["week_id"], r["canonical_topic_id"]): r for r in csv.DictReader((ROOT / "outputs/formal_auxiliary_metrics.csv").open(encoding="utf-8-sig", newline=""))}
        rows = list(csv.DictReader(benchmark.open(encoding="utf-8-sig", newline="")))
        errors = {"heat": [], "consensus": [], "risk": []}
        for row in rows:
            obs = metrics.get((row.get("week_id"), row.get("canonical_topic_id")))
            if not obs:
                continue
            for key, ref_key in (("heat_score", "heat_reference"), ("consensus_score", "consensus_reference"), ("risk_score", "risk_reference")):
                try:
                    ref = float(row.get(ref_key, "")); val = float(obs.get(key, ""))
                    if ref: errors[key.split("_")[0]].append(abs(val - ref) / abs(ref) * 100)
                except (TypeError, ValueError):
                    pass
        result = {"status": "evaluated", "bias_target_percent": list(TARGET), "n": {k: len(v) for k, v in errors.items()}, "mean_absolute_relative_error_percent": {k: round(sum(v) / len(v), 3) if v else None for k, v in errors.items()}, "within_2_to_5_percent": {k: bool(v) and 2 <= (sum(v) / len(v)) <= 5 for k, v in errors.items()}}
    (ROOT / "outputs/formal_metric_bias_evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "evaluated" else 2


if __name__ == "__main__":
    raise SystemExit(main())
