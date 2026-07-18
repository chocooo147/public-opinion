from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from snownlp import SnowNLP

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = ROOT / "data/raw/heybox/heybox_apex_2026_W25_W28_public_search_20260718.csv"
DEFAULT_OUTPUT = ROOT / "outputs/heybox_apex_W25_W28_public_search_assignments.csv"
DEFAULT_MANIFEST = ROOT / "outputs/heybox_apex_W25_W28_public_search_manifest.json"
DEFAULT_REPORT = ROOT / "reports/heybox_apex_W25_W28_public_search_report.md"
WEEKS = ["2026_W25", "2026_W26", "2026_W27", "2026_W28"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify(score: float) -> str:
    if score >= 0.65:
        return "positive"
    if score <= 0.35:
        return "negative"
    return "neutral"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description="整理小黑盒公开搜索可见样本的主题和情感字段")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.raw = args.raw.resolve()
    args.predictions = args.predictions.resolve()
    args.output = args.output.resolve()

    raw_rows = read_csv(args.raw)
    prediction_rows = read_csv(args.predictions)
    prediction_by_id = {row["text_id"]: row for row in prediction_rows}
    output_rows: list[dict[str, object]] = []
    missing_predictions: list[str] = []
    for raw in raw_rows:
        prediction = prediction_by_id.get(raw["text_id"])
        if not prediction:
            missing_predictions.append(raw["text_id"])
            continue
        text = raw.get("text", "").strip()
        score = float(SnowNLP(text).sentiments) if text else 0.5
        output_rows.append(
            {
                "text_id": raw["text_id"],
                "week_id": prediction.get("week_id", ""),
                "publish_time": raw.get("publish_time", ""),
                "platform": "小黑盒",
                "source_type": raw.get("source_type", "post"),
                "text": text,
                "likes": int(raw.get("likes") or 0),
                "comments": int(raw.get("comments") or 0),
                "url": raw.get("url", ""),
                "model_topic_id": prediction.get("model_topic_id", ""),
                "canonical_topic_id": prediction.get("canonical_topic_id", ""),
                "canonical_topic_name": prediction.get("canonical_topic_name", ""),
                "assignment_confidence": prediction.get("assignment_confidence", ""),
                "is_outlier": prediction.get("is_outlier", ""),
                "sentiment_score": round(score, 8),
                "sentiment_label": classify(score),
                "sentiment_model": "SnowNLP",
                "sentiment_status": "model_only_unvalidated",
                "sample_scope": "public_search_visible_posts_only",
                "metrics_source": "heybox_public_search_visible_sample",
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(output_rows[0].keys())
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)

    weekly = Counter(row["week_id"] for row in output_rows)
    mapped_weekly = Counter(row["week_id"] for row in output_rows if row["canonical_topic_id"])
    sentiments = Counter(row["sentiment_label"] for row in output_rows)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "raw_input": str(args.raw.relative_to(ROOT)),
        "raw_sha256": sha256(args.raw),
        "predictions_input": str(args.predictions.relative_to(ROOT)),
        "predictions_sha256": sha256(args.predictions),
        "output": str(args.output.relative_to(ROOT)),
        "row_count": len(output_rows),
        "weekly_rows": {week: weekly[week] for week in WEEKS},
        "mapped_weekly_rows": {week: mapped_weekly[week] for week in WEEKS},
        "mapped_rows": sum(mapped_weekly.values()),
        "outlier_rows": sum(1 for row in output_rows if not row["canonical_topic_id"]),
        "sentiment_counts": dict(sentiments),
        "missing_predictions": missing_predictions,
        "collection_scope": "Public search result cards visible in the logged-in Xiaoheihe web UI; not a platform-wide census.",
        "comment_body_collection": False,
        "formal_reporting_qualified": False,
    }
    DEFAULT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 小黑盒 APEX W25—W28 公开搜索样本报告",
        "",
        "## 样本边界",
        "",
        "- 数据来自已登录小黑盒网页端公开搜索结果卡片，仅代表搜索可见样本，不是平台全量数据。",
        "- 保留帖子发布日期、正文摘要、点赞数、评论数和原始链接；未采集评论正文。",
        "- 主题使用项目冻结 BERTopic 模型预测；情感使用 SnowNLP 模型输出，均不作为正式统计真值。",
        "",
        "## 周次覆盖",
        "",
        "| 周次 | 采集帖子 | 映射到既有主题 |",
        "|---|---:|---:|",
    ]
    for week in WEEKS:
        lines.append(f"| {week} | {weekly[week]} | {mapped_weekly[week]} |")
    lines.extend(
        [
            "",
            "## 质量结论",
            "",
            f"- 总样本：{len(output_rows)} 条；成功映射：{sum(mapped_weekly.values())} 条；离群/新主题候选：{manifest['outlier_rows']} 条。",
            "- 四个自然周均有样本，但周间样本量不均衡；环比仅用于探索性观察。",
            "- 点赞和评论数为采集时页面显示值，可能随后变化。",
        ]
    )
    DEFAULT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if not missing_predictions and all(weekly[week] > 0 for week in WEEKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
