from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile

from validate_weekly_report_contract import (
    ALLOWED_SENTIMENTS,
    DEFAULT_CONTRACT,
    _cells,
    _shared_strings,
    validate,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = ROOT / "reports/APEX_CHINA_W30_Weekly_Community_Report.xlsx"
DEFAULT_OUTPUT = (
    ROOT / "reports/APEX_CHINA_W30_Weekly_Community_Report.preview.json"
)


def build_preview(
    workbook_path: Path,
    output_path: Path,
    *,
    period_label: str,
    period_start: str,
    period_end: str,
    contract_path: Path = DEFAULT_CONTRACT,
    week_id: str | None = None,
) -> dict[str, object]:
    validation = validate(workbook_path, contract_path)
    if not validation["valid"]:
        raise ValueError(
            "workbook does not satisfy the weekly report contract: "
            + "; ".join(validation["errors"])
        )

    with ZipFile(workbook_path) as archive:
        shared = _shared_strings(archive)
        cells = _cells(archive, "xl/worksheets/sheet1.xml", shared)

    title_match = re.fullmatch(r"CHINA · (W\d{2})", cells.get("A1", ""))
    if not title_match:
        raise ValueError("A1 does not contain a valid CHINA · WNN title")
    week_label = title_match.group(1)

    drivers: list[dict[str, str]] = []
    for row in range(4, 200):
        sentiment_en = cells.get(f"B{row}")
        if sentiment_en not in ALLOWED_SENTIMENTS:
            continue
        drivers.append(
            {
                "topic_en": cells[f"A{row}"],
                "sentiment_en": sentiment_en,
                "narrative_en": cells[f"A{row + 1}"],
                "topic_zh": cells[f"D{row}"],
                "sentiment_zh": cells[f"E{row}"],
                "narrative_zh": cells[f"D{row + 1}"],
            }
        )

    resolved_week_id = week_id or f"2026_{week_label}"
    if not re.fullmatch(r"\d{4}_W\d{2}", resolved_week_id):
        raise ValueError("week_id must use YYYY_WNN")
    if resolved_week_id.split("_")[-1] != week_label:
        raise ValueError("week_id does not match workbook title")

    payload: dict[str, object] = {
        "schema_version": "apex_weekly_report_preview_v1",
        "week_id": resolved_week_id,
        "week_label": week_label,
        "period": {
            "label": period_label,
            "start": period_start,
            "end": period_end,
        },
        "region": "China",
        "layout": "single_sheet_bilingual_side_by_side",
        "sample_summary": {
            "en": cells.get("A2", ""),
            "zh": cells.get("D2", ""),
        },
        "driver_count": len(drivers),
        "drivers": drivers,
        "source": {
            "workbook": f"reports/{workbook_path.name}",
            "sha256": hashlib.sha256(workbook_path.read_bytes()).hexdigest(),
            "contract": f"config/{contract_path.name}",
        },
        "limitations": {
            "en": (
                "Bounded real samples only. Bilibili comment counts and Heybox "
                "search-visible post counts use different units and are not additive."
            ),
            "zh": (
                "仅使用有限真实样本。B站评论计数与小黑盒公开搜索可见帖子计数"
                "使用不同单位，不得相加。"
            ),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the current weekly bilingual report-preview payload."
    )
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--period-label", default="7.20—7.26")
    parser.add_argument("--period-start", default="2026-07-20")
    parser.add_argument("--period-end", default="2026-07-26")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--week-id")
    args = parser.parse_args()
    result = build_preview(
        args.workbook,
        args.output,
        period_label=args.period_label,
        period_start=args.period_start,
        period_end=args.period_end,
        contract_path=args.contract,
        week_id=args.week_id,
    )
    print(
        json.dumps(
            {
                "output": args.output.as_posix(),
                "week_id": result["week_id"],
                "driver_count": result["driver_count"],
                "source_sha256": result["source"]["sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
