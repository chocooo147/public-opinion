from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/weekly_bilingual_report_contract.json"
ALLOWED_SENTIMENTS = {"Positive", "Neutral", "Mixed", "Negative"}


def _shared_strings(archive: ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []
    root = ET.fromstring(archive.read(path))
    return ["".join(node.itertext()) for node in root if node.tag.endswith("}si")]


def _cells(archive: ZipFile, sheet_path: str, shared: list[str]) -> dict[str, str]:
    root = ET.fromstring(archive.read(sheet_path))
    values: dict[str, str] = {}
    for node in root.iter():
        if not node.tag.endswith("}c"):
            continue
        ref = node.attrib.get("r")
        value = next((child for child in node if child.tag.endswith("}v")), None)
        inline = next((child for child in node if child.tag.endswith("}is")), None)
        if not ref:
            continue
        if inline is not None:
            values[ref] = "".join(inline.itertext())
        elif value is not None:
            values[ref] = (
                shared[int(value.text)]
                if node.attrib.get("t") == "s"
                else (value.text or "")
            )
    return values


def validate(path: Path, contract_path: Path = DEFAULT_CONTRACT) -> dict[str, object]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = [node for node in workbook.iter() if node.tag.endswith("}sheet")]
        expected_sheets = contract["layout"]["worksheet_count"]
        if len(sheets) != expected_sheets:
            errors.append(f"expected {expected_sheets} worksheet, found {len(sheets)}")

        shared = _shared_strings(archive)
        cells = _cells(archive, "xl/worksheets/sheet1.xml", shared)
        if not re.fullmatch(r"CHINA · W\d{2}", cells.get("A1", "")):
            errors.append("A1 must use the English CHINA · WNN title")
        if not re.fullmatch(r"中国 · W\d{2}", cells.get("D1", "")):
            errors.append("D1 must use the Chinese 中国 · WNN title")
        if cells.get("A3") != "TOPIC/DRIVER" or cells.get("D3") != "话题/驱动因素":
            errors.append("row 3 bilingual driver headers do not match W30")

        driver_rows: list[int] = []
        for row in range(4, 200):
            if cells.get(f"B{row}") in ALLOWED_SENTIMENTS:
                driver_rows.append(row)
        minimum = contract["driver_policy"]["minimum_count"]
        maximum = contract["driver_policy"]["maximum_count"]
        if not minimum <= len(driver_rows) <= maximum:
            errors.append(
                f"driver count {len(driver_rows)} is outside the allowed {minimum}–{maximum}"
            )

        min_chars = contract["quality_gate"]["minimum_driver_narrative_characters"]
        for row in driver_rows:
            narrative_row = row + 1
            checks = {
                f"A{row}": cells.get(f"A{row}", ""),
                f"D{row}": cells.get(f"D{row}", ""),
                f"A{narrative_row}": cells.get(f"A{narrative_row}", ""),
                f"D{narrative_row}": cells.get(f"D{narrative_row}", ""),
            }
            for ref, value in checks.items():
                if not value.strip():
                    errors.append(f"{ref} is blank")
            if len(checks[f"A{narrative_row}"].strip()) < min_chars:
                errors.append(f"A{narrative_row} narrative is shorter than {min_chars} characters")
            if len(checks[f"D{narrative_row}"].strip()) < min_chars // 2:
                errors.append(f"D{narrative_row} narrative is too short for aligned Chinese meaning")

        threaded = [
            name
            for name in archive.namelist()
            if name.startswith("xl/threadedcomments/") and name.endswith(".xml")
        ]
        comment_count = 0
        for name in threaded:
            root = ET.fromstring(archive.read(name))
            comment_count += sum(
                1 for node in root.iter() if node.tag.endswith("}threadedComment")
            )
        if comment_count < len(driver_rows):
            errors.append(
                f"evidence comments {comment_count} are fewer than drivers {len(driver_rows)}"
            )

    return {
        "workbook": path.as_posix(),
        "contract": contract_path.as_posix(),
        "driver_count": len(driver_rows),
        "target_driver_count": contract["driver_policy"]["target_count"],
        "minimum_driver_count": minimum,
        "evidence_comment_count": comment_count,
        "valid": not errors,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an APEX weekly report against the stable W30 bilingual contract."
    )
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    result = validate(args.workbook, args.contract)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
