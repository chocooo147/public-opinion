import re
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_MD = ROOT / "templates/APAC_Weekly_Community_Sentiment_Report_Template.md"
TEMPLATE_DOCX = ROOT / "templates/APAC_Weekly_Community_Sentiment_Report_Template.docx"
NARRATIVE_RULES = ROOT / "templates/Community_Topic_Driver_Narrative_Rules.md"
HTML_PATHS = [
    ROOT / "index.html",
    ROOT / "game_sentiment_dashboard_v3.html",
    ROOT / "game_sentiment_dashboard_v5.html",
    ROOT / "game_sentiment_dashboard_apex_W25_W28_mixed_test.html",
    ROOT / "outputs/game_sentiment_dashboard_apex_W25_W28_mixed_test.html",
]


class ReportDownloadTests(unittest.TestCase):
    def test_template_uses_skill_section_order(self):
        source = TEMPLATE_MD.read_text(encoding="utf-8")
        headings = re.findall(r"^## (\d+)\. (.+)$", source, flags=re.MULTILINE)
        self.assertEqual(
            headings,
            [
                ("1", "OVERVIEW"),
                ("2", "TOP CONVERSATION DRIVERS"),
                ("3", "SENTIMENT HISTORY"),
                ("4", "UGC / STREAM VIEWERSHIP"),
                ("5", "METHODOLOGY NOTES"),
                ("6", "DATA QUALITY CHECK"),
            ],
        )

    def test_template_contains_every_required_output(self):
        source = TEMPLATE_MD.read_text(encoding="utf-8")
        required = (
            "### Executive Summary",
            "### China",
            "Positive / Neutral / Mixed / Negative",
            "### Data-Quality Warnings",
            "### Next-Week Watchlist",
            "Conclusion → Attribution → Evidence → Comparison → Impact",
            "China only",
        )
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, source)
        self.assertNotIn("## 7.", source)
        self.assertNotIn("## 8.", source)
        self.assertNotIn("Japan", source)
        self.assertNotIn("日本", source)
        self.assertNotIn("Regional Comparison", source)

    def test_word_is_primary_china_only_template(self):
        self.assertTrue(TEMPLATE_DOCX.is_file())
        with zipfile.ZipFile(TEMPLATE_DOCX) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
        self.assertIn("CHINA WEEKLY", document_xml)
        self.assertIn("China only", document_xml)
        self.assertNotIn("Japan", document_xml)
        self.assertNotIn("日本", document_xml)

    def test_download_center_replaces_direct_schema_download(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(source.count('id="downloadModal"'), 1)
                self.assertEqual(source.count("function buildReportInputPackage()"), 1)
                self.assertEqual(source.count("function openDownloadCenter()"), 1)
                self.assertIn("templates/APAC_Weekly_Community_Sentiment_Report_Template.docx", source)
                self.assertIn("templates/Community_Topic_Driver_Narrative_Rules.md", source)
                self.assertIn("apac_china_weekly_sentiment_report_input_v3", source)
                self.assertIn("export_status:'draft_input_only_not_a_complete_report'", source)
                self.assertIn("report_scope:{region:'China'", source)
                self.assertIn("regions:{\n      china:", source)
                self.assertIn("official_viewership:'missing'", source)
                self.assertNotIn("japan:{", source)
                self.assertNotIn("Japan data", source)
                self.assertNotIn("日本数据", source)
                self.assertIn('$("#downloadBtn").onclick=openDownloadCenter;', source)
                self.assertNotIn(
                    '$("#downloadBtn").onclick=()=>downloadJSON(schemaExample', source
                )

    def test_download_center_exposes_word_rules_and_data_artifacts(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        for element_id in (
            "downloadReportTemplateDocx",
            "downloadReportInput",
            "downloadFullDashboard",
            "downloadNarrativeRules",
        ):
            with self.subTest(element_id=element_id):
                self.assertEqual(source.count(f'id="{element_id}"'), 1)
        self.assertLess(
            source.index('id="downloadFullDashboard"'),
            source.index('id="downloadNarrativeRules"'),
        )
        self.assertNotIn('id="downloadReportTemplateMd"', source)
        self.assertIn("download-actions", source)

    def test_narrative_rules_are_packaged_without_content_changes(self):
        source_candidates = (
            ROOT / "templates/社区话题驱动因素表单叙述规则.md",
            ROOT.parents[1] / "社区话题驱动因素表单叙述规则.md",
        )
        source_rules = next((path for path in source_candidates if path.is_file()), None)
        self.assertIsNotNone(source_rules)
        self.assertTrue(NARRATIVE_RULES.is_file())
        self.assertEqual(NARRATIVE_RULES.read_bytes(), source_rules.read_bytes())


if __name__ == "__main__":
    unittest.main()
