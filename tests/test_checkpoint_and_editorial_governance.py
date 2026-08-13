from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from canonical_rules import load_canonical_rules  # noqa: E402
from validate_weekly_release import validate_data_topic_editorial_review  # noqa: E402
from workflow_checkpoint import create_checkpoint, verify_checkpoint  # noqa: E402


def _editorial_review() -> dict[str, object]:
    return {
        "drivers": [
            {
                "driver_id": "D01",
                "canonical_topic_ids": ["APEX-T001", "APEX-T002"],
            }
        ],
        "data_topic_editorial_review": {
            "schema_version": 1,
            "status": "completed",
            "entries": [
                {
                    "data_topic_ids": ["APEX-T001", "APEX-T002"],
                    "disposition": "merged",
                    "weekly_driver_ids": ["D01"],
                    "rationale": "Both Data Topics describe separate facets of one weekly event.",
                }
            ],
            "important_omission_review": {
                "status": "completed",
                "method": "editorial_judgment_no_numeric_threshold",
                "omitted_data_topic_ids": [],
                "rationale": "All current Data Topics are represented.",
            },
        },
    }


def test_editorial_review_requires_provenance_and_rationale_without_threshold():
    rules = load_canonical_rules(ROOT)
    payload = _editorial_review()
    assert validate_data_topic_editorial_review(
        payload, {"APEX-T001", "APEX-T002"}, rules
    ) == []

    payload["data_topic_editorial_review"]["impact_threshold"] = 0.8
    errors = validate_data_topic_editorial_review(
        payload, {"APEX-T001", "APEX-T002"}, rules
    )
    assert any("unapproved numeric impact field" in error for error in errors)


def test_editorial_review_cannot_silently_omit_a_data_topic():
    rules = load_canonical_rules(ROOT)
    payload = _editorial_review()
    payload["data_topic_editorial_review"]["entries"][0]["data_topic_ids"] = [
        "APEX-T001"
    ]
    payload["drivers"][0]["canonical_topic_ids"] = ["APEX-T001"]
    errors = validate_data_topic_editorial_review(
        payload, {"APEX-T001", "APEX-T002"}, rules
    )
    assert any("coverage differs" in error for error in errors)


def test_human_approval_checkpoint_detects_release_mutation(tmp_path: Path):
    release_dir = tmp_path / "release" / "2026_W33"
    release_dir.mkdir(parents=True)
    revision = {
        "commit": "a" * 40,
        "branch": "main",
        "clean": True,
        "dirty_entry_count": 0,
    }
    (release_dir / "release_context.json").write_text(
        json.dumps(
            {
                "week_id": "2026_W33",
                "week_start": "2026-08-10",
                "week_end": "2026-08-16",
                "source_revision": revision,
                "production_policy": {"version": "test"},
                "canonical_business_rules": {"version": "test"},
            }
        ),
        encoding="utf-8",
    )
    (release_dir / "prepared.json").write_text('{"prepared":true}', encoding="utf-8")
    checkpoint = tmp_path / "checkpoint.json"
    create_checkpoint(
        root=ROOT,
        release_dir=release_dir,
        week_id="2026_W33",
        state="awaiting_human_approval",
        output=checkpoint,
    )
    editorial = tmp_path / "editorial.json"
    editorial.write_text(
        json.dumps(
            {
                "week_id": "2026_W33",
                "review_status": "approved_for_release",
                "approval": {"status": "approved_for_release"},
            }
        ),
        encoding="utf-8",
    )
    with patch("workflow_checkpoint._git_revision", return_value=revision):
        verified = verify_checkpoint(
            root=ROOT,
            release_dir=release_dir,
            checkpoint=checkpoint,
            expected_state="awaiting_human_approval",
            editorial_package=editorial,
        )
    assert verified["valid"] is True

    (release_dir / "prepared.json").write_text('{"prepared":false}', encoding="utf-8")
    with patch("workflow_checkpoint._git_revision", return_value=revision):
        changed = verify_checkpoint(
            root=ROOT,
            release_dir=release_dir,
            checkpoint=checkpoint,
            expected_state="awaiting_human_approval",
            editorial_package=editorial,
        )
    assert changed["valid"] is False
    assert any("changed after checkpoint" in error for error in changed["errors"])


def test_analyst_checkpoint_allows_revised_derived_candidate_only(tmp_path: Path):
    release_dir = tmp_path / "release" / "2026_W33"
    release_dir.mkdir(parents=True)
    revision = {
        "commit": "b" * 40,
        "branch": "release/test",
        "clean": True,
        "dirty_entry_count": 0,
    }
    (release_dir / "release_context.json").write_text(
        json.dumps(
            {
                "week_id": "2026_W33",
                "week_start": "2026-08-10",
                "week_end": "2026-08-16",
                "source_revision": revision,
                "production_policy": {"version": "test"},
                "canonical_business_rules": {"version": "test"},
            }
        ),
        encoding="utf-8",
    )
    prepared = release_dir / "prepared.json"
    prepared.write_text('{"prepared":true}', encoding="utf-8")
    checkpoint = tmp_path / "analyst.json"
    create_checkpoint(
        root=ROOT,
        release_dir=release_dir,
        week_id="2026_W33",
        state="awaiting_analyst_synthesis",
        output=checkpoint,
    )
    (release_dir / "reports").mkdir()
    (release_dir / "reports/candidate.xlsx").write_bytes(b"derived")
    (release_dir / "candidate_deploy_receipt.json").write_text(
        "{}", encoding="utf-8"
    )
    with patch("workflow_checkpoint._git_revision", return_value=revision):
        verified = verify_checkpoint(
            root=ROOT,
            release_dir=release_dir,
            checkpoint=checkpoint,
            expected_state="awaiting_analyst_synthesis",
        )
    assert verified["valid"] is True
    prepared.write_text('{"prepared":false}', encoding="utf-8")
    with patch("workflow_checkpoint._git_revision", return_value=revision):
        changed = verify_checkpoint(
            root=ROOT,
            release_dir=release_dir,
            checkpoint=checkpoint,
            expected_state="awaiting_analyst_synthesis",
        )
    assert changed["valid"] is False
