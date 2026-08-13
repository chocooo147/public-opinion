#!/usr/bin/env python3
"""Build the stable bilingual weekly workbook from evidence-qualified records."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from build_weekly_report_preview import build_preview
from validate_narratives import validate_payload
from validate_weekly_report_contract import (
    ALLOWED_SENTIMENTS,
    DEFAULT_CONTRACT,
    _cells,
    _shared_strings,
    validate,
)
from weekly_release_common import atomic_json, load_production_policy, sha256


SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
THREADED_NS = (
    "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"
)
SENTIMENT_EN = {
    "positive": "Positive",
    "neutral": "Neutral",
    "negative": "Negative",
}
SENTIMENT_ZH = {
    "positive": "正向",
    "neutral": "中性",
    "negative": "负向",
}
TOPIC_EN = {
    "APEX-T001": "Ranked and Matchmaking",
    "APEX-T002": "Esports and Competition",
    "APEX-T003": "Server and Network Stability",
    "APEX-T004": "Version Updates",
    "APEX-T005": "Anti-Cheat and Fair Play",
    "APEX-T006": "Events and Collaborations",
    "APEX-T007": "Controller and Aim Assist Balance",
    "APEX-T008": "Cosmetics and Store Rotation",
    "APEX-T009": "New Player Experience",
    "APEX-T010": "Battle Pass and Monetization",
    "APEX-T011": "Legends and Abilities",
    "APEX-T012": "Maps and Modes",
    "APEX-T013": "Weapons and Legend Strength",
}


def _simulation_editorial_package(
    report_input: dict[str, object],
    policy: dict[str, object],
) -> dict[str, object]:
    """Create a deterministic, explicitly simulated package for E2E testing."""
    records = report_input["evidence"]["B站"]
    by_topic = {
        str(row["canonical_topic_id"]): row
        for row in records
        if row.get("canonical_topic_id") and not row.get("is_outlier")
    }
    openings_en = [
        "Test viewers welcomed", "Fixture players discussed", "Simulated users questioned",
        "Test community members described", "Fixture viewers recognized",
        "Simulated players worried about", "Test users debated", "Fixture audiences found",
        "Simulated newcomers expected", "Test participants interpreted",
    ]
    openings_zh = [
        "联调观众认可", "模拟玩家讨论", "测试用户质疑", "联调社区描述", "模拟观众关注",
        "测试玩家担忧", "联调用户讨论", "模拟群体认为", "测试新玩家期待", "联调参与者评价",
    ]
    drivers = []
    for index, topic_id in enumerate(sorted(by_topic)[:10], start=1):
        row = by_topic[topic_id]
        sentiment = str(row.get("sentiment_label") or "neutral")
        topic_zh = str(row.get("canonical_topic_name") or "联调主题")
        topic_en = TOPIC_EN.get(topic_id, "Simulation Driver")
        drivers.append(
            {
                "topic_en": topic_en,
                "topic_zh": topic_zh,
                "driver_id": f"simulation-driver-{index:02d}",
                "canonical_rank": index,
                "sentiment_en": SENTIMENT_EN[sentiment],
                "sentiment_zh": SENTIMENT_ZH[sentiment],
                "narrative_en": (
                    f"{openings_en[index - 1]} the clearly labelled {topic_en.lower()} fixture and "
                    "reported how its bounded scenario behaved during the pipeline rehearsal. "
                    "The synthetic reaction helped verify narrative placement and increased "
                    "confidence in the test flow, but it cannot support a real community verdict."
                ),
                "narrative_zh": (
                    f"{openings_zh[index - 1]}已明确标注的“{topic_zh}”联调情境，并说明该情境在流水线演练中的表现。"
                    "这类合成反馈帮助检查叙述排版和流程衔接，也限制了任何真实社区结论。"
                ),
                "canonical_topic_ids": [topic_id],
                "evidence_notes": ["Deterministic simulation fixture; no live-platform claim."],
                "source_urls": [str(row.get("url") or "")],
            }
        )
    meta = report_input["meta"]
    driver_ids = [str(driver["driver_id"]) for driver in drivers]
    topic_review = {
        "schema_version": 1,
        "status": "simulation_fixture_only",
        "entries": [
            {
                "data_topic_ids": list(driver["canonical_topic_ids"]),
                "disposition": "direct",
                "weekly_driver_ids": [driver["driver_id"]],
                "rationale": "Deterministic simulation mapping; no live-platform claim.",
            }
            for driver in drivers
        ],
        "important_omission_review": {
            "status": "simulation_fixture_only",
            "method": "editorial_judgment_no_numeric_threshold",
            "omitted_data_topic_ids": [],
            "rationale": "Every simulated Data Topic is represented directly.",
        },
    }
    report_policy = policy["weekly_report"]
    return {
        "schema": "apex_weekly_report_preview_v1",
        "review_status": "simulation_fixture_approved_for_test_only",
        "week_id": meta["week_id"],
        "period": {"start": meta["date_range"][0], "end": meta["date_range"][1], "timezone": "Asia/Shanghai"},
        "overview": {
            "en": "SIMULATION ONLY · deterministic pipeline rehearsal; no real platform claim",
            "zh": "仅限模拟联调 · 确定性流水线演练；不代表真实平台观点",
        },
        "driver_count": len(drivers),
        "drivers": drivers,
        "data_topic_editorial_review": topic_review,
        "driver_ranking": {
            "schema_version": 1,
            "ordering_basis": "composite_influence_descending",
            "ordering_method": "deterministic_simulation_only",
            "score_present": False,
            "ranked_driver_ids": driver_ids,
            "rank_provenance": {
                "source": "simulation_only_deterministic_editorial_fixture",
                "policy_version": policy["policy_version"],
                "skill_version": report_policy["skill_version"],
                "narrative_rule_version": report_policy["narrative_rule_version"],
                "review_status": "simulation_fixture_approved_for_test_only",
            },
        },
    }


def _cell_map(
    drivers: list[dict[str, object]],
    report_input: dict[str, object],
    editorial_package: dict[str, object],
) -> dict[str, str]:
    meta = report_input["meta"]
    week_label = str(meta["week_id"]).split("_")[-1]
    bili = report_input["bilibili_manifest"]
    heybox = report_input["heybox_manifest"]
    simulation = bool(meta.get("simulation_only"))
    prefix_en = "SIMULATION ONLY · " if simulation else ""
    prefix_zh = "仅限模拟联调 · " if simulation else ""
    cells = {
        "A1": f"CHINA · {week_label}",
        "D1": f"中国 · {week_label}",
        "A2": (
            f"{prefix_en}Weekly bounded observations: "
            f"{bili['raw_rows']} Bilibili comments; "
            f"{heybox['raw_rows']} Heybox search-visible posts. "
            "The platform units are different and are not a combined total."
        ),
        "D2": (
            f"{prefix_zh}每周有限观察：{bili['raw_rows']}条B站评论；"
            f"{heybox['raw_rows']}篇小黑盒公开搜索可见帖子。"
            "两平台计数单位不同，不构成跨平台总量。"
        ),
    }
    if editorial_package.get("overview"):
        cells["A2"] = str(editorial_package["overview"]["en"])
        cells["D2"] = str(editorial_package["overview"]["zh"])
    driver_rows = [4, 6, 8, 11, 13, 15, 17, 19, 21, 23]
    for row, driver in zip(driver_rows, drivers):
        cells[f"A{row}"] = str(driver["topic_en"])
        cells[f"B{row}"] = str(driver["sentiment_en"])
        cells[f"D{row}"] = str(driver["topic_zh"])
        cells[f"E{row}"] = str(driver["sentiment_zh"])
        cells[f"A{row + 1}"] = str(driver["narrative_en"])
        cells[f"D{row + 1}"] = str(driver["narrative_zh"])
    return cells


def _set_inline_cell(root: ET.Element, reference: str, value: str) -> None:
    cell = next(
        (
            node
            for node in root.iter(f"{{{SHEET_NS}}}c")
            if node.attrib.get("r") == reference
        ),
        None,
    )
    if cell is None:
        raise ValueError(f"template workbook is missing cell {reference}")
    for child in list(cell):
        if child.tag in (f"{{{SHEET_NS}}}v", f"{{{SHEET_NS}}}is"):
            cell.remove(child)
    cell.set("t", "inlineStr")
    inline = ET.SubElement(cell, f"{{{SHEET_NS}}}is")
    text = ET.SubElement(inline, f"{{{SHEET_NS}}}t")
    text.text = value


def _copy_cell_style(
    root: ET.Element,
    *,
    target_reference: str,
    source_reference: str,
) -> None:
    cells = {
        node.attrib.get("r"): node
        for node in root.iter(f"{{{SHEET_NS}}}c")
        if node.attrib.get("r")
    }
    target = cells.get(target_reference)
    source = cells.get(source_reference)
    if target is None or source is None:
        raise ValueError(
            f"cannot copy workbook style {source_reference} -> {target_reference}"
        )
    if "s" in source.attrib:
        target.set("s", source.attrib["s"])
    else:
        target.attrib.pop("s", None)


def _cell_style_id(root: ET.Element, reference: str) -> str | None:
    cell = next(
        (
            node
            for node in root.iter(f"{{{SHEET_NS}}}c")
            if node.attrib.get("r") == reference
        ),
        None,
    )
    if cell is None:
        raise ValueError(f"template workbook is missing cell {reference}")
    return cell.attrib.get("s")


def _set_cell_style_id(
    root: ET.Element, reference: str, style_id: str | None
) -> None:
    cell = next(
        (
            node
            for node in root.iter(f"{{{SHEET_NS}}}c")
            if node.attrib.get("r") == reference
        ),
        None,
    )
    if cell is None:
        raise ValueError(f"template workbook is missing cell {reference}")
    if style_id is None:
        cell.attrib.pop("s", None)
    else:
        cell.set("s", style_id)


def _comment_text(
    driver: dict[str, object],
    *,
    week_label: str,
    simulation: bool,
) -> str:
    lines = [
        f"{week_label} evidence used for this driver:",
        "Canonical trace: " + ", ".join(driver.get("canonical_topic_ids") or []),
    ]
    lines.extend(
        f"Evidence synthesis: {note}"
        for note in (driver.get("evidence_notes") or [])
    )
    lines.extend(f"Source: {url}" for url in (driver.get("source_urls") or []))
    lines.append(
        "Simulation fixture only; no real platform claim."
        if simulation
        else (
            "Sentiment direction is model-derived and unvalidated; the bounded "
            "evidence does not establish a platform-wide conclusion."
        )
    )
    return "\n".join(lines)


def _legacy_comment_text(text: str) -> str:
    return (
        "[Threaded comment]\n\n"
        "Your version of Excel allows you to read this threaded comment; "
        "however, any edits to it will get removed if the file is opened in a "
        "newer version of Excel.\n\nComment:\n    "
        + text
    )


def _patch_comments(
    xml_bytes: bytes,
    *,
    driver_comments: dict[str, str],
    overview: str,
    threaded: bool,
) -> bytes:
    root = ET.fromstring(xml_bytes)
    all_driver_comment_refs = {
        "A5", "A7", "A9", "A12", "A14", "A16", "A18", "A20", "A22", "A24"
    }
    for parent in root.iter():
        for node in list(parent):
            ref = node.attrib.get("ref")
            if ref in all_driver_comment_refs and ref not in driver_comments:
                parent.remove(node)
    if threaded:
        for node in root.iter(f"{{{THREADED_NS}}}threadedComment"):
            ref = node.attrib.get("ref")
            text_node = node.find(f"{{{THREADED_NS}}}text")
            if text_node is None:
                continue
            if ref == "A2":
                text_node.text = overview
            elif ref in driver_comments:
                text_node.text = driver_comments[ref]
    else:
        for node in root.iter(f"{{{SHEET_NS}}}comment"):
            ref = node.attrib.get("ref")
            text_node = node.find(f".//{{{SHEET_NS}}}t")
            if text_node is None:
                continue
            if ref == "A2":
                text_node.text = _legacy_comment_text(overview)
            elif ref in driver_comments:
                text_node.text = _legacy_comment_text(driver_comments[ref])
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _trim_unused_trailing_driver_rows(root: ET.Element, driver_count: int) -> None:
    """Remove only unused trailing driver pairs from the stable template."""
    if driver_count >= 10:
        return
    first_unused_title_row = [4, 6, 8, 11, 13, 15, 17, 19, 21, 23][driver_count]
    sheet_data = root.find(f"{{{SHEET_NS}}}sheetData")
    if sheet_data is not None:
        for row in list(sheet_data):
            if int(row.attrib.get("r", "0")) >= first_unused_title_row:
                sheet_data.remove(row)
    merge_cells = root.find(f"{{{SHEET_NS}}}mergeCells")
    if merge_cells is not None:
        for merge_cell in list(merge_cells):
            reference = merge_cell.attrib.get("ref", "")
            match = re.search(r"(\d+)", reference)
            if match and int(match.group(1)) >= first_unused_title_row:
                merge_cells.remove(merge_cell)
        merge_cells.set("count", str(len(list(merge_cells))))
    dimension = root.find(f"{{{SHEET_NS}}}dimension")
    if dimension is not None:
        dimension.set("ref", f"A1:E{first_unused_title_row - 1}")


def build_workbook(
    *,
    template: Path,
    output: Path,
    report_input: dict[str, object],
    editorial_package: dict[str, object],
) -> list[dict[str, object]]:
    drivers = list(editorial_package["drivers"])
    cells = _cell_map(drivers, report_input, editorial_package)
    meta = report_input["meta"]
    week_label = str(meta["week_id"]).split("_")[-1]
    simulation = bool(meta.get("simulation_only"))
    narrative_refs = ["A5", "A7", "A9", "A12", "A14", "A16", "A18", "A20", "A22", "A24"]
    driver_comments = {
        ref: _comment_text(
            driver,
            week_label=week_label,
            simulation=simulation,
        )
        for ref, driver in zip(narrative_refs, drivers)
    }
    overview = (
        f"Coverage: {meta['date_range'][0]}—{meta['date_range'][1]} "
        "(Asia/Shanghai).\n"
        f"Bilibili SHA-256: {report_input['bilibili_manifest']['raw_sha256']}.\n"
        f"Heybox SHA-256: {report_input['heybox_manifest']['raw_sha256']}.\n"
        "Bilibili comments and Heybox search-visible posts use different units "
        "and are not additive. This report is not qualified for platform-wide "
        "statistical reporting."
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.xlsx")
    with ZipFile(template) as source, ZipFile(
        temporary,
        "w",
        compression=ZIP_DEFLATED,
    ) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                root = ET.fromstring(data)
                for reference, value in cells.items():
                    _set_inline_cell(root, reference, value)
                _trim_unused_trailing_driver_rows(root, len(drivers))
                style_rows = {
                    "Positive": 4,
                    "Neutral": 6,
                    "Mixed": 6,
                    "Negative": 8,
                }
                sentiment_styles = {
                    sentiment: {
                        "en": _cell_style_id(root, f"B{source_row}"),
                        "zh": _cell_style_id(root, f"E{source_row}"),
                    }
                    for sentiment, source_row in style_rows.items()
                }
                for row, driver in zip(
                    [4, 6, 8, 11, 13, 15, 17, 19, 21, 23],
                    drivers,
                ):
                    sentiment = str(driver["sentiment_en"])
                    _set_cell_style_id(
                        root, f"B{row}", sentiment_styles[sentiment]["en"]
                    )
                    _set_cell_style_id(
                        root, f"E{row}", sentiment_styles[sentiment]["zh"]
                    )
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            elif info.filename == "xl/threadedcomments/threadedcomment.xml":
                data = _patch_comments(
                    data,
                    driver_comments=driver_comments,
                    overview=overview,
                    threaded=True,
                )
            elif info.filename == "xl/comments1.xml":
                data = _patch_comments(
                    data,
                    driver_comments=driver_comments,
                    overview=overview,
                    threaded=False,
                )
            target.writestr(info, data)
    os.replace(temporary, output)
    return drivers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument(
        "--editorial-package",
        type=Path,
        help="Skill-reviewed narrative JSON; required for production",
    )
    args = parser.parse_args()
    root = args.project_root.resolve()
    release_dir = args.release_root.resolve() / args.week
    context = json.loads(
        (release_dir / "release_context.json").read_text(encoding="utf-8")
    )
    if context["week_id"] != args.week:
        raise ValueError("release context week mismatch")
    report_input_path = (
        release_dir / "outputs" / context["files"]["report_input"]
    )
    report_input = json.loads(report_input_path.read_text(encoding="utf-8"))
    policy = load_production_policy(root)
    report_policy = policy["weekly_report"]
    if context["simulation_only"]:
        editorial_package = (
            json.loads(args.editorial_package.read_text(encoding="utf-8"))
            if args.editorial_package
            else _simulation_editorial_package(report_input, policy)
        )
        editorial_source = "generated_deterministic_simulation_fixture"
    else:
        if not args.editorial_package:
            raise ValueError(
                "production report requires --editorial-package produced under "
                "the apex-weekly-report-writing Skill"
            )
        editorial_package = json.loads(
            args.editorial_package.read_text(encoding="utf-8")
        )
        editorial_source = str(args.editorial_package.resolve())
    if editorial_package.get("week_id") != args.week:
        raise ValueError("editorial package week does not match release context")
    narrative_errors = validate_payload(editorial_package)
    if narrative_errors:
        raise ValueError("narrative validation failed: " + "; ".join(narrative_errors))
    template = root / report_policy["template_path"]
    if not template.is_file():
        raise FileNotFoundError(f"stable workbook template missing: {template}")
    report_path = release_dir / "reports" / context["files"]["report"]
    drivers = build_workbook(
        template=template,
        output=report_path,
        report_input=report_input,
        editorial_package=editorial_package,
    )
    validation = validate(report_path, root / DEFAULT_CONTRACT.relative_to(root))
    if not validation["valid"]:
        raise ValueError("; ".join(validation["errors"]))
    preview_path = release_dir / "reports" / context["files"]["report_preview"]
    preview = build_preview(
        report_path,
        preview_path,
        period_label=report_input["week"]["label"],
        period_start=report_input["meta"]["date_range"][0],
        period_end=report_input["meta"]["date_range"][1],
        contract_path=root / DEFAULT_CONTRACT.relative_to(root),
        week_id=args.week,
    )
    preview.update(
        {
            "review_status": editorial_package.get("review_status"),
            "approval": editorial_package.get("approval"),
            "revision_reason": editorial_package.get("revision_reason"),
            "previous_data_version": editorial_package.get("previous_data_version"),
            "current_data_version": editorial_package.get("current_data_version"),
            "driver_count": len(drivers),
            "drivers": drivers,
            "driver_ranking": editorial_package.get("driver_ranking"),
            "driver_reduction": editorial_package.get("driver_reduction"),
            "data_topic_editorial_review": editorial_package.get(
                "data_topic_editorial_review"
            ),
            "rule_provenance": context["report_rules"],
        }
    )
    atomic_json(preview_path, preview)
    markdown_path = release_dir / "reports" / context["files"]["report_markdown"]
    markdown_path.write_text(
        "\n".join(
            [
                f"# APEX CHINA {context['week_label']} Weekly Community Report",
                "",
                (
                    "> SIMULATION ONLY — this artifact is an isolated pipeline "
                    "fixture and must not be published as real data."
                    if context["simulation_only"]
                    else "> Bounded real samples; exploratory model output only."
                ),
                "",
                f"- Period: {context['week_start']}—{context['week_end']}",
                f"- Independent evidence-qualified drivers: {len(drivers)}",
                "- Bilibili comments and Heybox search-visible posts are incomparable units.",
                "- Sentiment and risk are model-derived and not formally validated.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    atomic_json(
        release_dir / "report_build.json",
        {
            "week_id": args.week,
            "simulation_only": context["simulation_only"],
            "driver_count": len(drivers),
            "editorial_source": editorial_source,
            "editorial_package_sha256": (
                sha256(args.editorial_package) if args.editorial_package else None
            ),
            "review_status": editorial_package.get("review_status"),
            "driver_ranking": editorial_package.get("driver_ranking"),
            "approval": editorial_package.get("approval"),
            "data_topic_editorial_review": editorial_package.get(
                "data_topic_editorial_review"
            ),
            "skill_name": context["report_rules"]["skill_name"],
            "skill_version": context["report_rules"]["skill_version"],
            "narrative_rule_version": context["report_rules"]["narrative_rule_version"],
            "rule_files": context["report_rules"]["files"],
            "narrative_validation": {"valid": True, "errors": []},
            "workbook": context["files"]["report"],
            "workbook_sha256": sha256(report_path),
            "preview_sha256": sha256(preview_path),
            "preview_week_id": preview["week_id"],
            "contract_valid": validation["valid"],
        },
    )
    print(
        json.dumps(
            {
                "workbook": str(report_path),
                "sha256": sha256(report_path),
                "drivers": len(drivers),
                "preview": str(preview_path),
                "simulation_only": context["simulation_only"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
