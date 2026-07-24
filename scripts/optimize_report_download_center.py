from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START = '    <div class="download-grid">'
END = '    <div class="download-spec">'

DOWNLOAD_GRID = """    <div class="download-grid">
      <article class="download-card">
        <strong>① W29 中国区样本周报</strong>
        <p>已完成 W29（7.13—7.19）有限样本周报。B站为评论样本，小黑盒为搜索可见帖子样本；不代表平台全量。</p>
        <div class="download-actions">
          <a class="btn primary" id="downloadW29Report" href="reports/APEX_CHINA_W29_Weekly_Community_Report.xlsx" download>下载 W29 Excel 周报 .xlsx</a>
        </div>
      </article>
      <article class="download-card">
        <strong>② 当前周报告输入包</strong>
        <p>导出中国地区当前周、所选平台、上一周基准、主题指标、真实关键词与方法限制。该文件不会把缺失的官方观看数据伪装成已完成报告。</p>
        <div class="download-actions">
          <button class="btn primary" id="downloadReportInput" type="button">下载当前周输入包 .json</button>
        </div>
      </article>
      <article class="download-card">
        <strong>③ 完整看板数据</strong>
        <p>下载 W25—W29 综合看板数据、横版分页 PDF，以及唯一的数据口径与叙述规则说明。</p>
        <div class="download-actions">
          <button class="btn primary" id="downloadFullDashboard" type="button">下载综合看板数据 .json</button>
          <a class="btn" id="downloadDashboardPdf" href="reports/APEX_W29_Combined_Dashboard_Landscape.pdf" download>下载综合看板横版 PDF</a>
          <a class="btn" id="downloadDashboardGuide" href="templates/APEX_Dashboard_Data_and_Narrative_Guide.md" download>下载数据口径与叙述规则 .md</a>
        </div>
      </article>
    </div>
"""

TRANSLATION_REPLACEMENTS = {
    "['① APAC 中国区报告模板','① APAC China report templates'],": "['① W29 中国区样本周报','① W29 China sample weekly report'],",
    "['下载 Word 主模板 .docx','Download Word master template .docx'],": "",
    "['下载完整数据 .json','Download full data .json'],": "['下载综合看板数据 .json','Download combined dashboard data .json'],",
    "['下载叙述规则 .md','Download narrative rules .md'],": "",
    "['Word 为正式主模板，固定中国地区周报的章节顺序与质量检查规则。','Word is the official master template and fixes the China weekly report section order and quality checks.'],": "",
    "['下载 W25—W29 完整看板数据，或配套叙述规则，用于数据复核与后续报告生成。','Download the complete W25–W28 dashboard data or the companion narrative rules for review and later report generation.'],": "['下载 W25—W29 综合看板数据、横版分页 PDF，以及唯一的数据口径与叙述规则说明。','Download W25–W29 combined dashboard data, the paginated landscape PDF, and the single data-and-narrative guide.'],",
}


def optimize_html(source: str) -> str:
    start = source.index(START)
    end = source.index(END, start)
    source = source[:start] + DOWNLOAD_GRID + source[end:]
    source = source.replace(
        "下载内容已按中国地区周报导出规则整理，仅覆盖中国地区。报告固定采用“概览 → 核心话题 → 情感历史 → UGC/直播观看 → 方法说明 → 数据质量检查”的顺序，并要求结论、归因、证据、对比和影响完整闭环。",
        "下载内容仅覆盖中国地区。W29 样本周报仅提供 Excel；综合看板横版 PDF 按“概览 → 趋势 → 主题 → 风险 → 证据 → 方法边界”分页展示。",
    )
    source = source.replace(
        "Downloads follow the China weekly-report export rules and cover China only. The fixed order is Overview → Top Conversation Drivers → Sentiment History → UGC / Stream Viewership → Methodology Notes → Data Quality Check, using conclusion, attribution, evidence, comparison, and impact.",
        "Downloads cover China only. The W29 sample weekly report is Excel-only; the landscape dashboard PDF is paginated as Overview → Trends → Topics → Risks → Evidence → Method boundaries.",
    )
    for old, new in TRANSLATION_REPLACEMENTS.items():
        source = source.replace(old, new)
    source = source.replace("\n  \n", "\n")
    source = source.replace(
        "template_paths:{word:'templates/APAC_Weekly_Community_Sentiment_Report_Template.docx',markdown:'templates/APAC_Weekly_Community_Sentiment_Report_Template.md',narrative_rules:'templates/Community_Topic_Driver_Narrative_Rules.md'}",
        "download_paths:{dashboard_pdf:'reports/APEX_W29_Combined_Dashboard_Landscape.pdf',data_and_narrative_guide:'templates/APEX_Dashboard_Data_and_Narrative_Guide.md'}",
    )

    grid_end = source.index(END, source.index(START))
    grid = source[source.index(START):grid_end]
    forbidden = {
        "Word template": "Word",
        "Word template download id": "downloadReportTemplateDocx",
        "Bilibili platform JSON": "bilibili_apex_2026_W29.json",
        "Heybox platform JSON": "heybox_apex_2026_W29_public_search.json",
        "standalone scope link": "下载口径说明",
        "old narrative rules link": "downloadNarrativeRules",
    }
    present = [label for label, token in forbidden.items() if token in grid]
    if present:
        raise ValueError(f"download center still contains forbidden items: {present}")

    required = [
        "APEX_CHINA_W29_Weekly_Community_Report.xlsx",
        "APEX_W29_Combined_Dashboard_Landscape.pdf",
        "APEX_Dashboard_Data_and_Narrative_Guide.md",
        "downloadFullDashboard",
    ]
    missing = [token for token in required if token not in grid]
    if missing:
        raise ValueError(f"download center missing required items: {missing}")
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=ROOT / "work/public-opinion")
    args = parser.parse_args()
    repo = args.repo.resolve()
    index = repo / "index.html"
    source = optimize_html(index.read_text(encoding="utf-8"))
    index.write_text(source, encoding="utf-8")

    deliverables = [
        ROOT / "outputs/game_sentiment_dashboard_apex_W25_W29_mixed_sample.html",
        repo / "game_sentiment_dashboard_apex_W25_W29_mixed_sample.html",
    ]
    for path in deliverables:
        path.write_text(source, encoding="utf-8")
    print(json.dumps(
        {"index": str(index), "deliverables": [str(path) for path in deliverables]},
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
