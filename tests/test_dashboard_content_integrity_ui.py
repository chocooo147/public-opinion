import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from weekly_release_common import (  # noqa: E402
    _combined_metric,
    _platform_metric,
)


def load_publisher():
    spec = importlib.util.spec_from_file_location(
        "publish_protected_site_content_ui",
        ROOT / "scripts/publish_protected_site.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DashboardContentIntegrityUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.publisher = load_publisher()

    def test_no_new_standalone_top_keyword_or_high_frequency_block(self):
        self.assertNotIn('id="topKeywordOverview"', self.source)
        self.assertNotIn('id="topKeywordList"', self.source)
        self.assertNotIn("function renderTopKeywords()", self.source)
        self.assertIn("stats.slice(0,30)", self.source)
        self.assertIn("sortKeywordStats", self.source)
        self.assertIn("occurrence_count", self.source)
        self.assertIn("function openKeywordDrawer()", self.source)
        self.assertIn('loc("有效关键词","Observed keywords")', self.source)
        self.assertNotIn('loc("TOP关键词","Top keywords")', self.source)
        self.assertNotIn('<h3 class="panel-title">高频关键词</h3>', self.source)
        self.assertNotIn('id="keywordCloud"', self.source)

    def test_main_keyword_fallback_and_platform_quality_state_are_distinct(self):
        self.assertIn("const topicMainKeywords=t=>", self.source)
        self.assertIn("kind:'descriptor'", self.source)
        self.assertIn("主题描述词：", self.source)
        self.assertIn("主题语义描述", self.source)
        self.assertIn("严格平台关键词（已通过质量校验）", self.source)
        self.assertIn("上方主题描述词仅用于语义说明，不代表质量通过", self.source)
        self.assertIn("rows.filter(x=>x?.quality_status==='passed')", self.source)

    def test_data_topic_methodology_is_preserved_and_heat_uses_v1_metadata(self):
        self.assertIn("function heatBreakdownHtml(t)", self.source)
        self.assertIn("BERTopic 对每条文本执行只读 transform", self.source)
        self.assertIn("Data Topic 不等同于 Weekly Report Driver", self.source)
        self.assertIn("计算主题热议度公式", self.source)
        self.assertIn("apex-heat-v1.0", self.source)
        self.assertIn("讨论强度 35%", self.source)
        self.assertIn("讨论广度 30%", self.source)
        self.assertIn("参与深度 20%", self.source)
        self.assertIn("触达 10%", self.source)
        self.assertIn("升温 5%", self.source)
        self.assertIn("frontend_recalculation_allowed:false", self.source)
        self.assertIn("if(value===null||value===undefined||value==='') return '—';", self.source)
        self.assertNotIn("35% × 讨论覆盖度", self.source)
        self.assertNotIn("60% × 覆盖视频得分", self.source)
        self.assertNotIn("weightedRealMetric", self.source)

    def test_sidebar_brand_is_exact_chocooo(self):
        self.assertIn(
            '<span class="brand-divider">/</span>'
            '<span class="apex-wordmark">APEX</span>',
            self.source,
        )
        self.assertIn(
            '<div class="sidebar-signature" aria-label="chocooo">chocooo</div>',
            self.source,
        )
        self.assertNotIn('<span class="apex-wordmark">chocooo</span>', self.source)
        self.assertNotIn(
            '<div class="sidebar-signature" aria-label="APEX">APEX</div>',
            self.source,
        )

    def test_privacy_scanner_allows_only_exact_public_brand_markup(self):
        whitelist = {
            "forbidden_public_prefixes": [],
            "forbidden_public_names": [],
            "sanitized_dashboard_keys": [],
        }
        with tempfile.TemporaryDirectory(prefix="apex-brand-scan-") as temp:
            index = Path(temp) / "index.html"
            index.write_text(
                '<div class="sidebar-signature" aria-label="chocooo">chocooo</div>',
                encoding="utf-8",
            )
            self.assertEqual(
                self.publisher._privacy_scan(Path(temp), whitelist)["errors"], []
            )
            index.write_text(
                '<div class="sidebar-signature" aria-label="chocooo">chocooo</div>'
                '<p>choco</p>',
                encoding="utf-8",
            )
            errors = self.publisher._privacy_scan(Path(temp), whitelist)["errors"]
            self.assertTrue(any("private marker 'choco'" in item for item in errors))

    def test_platform_metric_cannot_emit_the_removed_proxy(self):
        records = [
            {"likes": 3, "comments": 5, "bvid": "BV1"},
            {"likes": 7, "comments": 11, "bvid": "BV2"},
        ]
        metric = _platform_metric(
            records, None, platform="B站", simulated=False
        )
        self.assertIsNone(metric["heat_score"])
        for field in (
            "discussion_coverage",
            "discussion_volume_score",
            "influence_score",
            "engagement_score",
            "growth_score",
        ):
            self.assertNotIn(field, metric)

        empty = _platform_metric([], None, platform="小黑盒", simulated=False)
        combined = _combined_metric(metric, empty, simulated=False)
        self.assertIsNone(combined["heat_score"])

    def test_five_week_sentiment_schema_compatibility_is_explicit(self):
        self.assertIn("function sentimentBackendForWeek", self.source)
        self.assertIn("legacy_week_sentiment", self.source)
        self.assertIn("percentFromLegacy", self.source)
        self.assertIn("dashboardData.weeks.slice(-5)", self.source)

    def test_published_default_week_and_notice_override_stale_copy(self):
        self.assertIn("function defaultDashboardWeekIndex()", self.source)
        self.assertIn("dashboardData.meta?.default_week_id", self.source)
        self.assertIn("state.weekIndex=defaultDashboardWeekIndex()", self.source)
        self.assertIn('id="sidebarDataNotice"', self.source)
        self.assertIn("dashboardData.meta?.notice", self.source)
        self.assertNotIn("week_id==='2026-W31'", self.source)

    def test_chain_drawer_uses_sources_and_responsive_grid(self):
        self.assertIn("按周代表来源", self.source)
        self.assertIn("不回退展示评论正文", self.source)
        self.assertIn("if(raw==null) return null", self.source)
        self.assertIn('grid-template-areas:"label bar bar bar"', self.source)
        self.assertIn("overflow-wrap:anywhere", self.source)

    def test_public_source_cards_are_allowlisted_and_hide_heybox_body(self):
        self.assertIn("function validatedRepresentativeHref(item)", self.source)
        self.assertIn("www\\.bilibili\\.com\\/video", self.source)
        self.assertIn("www\\.xiaoheihe\\.cn\\/app\\/bbs\\/link", self.source)
        private = {
            "representative_contents": [
                {
                    "platform": "bilibili",
                    "content_type": "video",
                    "content_id": "BV1LXMo6kEeC",
                    "title": "公开视频标题",
                    "url": "https://www.bilibili.com/video/BV1LXMo6kEeC",
                    "topic_text_count": 4,
                    "text": "private comment",
                },
                {
                    "platform": "heybox",
                    "content_type": "post",
                    "content_id": "187297674",
                    "title": "这是不应公开的完整帖子正文",
                    "url": "https://www.xiaoheihe.cn/app/bbs/link/187297674",
                    "topic_text_count": 1,
                },
                {
                    "platform": "bilibili",
                    "content_type": "video",
                    "content_id": "BV1LXMo6kEeC",
                    "title": "链接不匹配",
                    "url": "https://www.bilibili.com/video/BV1pyuG6PEbE",
                    "topic_text_count": 1,
                },
            ],
            "representative_content_count": 3,
        }
        public = self.publisher._normalize_public_representative_contents(
            private, {"content_id", "url", "text"}
        )
        items = public["representative_contents"]
        self.assertEqual(public["representative_content_count"], 3)
        self.assertEqual(items[0]["source_label"], "BV1LXMo6kEeC")
        self.assertEqual(
            items[0]["source_href"],
            "https://www.bilibili.com/video/BV1LXMo6kEeC",
        )
        self.assertEqual(items[1]["title"], "小黑盒帖子 187297674")
        self.assertNotIn("完整帖子正文", json.dumps(public, ensure_ascii=False))
        self.assertFalse(items[2]["source_available"])
        self.assertNotIn("source_href", items[2])
        self.assertNotIn("content_id", json.dumps(public))
        self.assertNotIn("private comment", json.dumps(public))


if __name__ == "__main__":
    unittest.main()
