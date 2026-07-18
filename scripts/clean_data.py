from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from common import (
    DERIVED_FIELDS, RAW_FIELDS, clean_whitespace, effective_length, load_rules,
    normalize_for_duplicate, parse_datetime, parse_nonnegative_int, project_root,
    read_csv_rows, sha256_file, timestamp_id, unique_path, week_fields, write_csv,
)


def clean_file(input_path: Path, output_path: Path | None = None, rules_path: Path | None = None) -> tuple[Path, Path]:
    input_path = input_path.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"输入文件不存在：{input_path}")
    rules = load_rules(rules_path)
    before_hash = sha256_file(input_path)
    fields, rows = read_csv_rows(input_path)
    missing_fields = [field for field in RAW_FIELDS if field not in fields]
    if missing_fields:
        raise ValueError(f"缺少必需字段：{', '.join(missing_fields)}")

    short_threshold = int(rules["short_text_min_chars"])
    normalized_texts = [normalize_for_duplicate(clean_whitespace(row.get("text", ""))) for row in rows]
    duplicate_sizes = Counter(text for text in normalized_texts if text)
    seen: Counter[str] = Counter()
    cleaned_rows: list[dict[str, str | int]] = []
    invalid_counts = Counter()

    for row, normalized in zip(rows, normalized_texts):
        clean_text = clean_whitespace(row.get("text", ""))
        parsed_time = parse_datetime(row.get("publish_time", ""), rules["timezone"])
        if row.get("publish_time", "").strip() and parsed_time is None:
            invalid_counts["publish_time"] += 1
        week_start, week_end, week_label = week_fields(parsed_time)

        cleaned = {field: clean_whitespace(row.get(field, "")) for field in RAW_FIELDS}
        for field in ("likes", "comments", "shares"):
            cleaned[field], valid = parse_nonnegative_int(row.get(field, ""))
            if not valid:
                invalid_counts[field] += 1

        seen[normalized] += 1 if normalized else 0
        cleaned.update({
            "publish_datetime": parsed_time.isoformat(sep=" ") if parsed_time else "",
            "week_start": week_start,
            "week_end": week_end,
            "week_label": week_label,
            "clean_text": clean_text,
            "text_length": effective_length(clean_text),
            "is_short": int(effective_length(clean_text) < short_threshold),
            "duplicate_group_size": duplicate_sizes.get(normalized, 0),
            "is_duplicate": int(bool(normalized) and seen[normalized] > 1),
        })
        cleaned_rows.append(cleaned)

    if output_path is None:
        output_path = project_root() / "data" / "processed" / f"{input_path.stem}_cleaned_{timestamp_id()}.csv"
    output_path = unique_path(output_path.resolve())
    write_csv(output_path, RAW_FIELDS + DERIVED_FIELDS, cleaned_rows)

    after_hash = sha256_file(input_path)
    if before_hash != after_hash:
        raise RuntimeError("原始文件校验值发生变化，已停止。")

    log_path = unique_path(output_path.with_name(f"{output_path.stem}_cleaning_log.json"))
    with log_path.open("x", encoding="utf-8") as f:
        json.dump({
            "input_file": str(input_path), "input_sha256": before_hash,
            "output_file": str(output_path), "row_count": len(rows),
            "invalid_values": dict(invalid_counts), "rules": rules,
            "raw_file_unchanged": True,
        }, f, ensure_ascii=False, indent=2)
    return output_path, log_path


def main() -> int:
    parser = argparse.ArgumentParser(description="清洗 APEX 舆情 CSV，不覆盖原始文件。")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="可选输出路径；已存在时自动添加序号。")
    parser.add_argument("--rules", type=Path)
    args = parser.parse_args()
    try:
        output, log = clean_file(args.input, args.output, args.rules)
    except (OSError, ValueError, RuntimeError, csv.Error) as exc:
        print(f"清洗失败：{exc}", file=sys.stderr)
        return 1
    print(f"清洗结果：{output}")
    print(f"清洗日志：{log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
