from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from canonical_rules import (  # noqa: E402
    is_forbidden_keyword,
    iter_visible_keywords,
    load_canonical_rules,
    sanitize_dashboard_keywords,
)
from content_integrity import KEYWORD_RULES, KEYWORD_RULE_VERSION  # noqa: E402
from weekly_release_common import (  # noqa: E402
    load_production_policy,
    verify_policy_asset_hashes,
)


class RuleWorkflowIntegrityTests(unittest.TestCase):
    def test_workflow_v1_config_matches_executable_phase_and_email_boundaries(self):
        workflow = json.loads(
            (ROOT / "config/workflow_v1.json").read_text(encoding="utf-8")
        )
        registry = json.loads(
            (ROOT / "config/automation_entrypoints.json").read_text(
                encoding="utf-8"
            )
        )
        pipeline = (ROOT / "ops/production/weekly_pipeline.py").read_text(
            encoding="utf-8"
        )
        publisher = (ROOT / "scripts/publish_protected_site.py").read_text(
            encoding="utf-8"
        )
        email = (ROOT / "ops/production/send_weekly_email.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(workflow["machine_phases"], ["prepare", "candidate", "publish"])
        self.assertEqual(registry["workflow"]["phases"], workflow["machine_phases"])
        for phase in workflow["machine_phases"]:
            self.assertIn(f'workflow_phase == "{phase}"', pipeline)
        self.assertIn("--candidate-only", publisher)
        self.assertIn("candidate_artifact_reused", publisher)
        self.assertIn("internal-review", email)
        self.assertIn("final-delivery", email)
    def test_machine_policy_hash_and_model_assets_are_pinned(self):
        rules = load_canonical_rules(ROOT)
        policy = load_production_policy(ROOT)
        self.assertEqual(
            rules["_sha256"], policy["canonical_business_rules"]["sha256"]
        )
        verified = verify_policy_asset_hashes(ROOT, policy)
        self.assertEqual(
            verified["topic_registry"]["sha256"],
            policy["model_gate"]["topic_registry_sha256"],
        )
        self.assertEqual(
            verified["topic_mapping"]["sha256"],
            policy["model_gate"]["topic_mapping_sha256"],
        )

    def test_keyword_extractor_uses_canonical_machine_rules(self):
        rules = load_canonical_rules(ROOT)
        self.assertEqual(KEYWORD_RULE_VERSION, rules["keywords"]["rule_version"])
        self.assertEqual(list(KEYWORD_RULES), rules["keywords"]["rules"])

    def test_five_terms_are_removed_from_all_visible_paths(self):
        rules = load_canonical_rules(ROOT)
        forbidden = rules["keywords"]["forbidden_visible_exact_terms"]
        dashboard = {
            "weeks": [
                {
                    "week_id": "2026-W32",
                    "keyword_stats": {
                        "综合": [
                            {"keyword": term, "normalized_keyword": term}
                            for term in forbidden
                        ]
                    },
                    "topics": [
                        {
                            "id": "APEX-T007",
                            "descriptor_keywords": list(forbidden),
                            "keywords": list(forbidden),
                            "platform_keyword_stats": {
                                "B站": [
                                    {"keyword": term, "normalized_keyword": term}
                                    for term in forbidden
                                ]
                            },
                        }
                    ],
                }
            ]
        }
        sanitize_dashboard_keywords(dashboard, rules)
        hits = [
            (path, value)
            for path, value in iter_visible_keywords(dashboard)
            if is_forbidden_keyword(value, rules)
        ]
        self.assertEqual(hits, [])

    def test_topics_and_drivers_are_separate_provenance_layers(self):
        policy = load_production_policy(ROOT)
        driver = load_canonical_rules(ROOT)["weekly_report_drivers"]
        self.assertFalse(driver["data_topic_title_count_granularity_match_required"])
        self.assertTrue(driver["data_topic_and_evidence_provenance_required"])
        self.assertTrue(driver["forced_alignment_forbidden"])
        self.assertEqual(
            driver["high_impact_topic_omission_rule"]["status"],
            "approved_editorial_review_only",
        )
        self.assertIsNone(
            driver["high_impact_topic_omission_rule"]["machine_numeric_threshold"]
        )
        self.assertFalse(
            driver["high_impact_topic_omission_rule"]["machine_hard_gate"]
        )
        validator = (ROOT / "scripts/validate_weekly_release.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("editorial mapping rationale", validator)
        self.assertIn("editorial_judgment_no_numeric_threshold", validator)
        self.assertEqual(
            policy["editorial_workflow"]["product_chain"],
            [
                "raw_community_data",
                "data_topics",
                "evidence_and_editorial_synthesis",
                "weekly_report_drivers",
            ],
        )
        self.assertTrue(policy["editorial_workflow"]["human_approval_required"])
        self.assertEqual(
            policy["editorial_workflow"][
                "single_shot_systemd_integration_status"
            ],
            "checkpointed_workflow_v1",
        )
        self.assertFalse(policy["formal_agents"]["systemd_is_custom_agent_orchestrator"])

    def test_heat_v1_is_hash_pinned_and_approved(self):
        rules = load_canonical_rules(ROOT)
        heat = rules["heat"]
        self.assertEqual(heat["status"], "approved")
        self.assertEqual(heat["rule_version"], "apex-heat-v1.0")
        self.assertEqual(heat["effective_from_week"], "2026_W32")
        self.assertEqual(heat["legacy_through_week"], "2026_W31")
        self.assertEqual(
            heat["canonical_weights"],
            {
                "discussion_intensity": 0.35,
                "discussion_breadth": 0.3,
                "engagement_depth": 0.2,
                "reach": 0.1,
                "momentum": 0.05,
            },
        )
        self.assertEqual(heat["policy_sha256"], rules["_heat_policy_sha256"])
        self.assertTrue(heat["production_release_allowed"])
        self.assertFalse(heat["frontend_recalculation_allowed"])
        self.assertFalse(heat["proxy_or_legacy_fallback_allowed"])
        eligibility = heat["platform_eligibility"]
        self.assertEqual(
            eligibility["policy_version"],
            "apex-heat-platform-eligibility-v1.0",
        )
        self.assertEqual(eligibility["platforms"]["B站"], "ELIGIBLE")
        self.assertEqual(
            eligibility["platforms"]["小黑盒"],
            "INELIGIBLE_REACH_UNAVAILABLE",
        )

    def test_command_authority_has_machine_classification(self):
        registry = json.loads(
            (ROOT / "config/automation_entrypoints.json").read_text(
                encoding="utf-8"
            )
        )
        commands = {item["path"]: item for item in registry["command_registry"]}
        self.assertEqual(
            commands["ops/production/weekly_pipeline.py"]["classification"],
            "current_production",
        )
        self.assertEqual(
            commands["archive/legacy_scripts/**"]["classification"],
            "historical_forbidden_by_default",
        )

    def test_page_reads_metadata_and_does_not_publish_old_formula(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("dashboardData.meta?.canonical_rules", html)
        self.assertIn("Data Topic 不等同于 Weekly Report Driver", html)
        self.assertNotIn("35% × 讨论覆盖度", html)
        self.assertIn("讨论强度 35%", html)
        self.assertIn("仅 Heat-eligible 平台进入综合 Heat", html)
        self.assertIn("仅 Heat-eligible 平台进入综合 Heat", html)
        self.assertIn("INELIGIBLE_REACH_UNAVAILABLE", html)
        self.assertNotIn("function weightedRealMetric", html)


if __name__ == "__main__":
    unittest.main()
