from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from canonical_rules import load_canonical_rules  # noqa: E402
from heat_v1 import recalculate_dashboard_heat_v1  # noqa: E402
from validate_heat_v1 import validate_heat_v1_dashboard  # noqa: E402


def metric(count: int) -> dict:
    return {
        "count": count,
        "video_count": count,
        "creator_count": count,
        "consensus_score": 50,
        "heat_score": 99,
        "discussion_coverage": 99,
        "discussion_volume_score": 99,
        "influence_score": 99,
        "engagement_score": 99,
        "growth_score": 99,
    }


def topic(topic_id: str, b_count: int, h_count: int) -> dict:
    return {
        "id": topic_id,
        "heat_score": 99,
        "platform_metrics": {
            "B站": metric(b_count),
            "小黑盒": metric(h_count),
        },
        "combined_metrics": {"heat_score": 99},
    }


class HeatV1Tests(unittest.TestCase):
    def setUp(self):
        self.rules = load_canonical_rules(ROOT)
        self.policy = self.rules["_heat_policy"]
        self.policy_hash = self.rules["_heat_policy_sha256"]
        self.dashboard = {
            "meta": {},
            "weeks": [
                {
                    "week_id": "2026-W31",
                    "topics": [topic("APEX-T001", 2, 0), topic("APEX-T002", 2, 0)],
                },
                {
                    "week_id": "2026-W32",
                    "topics": [topic("APEX-T001", 2, 0), topic("APEX-T002", 3, 0)],
                },
            ],
        }
        self.bilibili = {
            "meta": {"week_id": "2026_W32"},
            "records": [
                {
                    "canonical_topic_id": "APEX-T001",
                    "is_outlier": False,
                    "bvid": "BV1",
                    "author_uid": "u1",
                    "likes": 1,
                    "views": 100,
                },
                {
                    "canonical_topic_id": "APEX-T001",
                    "is_outlier": False,
                    "bvid": "BV2",
                    "author_uid": "u2",
                    "likes": 3,
                    "views": 200,
                },
                {
                    "canonical_topic_id": "APEX-T002",
                    "is_outlier": False,
                    "bvid": "BV3",
                    "author_uid": "u3",
                    "likes": 4,
                    "views": 400,
                },
                {
                    "canonical_topic_id": "APEX-T002",
                    "is_outlier": False,
                    "bvid": "BV4",
                    "author_uid": "u4",
                    "likes": 6,
                    "views": 800,
                },
                {
                    "canonical_topic_id": "APEX-T002",
                    "is_outlier": False,
                    "bvid": "BV5",
                    "author_uid": "u5",
                    "likes": 8,
                    "views": 1600,
                },
            ],
        }
        self.heybox = {"meta": {"week_id": "2026_W32"}, "records": []}
        self.hashes = {"B站": "b" * 64, "小黑盒": "h" * 64}

    def recalculate(self, heybox=None):
        return recalculate_dashboard_heat_v1(
            self.dashboard,
            self.bilibili,
            self.heybox if heybox is None else heybox,
            target_week_id="2026_W32",
            policy=self.policy,
            policy_hash=self.policy_hash,
            source_artifact_hashes=self.hashes,
        )

    def test_bilibili_and_composite_are_exactly_recalculable(self):
        result = self.recalculate()
        current = result["weeks"][-1]
        for row in current["topics"]:
            bilibili = row["platform_metrics"]["B站"]
            self.assertEqual(bilibili["heat_status"], "calculated")
            self.assertIsInstance(bilibili["heat_score"], float)
            self.assertEqual(row["combined_metrics"]["heat_status"], "calculated")
            self.assertEqual(
                row["combined_metrics"]["heat_score"], bilibili["heat_score"]
            )
            self.assertEqual(bilibili["heat_eligibility_status"], "ELIGIBLE")
            self.assertEqual(
                row["platform_metrics"]["小黑盒"]["heat_eligibility_status"],
                "INELIGIBLE_REACH_UNAVAILABLE",
            )
            self.assertEqual(
                row["platform_metrics"]["小黑盒"]["heat_display"], "N/A"
            )
            self.assertEqual(
                row["combined_metrics"]["heat_platform_weights"], {"B站": 1.0}
            )
            self.assertEqual(
                row["combined_metrics"]["heat_platform_coverage"], "partial"
            )
            for legacy in (
                "discussion_coverage",
                "discussion_volume_score",
                "influence_score",
                "engagement_score",
                "growth_score",
            ):
                self.assertNotIn(legacy, bilibili)
        validation = validate_heat_v1_dashboard(
            result,
            self.bilibili,
            self.heybox,
            target_week_id="2026_W32",
            business_rules=self.rules,
            source_artifact_hashes=self.hashes,
        )
        self.assertTrue(validation["recalculation_match"])
        self.assertTrue(validation["release_ready"])

    def test_ineligible_heybox_is_na_and_does_not_block_composite(self):
        heybox = {
            "meta": {"week_id": "2026_W32"},
            "records": [
                {
                    "canonical_topic_id": "APEX-T001",
                    "is_outlier": False,
                    "text_id": "heybox:1",
                    "likes": 5,
                    "comments": 2,
                    "views": 0,
                }
            ],
        }
        result = self.recalculate(heybox)
        current = result["weeks"][-1]
        first = next(row for row in current["topics"] if row["id"] == "APEX-T001")
        heybox_metric = first["platform_metrics"]["小黑盒"]
        self.assertEqual(
            heybox_metric["heat_status"], "not_applicable_platform_ineligible"
        )
        self.assertEqual(
            heybox_metric["heat_eligibility_status"],
            "INELIGIBLE_REACH_UNAVAILABLE",
        )
        self.assertEqual(heybox_metric["heat_display"], "N/A")
        self.assertIn("reach", heybox_metric["heat_missing_components"])
        self.assertIsNone(heybox_metric["heat_score"])
        self.assertEqual(
            first["combined_metrics"]["heat_score"],
            first["platform_metrics"]["B站"]["heat_score"],
        )
        self.assertEqual(
            first["combined_metrics"]["heat_status"],
            "calculated",
        )
        self.assertEqual(
            first["combined_metrics"]["heat_platform_weights"], {"B站": 1.0}
        )
        self.assertEqual(first["combined_metrics"]["heat_blocked_platforms"], [])
        self.assertEqual(
            first["combined_metrics"]["heat_platform_coverage"], "partial"
        )
        validation = validate_heat_v1_dashboard(
            result,
            self.bilibili,
            heybox,
            target_week_id="2026_W32",
            business_rules=self.rules,
            source_artifact_hashes=self.hashes,
        )
        self.assertTrue(validation["recalculation_match"])
        self.assertTrue(validation["release_ready"])
        self.assertEqual(validation["missing_input_blocks"], [])

    def test_missing_component_on_eligible_bilibili_still_blocks(self):
        bilibili = copy.deepcopy(self.bilibili)
        for row in bilibili["records"]:
            row["views"] = 0
        result = recalculate_dashboard_heat_v1(
            self.dashboard,
            bilibili,
            self.heybox,
            target_week_id="2026_W32",
            policy=self.policy,
            policy_hash=self.policy_hash,
            source_artifact_hashes=self.hashes,
        )
        validation = validate_heat_v1_dashboard(
            result,
            bilibili,
            self.heybox,
            target_week_id="2026_W32",
            business_rules=self.rules,
            source_artifact_hashes=self.hashes,
        )
        self.assertTrue(validation["recalculation_match"])
        self.assertFalse(validation["release_ready"])
        self.assertTrue(
            all("B站" in item for item in validation["missing_input_blocks"])
        )

    def test_validator_rejects_ineligible_platform_score_or_weight(self):
        heybox = {
            "meta": {"week_id": "2026_W32"},
            "records": [
                {
                    "canonical_topic_id": "APEX-T001",
                    "is_outlier": False,
                    "text_id": "heybox:1",
                    "likes": 5,
                    "comments": 2,
                }
            ],
        }
        result = self.recalculate(heybox)
        first = result["weeks"][-1]["topics"][0]
        first["platform_metrics"]["小黑盒"]["heat_score"] = 1.0
        first["combined_metrics"]["heat_platform_weights"] = {
            "B站": 0.5,
            "小黑盒": 0.5,
        }
        validation = validate_heat_v1_dashboard(
            result,
            self.bilibili,
            heybox,
            target_week_id="2026_W32",
            business_rules=self.rules,
            source_artifact_hashes=self.hashes,
        )
        self.assertFalse(validation["recalculation_match"])
        self.assertTrue(
            any("ineligible platform" in error for error in validation["errors"])
        )

    def test_legacy_week_is_byte_semantically_untouched(self):
        before = copy.deepcopy(self.dashboard["weeks"][0])
        result = self.recalculate()
        self.assertEqual(result["weeks"][0], before)
        self.assertEqual(
            result["meta"]["heat_version_boundary"],
            {
                "legacy_through_week": "2026-W31",
                "canonical_from_week": "2026-W32",
                "legacy_recalculated": False,
                "cross_version_scores_directly_comparable": False,
            },
        )

    def test_validator_detects_stored_heat_tampering(self):
        result = self.recalculate()
        result["weeks"][-1]["topics"][0]["platform_metrics"]["B站"][
            "heat_score"
        ] += 1
        validation = validate_heat_v1_dashboard(
            result,
            self.bilibili,
            self.heybox,
            target_week_id="2026_W32",
            business_rules=self.rules,
            source_artifact_hashes=self.hashes,
        )
        self.assertFalse(validation["recalculation_match"])
        self.assertTrue(
            any("heat_score differs" in error for error in validation["errors"])
        )


if __name__ == "__main__":
    unittest.main()
