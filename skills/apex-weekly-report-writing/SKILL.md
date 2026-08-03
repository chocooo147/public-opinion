---
name: apex-weekly-report-writing
description: Write, rewrite, and quality-check APEX China weekly community report narratives in the approved W30 editorial pattern while preserving the W30 bilingual Excel layout. Use for APEX weekly report XLSX or preview JSON work, especially when converting bounded Bilibili and Heybox evidence into concise topic-driver summaries, correcting mechanical model/provenance boilerplate, checking sentiment consistency, or preparing a report for GitHub Pages publication.
---

# APEX Weekly Report Writing

Produce an editorial weekly synthesis, not a topic-assignment receipt. Treat the W30 workbook in `assets/` as the visual and narrative baseline.

## Required workflow

1. Read the current report input, platform manifests, and evidence rows. Keep Bilibili comments and Heybox search-visible posts as different units.
2. Read `references/w30-writing-pattern.md` before drafting or reviewing any narrative.
3. Open and render `assets/APEX_CHINA_W30_Weekly_Community_Report.xlsx` before editing a workbook. Preserve its one-sheet bilingual structure, styles, merged sentiment cells, row pattern, borders, and comments.
4. Form editorial drivers from coherent evidence. Use canonical topic IDs for traceability in comments or metadata, not as the visible report headline.
5. Select **10 distinct, evidence-qualified drivers**. Only reduce the count when the available evidence cannot support 10 without artificial splitting, duplication, or noise; the absolute minimum is 8. A report with 8 or 9 drivers must include the reduction audit described below.
6. Write the Chinese narrative first, then write an equivalent English narrative. Do not translate mechanically if that makes the English unnatural.
7. Check every driver against the content test below, then run `scripts/validate_narratives.py` on the preview JSON.
8. Render the completed workbook and visually compare it with the W30 asset before release.

## Content test for every driver

Write two or three compact sentences that answer all four questions:

1. Who reacted or discussed the topic?
2. What exactly did they welcome, reject, question, report, or compare?
3. Which concrete details explain that reaction?
4. What did the reaction affect: understanding, interest, play continuity, trust, participation, or the ability to form a consensus?

Use bounded subjects such as `部分玩家`, `赛事观众`, `少量玩家`, or `一篇公开搜索可见帖子`. Match the strength of the subject to the evidence.

## Non-negotiable rules

- Synthesize multiple evidence points into a finding. Do not paste one representative comment and call it a summary.
- Put sample counts, model status, provenance, and unit warnings in the overview or methodology. Do not repeat them in each driver narrative.
- Do not start a driver with `在本周有限样本中` or `Within this bounded weekly sample`.
- Do not write `被归入`, `代表性观察涉及`, `model-derived and exploratory`, or equivalent pipeline language in a driver narrative.
- Do not show `(APEX-Txxx)` in the visible driver title. Preserve the canonical ID in evidence comments or structured metadata.
- Do not infer causality, platform-wide incidence, or community consensus from a bounded sample.
- When evidence conflicts, state the contrast and use Neutral or Mixed. Do not force a positive or negative label from the model majority.
- When only one search-visible post supports a driver, identify it as one post and state the missing-comment or unconfirmed-detail limitation in editorial language.
- Keep direct quotations short and purposeful. Paraphrase the evidence into the report's voice.
- Never rename or alter the frozen canonical topic registry. A report headline may be narrower and evidence-led while retaining the canonical ID in metadata.

## Driver-count gate

- The normal weekly report contains exactly **10 drivers**. Ten is the editorial standard, not an optional maximum.
- Use 8 or 9 drivers only when the reviewed evidence genuinely cannot support 10 independent findings. Never publish fewer than 8.
- Do not reach 10 by splitting one finding into near-duplicates, repeating the same evidence under different headlines, promoting irrelevant/noisy rows, or treating a raw quote as a separate driver.
- When the report has 8 or 9 drivers, the preview JSON must contain a top-level `driver_reduction` object with:
  - `target_count: 10`
  - `actual_count` equal to the number of drivers
  - a specific, evidence-based `reason`
  - `padding_forbidden: true`
  - `excluded_candidates`, with at least one candidate and exclusion reason for every missing driver
- The reduction audit is internal metadata. Keep it out of visible driver narratives, but preserve it for review and release validation.
- `--allow-legacy-reference` exists only to validate historical reference files created before this rule. Never use it for a newly generated weekly report.

## W30 workbook contract

- Use one worksheet with English in A:B, a spacer in C, and Chinese in D:E.
- Use rows 1–2 for the bilingual overview, row 3 for headers, and 10 evidence-qualified drivers in title/narrative pairs at rows `4/5`, `6/7`, `8/9`, `11/12`, `13/14`, `15/16`, `17/18`, `19/20`, `21/22`, and `23/24`.
- Merge each sentiment cell across its driver pair; the third driver spans rows 8–10 because row 10 is retained as template spacing.
- If a documented evidence shortage reduces the report to 8 or 9 drivers, remove only the unused trailing pair or pairs; do not leave blank drivers between populated rows.
- Keep the driver title bold, the narrative italic, and the sentiment centered with W30 color semantics.
- Preserve evidence comments and source URLs without exposing raw source paths or local filesystem paths.

## Quality gate

Run:

```bash
python scripts/validate_narratives.py path/to/report.preview.json
```

The report fails if any driver contains pipeline boilerplate, visible canonical IDs, missing reaction/impact language, excessive length, or a bilingual structure mismatch. Fix the narratives; do not weaken the validator to pass a report.

After the narrative gate passes, run the normal workbook contract validation, formula/error scan, archive check, and visual render comparison. Do not publish until both editorial and workbook checks pass.
