#!/usr/bin/env python3
"""Fail-closed validation for a prepared weekly release."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from canonical_rules import (
    is_forbidden_keyword,
    iter_visible_keywords,
    load_canonical_rules,
)
from validate_narratives import validate_payload
from validate_heat_v1 import validate_heat_v1_dashboard
from validate_weekly_report_contract import DEFAULT_CONTRACT, validate
from weekly_release_common import (
    atomic_json,
    load_production_policy,
    resolve_project_asset,
    sha256,
    storage_week_id,
    week_dates,
    verify_policy_asset_hashes,
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


def validate_data_topic_editorial_review(
    preview: dict[str, object],
    source_topic_ids: set[str],
    business_rules: dict[str, object],
) -> list[str]:
    """Validate provenance/rationale coverage without inventing impact scoring."""

    errors: list[str] = []
    contract = business_rules["weekly_report_drivers"][
        "editorial_topic_disposition_contract"
    ]
    field = str(contract["field"])
    review = preview.get(field)
    if not isinstance(review, dict):
        return [f"editorial package is missing {field}"]
    if review.get("status") not in {"completed", "simulation_fixture_only"}:
        errors.append("Data Topic editorial review is not completed")
    forbidden_numeric_keys = {"impact_score", "high_impact_score", "impact_threshold"}

    def find_forbidden(value: object, location: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in forbidden_numeric_keys:
                    errors.append(
                        f"unapproved numeric impact field in editorial review: {location}.{key}"
                    )
                find_forbidden(item, f"{location}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                find_forbidden(item, f"{location}[{index}]")

    find_forbidden(review, field)
    entries = review.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("Data Topic editorial review entries are missing")
        return errors
    allowed = set(contract["allowed_dispositions"])
    driver_ids = {
        str(driver.get("driver_id") or "")
        for driver in (preview.get("drivers") or [])
        if isinstance(driver, dict)
    }
    covered_topics: set[str] = set()
    entry_pairs: set[tuple[str, str]] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"editorial review entry {index} is not an object")
            continue
        topics = {str(value) for value in entry.get("data_topic_ids") or []}
        disposition = entry.get("disposition")
        linked_drivers = {
            str(value) for value in entry.get("weekly_driver_ids") or []
        }
        if not topics:
            errors.append(f"editorial review entry {index} has no Data Topics")
        unknown_topics = topics - source_topic_ids
        if unknown_topics:
            errors.append(
                f"editorial review entry {index} references unknown Data Topics: "
                f"{sorted(unknown_topics)}"
            )
        if disposition not in allowed:
            errors.append(f"editorial review entry {index} has invalid disposition")
        if not str(entry.get("rationale") or "").strip():
            errors.append(f"editorial review entry {index} lacks editorial rationale")
        if disposition in set(contract["driver_reference_required_for"]):
            if not linked_drivers:
                errors.append(
                    f"editorial review entry {index} lacks Weekly Driver references"
                )
            unknown_drivers = linked_drivers - driver_ids
            if unknown_drivers:
                errors.append(
                    f"editorial review entry {index} references unknown Drivers: "
                    f"{sorted(unknown_drivers)}"
                )
        covered_topics.update(topics)
        entry_pairs.update((topic, driver) for topic in topics for driver in linked_drivers)
    if covered_topics != source_topic_ids:
        errors.append(
            "Data Topic editorial review coverage differs from current Data Topics: "
            f"missing={sorted(source_topic_ids - covered_topics)} "
            f"extra={sorted(covered_topics - source_topic_ids)}"
        )
    for driver in preview.get("drivers") or []:
        if not isinstance(driver, dict):
            continue
        driver_id = str(driver.get("driver_id") or "")
        for topic_id in driver.get("canonical_topic_ids") or []:
            if (str(topic_id), driver_id) not in entry_pairs:
                errors.append(
                    f"Weekly Driver {driver_id} Data Topic {topic_id} lacks an "
                    "editorial mapping rationale"
                )
    omission = review.get("important_omission_review")
    if not isinstance(omission, dict):
        errors.append("important Data Topic omission editorial review is missing")
    else:
        if omission.get("method") != "editorial_judgment_no_numeric_threshold":
            errors.append("important omission review uses an unapproved method")
        if not str(omission.get("rationale") or "").strip():
            errors.append("important omission review lacks rationale")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument(
        "--candidate-only",
        action="store_true",
        help="Validate a candidate before external apex_validator/Sol authorization",
    )
    args = parser.parse_args()
    root = args.project_root.resolve()
    policy = load_production_policy(root)
    business_rules = load_canonical_rules(root)
    approved_assets = verify_policy_asset_hashes(root, policy)
    release_dir = args.release_root.resolve() / args.week
    context = json.loads(
        (release_dir / "release_context.json").read_text(encoding="utf-8")
    )
    files = context["files"]
    start, end = week_dates(args.week)
    errors: list[str] = []

    context_rule = context.get("canonical_business_rules") or {}
    if context_rule.get("version") != business_rules["policy_version"]:
        errors.append("release context has the wrong canonical business-rule version")
    if context_rule.get("sha256") != business_rules["_sha256"]:
        errors.append("release context has the wrong canonical business-rule hash")
    if context.get("approved_model_assets") != approved_assets:
        errors.append("release context approved model-asset bindings differ from policy")

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
        if not (context.get("source_revision") or {}).get("clean"):
            errors.append("production release is not traceable to a clean Git revision")
        workflow = context.get("release_workflow") or {}
        if workflow.get("final_authorization_required"):
            if not args.candidate_only:
                errors.append(
                    "checkpointed production validation must run as candidate-only; "
                    "final Agent/Sol authorization is a separate publication gate"
                )
        else:
            receipt = context.get("agent_runtime_receipt") or {}
            receipt_payload = receipt.get("payload") or {}
            if not receipt_payload:
                errors.append("production release has no Agent Runtime Receipt")
            else:
                for role in ("collector", "analyst", "validator"):
                    expected_agent = policy["formal_agents"][role]
                    actual_agent = (receipt_payload.get("formal_agents") or {}).get(role) or {}
                    for key in ("agent", "model_family", "reasoning_effort"):
                        if str(actual_agent.get(key) or "").casefold() != str(
                            expected_agent[key]
                        ).casefold():
                            errors.append(f"Agent Runtime Receipt {role}.{key} is incorrect")
                    if actual_agent.get("status") != "completed":
                        errors.append(f"Agent Runtime Receipt {role} is not completed")
        if context.get("run_mode") == "revision" and not context.get(
            "manual_revision_provenance"
        ):
            errors.append("revision release lacks controlled-recovery provenance")
    public_rules = dashboard["meta"].get("canonical_rules") or {}
    if public_rules.get("policy_version") != business_rules["policy_version"]:
        errors.append("dashboard has the wrong canonical rule version")
    if public_rules.get("policy_sha256") != business_rules["_sha256"]:
        errors.append("dashboard has the wrong canonical rule hash")
    forbidden_hits = [
        f"{path}={value}"
        for path, value in iter_visible_keywords(dashboard)
        if is_forbidden_keyword(value, business_rules)
    ]
    if forbidden_hits:
        errors.append(
            "approved low-quality keyword reached a visible path: "
            + ", ".join(forbidden_hits)
        )

    heat_validation = validate_heat_v1_dashboard(
        dashboard,
        bilibili,
        heybox,
        target_week_id=args.week,
        business_rules=business_rules,
        source_artifact_hashes={
            "B站": sha256(release_dir / "outputs" / files["bilibili"]),
            "小黑盒": sha256(release_dir / "outputs" / files["heybox"]),
        },
    )
    errors.extend(
        f"Heat v1.0: {error}" for error in heat_validation["errors"]
    )
    errors.extend(
        f"Heat v1.0 missing real input: {block}"
        for block in heat_validation["missing_input_blocks"]
    )

    html = (release_dir / "index.html").read_text(encoding="utf-8")
    embedded = _embedded_dashboard(html)
    if embedded != dashboard:
        errors.append("HTML embedded dashboard differs from release JSON")
    for filename in (
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
    if preview.get("driver_ranking") != report_build.get("driver_ranking"):
        errors.append("report preview driver_ranking differs from report build")
    approved = policy["weekly_report"]["approved_review_statuses"]
    candidate_statuses = policy["weekly_report"]["candidate_review_statuses"]
    expected_statuses = candidate_statuses if args.candidate_only else approved
    if not context["simulation_only"] and preview.get("review_status") not in expected_statuses:
        errors.append(
            "editorial package has the wrong workflow review status: "
            f"{preview.get('review_status')}"
        )
    approval = preview.get("approval")
    if (
        not context["simulation_only"]
        and args.candidate_only
        and approval is not None
    ):
        errors.append("review candidate must not contain human approval")
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
    if context["simulation_only"]:
        expected_simulation_status = (
            "review_candidate"
            if args.candidate_only
            else "simulation_fixture_approved_for_test_only"
        )
        if preview.get("review_status") != expected_simulation_status:
            errors.append("simulation editorial package has the wrong test-only status")

    # Data Topics and Weekly Drivers are separate product layers. Data Topics
    # are checked against model-mapped source records. Drivers are checked only
    # for Topic/evidence provenance, never for title, count, or granularity
    # equality with dashboard topics.
    source_records = list(bilibili["records"]) + list(heybox["records"])
    source_topic_ids = {
        str(row.get("canonical_topic_id"))
        for row in source_records
        if row.get("canonical_topic_id") and not row.get("is_outlier")
    }
    dashboard_topic_ids = {str(topic.get("id")) for topic in latest["topics"]}
    if source_topic_ids != dashboard_topic_ids:
        errors.append("Data Topic IDs differ from mapped non-outlier source records")
    minimum_topics = int(
        business_rules["data_topics"]["qualification"][
            "minimum_active_topic_count"
        ]
    )
    if len(dashboard_topic_ids) < minimum_topics:
        errors.append(
            f"Data Topic qualification count {len(dashboard_topic_ids)} is below "
            f"canonical minimum {minimum_topics}"
        )

    if not context["simulation_only"]:
        identifiers: dict[str, set[str]] = {"B站": set(), "小黑盒": set()}
        identifier_topics: dict[str, dict[str, str]] = {"B站": {}, "小黑盒": {}}
        for platform, payload in (("B站", bilibili), ("小黑盒", heybox)):
            for row in payload["records"]:
                for key in (
                    "text_id", "comment_id", "record_id", "post_id", "visible_post_id"
                ):
                    if row.get(key):
                        evidence_id = str(row[key])
                        identifiers[platform].add(evidence_id)
                        identifier_topics[platform][evidence_id] = str(
                            row.get("canonical_topic_id") or ""
                        )
        used_evidence: set[tuple[str, str]] = set()
        for driver in preview.get("drivers") or []:
            driver_id = str(driver.get("driver_id") or "unknown")
            topic_ids = {str(value) for value in driver.get("canonical_topic_ids") or []}
            if not topic_ids:
                errors.append(f"Weekly Driver {driver_id} has no Data Topic provenance")
            elif not topic_ids.issubset(source_topic_ids):
                errors.append(
                    f"Weekly Driver {driver_id} references unknown Data Topics: "
                    f"{sorted(topic_ids - source_topic_ids)}"
                )
            binding = driver.get("evidence_binding") or {}
            evidence_pairs = [
                ("B站", str(value))
                for value in binding.get("bilibili_comment_ids") or []
            ] + [
                ("小黑盒", str(value))
                for value in binding.get("heybox_visible_post_ids") or []
            ]
            if not evidence_pairs:
                errors.append(f"Weekly Driver {driver_id} has no evidence binding")
            for platform, evidence_id in evidence_pairs:
                key = (platform, evidence_id)
                if evidence_id not in identifiers[platform]:
                    errors.append(
                        f"Weekly Driver {driver_id} evidence is missing from "
                        f"{platform}: {evidence_id}"
                    )
                elif identifier_topics[platform].get(evidence_id) not in topic_ids:
                    errors.append(
                        f"Weekly Driver {driver_id} evidence {platform} "
                        f"{evidence_id} does not trace to its declared Data Topics"
                    )
                if key in used_evidence:
                    errors.append(
                        f"Weekly Driver evidence is reused across drivers: "
                        f"{platform} {evidence_id}"
                    )
                used_evidence.add(key)

        errors.extend(
            validate_data_topic_editorial_review(
                preview, source_topic_ids, business_rules
            )
        )

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

    mutable_or_validator_owned = {
        "candidate_deploy_receipt.json",
        "candidate_verification.json",
        "error_report.json",
        "error_report.md",
        "live_verification.json",
        "manifest.json",
        "publish_receipt.json",
        "rollback_receipt.json",
        "validation.json",
    }
    artifacts = {}
    for path in sorted(release_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(release_dir).as_posix()
        if (
            relative in mutable_or_validator_owned
            or relative.startswith("candidate_deploy_receipts/")
        ):
            continue
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
        "canonical_business_rules": context["canonical_business_rules"],
        "source_revision": context.get("source_revision"),
        "agent_runtime_receipt": context.get("agent_runtime_receipt"),
        "candidate_only": bool(args.candidate_only),
        "release_authorization_required": bool(
            (context.get("release_workflow") or {}).get(
                "final_authorization_required"
            )
        ),
        "report_rules": context["report_rules"],
        "approval": {
            **(approval or {}),
            "editorial_package_sha256": report_build.get(
                "editorial_package_sha256"
            ),
        },
        "driver_ranking": preview.get("driver_ranking"),
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
        "heat_v1_validation": heat_validation,
        "reconciliation": {
            "raw_archives": "hash_verified",
            "effective_rows": "verified",
            "mapped_rows": "verified",
            "topic_volumes": "verified",
            "dashboard_total": "verified",
            "report_preview_workbook_hash": "verified",
            "driver_ranking": "preview_and_report_build_equal",
            "html_embedded_json": "verified",
            "heat_v1_independent_recalculation": "verified",
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
            "driver_ranking": preview.get("driver_ranking"),
            "heat_v1_validation": heat_validation,
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
