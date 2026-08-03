#!/usr/bin/env python3
"""Fail-closed validation for a prepared weekly release."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from validate_narratives import validate_payload
from validate_weekly_report_contract import DEFAULT_CONTRACT, validate
from weekly_release_common import (
    atomic_json,
    load_production_policy,
    resolve_project_asset,
    sha256,
    storage_week_id,
    week_dates,
)


FORBIDDEN_REPORT_CLAIMS = (
    "platform-wide trend",
    "representative sample",
    "全平台趋势",
    "平台总体趋势",
    "代表性样本",
    "构成跨平台总量",
    "作为跨平台总量",
)


def _fingerprint(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def _embedded_dashboard(html: str) -> dict[str, object]:
    match = re.search(
        r"const REAL_DASHBOARD_DATA = (\{.*?\});\s*\n",
        html,
        flags=re.S,
    )
    if not match:
        raise ValueError("embedded dashboard payload is missing")
    return json.loads(match.group(1))


def _write_error_report(release_dir: Path, week_id: str, errors: list[str]) -> None:
    payload = {
        "schema_version": 1,
        "week_id": week_id,
        "valid": False,
        "publication_blocked": True,
        "errors": errors,
    }
    atomic_json(release_dir / "validation.json", payload)
    atomic_json(release_dir / "error_report.json", payload)
    (release_dir / "error_report.md").write_text(
        "# APEX weekly release error report\n\n"
        f"- Week: {week_id}\n"
        "- Publication: BLOCKED\n\n"
        + "\n".join(f"- {error}" for error in errors)
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root.resolve()
    policy = load_production_policy(root)
    release_dir = args.release_root.resolve() / args.week
    context = json.loads(
        (release_dir / "release_context.json").read_text(encoding="utf-8")
    )
    files = context["files"]
    start, end = week_dates(args.week)
    errors: list[str] = []

    expected = [
        release_dir / "index.html",
        release_dir / files["dashboard"],
        release_dir / "outputs" / files["dashboard"],
        release_dir / "outputs" / files["bilibili"],
        release_dir / "outputs" / files["heybox"],
        release_dir / "outputs" / files["report_input"],
        release_dir / "reports" / files["report"],
        release_dir / "reports" / files["report_preview"],
        release_dir / "reports" / files["report_markdown"],
        release_dir / "report_build.json",
        *(release_dir / path for path in context.get("raw_archive", {}).values()),
    ]
    errors.extend(
        f"missing required file: {path.relative_to(release_dir)}"
        for path in expected
        if not path.is_file()
    )
    if errors:
        _write_error_report(release_dir, args.week, errors)
        raise ValueError("; ".join(errors))

    report_input = json.loads(
        (release_dir / "outputs" / files["report_input"]).read_text(encoding="utf-8")
    )
    bilibili = json.loads(
        (release_dir / "outputs" / files["bilibili"]).read_text(encoding="utf-8")
    )
    heybox = json.loads(
        (release_dir / "outputs" / files["heybox"]).read_text(encoding="utf-8")
    )
    for label, payload in (("B站", bilibili), ("小黑盒", heybox)):
        quality = context["sample_quality"][label]
        if len(payload["records"]) != quality["effective_rows"]:
            errors.append(f"{label} effective-row reconciliation failed")
        cleaning = context["cleaning"][label]
        if (
            int(cleaning["raw_rows"])
            != int(cleaning["effective_rows"])
            + int(cleaning["blank_rows_removed"])
            + int(cleaning["duplicate_rows_removed"])
            + int(cleaning["technical_issue_rows"])
        ):
            errors.append(f"{label} raw-to-effective cleaning reconciliation failed")
        mapped = sum(
            bool(row.get("canonical_topic_id")) and not row.get("is_outlier")
            for row in payload["records"]
        )
        if mapped != quality["mapped_rows"]:
            errors.append(f"{label} mapped-row reconciliation failed")
        if report_input["sample_quality"][label] != quality:
            errors.append(f"{label} report-input sample quality differs from context")
    for label, archive_key in (("bilibili", "bilibili"), ("heybox", "heybox")):
        raw_path = release_dir / context["raw_archive"][archive_key]
        if sha256(raw_path) != context["input_hashes"][label]:
            errors.append(f"immutable raw archive hash mismatch: {label}")

    for item in context["report_rules"]["files"].values():
        path = Path(item["path"])
        if not path.is_absolute():
            path = root / path
        if not path.is_file() or sha256(path) != item["sha256"]:
            errors.append(f"Skill/rule fingerprint changed after preparation: {path}")
    policy_path = Path(context["production_policy"]["path"])
    if not policy_path.is_absolute():
        policy_path = root / policy_path
    if not policy_path.is_file() or sha256(policy_path) != context["production_policy"]["sha256"]:
        errors.append("weekly production policy changed after preparation")
    report_build = json.loads(
        (release_dir / "report_build.json").read_text(encoding="utf-8")
    )
    if report_build.get("skill_version") != context["report_rules"]["skill_version"]:
        errors.append("report build logged the wrong Skill version")
    if report_build.get("narrative_rule_version") != context["report_rules"]["narrative_rule_version"]:
        errors.append("report build logged the wrong narrative-rule version")
    if not context["simulation_only"] and not context.get("publication_gate_passed"):
        errors.append("Bilibili sample/source-quality gate failed; low-sample week publication blocked")

    dashboard = json.loads(
        (release_dir / files["dashboard"]).read_text(encoding="utf-8")
    )
    week_ids = [week["week_id"] for week in dashboard["weeks"]]
    if len(week_ids) != 5:
        errors.append(f"dashboard history has {len(week_ids)} weeks, expected 5")
    if len(set(week_ids)) != len(week_ids):
        errors.append("dashboard history contains duplicate weeks")
    if storage_week_id(week_ids[-1]) != args.week:
        errors.append("dashboard latest week does not match target")
    if dashboard["meta"]["default_week_id"] != week_ids[-1]:
        errors.append("dashboard default week is not latest")
    latest = dashboard["weeks"][-1]
    if latest["start"] != start.isoformat() or latest["end"] != end.isoformat():
        errors.append("dashboard latest week violates natural-week boundary")
    if any(
        week["start"] > latest["start"]
        for week in dashboard["weeks"][:-1]
    ):
        errors.append("future data leaked into selected-week history")
    if dashboard["meta"].get("qualified_for_formal_reporting") is not False:
        errors.append("formal reporting qualification must remain false")
    if context["simulation_only"] != bool(
        dashboard["meta"].get("simulation_only")
    ):
        errors.append("simulation label is inconsistent")
    if not context["simulation_only"]:
        expected_boundaries = {
            "B站": "real_bounded_sample",
            "小黑盒": "real_public_search_sample",
            "综合": "mixed_real_observations_incomparable_units",
        }
        if dashboard["meta"].get("platform_status") != expected_boundaries:
            errors.append("production data boundaries are incorrect")

    html = (release_dir / "index.html").read_text(encoding="utf-8")
    embedded = _embedded_dashboard(html)
    if embedded != dashboard:
        errors.append("HTML embedded dashboard differs from release JSON")
    for filename in (
        files["bilibili"],
        files["heybox"],
        files["report"],
        files["report_preview"],
        files["report_markdown"],
    ):
        if filename not in html:
            errors.append(f"HTML does not reference {filename}")
    if context["week_label"] not in html:
        errors.append("HTML does not identify the target week")

    workbook = release_dir / "reports" / files["report"]
    contract = validate(workbook, root / DEFAULT_CONTRACT.relative_to(root))
    if not contract["valid"]:
        errors.extend(f"report contract: {error}" for error in contract["errors"])
    preview = json.loads(
        (release_dir / "reports" / files["report_preview"]).read_text(
            encoding="utf-8"
        )
    )
    if preview.get("week_id") != args.week:
        errors.append("report preview week does not match target")
    if preview.get("source", {}).get("sha256") != sha256(workbook):
        errors.append("report preview workbook hash mismatch")
    narrative_errors = validate_payload(preview)
    errors.extend(f"narrative gate: {error}" for error in narrative_errors)
    approved = policy["weekly_report"]["approved_review_statuses"]
    if not context["simulation_only"] and preview.get("review_status") not in approved:
        errors.append(
            "editorial package is not approved for release: "
            f"{preview.get('review_status')}"
        )
    approval = preview.get("approval")
    if not context["simulation_only"] and preview.get("review_status") in approved:
        required_approval_fields = {
            "status",
            "approved_at",
            "approver_role",
            "approval_source",
            "approval_statement",
            "scope",
        }
        if not isinstance(approval, dict):
            errors.append("approved editorial package is missing structured approval evidence")
        else:
            missing_approval = sorted(
                field for field in required_approval_fields if not approval.get(field)
            )
            if missing_approval:
                errors.append(
                    "approved editorial package has incomplete approval evidence: "
                    f"{missing_approval}"
                )
            if approval.get("status") != preview.get("review_status"):
                errors.append("approval evidence status differs from editorial review status")
        if report_build.get("approval") != approval:
            errors.append("report build approval evidence differs from report preview")
    if context["simulation_only"] and preview.get("review_status") != "simulation_fixture_approved_for_test_only":
        errors.append("simulation editorial package has the wrong test-only status")

    topic_counts = Counter(
        str(row.get("canonical_topic_id"))
        for row in bilibili["records"]
        if row.get("canonical_topic_id") and not row.get("is_outlier")
    )
    dashboard_counts = {
        str(topic["id"]): int(topic["platform_metrics"]["B站"]["count"])
        for topic in latest["topics"]
        if int(topic["platform_metrics"]["B站"]["count"])
    }
    if dict(topic_counts) != dashboard_counts:
        errors.append("Bilibili topic-volume reconciliation failed")
    if sum(dashboard_counts.values()) != int(latest["kpis"]["total_volume"]):
        errors.append("dashboard total volume does not equal topic volumes")
    markdown = (
        release_dir / "reports" / files["report_markdown"]
    ).read_text(encoding="utf-8")
    claims = [claim for claim in FORBIDDEN_REPORT_CLAIMS if claim in markdown]
    if claims:
        errors.append(f"report contains forbidden claims: {claims}")
    if context["simulation_only"] and "SIMULATION ONLY" not in markdown:
        errors.append("simulation report is missing its warning")

    if errors:
        _write_error_report(release_dir, args.week, errors)
        raise ValueError("; ".join(errors))

    artifacts = {}
    for path in sorted(release_dir.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        relative = path.relative_to(release_dir).as_posix()
        artifacts[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    manifest = {
        "schema_version": 2,
        "week_id": args.week,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "simulation_only": context["simulation_only"],
        "history_week_ids": week_ids,
        "data_boundary": dashboard["meta"]["platform_status"],
        "report_contract": contract,
        "production_policy": context["production_policy"],
        "report_rules": context["report_rules"],
        "approval": {
            **(approval or {}),
            "editorial_package_sha256": report_build.get(
                "editorial_package_sha256"
            ),
        },
        "revision": {
            "revision_reason": preview.get("revision_reason"),
            "previous_data_version": preview.get("previous_data_version"),
            "current_data_version": preview.get("current_data_version"),
        },
        "models_and_registry": {
            key: _fingerprint(resolve_project_asset(root, relative))
            for key, relative in policy["model_gate"].items()
            if key.endswith("_path")
        },
        "sample_quality": context["sample_quality"],
        "reconciliation": {
            "raw_archives": "hash_verified",
            "effective_rows": "verified",
            "mapped_rows": "verified",
            "topic_volumes": "verified",
            "dashboard_total": "verified",
            "report_preview_workbook_hash": "verified",
            "html_embedded_json": "verified",
        },
        "artifacts": artifacts,
        "valid": True,
    }
    atomic_json(release_dir / "manifest.json", manifest)
    atomic_json(
        release_dir / "validation.json",
        {
            "week_id": args.week,
            "valid": True,
            "history_week_ids": week_ids,
            "artifact_count": len(artifacts),
            "report_driver_count": contract["driver_count"],
        },
    )
    print(
        json.dumps(
            {
                "release_dir": str(release_dir),
                "valid": True,
                "week_id": args.week,
                "history_week_ids": week_ids,
                "artifact_count": len(artifacts),
                "report_driver_count": contract["driver_count"],
                "simulation_only": context["simulation_only"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
