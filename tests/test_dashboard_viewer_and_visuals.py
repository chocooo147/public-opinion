import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATHS = [
    ROOT / "index.html",
    ROOT / "game_sentiment_dashboard_v3.html",
    ROOT / "game_sentiment_dashboard_v5.html",
    ROOT / "game_sentiment_dashboard_apex_W25_W28_mixed_test.html",
    ROOT / "outputs/game_sentiment_dashboard_apex_W25_W28_mixed_test.html",
    ROOT / "game_sentiment_dashboard_apex_W25_W30_mixed_sample.html",
]


class DashboardViewerAndVisualTests(unittest.TestCase):
    def test_sidebar_drops_empty_sentiment_navigation(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn('data-anchor="sentiment"', source)

    def test_sidebar_art_is_clipped_inside_sidebar(self):
        asset = ROOT / "assets/sidebar-apex-character.png"
        self.assertTrue(asset.is_file())
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            expected_src = (
                "../assets/sidebar-apex-character.png"
                if path.parent.name == "outputs"
                else "assets/sidebar-apex-character.png"
            )
            with self.subTest(path=path.name):
                self.assertIn(
                    f'<img class="sidebar-art" src="{expected_src}" '
                    'alt="" aria-hidden="true" />',
                    source,
                )
                self.assertIn(
                    ".sidebar { overflow-y:auto; overflow-x:hidden;",
                    source,
                )
                self.assertIn(
                    "padding-bottom:0; isolation:isolate; display:flex; "
                    "flex-direction:column;",
                    source,
                )
                self.assertIn(
                    ".sidebar-art-wrap { position:relative; z-index:0; "
                    "flex:0 0 443px; width:calc(100% + 32px); height:443px; "
                    "margin:auto -16px 0; overflow:hidden; }",
                    source,
                )
                self.assertIn(
                    ".sidebar-art-wrap .sidebar-signature { z-index:1; "
                    "bottom:18px; }",
                    source,
                )

    def test_apex_is_seeded_as_fixed_read_only_viewer(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(source.count("const VIEWER_USERNAME='apex';"), 1)
                self.assertEqual(
                    source.count(
                        "const VIEWER_PASSWORD_HASH='314ffd6162923d94123a7010c7c67be278592e5922ac5e3e404d65aa01608293';"
                    ),
                    1,
                )
                self.assertIn("viewer.role='viewer'", source)
                self.assertIn("function requireContentManager()", source)
                self.assertIn("body.viewer-mode #downloadBtn", source)
                self.assertIn("body.viewer-mode #importBtn", source)
                self.assertIn("body.viewer-mode #downloadSchema", source)
                self.assertIn(
                    'if(!requireContentManager()) return;\n  const file=e.target.files[0]',
                    source,
                )

    def test_admin_can_assign_download_or_read_only_access(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn('id="accountRole"', source)
                self.assertIn('<option value="manager">可下载与导入</option>', source)
                self.assertIn('<option value="viewer">只读</option>', source)
                self.assertIn("function canManageContent(account)", source)
                self.assertIn("existing.role=role", source)
                self.assertIn("accounts.push({username,passwordHash,role,active:true", source)
                self.assertIn("$('#accountPassword').required=false", source)

    def test_read_only_account_can_preview_but_not_download_report(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn('id="reportPreviewBtn"', source)
                self.assertNotIn(
                    "body.viewer-mode #reportPreviewBtn",
                    source,
                )
                self.assertIn(
                    "body.viewer-mode #previewDownloadBtn",
                    source,
                )
                self.assertIn(
                    "if(!requireContentManager()) return;",
                    source[
                        source.index("function downloadCurrentPreviewReport()"):
                        source.index("function finiteOrNull")
                    ],
                )

    def test_admin_password_hash_is_rotated(self):
        expected = (
            "const ADMIN_PASSWORD_HASH="
            "'81fbb13319447db0b23f11ece014eeec6f2f661b3922b996bd0b46a9aa759c8c';"
        )
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(source.count(expected), 1)
                self.assertEqual(
                    source.count("const ADMIN_PASSWORD_FALLBACK_FINGERPRINT='71fa9ebc';"),
                    1,
                )

    def test_english_mode_has_canonical_topic_and_event_translations(self):
        current_paths = [ROOT / "index.html", ROOT / "game_sentiment_dashboard_v5.html"]
        for path in current_paths:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("'APEX-T001':'Ranked Play & Matchmaking'", source)
                self.assertIn("'APEX-T013':'Weapon & Legend Strength'", source)
                self.assertIn("(e.title_en||e.title)", source)
                self.assertIn("(e.summary_en||e.summary)", source)
                self.assertIn(
                    "canonicalTopicTranslations[t.id]",
                    source,
                )
                self.assertIn("displayKeyword(x.normalized_keyword)", source)

    def test_t006_uses_presentation_only_clearer_display_name(self):
        expected_alias = "const canonicalTopicDisplayNames={'APEX-T006':'联动活动与体验'};"
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(source.count(expected_alias), 1)
                self.assertIn(
                    "canonicalTopicDisplayNames[t.id]||t.name",
                    source,
                )
                self.assertIn(
                    "'APEX-T006':'Collaboration Events & Experience'",
                    source,
                )
                self.assertNotIn(
                    "'APEX-T006':'Cyberpunk Collaboration & Controller Experience'",
                    source,
                )

        registry_path = (
            ROOT
            / "models"
            / "bertopic_apex_exploratory_v1"
            / "topic_registry_exploratory.json"
        )
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        t006 = next(
            row for row in registry
            if row["canonical_topic_id"] == "APEX-T006"
        )
        self.assertEqual(
            t006["canonical_topic_name"],
            "赛博朋克联动与手柄体验",
        )

    def test_trend_uses_data_scaled_nice_axis(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("const roughStep=rawMaxV/4;", source)
                self.assertIn(
                    "const maxV=Math.ceil(rawMaxV/volumeStep)*volumeStep;",
                    source,
                )
                self.assertNotIn(
                    "Math.ceil(Math.max(...vols)/5000)*5000",
                    source,
                )
                self.assertIn("stroke-width:4", source)

    def test_topic_and_chain_drawers_have_distinct_responsibilities(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(source.count("function openChain(chain)"), 1)
                self.assertIn(
                    "el.onclick=()=>openChain(el.dataset.chain)",
                    source,
                )
                self.assertIn("本周主题快照", source)
                self.assertIn("持续主题追踪", source)
                topic_drawer = source[
                    source.index("function openTopic(id)"):
                    source.index("function closeDrawer()", source.index("function openTopic(id)"))
                ]
                self.assertNotIn('class="timeline"', topic_drawer)
                self.assertIn("openChainDetail", topic_drawer)

    def test_drawers_follow_selected_platform(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("function detailPlatforms()", source)
                self.assertIn(
                    "return state.platform==='综合'?['B站','小黑盒']:[state.platform];",
                    source,
                )
                self.assertIn("function platformChainHistory(", source)
                self.assertIn("metricFor(t,platform)", source)
                self.assertIn("if(state.platform==='小黑盒')", source)
                self.assertIn("不使用B站文本补位", source)
                self.assertIn("不合并为单一正式累计声量", source)


if __name__ == "__main__":
    unittest.main()
