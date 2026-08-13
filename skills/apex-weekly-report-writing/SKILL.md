---
name: apex-weekly-report-writing
description: Write, rewrite, and quality-check APEX China weekly community report narratives in the approved W30 editorial pattern while preserving the W30 bilingual Excel layout. Use for APEX weekly report XLSX or preview JSON work, especially when converting bounded Bilibili and Heybox evidence into concise topic-driver summaries, correcting mechanical model/provenance boilerplate, checking sentiment consistency, or preparing a report for GitHub Pages publication.
version: w30-editorial-driver-selection-mixed-sentiment-2026-08-12
---

# APEX Weekly Report Writing

Produce an editorial weekly synthesis, not a topic-assignment receipt. Treat the W30 workbook in `assets/` as the visual and narrative baseline.

## Required workflow

1. Read the current report input, platform manifests, and evidence rows. Keep Bilibili comments and Heybox search-visible posts as different units.
2. Read `references/w30-writing-pattern.md` before drafting or reviewing any narrative.
3. Open and render `assets/APEX_CHINA_W30_Weekly_Community_Report.xlsx` before editing a workbook. Preserve its one-sheet bilingual structure, styles, merged sentiment cells, row pattern, borders, and comments.
4. Within editorial synthesis, identify the **current-week Event / Issue** represented by the evidence before forming a visible Driver. This is an editorial grouping step, not a new canonical topic and not a change to the frozen topic registry.
5. Form **Driver Candidates** from concrete current-week events/issues. Use canonical topic IDs for traceability in comments or metadata, not as visible report headlines. Multiple Data Topics may merge into one Driver when they describe the same event; one broad Data Topic may split into multiple Drivers when it contains distinct current-week events or player reactions.
6. Rank Driver Candidates by editorial importance before final selection. Evidence qualification only makes a candidate eligible; it does not guarantee inclusion. Consider discussion scale, independent evidence coverage, current-week novelty/change, version/esports/business relevance, engagement, player-experience impact, and evidence reliability. Do not invent a numeric impact score when the current business rules do not define one.
7. Select **10 distinct, evidence-qualified and importance-ranked drivers**. Only reduce the count when the available evidence cannot support 10 without artificial splitting, duplication, or noise; the absolute minimum is 8. A report with 8 or 9 drivers must include the reduction audit described below.
8. Resolve each Driver's sentiment from reviewed evidence using only **Positive / Neutral / Mixed / Negative**. Identify a dominant direction first and preserve meaningful minority caveats in the narrative. Use Neutral only for mechanism understanding, information discussion, problem definition, analysis, or discussion without a clear evaluative direction. Use Mixed only when Positive and Negative reactions both have substantive, traceable support and neither direction clearly dominates. Do not downgrade a clearly dominant Positive or Negative reaction to Neutral or Mixed merely because a smaller opposing view exists. Model output is supporting evidence, not the final editorial vote.
9. Write the Chinese narrative first, then write an equivalent English narrative. Do not translate mechanically if that makes the English unnatural.
10. Check every driver against the content test below, then run `scripts/validate_narratives.py` on the preview JSON.
11. Render the completed workbook and visually compare it with the W30 asset before release.

## Editorial synthesis and selection rules

- Treat `Data Topic` and `Weekly Report Driver` as different product layers. Never use a canonical topic label as the final Driver solely because records were assigned to it.
- The current-week Event / Issue layer must identify what actually happened or what concrete object players discussed this week: for example a Legend rework, weapon balance change, ammo rework, loot-system change, cosmetic pack, tournament, or technical issue.
- Prefer a concrete event/object as the Driver headline. Keep higher-order interpretations such as `Trust`, `Friction`, `Uncertainty`, `Pressure`, or monetization intent in the narrative unless repeated direct evidence shows that the abstract concept itself is the community's discussion object.
- Split distinct events even when they share one Data Topic. Merge evidence across Data Topics when it describes the same concrete current-week event.
- Each current Data Topic must retain an editorial disposition and rationale according to the canonical business rules. Exclusion or omission is allowed when the evidence does not support a sufficiently important, independent Driver.
- Do not select a candidate only because its evidence is internally coherent. Final selection must answer: **Is this one of the most important things the client should know about the community this week?**
- Preserve source limitations in the overview, methodology, evidence comments, or internal audit. Do not turn bounded samples into platform-wide or community-wide incidence claims.

## Content test for every driver

Write one to three compact sentences that answer all four questions:

1. Who reacted or discussed the topic?
2. What exactly did they welcome, reject, question, report, or compare?
3. Which concrete details explain that reaction?
4. What did the reaction affect: understanding, interest, play continuity, trust, participation, or the ability to form a consensus?

Use bounded subjects such as `部分玩家`, `赛事观众`, `少量玩家`, or `一篇公开搜索可见帖子`. Match the strength of the subject to the evidence.

## Sentiment resolution

- Determine sentiment from the **direction and breadth of reviewed evidence**, not from model majority alone.
- Use only `Positive`, `Neutral`, `Mixed`, or `Negative`.
- Use Neutral only when the principal content is mechanism understanding, information discussion, problem definition, analysis, verification, or another discussion without a clear evaluative direction. Neutral is never the default bucket for opposing evaluations.
- Use Mixed only when both Positive and Negative reactions have substantive, traceable evidence and neither direction clearly dominates across evidence breadth, repeated occurrence, source scope, and representativeness. Do not invent a fixed percentage or other numeric threshold.
- If one direction clearly dominates across independent evidence, label it Positive or Negative and state any meaningful minority concern as a caveat.
- Do not convert a broadly Positive or Negative Driver to Neutral or Mixed merely because a smaller group asks questions, accepts, adapts to, or raises a secondary concern.

## Non-negotiable rules

- Synthesize multiple evidence points into a finding. Do not paste one representative comment and call it a summary.
- Put sample counts, model status, provenance, and unit warnings in the overview or methodology. Do not repeat them in each driver narrative.
- Do not start a driver with `在本周有限样本中` or `Within this bounded weekly sample`.
- Do not write `被归入`, `代表性观察涉及`, `model-derived and exploratory`, or equivalent pipeline language in a driver narrative.
- Do not show `(APEX-Txxx)` in the visible driver title. Preserve the canonical ID in evidence comments or structured metadata.
- Do not infer causality, platform-wide incidence, or community consensus from a bounded sample.
- Do not infer community-wide trust, monetization intent, churn, or purchase impact from isolated comments. Such conclusions require repeated direct evidence.
- When only one search-visible post supports a driver, identify it as one post and state the missing-comment or unconfirmed-detail limitation in editorial language.
- Keep direct quotations short and purposeful. Paraphrase the evidence into the report's voice.
- Never rename or alter the frozen canonical topic registry. A report headline may be narrower and evidence-led while retaining the canonical ID in metadata.

## Driver-count gate

- The normal weekly report contains exactly **10 drivers**. Ten is the editorial standard, not an optional maximum.
- Use 8 or 9 drivers only when the reviewed evidence genuinely cannot support 10 independent, importance-qualified findings. Never publish fewer than 8.
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

Before accepting the narratives, verify that:

- each visible Driver is tied to a concrete current-week Event / Issue;
- the selected Drivers are importance-ranked rather than merely evidence-qualified;
- no broad canonical Topic has swallowed distinct high-value events that should be separate Drivers;
- no abstract headline overstates what players directly discussed;
- the sentiment label reflects the dominant reviewed evidence and preserves meaningful minority caveats;
- every current Data Topic has the required editorial disposition and provenance.

The report fails if any driver contains pipeline boilerplate, visible canonical IDs, missing reaction/impact language, excessive length, or a bilingual structure mismatch. Fix the narratives; do not weaken the validator to pass a report.

After the narrative gate passes, run the normal workbook contract validation, formula/error scan, archive check, and visual render comparison. Do not publish until both editorial and workbook checks pass.
