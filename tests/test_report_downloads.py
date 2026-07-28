import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "templates/APEX_Dashboard_Data_and_Narrative_Guide.md"
LONG_CAPTURE = ROOT / "reports/APEX_W29_Combined_Dashboard_Long_Capture.png"
EXCEL = ROOT / "reports/APEX_CHINA_W30_Weekly_Community_Report.xlsx"
W29_EXCEL = ROOT / "reports/APEX_CHINA_W29_Weekly_Community_Report.xlsx"
WEEKLY_DATA = (
    ROOT / "outputs/bilibili_apex_2026_W30.json",
    ROOT / "outputs/heybox_apex_2026_W30_public_search.json",
    ROOT / "outputs/bilibili_apex_2026_W29.json",
    ROOT / "outputs/heybox_apex_2026_W29_public_search.json",
)
NARRATIVE_RULES = ROOT / "templates/Community_Topic_Driver_Narrative_Rules.md"
HTML_PATHS = [
    ROOT / "index.html",
    ROOT / "game_sentiment_dashboard_apex_W25_W30_mixed_sample.html",
]


class ReportDownloadTests(unittest.TestCase):
    def test_current_artifacts_exist(self):
        self.assertTrue(EXCEL.is_file())
        self.assertTrue(W29_EXCEL.is_file())
        self.assertTrue(LONG_CAPTURE.is_file())
        self.assertTrue(GUIDE.is_file())
        for path in WEEKLY_DATA:
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file())

    def test_download_center_replaces_direct_schema_download(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(source.count('id="downloadModal"'), 1)
                self.assertEqual(source.count("function buildReportInputPackage()"), 1)
                self.assertEqual(source.count("function openDownloadCenter()"), 1)
                self.assertNotIn("APAC_Weekly_Community_Sentiment_Report_Template", source)
                self.assertIn("templates/APEX_Dashboard_Data_and_Narrative_Guide.md", source)
                self.assertIn("reports/APEX_W29_Combined_Dashboard_Long_Capture.png", source)
                self.assertNotIn("reports/APEX_W29_Combined_Dashboard_Landscape.pdf", source)
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

    def test_download_center_exposes_excel_png_guide_and_combined_data(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        for element_id in (
            "downloadW30Report",
            "downloadReportInput",
            "downloadFullDashboard",
            "downloadDashboardLongCapture",
            "downloadDashboardGuide",
        ):
            with self.subTest(element_id=element_id):
                self.assertEqual(source.count(f'id="{element_id}"'), 1)
        self.assertNotIn("Word", source[source.index('<div class="download-grid">'):source.index('<div class="download-spec">')])
        download_grid = source[source.index('<div class="download-grid">'):source.index('<div class="download-spec">')]
        self.assertIn("bilibili_apex_2026_W30.json", download_grid)
        self.assertIn("heybox_apex_2026_W30_public_search.json", download_grid)
        self.assertIn("bilibili_apex_2026_W29.json", download_grid)
        self.assertIn("heybox_apex_2026_W29_public_search.json", download_grid)
        self.assertIn("APEX_CHINA_W29_Weekly_Community_Report.xlsx", download_grid)
        self.assertIn("APEX_CHINA_W29_Weekly_Community_Report.md", download_grid)
        self.assertEqual(source.count('id="downloadDashboardGuide"'), 1)
        self.assertNotIn('id="downloadDashboardPdf"', source)
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

    def test_w30_report_uses_bilingual_driver_form_with_evidence_comments(self):
        with ZipFile(EXCEL) as archive:
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [
                "".join(node.itertext())
                for node in shared_root
                if node.tag.endswith("}si")
            ]
            sheet_root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            cells = {}
            for node in sheet_root.iter():
                if not node.tag.endswith("}c"):
                    continue
                value = next(
                    (child for child in node if child.tag.endswith("}v")),
                    None,
                )
                if value is None:
                    continue
                cells[node.attrib["r"]] = (
                    shared_strings[int(value.text)]
                    if node.attrib.get("t") == "s"
                    else value.text
                )

            self.assertEqual(cells["A1"], "CHINA · W30")
            self.assertEqual(cells["D1"], "中国 · W30")
            self.assertEqual(cells["B4"], "Positive")
            self.assertEqual(cells["B6"], "Neutral")
            self.assertEqual(cells["B8"], "Negative")
            self.assertEqual(cells["A4"], "PLQ Explainer Content")
            self.assertEqual(cells["A6"], "Season 30 Outlook")
            self.assertEqual(cells["A8"], "Ranked Server Stability")
            self.assertEqual(cells["D4"], "PLQ赛制科普内容")
            self.assertIn(
                "xl/threadedcomments/threadedcomment.xml",
                archive.namelist(),
            )
            thread_root = ET.fromstring(
                archive.read("xl/threadedcomments/threadedcomment.xml")
            )
            comments = [
                node for node in thread_root.iter()
                if node.tag.endswith("}threadedComment")
            ]
            self.assertEqual(len(comments), 9)

        narrative = (
            ROOT / "reports/APEX_CHINA_W30_Weekly_Community_Report.md"
        ).read_text(encoding="utf-8")
        self.assertIn("玩家范围 → 评价对象 → 直接反应 → 具体原因 → 结果影响", narrative)
        self.assertIn("本周共有 8 个独立驱动因素通过证据检查", narrative)
        self.assertNotIn("| 赛博朋克联动与手柄体验 | 1 | 2 | 100.0% |", narrative)

    def test_w29_report_uses_w30_bilingual_driver_form(self):
        with ZipFile(W29_EXCEL) as archive:
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [
                "".join(node.itertext())
                for node in shared_root
                if node.tag.endswith("}si")
            ]
            sheet_root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            cells = {}
            for node in sheet_root.iter():
                if not node.tag.endswith("}c"):
                    continue
                value = next(
                    (child for child in node if child.tag.endswith("}v")),
                    None,
                )
                if value is None:
                    continue
                cells[node.attrib["r"]] = (
                    shared_strings[int(value.text)]
                    if node.attrib.get("t") == "s"
                    else value.text
                )

            self.assertEqual(cells["A1"], "CHINA · W29")
            self.assertEqual(cells["D1"], "中国 · W29")
            self.assertEqual(cells["B4"], "Positive")
            self.assertEqual(cells["B6"], "Neutral")
            self.assertEqual(cells["B8"], "Negative")
            self.assertEqual(cells["A4"], "Creator Performance Interest")
            self.assertEqual(cells["D4"], "主播竞技表现关注")
            self.assertIn(
                "xl/threadedcomments/threadedcomment.xml",
                archive.namelist(),
            )
            thread_root = ET.fromstring(
                archive.read("xl/threadedcomments/threadedcomment.xml")
            )
            comments = [
                node for node in thread_root.iter()
                if node.tag.endswith("}threadedComment")
            ]
            self.assertEqual(len(comments), 9)


if __name__ == "__main__":
    unittest.main()
