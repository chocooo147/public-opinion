import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/APAC_Weekly_Community_Sentiment_Report_Template.md"
HTML_PATHS = [
    ROOT / "index.html",
    ROOT / "game_sentiment_dashboard_v3.html",
    ROOT / "game_sentiment_dashboard_v5.html",
    ROOT / "game_sentiment_dashboard_apex_W25_W28_mixed_test.html",
    ROOT / "outputs/game_sentiment_dashboard_apex_W25_W28_mixed_test.html",
]


class ReportDownloadTests(unittest.TestCase):
    def test_template_uses_skill_section_order(self):
        source = TEMPLATE.read_text(encoding="utf-8")
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
        source = TEMPLATE.read_text(encoding="utf-8")
        required = (
            "### Executive Summary",
            "### Japan",
            "### China",
            "### Regional Comparison",
            "Positive / Neutral / Mixed / Negative",
            "### Data-Quality Warnings",
            "### Next-Week Watchlist",
            "Conclusion → Attribution → Evidence → Comparison → Impact",
        )
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, source)
        self.assertNotIn("## 7.", source)
        self.assertNotIn("## 8.", source)

    def test_download_center_replaces_direct_schema_download(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(source.count('id="downloadModal"'), 1)
                self.assertEqual(source.count("function buildReportInputPackage()"), 1)
                self.assertEqual(source.count("function openDownloadCenter()"), 1)
                self.assertIn("templates/APAC_Weekly_Community_Sentiment_Report_Template.md", source)
                self.assertIn("apac_weekly_sentiment_report_input_v2", source)
                self.assertIn("export_status:'draft_input_only_not_a_complete_report'", source)
                self.assertIn("japan:{status:'missing'", source)
                self.assertIn("official_viewership:'missing'", source)
                self.assertIn('$("#downloadBtn").onclick=openDownloadCenter;', source)
                self.assertNotIn(
                    '$("#downloadBtn").onclick=()=>downloadJSON(schemaExample', source
                )

    def test_download_center_exposes_three_distinct_artifacts(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        for element_id in (
            "downloadReportTemplate",
            "downloadReportInput",
            "downloadFullDashboard",
        ):
            with self.subTest(element_id=element_id):
                self.assertEqual(source.count(f'id="{element_id}"'), 1)


if __name__ == "__main__":
    unittest.main()
