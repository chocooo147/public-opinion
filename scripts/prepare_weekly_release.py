#!/usr/bin/env python3
"""Validate weekly collection outputs and prepare an isolated site release."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from canonical_rules import load_canonical_rules
from weekly_release_common import (
    apply_frozen_model,
    atomic_json,
    build_dashboard,
    clean_and_deduplicate,
    copy_public_assets,
    file_fingerprint,
    load_production_policy,
    newest_dashboard,
    patch_site_html,
    sample_quality,
    sha256,
    validate_collection,
    verify_policy_asset_hashes,
    week_dates,
    week_number,
)


def source_revision(root: Path) -> dict[str, object]:
    def git(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        )
        return completed.stdout.strip()

    try:
        status = git("status", "--porcelain=v1")
        return {
            "commit": git("rev-parse", "HEAD"),
            "branch": git("branch", "--show-current"),
            "clean": not bool(status),
            "dirty_entry_count": len(status.splitlines()) if status else 0,
        }
    except (OSError, subprocess.CalledProcessError) as exc:
        return {
            "commit": None,
            "branch": None,
            "clean": False,
            "dirty_entry_count": None,
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--bilibili", type=Path, required=True)
    parser.add_argument("--heybox", type=Path, required=True)
    parser.add_argument("--allow-simulated", action="store_true")
    parser.add_argument("--agent-runtime-receipt", type=Path)
    parser.add_argument("--revision-provenance", type=Path)
    parser.add_argument(
        "--run-mode", choices=("production", "revision", "simulate")
    )
    args = parser.parse_args()

    root = args.project_root.resolve()
    policy = load_production_policy(root)
    business_rules = load_canonical_rules(root)
    approved_assets = verify_policy_asset_hashes(root, policy)
    release_dir = args.release_root.resolve() / args.week
    if release_dir.exists():
        raise FileExistsError(
            f"release already exists; refusing to overwrite: {release_dir}"
        )
    start, end = week_dates(args.week)
    bilibili_raw = json.loads(args.bilibili.read_text(encoding="utf-8"))
    heybox_raw = json.loads(args.heybox.read_text(encoding="utf-8"))
    validate_collection(
        bilibili_raw,
        platform="B站",
        week_id=args.week,
        start=start,
        end=end,
        allow_simulated=args.allow_simulated,
    )
    validate_collection(
        heybox_raw,
        platform="小黑盒",
        week_id=args.week,
        start=start,
        end=end,
        allow_simulated=args.allow_simulated,
    )
    simulated = bool(
        bilibili_raw["meta"].get("simulation_only")
        or heybox_raw["meta"].get("simulation_only")
    )
    run_mode = args.run_mode or ("simulate" if simulated else "production")
    if (run_mode == "simulate") != simulated:
        raise ValueError("run mode and input simulation status are inconsistent")
    if simulated and not (
        bilibili_raw["meta"].get("simulation_only")
        and heybox_raw["meta"].get("simulation_only")
    ):
        raise ValueError("mixed real/simulated platform inputs are forbidden")
    bilibili, bilibili_cleaning = clean_and_deduplicate(
        bilibili_raw,
        platform="B站",
    )
    heybox, heybox_cleaning = clean_and_deduplicate(
        heybox_raw,
        platform="小黑盒",
    )
    bilibili = apply_frozen_model(root, bilibili, platform="B站")
    heybox = apply_frozen_model(root, heybox, platform="小黑盒")
    quality = {
        "B站": sample_quality(
            bilibili,
            platform="B站",
            policy=policy,
            simulated=simulated,
        ),
        "小黑盒": sample_quality(
            heybox,
            platform="小黑盒",
            policy=policy,
            simulated=simulated,
        ),
    }

    baseline_path = newest_dashboard(root, before_week_id=args.week)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    dashboard = build_dashboard(
        baseline,
        bilibili,
        heybox,
        week_id=args.week,
        start=start,
        end=end,
        simulated=simulated,
        sample_quality_by_platform=quality,
        business_rules=business_rules,
    )

    week_label = f"W{week_number(args.week):02d}"
    oldest_label = dashboard["weeks"][0]["week_id"].split("-")[-1]
    dashboard_name = f"dashboard_data_apex_{oldest_label}_{week_label}.json"
    bilibili_name = f"bilibili_apex_{args.week}.json"
    heybox_name = f"heybox_apex_{args.week}_public_search.json"
    report_name = f"APEX_CHINA_{week_label}_Weekly_Community_Report.xlsx"
    preview_name = f"APEX_CHINA_{week_label}_Weekly_Community_Report.preview.json"
    markdown_name = f"APEX_CHINA_{week_label}_Weekly_Community_Report.md"
    report_input_name = f"APEX_CHINA_{week_label}_report_input.json"

    outputs_dir = release_dir / "outputs"
    reports_dir = release_dir / "reports"
    raw_dir = release_dir / "archive" / "raw_inputs"
    outputs_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    shutil.copy2(args.bilibili, raw_dir / args.bilibili.name)
    shutil.copy2(args.heybox, raw_dir / args.heybox.name)
    atomic_json(outputs_dir / bilibili_name, bilibili)
    atomic_json(outputs_dir / heybox_name, heybox)
    atomic_json(outputs_dir / dashboard_name, dashboard)
    shutil.copy2(outputs_dir / dashboard_name, release_dir / dashboard_name)
    report_input = {
        "meta": {
            "region": "CHINA",
            "week_id": args.week,
            "date_range": [start.isoformat(), end.isoformat()],
            "data_status": (
                "simulation_fixture"
                if simulated
                else "bounded_real_samples_model_only_exploratory"
            ),
            "formal_reporting_qualified": False,
            "simulation_only": simulated,
            "low_sample_week": quality["B站"]["low_sample_week"],
            "publication_gate_passed": quality["B站"]["production_gate_passed"],
            "sample_policy_version": policy["policy_version"],
            "unit_warning": (
                "Bilibili counts comments; Heybox counts search-visible posts. "
                "Do not sum as a platform-wide total."
            ),
        },
        "bilibili_manifest": bilibili["meta"],
        "heybox_manifest": heybox["meta"],
        "week": dashboard["weeks"][-1],
        "evidence": {
            "B站": bilibili["records"],
            "小黑盒": heybox["records"],
        },
        "cleaning": {
            "B站": bilibili_cleaning,
            "小黑盒": heybox_cleaning,
        },
        "sample_quality": quality,
    }
    atomic_json(outputs_dir / report_input_name, report_input)
    copy_public_assets(root, release_dir)

    template_html = (root / "index.html").read_text(encoding="utf-8")
    html = patch_site_html(
        template_html,
        dashboard=dashboard,
        dashboard_filename=dashboard_name,
        report_filename=report_name,
        preview_filename=preview_name,
        report_markdown_filename=markdown_name,
        bilibili_filename=bilibili_name,
        heybox_filename=heybox_name,
    )
    (release_dir / "index.html").write_text(html, encoding="utf-8")
    report_policy = policy["weekly_report"]
    rule_files = {}
    for key, path_key in (
        ("skill", "skill_path"),
        ("writing_pattern", "writing_pattern_path"),
        ("narrative_rule", "narrative_rule_path"),
        ("narrative_validator", "narrative_validator_path"),
        ("report_contract", "contract_path"),
        ("workbook_template", "template_path"),
    ):
        relative_path = report_policy[path_key]
        rule_files[key] = file_fingerprint(root / relative_path)
        rule_files[key]["path"] = relative_path
    context = {
        "schema_version": 2,
        "week_id": args.week,
        "week_label": week_label,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "simulation_only": simulated,
        "run_mode": run_mode,
        "release_workflow": {
            "schema_version": 1,
            "machine_phase": "prepare",
            "state_after_prepare": "awaiting_analyst_synthesis",
            "human_approval_required": not simulated,
            "final_authorization_required": not simulated,
            "systemd_is_custom_agent_orchestrator": False,
        },
        "low_sample_week": quality["B站"]["low_sample_week"],
        "publication_gate_passed": quality["B站"]["production_gate_passed"],
        "sample_quality": quality,
        "cleaning": {"B站": bilibili_cleaning, "小黑盒": heybox_cleaning},
        "production_policy": {
            "version": policy["policy_version"],
            "path": "config/weekly_production_policy.json",
            "sha256": policy["_sha256"],
        },
        "canonical_business_rules": {
            "version": business_rules["policy_version"],
            "path": business_rules["_path"],
            "sha256": business_rules["_sha256"],
            "heat_status": business_rules["heat"]["status"],
        },
        "source_revision": source_revision(root),
        "approved_model_assets": approved_assets,
        "agent_runtime_receipt": (
            {
                "path": str(args.agent_runtime_receipt.resolve()),
                "sha256": sha256(args.agent_runtime_receipt.resolve()),
                "payload": json.loads(
                    args.agent_runtime_receipt.read_text(encoding="utf-8")
                ),
            }
            if args.agent_runtime_receipt
            else None
        ),
        "manual_revision_provenance": (
            {
                "path": str(args.revision_provenance.resolve()),
                "sha256": sha256(args.revision_provenance.resolve()),
                "payload": json.loads(
                    args.revision_provenance.read_text(encoding="utf-8")
                ),
            }
            if args.revision_provenance
            else None
        ),
        "report_rules": {
            "skill_name": report_policy["skill_name"],
            "skill_version": report_policy["skill_version"],
            "narrative_rule_version": report_policy["narrative_rule_version"],
            "files": rule_files,
        },
        "source_dashboard": baseline_path.name,
        "release_dir": str(release_dir),
        "files": {
            "dashboard": dashboard_name,
            "bilibili": bilibili_name,
            "heybox": heybox_name,
            "report_input": report_input_name,
            "report": report_name,
            "report_preview": preview_name,
            "report_markdown": markdown_name,
        },
        "input_hashes": {
            "bilibili": sha256(args.bilibili),
            "heybox": sha256(args.heybox),
            "baseline_dashboard": sha256(baseline_path),
        },
        "raw_archive": {
            "bilibili": str((raw_dir / args.bilibili.name).relative_to(release_dir)),
            "heybox": str((raw_dir / args.heybox.name).relative_to(release_dir)),
        },
    }
    atomic_json(release_dir / "release_context.json", context)
    print(
        json.dumps(
            {
                "release_dir": str(release_dir),
                "week_id": args.week,
                "weeks": [week["week_id"] for week in dashboard["weeks"]],
                "simulation_only": simulated,
                "topics": len(dashboard["weeks"][-1]["topics"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
