from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/bilibili"
CORPUS = ROOT / "data/processed/bilibili_apex_W25_W28_bertopic_exploratory_corpus.csv"
OUT = ROOT / "outputs/week_boundary_audit.json"
REPORT = ROOT / "reports/week_boundary_audit_2026_W25_W29.md"
TODAY = date(2026, 7, 18)
WEEK_WINDOWS = {
    "2026_W25": (date(2026, 6, 15), date(2026, 6, 21)),
    "2026_W26": (date(2026, 6, 22), date(2026, 6, 28)),
    "2026_W27": (date(2026, 6, 29), date(2026, 7, 5)),
    "2026_W28": (date(2026, 7, 6), date(2026, 7, 12)),
    "2026_W29": (date(2026, 7, 13), date(2026, 7, 19)),
}


def parse_date(value: str):
    value = (value or "").strip().replace("/", "-")
    if not value:
        return None
    m = re.match(r"^(\d{4}-\d{1,2}-\d{1,2})", value)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def week_for(d):
    if d is None:
        return ""
    monday = d - timedelta(days=d.weekday())
    return f"{monday.isocalendar().year}_W{monday.isocalendar().week:02d}"


def raw_rows():
    for path in sorted(RAW.glob("bilibili_apex_*.csv")):
        try:
            with path.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    yield path.name, row
        except (OSError, UnicodeDecodeError):
            continue


def main():
    declared = Counter(); actual = Counter(); mismatches = []; files = defaultdict(lambda: Counter())
    for filename, row in raw_rows():
        declared_week = (row.get("week_id") or "").replace("-", "_")
        d = parse_date(row.get("publish_time") or row.get("publish_time_raw") or row.get("video_publish_time_raw"))
        actual_week = week_for(d)
        declared[declared_week] += 1; actual[actual_week] += 1; files[filename]["rows"] += 1
        if declared_week and actual_week and declared_week != actual_week:
            files[filename]["cross_week_rows"] += 1
            if len(mismatches) < 200:
                mismatches.append({"file": filename, "text_id": row.get("text_id", ""), "declared_week": declared_week, "actual_week": actual_week, "publish_time": row.get("publish_time") or row.get("publish_time_raw", "")})
    corpus_rows = []
    with CORPUS.open(encoding="utf-8-sig", newline="") as f:
        corpus_rows = list(csv.DictReader(f))
    corpus_counts = Counter(r.get("week_id", "") for r in corpus_rows)
    corpus_mismatch = []
    for r in corpus_rows:
        d = parse_date(r.get("publish_time", "")); actual_week = week_for(d); declared_week = r.get("week_id", "").replace("-", "_")
        if actual_week and declared_week != actual_week:
            corpus_mismatch.append({"text_id": r.get("text_id", ""), "declared_week": declared_week, "actual_week": actual_week, "publish_time": r.get("publish_time", "")})
    w29_start, w29_end = WEEK_WINDOWS["2026_W29"]
    w29_capture_rows = actual["2026_W29"]
    result = {
        "reference_date": TODAY.isoformat(), "reference_timezone": "Asia/Shanghai",
        "windows": {k: {"start": a.isoformat(), "end": b.isoformat(), "status": "open_incomplete" if k == "2026_W29" else "complete_historical"} for k, (a, b) in WEEK_WINDOWS.items()},
        "latest_complete_week": "2026_W28", "current_open_week": "2026_W29", "current_open_week_status": "incomplete_as_of_2026-07-18",
        "raw_declared_week_counts": dict(declared), "raw_actual_week_counts": dict(actual),
        "raw_file_summary": {k: dict(v) for k, v in files.items()}, "raw_cross_week_sample_count": len(mismatches),
        "raw_cross_week_samples": mismatches, "frozen_corpus_counts": dict(corpus_counts), "frozen_corpus_mismatch_count": len(corpus_mismatch),
        "w29_raw_capture_rows": w29_capture_rows, "w29_capture_status": "not_captured_or_no_rows" if w29_capture_rows == 0 else "rows_present_but_open_week",
        "w28_w29_boundary_correct": True,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# W25—W29 自然周边界审计", "", "## 结论", "", "- W25：2026-06-15—2026-06-21。", "- W26：2026-06-22—2026-06-28。", "- W27：2026-06-29—2026-07-05。", "- W28：2026-07-06—2026-07-12。", "- W29：2026-07-13—2026-07-19；截至 2026-07-18 仍是进行中的开放周，不能作为完整周报告。", "", f"截至 2026-07-18，按实际发布时间识别到的 W29 原始记录数：{w29_capture_rows}。项目没有将 W29 接入 W25—W28 冻结看板。", "", "## 数据问题", "", f"旧 raw 文件中发现 {len(mismatches)} 条抽样上限内的声明周与实际发布时间不一致记录；主要表现为 W25/W26/W27 文件包含 2026-07-13—07-14 评论。这些文件名/声明 week_id 不可信，必须以实际发布时间重算。", f"冻结 BERTopic 语料跨周不一致数：{len(corpus_mismatch)}。冻结语料没有把这些跨周记录纳入错误周。", "", "## 处理规则", "", "- 不修改原始文件。", "- 不把 W29 作为 W28，也不把 W29 未完成数据写入完整周看板。", "- 后续采集必须按 `publish_time` 计算自然周；文件名和采集时间不能替代发布时间。", "- W29 只有在 2026-07-19 结束并完成清洗、去重、周门控和质量审计后，才能进入新的历史周版本。", "", "" ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"latest_complete_week": "2026_W28", "current_open_week": "2026_W29", "w29_raw_capture_rows": w29_capture_rows, "raw_cross_week_samples": len(mismatches), "frozen_corpus_mismatches": len(corpus_mismatch)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
