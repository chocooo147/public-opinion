from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from common import (
    DERIVED_FIELDS, RAW_FIELDS, effective_length, load_rules, normalize_for_duplicate,
    parse_datetime, project_root, read_csv_rows, sha256_file, timestamp_id, week_fields,
    write_csv,
)


def rate(numerator: int, denominator: int) -> str:
    return f"{numerator / denominator:.4f}" if denominator else "0.0000"


def enriched_rows(rows: list[dict[str, str]], threshold: int, timezone_name: str) -> list[dict[str, str]]:
    normalized = [normalize_for_duplicate(row.get("clean_text") or row.get("text", "")) for row in rows]
    seen: Counter[str] = Counter()
    result = []
    for row, key in zip(rows, normalized):
        item = dict(row)
        dt = parse_datetime(row.get("publish_datetime") or row.get("publish_time", ""), timezone_name)
        ws, we, wl = week_fields(dt)
        item.setdefault("week_start", ws)
        item.setdefault("week_end", we)
        item.setdefault("week_label", wl)
        text = row.get("clean_text") or row.get("text", "")
        seen[key] += 1 if key else 0
        item.setdefault("text_length", str(effective_length(text)))
        item.setdefault("is_short", str(int(effective_length(text) < threshold)))
        item.setdefault("is_duplicate", str(int(bool(key) and seen[key] > 1)))
        result.append(item)
    return result


def tokenize(text: str, stopwords: set[str]) -> list[str]:
    text = (text or "").casefold()
    tokens = re.findall(r"[a-z][a-z0-9_+-]{1,}|[\u4e00-\u9fff]+", text)
    output: list[str] = []
    for token in tokens:
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            pieces = [token] if len(token) <= 4 else [token[i:i + 2] for i in range(len(token) - 1)]
        else:
            pieces = [token]
        output.extend(piece for piece in pieces if len(piece) >= 2 and piece not in stopwords)
    return output


def quality_check(input_path: Path, report_dir: Path | None = None, rules_path: Path | None = None) -> Path:
    input_path = input_path.resolve()
    rules = load_rules(rules_path)
    fields, source_rows = read_csv_rows(input_path)
    missing = [field for field in RAW_FIELDS if field not in fields]
    if missing:
        raise ValueError(f"缺少必需字段：{', '.join(missing)}")
    rows = enriched_rows(source_rows, int(rules["short_text_min_chars"]), rules["timezone"])
    if report_dir is None:
        report_dir = project_root() / "outputs" / "quality_reports" / f"{input_path.stem}_{timestamp_id()}"
    base = report_dir.resolve()
    suffix = 2
    while base.exists():
        base = report_dir.resolve().with_name(f"{report_dir.name}_{suffix}")
        suffix += 1
    base.mkdir(parents=True)

    valid_weeks = sorted({(r.get("week_start", ""), r.get("week_label", "")) for r in rows if r.get("week_start")})
    scopes: list[tuple[str, str, list[dict[str, str]]]] = [("overall", "总体", rows)]
    scopes += [("week", label, [r for r in rows if r.get("week_start") == start]) for start, label in valid_weeks]

    weekly_rows = []
    for start, label in valid_weeks:
        selected = [r for r in rows if r.get("week_start") == start]
        weekly_rows.append({"week_start": start, "week_end": selected[0].get("week_end", ""), "week_label": label, "text_count": len(selected)})
    unassigned = sum(1 for r in rows if not r.get("week_start"))
    if unassigned:
        weekly_rows.append({"week_start": "", "week_end": "", "week_label": "时间无效或缺失", "text_count": unassigned})
    write_csv(base / "weekly_text_volume.csv", ["week_start", "week_end", "week_label", "text_count"], weekly_rows)

    platform_rows = []
    duplicate_rows = []
    short_rows = []
    for scope_type, scope_label, selected in scopes:
        platforms = Counter((r.get("platform") or "[缺失]").strip() for r in selected)
        for platform, count in platforms.most_common():
            platform_rows.append({"scope_type": scope_type, "scope": scope_label, "platform": platform, "text_count": count, "share": rate(count, len(selected))})
        duplicate_count = sum(str(r.get("is_duplicate", "0")) == "1" for r in selected)
        short_count = sum(str(r.get("is_short", "0")) == "1" for r in selected)
        duplicate_rows.append({"scope_type": scope_type, "scope": scope_label, "text_count": len(selected), "duplicate_count": duplicate_count, "duplicate_rate": rate(duplicate_count, len(selected))})
        short_rows.append({"scope_type": scope_type, "scope": scope_label, "text_count": len(selected), "short_text_count": short_count, "short_text_rate": rate(short_count, len(selected)), "threshold_chars": rules["short_text_min_chars"]})
    write_csv(base / "platform_distribution.csv", ["scope_type", "scope", "platform", "text_count", "share"], platform_rows)
    write_csv(base / "duplicate_rate.csv", ["scope_type", "scope", "text_count", "duplicate_count", "duplicate_rate"], duplicate_rows)
    write_csv(base / "short_text_rate.csv", ["scope_type", "scope", "text_count", "short_text_count", "short_text_rate", "threshold_chars"], short_rows)

    checked_fields = RAW_FIELDS + [f for f in DERIVED_FIELDS if f in rows[0]] if rows else RAW_FIELDS
    missing_rows = []
    for field in checked_fields:
        count = sum(not str(r.get(field, "")).strip() for r in rows)
        missing_rows.append({"field": field, "missing_count": count, "total_count": len(rows), "missing_rate": rate(count, len(rows))})
    write_csv(base / "missing_values.csv", ["field", "missing_count", "total_count", "missing_rate"], missing_rows)

    stopwords = set(rules.get("stopwords", []))
    word_rows = []
    for scope_type, scope_label, selected in scopes:
        counts = Counter(token for r in selected for token in tokenize(r.get("clean_text") or r.get("text", ""), stopwords))
        limit = int(rules["top_words_overall"] if scope_type == "overall" else rules["top_words_per_week"])
        for rank, (word, count) in enumerate(counts.most_common(limit), 1):
            word_rows.append({"scope_type": scope_type, "scope": scope_label, "rank": rank, "word": word, "count": count})
    write_csv(base / "high_frequency_words.csv", ["scope_type", "scope", "rank", "word", "count"], word_rows)

    rng = random.Random(int(rules["random_seed"]))
    sample_rows = []
    for scope_type, scope_label, selected in scopes:
        size = int(rules["random_sample_size_overall"] if scope_type == "overall" else rules["random_sample_size_per_week"])
        for item in rng.sample(selected, min(size, len(selected))):
            sample_rows.append({"scope_type": scope_type, "scope": scope_label, **{field: item.get(field, "") for field in RAW_FIELDS}, "week_label": item.get("week_label", ""), "clean_text": item.get("clean_text") or item.get("text", "")})
    sample_fields = ["scope_type", "scope"] + RAW_FIELDS + ["week_label", "clean_text"]
    write_csv(base / "random_samples.csv", sample_fields, sample_rows)

    overall_dup = duplicate_rows[0]
    overall_short = short_rows[0]
    summary = [
        {"metric": "文本总量", "value": len(rows), "note": "含时间无效或缺失的记录"},
        {"metric": "有效自然周数", "value": len(valid_weeks), "note": "周一至周日"},
        {"metric": "未分配周记录数", "value": unassigned, "note": "发布时间缺失或无法解析"},
        {"metric": "重复率", "value": overall_dup["duplicate_rate"], "note": "规范化文本从第二次出现起计重复"},
        {"metric": "短文本率", "value": overall_short["short_text_rate"], "note": f"少于 {rules['short_text_min_chars']} 个有效字符"},
    ]
    write_csv(base / "summary.csv", ["metric", "value", "note"], summary)

    with (base / "run_metadata.json").open("x", encoding="utf-8") as f:
        json.dump({"input_file": str(input_path), "input_sha256": sha256_file(input_path), "row_count": len(rows), "rules": rules}, f, ensure_ascii=False, indent=2)
    with (base / "quality_report.md").open("x", encoding="utf-8") as f:
        f.write("# APEX 舆情数据质量报告\n\n")
        f.write(f"- 输入文件：`{input_path}`\n- 文本总量：{len(rows)}\n- 有效自然周：{len(valid_weeks)}\n")
        f.write(f"- 重复率：{float(overall_dup['duplicate_rate']):.2%}\n- 短文本率：{float(overall_short['short_text_rate']):.2%}\n- 未分配周记录：{unassigned}\n\n")
        f.write("详细结果见同目录各 CSV 文件。比例字段采用 0—1 小数表示。\n")
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description="输出 APEX 舆情 CSV 的数据质量报告。")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--rules", type=Path)
    args = parser.parse_args()
    try:
        result = quality_check(args.input, args.report_dir, args.rules)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"质量检查失败：{exc}", file=sys.stderr)
        return 1
    print(f"质量报告：{result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
