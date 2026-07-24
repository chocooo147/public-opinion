import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "templates/APEX_Dashboard_Data_and_Narrative_Guide.md"
PDF = ROOT / "reports/APEX_W29_Combined_Dashboard_Landscape.pdf"
EXCEL = ROOT / "reports/APEX_CHINA_W29_Weekly_Community_Report.xlsx"
NARRATIVE_RULES = ROOT / "templates/Community_Topic_Driver_Narrative_Rules.md"
HTML_PATHS = [
    ROOT / "index.html",
    ROOT / "game_sentiment_dashboard_apex_W25_W29_mixed_sample.html",
]


class ReportDownloadTests(unittest.TestCase):
    def test_current_artifacts_exist(self):
        self.assertTrue(EXCEL.is_file())
        self.assertTrue(PDF.is_file())
        self.assertTrue(GUIDE.is_file())

    def test_download_center_replaces_direct_schema_download(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(source.count('id="downloadModal"'), 1)
                self.assertEqual(source.count("function buildReportInputPackage()"), 1)
                self.assertEqual(source.count("function openDownloadCenter()"), 1)
                self.assertNotIn("APAC_Weekly_Community_Sentiment_Report_Template", source)
                self.assertIn("templates/APEX_Dashboard_Data_and_Narrative_Guide.md", source)
                self.assertIn("reports/APEX_W29_Combined_Dashboard_Landscape.pdf", source)
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

    def test_download_center_exposes_excel_pdf_guide_and_combined_data(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        for element_id in (
            "downloadW29Report",
            "downloadReportInput",
            "downloadFullDashboard",
            "downloadDashboardPdf",
            "downloadDashboardGuide",
        ):
            with self.subTest(element_id=element_id):
                self.assertEqual(source.count(f'id="{element_id}"'), 1)
        self.assertNotIn("Word", source[source.index('<div class="download-grid">'):source.index('<div class="download-spec">')])
        self.assertNotIn("bilibili_apex_2026_W29.json", source[source.index('<div class="download-grid">'):source.index('<div class="download-spec">')])
        self.assertNotIn("heybox_apex_2026_W29_public_search.json", source[source.index('<div class="download-grid">'):source.index('<div class="download-spec">')])
        self.assertEqual(source.count('id="downloadDashboardGuide"'), 1)
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
