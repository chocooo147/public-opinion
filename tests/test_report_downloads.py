import re
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RULES_MD = ROOT / "templates/社区话题驱动因素表单叙述规则.md"
APPROVED_W28_XLSX = ROOT / "reports/APEX_CHINA_W28_Weekly_Community_Report.xlsx"
HTML_PATHS = [
    ROOT / "index.html",
    ROOT / "game_sentiment_dashboard_v3.html",
    ROOT / "game_sentiment_dashboard_v5.html",
    ROOT / "game_sentiment_dashboard_apex_W25_W28_mixed_test.html",
    ROOT / "outputs/game_sentiment_dashboard_apex_W25_W28_mixed_test.html",
]


class ReportDownloadTests(unittest.TestCase):
    def test_narrative_rules_lock_form_and_ten_topic_output(self):
        source = RULES_MD.read_text(encoding="utf-8")
        required = (
            "CHINA",
            "Weekly Conversations",
            "Engagements",
            "TOPIC / DRIVER",
            "Positive / Neutral / Negative",
            "Narrative / Summary",
            "默认必须输出10个互不重复的话题",
            "前3个为核心驱动因素",
            "后7个为补充驱动因素",
            "才允许少于10个",
            "不得通过拆分同一话题",
        )
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, source)
        self.assertNotIn("Japan", source)
        self.assertNotIn("日本", source)

    def test_approved_w28_excel_matches_locked_two_column_form(self):
        self.assertTrue(APPROVED_W28_XLSX.is_file())
        with zipfile.ZipFile(APPROVED_W28_XLSX) as archive:
            names = set(archive.namelist())
            self.assertIn("xl/worksheets/sheet1.xml", names)
            combined = "".join(
                archive.read(name).decode("utf-8", errors="ignore")
                for name in names
                if name.startswith("xl/") and name.endswith(".xml")
            )
        for token in (
            "CHINA",
            "Weekly conversations",
            "Engagements",
            "TOPIC/DRIVER",
            "SENTIMENT",
        ):
            with self.subTest(token=token):
                self.assertIn(token, combined)
        self.assertEqual(len(re.findall(r"\b(?:Positive|Neutral|Negative)\b", combined)), 10)

    def test_download_center_uses_approved_excel_and_v4_rules(self):
        for path in HTML_PATHS:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(source.count('id="downloadModal"'), 1)
                self.assertEqual(source.count("function buildReportInputPackage()"), 1)
                self.assertEqual(source.count("function openDownloadCenter()"), 1)
                self.assertIn("reports/APEX_CHINA_W28_Weekly_Community_Report.xlsx", source)
                self.assertIn("templates/社区话题驱动因素表单叙述规则.md", source)
                self.assertIn("apex_china_weekly_topic_driver_report_input_v4", source)
                self.assertIn("target_count:10", source)
                self.assertIn("core_count:3", source)
                self.assertIn("supplemental_count:7", source)
                self.assertIn("allow_fewer_only_when_qualified_topics_insufficient:true", source)
                self.assertIn("padding_by_split_repeat_or_noise_forbidden:true", source)
                self.assertIn("report_scope:{region:'China'", source)
                self.assertIn("regions:{\n      china:", source)
                self.assertNotIn("japan:{", source)
                self.assertNotIn("Japan data", source)
                self.assertNotIn("日本数据", source)
                self.assertIn('$("#downloadBtn").onclick=openDownloadCenter;', source)

    def test_download_center_exposes_excel_rules_and_data_artifacts(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        for element_id in (
            "downloadApprovedReportXlsx",
            "downloadNarrativeRulesMd",
            "downloadReportInput",
            "downloadFullDashboard",
        ):
            with self.subTest(element_id=element_id):
                self.assertEqual(source.count(f'id="{element_id}"'), 1)
        self.assertLess(
            source.index('id="downloadApprovedReportXlsx"'),
            source.index('id="downloadNarrativeRulesMd"'),
        )


if __name__ == "__main__":
    unittest.main()
