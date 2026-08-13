import json
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "templates/APEX_Dashboard_Data_and_Narrative_Guide.md"
LONG_CAPTURE = ROOT / "reports/APEX_W29_Combined_Dashboard_Long_Capture.png"
EXCEL = ROOT / "reports/APEX_CHINA_W30_Weekly_Community_Report.xlsx"
CURRENT_EXCEL = ROOT / "reports/APEX_CHINA_W31_Weekly_Community_Report.xlsx"
W29_EXCEL = ROOT / "reports/APEX_CHINA_W29_Weekly_Community_Report.xlsx"
CURRENT_WEEKLY_DATA = (
    ROOT / "outputs/bilibili_apex_2026_W31.json",
    ROOT / "outputs/heybox_apex_2026_W31_public_search.json",
)
WEEKLY_DATA = (
    ROOT / "outputs/bilibili_apex_2026_W30.json",
    ROOT / "outputs/heybox_apex_2026_W30_public_search.json",
)
NARRATIVE_RULES = ROOT / "templates/Community_Topic_Driver_Narrative_Rules.md"
REPORT_CONTRACT = ROOT / "config/weekly_bilingual_report_contract.json"
REPORT_VALIDATOR = ROOT / "scripts/validate_weekly_report_contract.py"
REPORT_PREVIEW = (
    ROOT / "reports/APEX_CHINA_W30_Weekly_Community_Report.preview.json"
)
CURRENT_REPORT_PREVIEW = (
    ROOT / "reports/APEX_CHINA_W31_Weekly_Community_Report.preview.json"
)
REPORT_PREVIEW_BUILDER = ROOT / "scripts/build_weekly_report_preview.py"
HTML_PATHS = [
    ROOT / "index.html",
    ROOT / "game_sentiment_dashboard_apex_W25_W30_mixed_sample.html",
]


class ReportDownloadTests(unittest.TestCase):
    def test_current_artifacts_exist(self):
        self.assertTrue(CURRENT_EXCEL.is_file())
        self.assertTrue(EXCEL.is_file())
        self.assertTrue(W29_EXCEL.is_file())
        self.assertTrue(LONG_CAPTURE.is_file())
        self.assertTrue(GUIDE.is_file())
        self.assertTrue(CURRENT_REPORT_PREVIEW.is_file())
        self.assertTrue(REPORT_PREVIEW_BUILDER.is_file())
        for path in CURRENT_WEEKLY_DATA:
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
                if path.name == "index.html":
                    self.assertNotIn('href="templates/', source)
                    self.assertNotIn('href="outputs/', source)
                else:
                    self.assertIn("templates/APEX_Dashboard_Data_and_Narrative_Guide.md", source)
                    self.assertIn("reports/APEX_W29_Combined_Dashboard_Long_Capture.png", source)
                self.assertNotIn("reports/APEX_W29_Combined_Dashboard_Landscape.pdf", source)
                self.assertIn("apac_china_weekly_sentiment_report_input_v4", source)
                self.assertIn("export_status:'draft_input_only_not_a_complete_report'", source)
                self.assertIn("history_scope:'current_week_only'", source)
                self.assertIn("report_scope:{region:'China'", source)
                self.assertIn("regions:{\n      china:", source)
                self.assertIn("official_viewership:'missing'", source)
                self.assertIn("historical_weeks:'omitted_by_current_week_only_policy'", source)
                self.assertNotIn("previous_week:previousSummary", source)
                self.assertNotIn("sentiment_history:dashboardData.weeks", source)
                self.assertNotIn("japan:{", source)
                self.assertNotIn("Japan data", source)
                self.assertNotIn("日本数据", source)
                self.assertIn('$("#downloadBtn").onclick=openDownloadCenter;', source)
                self.assertNotIn(
                    '$("#downloadBtn").onclick=()=>downloadJSON(schemaExample', source
                )

    def test_current_report_preview_is_above_download_center(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(source.count('id="reportPreviewBtn"'), 1)
                self.assertEqual(source.count('id="reportPreviewModal"'), 1)
                self.assertEqual(source.count("async function openReportPreview()"), 1)
                self.assertEqual(
                    source.count(
                        "reports/APEX_CHINA_W31_Weekly_Community_Report.preview.json"
                        if path.name == "index.html"
                        else "reports/APEX_CHINA_W30_Weekly_Community_Report.preview.json"
                    ),
                    1,
                )
                self.assertLess(
                    source.index('id="reportPreviewBtn"'),
                    source.index('id="downloadBtn"'),
                )

    def test_report_preview_uses_one_aligned_center_divider(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn(
                    ".report-preview-title > div + div "
                    "{ border-left:1px solid #f5f5f2; }",
                    source,
                )
                self.assertIn(
                    ".report-preview-bilingual-head span:nth-child(3) "
                    "{ border-left:1px solid #8f8f8f; }",
                    source,
                )
                self.assertIn(
                    ".report-preview-bilingual-row "
                    ".report-preview-copy:nth-child(3) "
                    "{ border-left:1px solid #9a9a9a; }",
                    source,
                )
                self.assertNotIn(
                    ".report-preview-bilingual-head::after,"
                    ".report-preview-bilingual-row::after",
                    source,
                )
                self.assertIn(
                    '$("#reportPreviewBtn").onclick=openReportPreview;',
                    source,
                )
                preview_function = source[
                    source.index("async function openReportPreview()"):
                    source.index("function closeReportPreview()")
                ]
                self.assertIn("requireAuthenticated()", preview_function)
                self.assertNotIn("requireContentManager()", preview_function)
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

    def test_w30_report_preview_matches_the_validated_workbook(self):
        preview = json.loads(REPORT_PREVIEW.read_text(encoding="utf-8"))
        self.assertEqual(
            preview["schema_version"],
            "apex_weekly_report_preview_v1",
        )
        self.assertEqual(preview["week_id"], "2026_W30")
        self.assertEqual(preview["period"]["label"], "7.20—7.26")
        self.assertEqual(
            preview["layout"],
            "single_sheet_bilingual_side_by_side",
        )
        self.assertEqual(preview["driver_count"], 8)
        self.assertEqual(preview["driver_count"], len(preview["drivers"]))
        self.assertEqual(
            [item["sentiment_en"] for item in preview["drivers"][:3]],
            ["Positive", "Neutral", "Negative"],
        )
        self.assertEqual(
            preview["drivers"][0]["topic_en"],
            "PLQ Explainer Content",
        )
        self.assertEqual(
            preview["drivers"][0]["topic_zh"],
            "PLQ赛制科普内容",
        )
        self.assertEqual(
            preview["source"]["sha256"],
            __import__("hashlib").sha256(EXCEL.read_bytes()).hexdigest(),
        )

    def test_w31_report_preview_matches_the_validated_workbook(self):
        preview = json.loads(CURRENT_REPORT_PREVIEW.read_text(encoding="utf-8"))
        self.assertEqual(preview["week_id"], "2026_W31")
        self.assertEqual(preview["period"]["label"], "7.27—8.2")
        self.assertEqual(preview["driver_count"], 10)
        self.assertEqual(preview["driver_count"], len(preview["drivers"]))
        self.assertEqual(
            [item["sentiment_en"] for item in preview["drivers"][:3]],
            ["Positive", "Positive", "Negative"],
        )
        self.assertEqual(
            preview["drivers"][0]["topic_en"],
            "ENC Qualifying Performance",
        )
        self.assertEqual(
            preview["drivers"][0]["topic_zh"],
            "ENC资格赛表现",
        )
        self.assertEqual(
            preview["source"]["sha256"],
            __import__("hashlib").sha256(CURRENT_EXCEL.read_bytes()).hexdigest(),
        )

    def test_download_center_exposes_excel_png_guide_and_combined_data(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        for element_id in (
            "downloadW31Report",
            "downloadW30HistoricalReport",
            "downloadReportInput",
            "downloadFullDashboard",
            "downloadCurrentMethodology",
        ):
            with self.subTest(element_id=element_id):
                self.assertEqual(source.count(f'id="{element_id}"'), 1)
        self.assertNotIn("Word", source[source.index('<div class="download-grid">'):source.index('<div class="download-spec">')])
        download_grid = source[source.index('<div class="download-grid">'):source.index('<div class="download-spec">')]
        self.assertNotIn("bilibili_apex_2026_W31.json", download_grid)
        self.assertNotIn("heybox_apex_2026_W31_public_search.json", download_grid)
        self.assertNotIn("bilibili_apex_2026_W30.json", download_grid)
        self.assertNotIn("heybox_apex_2026_W30_public_search.json", download_grid)
        self.assertIn("APEX_CHINA_W30_Weekly_Community_Report.xlsx", download_grid)
        self.assertNotIn("APEX_CHINA_W29_Weekly_Community_Report.md", download_grid)
        self.assertEqual(
            download_grid.count("APEX_CHINA_W31_Weekly_Community_Report.md"),
            1,
        )
        self.assertEqual(source.count('id="downloadDashboardGuide"'), 0)
        self.assertNotIn('id="downloadDashboardPdf"', source)
        self.assertIn("download-actions", source)

    def test_stable_w30_report_contract_is_packaged(self):
        self.assertTrue(REPORT_CONTRACT.is_file())
        self.assertTrue(REPORT_VALIDATOR.is_file())
        contract = __import__("json").loads(REPORT_CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["layout"]["worksheet_count"], 1)
        self.assertEqual(
            contract["layout"]["worksheet_structure"],
            "single_sheet_bilingual_side_by_side",
        )
        self.assertEqual(contract["driver_policy"]["target_count"], 10)
        self.assertEqual(contract["driver_policy"]["minimum_count"], 8)
        self.assertEqual(contract["driver_policy"]["maximum_count"], 10)
        self.assertTrue(
            contract["driver_policy"][
                "reduction_only_when_independent_evidence_qualified_drivers_are_insufficient"
            ]
            if "reduction_only_when_independent_evidence_qualified_drivers_are_insufficient"
            in contract["driver_policy"]
            else "independent evidence-qualified" in contract["driver_policy"]["reduction_rule"]
        )

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
