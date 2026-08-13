import sys
import unittest
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

CURRENT_POLICY = __import__("json").loads(
    (ROOT / "config" / "weekly_production_policy.json").read_text(encoding="utf-8")
)
CURRENT_POLICY_VERSION = CURRENT_POLICY["policy_version"]
CURRENT_SKILL_VERSION = CURRENT_POLICY["weekly_report"]["skill_version"]
CURRENT_NARRATIVE_RULE_VERSION = CURRENT_POLICY["weekly_report"][
    "narrative_rule_version"
]

from build_weekly_report import _simulation_editorial_package, build_workbook  # noqa: E402
from validate_narratives import validate_payload  # noqa: E402


def _driver(index: int, sentiment: str = "Neutral") -> dict[str, object]:
    return {
        "driver_id": f"driver-{index:02d}",
        "canonical_rank": index,
        "topic_en": f"Fixture Topic {index}",
        "topic_zh": f"联调话题{index}",
        "sentiment_en": sentiment,
        "sentiment_zh": {"Positive": "正向", "Neutral": "中性", "Negative": "负向"}[sentiment],
        "narrative_en": (
            f"Group {index} players discussed the fixture topic and reported a clear reaction to its details. "
            "The comparison helped their understanding and increased confidence in the resulting decision."
        ),
        "narrative_zh": (
            f"第{index}组玩家认为该联调话题的具体细节值得讨论，并说明了直接反应。"
            "这些比较帮助理解实际差异，也提升了后续判断的信心。"
        ),
        "canonical_topic_ids": [f"APEX-T{index:03d}"],
        "evidence_notes": ["Fixture evidence."],
        "source_urls": ["https://example.test/evidence"],
    }


def _payload() -> dict[str, object]:
    drivers = [_driver(index) for index in range(1, 11)]
    return {
        "review_status": "approved_for_release",
        "drivers": drivers,
        "driver_ranking": {
            "schema_version": 1,
            "ordering_basis": "composite_influence_descending",
            "ordering_method": "skill_reviewed_editorial_judgment",
            "score_present": False,
            "ranked_driver_ids": [driver["driver_id"] for driver in drivers],
            "rank_provenance": {
                "source": "pre_workbook_skill_reviewed_editorial_package",
                "policy_version": CURRENT_POLICY_VERSION,
                "skill_version": CURRENT_SKILL_VERSION,
                "narrative_rule_version": CURRENT_NARRATIVE_RULE_VERSION,
                "review_status": "approved_for_release",
            },
        },
    }


def test_valid_editorial_order_passes():
    assert validate_payload(_payload()) == []


def test_shuffled_driver_array_fails_even_if_ids_are_unchanged():
    payload = _payload()
    payload["drivers"][0], payload["drivers"][1] = payload["drivers"][1], payload["drivers"][0]
    errors = validate_payload(payload)
    assert any("ascending canonical_rank" in error for error in errors)
    assert any("ranked_driver_ids" in error for error in errors)


def test_missing_ranking_evidence_fails_for_current_payload():
    payload = _payload()
    payload.pop("driver_ranking")
    assert "preview must contain driver_ranking evidence" in validate_payload(payload)


def test_legacy_reference_can_explicitly_bypass_missing_ranking_evidence():
    payload = _payload()
    payload.pop("driver_ranking")
    assert validate_payload(payload, allow_legacy_reference=True) == []


def test_legacy_reference_does_not_bypass_present_invalid_ranking_evidence():
    payload = _payload()
    payload["driver_ranking"]["score_present"] = True
    assert any("score_present" in error for error in validate_payload(payload, allow_legacy_reference=True))
    for invalid_ranking in (None, [], "invalid"):
        payload = _payload()
        payload["driver_ranking"] = invalid_ranking
        assert any(
            "must be an object" in error
            for error in validate_payload(payload, allow_legacy_reference=True)
        )


def test_duplicate_or_invalid_rank_fails():
    payload = _payload()
    payload["drivers"][1]["canonical_rank"] = 1
    errors = validate_payload(payload)
    assert any("canonical ranks must be unique" in error for error in errors)
    assert any("continuous" in error for error in errors)


def test_report_driver_absent_from_ranked_ids_fails():
    payload = _payload()
    payload["driver_ranking"]["ranked_driver_ids"][-1] = "missing-driver"
    assert any("exactly equal" in error for error in validate_payload(payload))


def test_fixed_sentiment_grouping_that_reorders_rank_fails():
    payload = _payload()
    sentiments = ["Positive", "Positive", "Positive", "Neutral", "Neutral", "Neutral", "Negative", "Negative", "Negative", "Negative"]
    for driver, sentiment in zip(payload["drivers"], sentiments):
        driver["sentiment_en"] = sentiment
        driver["sentiment_zh"] = {"Positive": "正向", "Neutral": "中性", "Negative": "负向"}[sentiment]
    payload["drivers"] = sorted(payload["drivers"], key=lambda driver: driver["sentiment_en"])
    errors = validate_payload(payload)
    assert any("ascending canonical_rank" in error for error in errors)


def test_builder_preserves_the_canonical_driver_sequence(tmp_path):
    payload = _payload()
    report_input = {
        "meta": {"week_id": "2026_W31", "date_range": ["2026-07-27", "2026-08-02"], "simulation_only": False},
        "bilibili_manifest": {"raw_rows": 1, "raw_sha256": "a"},
        "heybox_manifest": {"raw_rows": 1, "raw_sha256": "b"},
    }
    output = tmp_path / "report.xlsx"
    built = build_workbook(
        template=ROOT / "templates" / "APEX_CHINA_W30_10_DRIVER_TEMPLATE.xlsx",
        output=output,
        report_input=report_input,
        editorial_package=deepcopy(payload),
    )
    assert output.is_file()
    assert [driver["driver_id"] for driver in built] == payload["driver_ranking"]["ranked_driver_ids"]


def _style_id(path: Path, reference: str) -> str | None:
    with ZipFile(path) as workbook:
        root = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    return next(
        cell.attrib.get("s")
        for cell in root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c")
        if cell.attrib.get("r") == reference
    )


def test_builder_snapshots_sentiment_styles_before_ranked_overwrite(tmp_path):
    payload = _payload()
    payload["drivers"][0]["sentiment_en"] = "Negative"
    payload["drivers"][0]["sentiment_zh"] = "负向"
    template = ROOT / "templates" / "APEX_CHINA_W30_10_DRIVER_TEMPLATE.xlsx"
    report_input = {
        "meta": {"week_id": "2026_W32", "date_range": ["2026-08-03", "2026-08-09"], "simulation_only": False},
        "bilibili_manifest": {"raw_rows": 1, "raw_sha256": "a"},
        "heybox_manifest": {"raw_rows": 1, "raw_sha256": "b"},
    }
    output = tmp_path / "report.xlsx"
    build_workbook(
        template=template,
        output=output,
        report_input=report_input,
        editorial_package=payload,
    )
    assert _style_id(output, "B4") == _style_id(template, "B8")
    assert _style_id(output, "E4") == _style_id(template, "E8")
    assert _style_id(output, "B6") == _style_id(template, "B6")
    assert _style_id(output, "E6") == _style_id(template, "E6")


def test_simulation_package_has_explicit_test_only_ranking_evidence():
    report_input = {
        "meta": {"week_id": "2026_W31", "date_range": ["2026-07-27", "2026-08-02"]},
        "evidence": {
            "B站": [
                {
                    "canonical_topic_id": f"APEX-T{index:03d}",
                    "canonical_topic_name": f"模拟主题{index}",
                    "sentiment_label": "neutral",
                    "url": "https://example.test/simulation",
                    "is_outlier": False,
                }
                for index in range(1, 11)
            ]
        },
    }
    policy = {
        "policy_version": CURRENT_POLICY_VERSION,
        "weekly_report": {
            "skill_version": CURRENT_SKILL_VERSION,
            "narrative_rule_version": CURRENT_NARRATIVE_RULE_VERSION,
        },
    }
    package = _simulation_editorial_package(report_input, policy)
    assert validate_payload(package) == []
    assert package["driver_ranking"]["score_present"] is False
    assert package["driver_ranking"]["ordering_method"] == "deterministic_simulation_only"


class DriverOrderingEnforcementTests(unittest.TestCase):
    def test_valid_order(self):
        test_valid_editorial_order_passes()

    def test_shuffled_order(self):
        test_shuffled_driver_array_fails_even_if_ids_are_unchanged()

    def test_missing_evidence(self):
        test_missing_ranking_evidence_fails_for_current_payload()

    def test_legacy_bypass(self):
        test_legacy_reference_can_explicitly_bypass_missing_ranking_evidence()

    def test_legacy_invalid_evidence(self):
        test_legacy_reference_does_not_bypass_present_invalid_ranking_evidence()

    def test_invalid_rank(self):
        test_duplicate_or_invalid_rank_fails()

    def test_absent_ranked_id(self):
        test_report_driver_absent_from_ranked_ids_fails()

    def test_sentiment_grouping(self):
        test_fixed_sentiment_grouping_that_reorders_rank_fails()

    def test_builder_sequence(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temporary:
            test_builder_preserves_the_canonical_driver_sequence(Path(temporary))

    def test_sentiment_style_snapshot(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temporary:
            test_builder_snapshots_sentiment_styles_before_ranked_overwrite(Path(temporary))

    def test_simulation_ranking(self):
        test_simulation_package_has_explicit_test_only_ranking_evidence()
