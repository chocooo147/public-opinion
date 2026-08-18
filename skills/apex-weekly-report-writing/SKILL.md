---
name: apex-weekly-report-writing
description: Write, rewrite, and quality-check APEX China weekly community report narratives in the approved W30 editorial pattern while preserving the W30 bilingual Excel layout. Use for APEX weekly report XLSX or preview JSON work, especially when converting bounded Bilibili and Heybox evidence into concise topic-driver summaries, correcting mechanical model/provenance boilerplate, checking sentiment consistency, or preparing a report for protected production publication.
version: w30-editorial-calibration-v1-2026-08-18
---

# APEX Weekly Report Writing

Produce an editorial weekly synthesis, not a topic-assignment receipt. Treat the W30 workbook in `assets/` as the visual and narrative baseline.

## Required workflow

1. Read the current report input, platform manifests, Data Topics, and evidence rows. Keep Bilibili comments and Heybox search-visible posts as different units.
2. Read `references/w30-writing-pattern.md` before drafting or reviewing any narrative.
3. Open and render `assets/APEX_CHINA_W30_Weekly_Community_Report.xlsx` before editing a workbook. Preserve its one-sheet bilingual structure, styles, merged sentiment cells, row pattern, borders, and comments.
4. Within editorial synthesis, enumerate the complete **current-week Event / Issue inventory** represented by the reviewed evidence before ranking visible Drivers. This is an editorial grouping step, not a new canonical topic and not a change to the frozen topic registry.
5. Form **Driver Candidates** from concrete current-week events/issues. Use canonical topic IDs for traceability in comments or metadata, not as visible report headlines. Multiple Data Topics may merge into one Driver when they describe the same event; one broad Data Topic may split into multiple Drivers when it contains distinct current-week events or player reactions.
6. Assign each Driver Candidate a qualitative editorial priority band: **A / B / C / D**. This is a review ladder, not a numeric impact score.
7. Resolve event coverage and granularity before final ranking. Every enumerated Event / Issue must receive an editorial disposition of `Selected`, `Merged`, `Split`, or `Excluded` with traceable rationale. Band-A events require the earliest review and must not be silently displaced by lower-priority candidates. This is an editorial review requirement and does not change any canonical machine hard-gate setting.
8. Rank the surviving Driver Candidates by editorial importance. Evidence qualification only makes a candidate eligible; it does not guarantee inclusion. Consider discussion scale, independent evidence coverage, current-week novelty/change, version/esports/business relevance, engagement, player-experience impact, and evidence reliability. Do not invent a numeric impact score when the current business rules do not define one.
9. Select **10 distinct, evidence-qualified and importance-ranked Drivers**. Only reduce the count when the available evidence cannot support 10 without artificial splitting, duplication, or noise; the absolute minimum is 8. A report with 8 or 9 Drivers must include the reduction audit described below.
10. Resolve each Driver's sentiment from reviewed evidence using only **Positive / Neutral / Mixed / Negative** after the final Driver boundary is fixed. Identify a dominant direction first and preserve meaningful minority caveats in the narrative. Use Neutral only for mechanism understanding, information discussion, problem definition, analysis, or discussion without a clear evaluative direction. Use Mixed only when Positive and Negative reactions both have substantive, traceable support and neither direction clearly dominates. Do not downgrade a clearly dominant Positive or Negative reaction to Neutral or Mixed merely because a smaller opposing view exists. Model output is supporting evidence, not the final editorial vote.
11. Write the Chinese narrative first, then write an equivalent English narrative. Do not translate mechanically if that makes the English unnatural.
12. Check every Driver against the content test below, then run `scripts/validate_narratives.py` on the preview JSON.
13. Render the completed workbook and visually compare it with the W30 asset before release.

## Editorial synthesis and selection rules

Treat `Data Topic` and `Weekly Report Driver` as different product layers. Never use a canonical Topic label as the final Driver solely because records were assigned to it.

### Current-week Event / Issue inventory

Before ranking, identify every distinct current-week event or bounded issue supported by the reviewed evidence. Examples include a Legend rework, weapon balance change, ammo rework, loot-system change, named cosmetic or pack, tournament/team outcome, anti-cheat action, mode, collaboration asset, or technical issue.

For every enumerated Event / Issue, preserve an internal editorial disposition:

- `Selected` — survives as a final Weekly Driver.
- `Merged` — represented inside another final Driver; preserve the merge target and rationale.
- `Split` — represented by multiple final Drivers because distinct reactions or conclusions require separation; preserve child Driver references and rationale.
- `Excluded` — intentionally omitted after editorial review; preserve a specific evidence/relevance rationale.

Broad semantic or parent-category overlap does not count as event coverage. A concrete event must not silently disappear because a broader Driver or Data Topic exists.

### Editorial Selection Ladder

Use the ladder qualitatively. It does not introduce a score.

- **Band A — Must Compete / mandatory early editorial review.** Named current-week changes, products, modes, mechanics, Legend/weapon reworks, monetization objects, or named esports events/team outcomes with material player reaction. Examples: Bloodhound Rework, Loot System, Weapon Balance, Energy Ammo Rework, Heirloom Pack, named weapon skins, ALGS/ENC/EWC team performance.
- **Band B — Strong Candidate.** Named recurring system or competitive issues with a clear current-week trigger/enforcement event and meaningful player-experience impact. Examples: D+ Solo Queue, Matchmaking, Anti-Cheat, Aim Assist, severe server/access issues when demonstrably material.
- **Band C — Contextual Candidate.** Event-linked creator/community content, explainers, information or utility tied to a named current event and showing distinct client value. Examples: esports-format explainers, event information, event-linked creator cosplay or Wildcard previews.
- **Band D — Normally Demote.** Evergreen help, generic settings/new-player questions, narrow recurring subissues, peripheral content/meta, or abstract synthesis that is not itself the concrete discussion object. Examples: Settings Help Requests, Ranked Skill Benchmarks, New-Player Entry, generic Trust/Friction/Direction summaries.

Band A is an editorial review priority, not a new automated release blocker. The canonical machine hard-gate setting remains authoritative.

### Selection checks

Before a Candidate consumes a final Driver slot, verify:

1. **Concrete object/event** — a reader can tell exactly what is being discussed.
2. **Current-week trigger** — recurring issues explain why they belong in this week rather than any ordinary week.
3. **Client relevance** — the Candidate materially changes player experience, product perception, purchase/participation decisions, or esports/community understanding.
4. **Evidence breadth** — evidence is coherent and representative enough for the stated scope; evidence-qualified alone does not guarantee inclusion.
5. **Band-A review coverage** — plausible Band-A events have explicit editorial dispositions before lower-priority candidates are used to fill final slots.
6. **Context integrity** — semantically similar wording does not substitute a different subject/context. China pro-team tournament performance is not generic creator performance.
7. **Specificity** — do not generalize a named product/event into a category that would imply additional unsupported products/events.
8. **Operational restraint** — access/server/reliability issues remain eligible but do not automatically outrank named release or event Drivers without clearly stronger weekly importance.

Do not select a Candidate only because its evidence is internally coherent. Final selection must answer: **Is this one of the most important things the client should know about the community this week?**

## Granularity and visible Driver boundaries

One Weekly Driver should represent one bounded player judgment object capable of supporting one coherent reaction → reason → impact conclusion.

### Merge when

- evidence clusters evaluate the same concrete subject/event;
- they share the same current-week trigger/change;
- they support one coherent player judgment and client takeaway;
- one cluster is mainly a cause, caveat, reason, or impact of the other rather than an independent discussion object; and
- splitting would duplicate the same weekly event across multiple Driver slots without distinct editorial value.

Example: Loot scarcity/combat pace and supply/recovery reactions can remain one `Loot System Overhaul` Driver when they evaluate the same system change.

### Keep separate when

- the concrete named subjects/events differ even if they share one Data Topic or parent category;
- a named rework/product/mechanic has an independent material player reaction and conclusion;
- player decisions or client implications differ enough that one conclusion would blur them;
- combining would broaden scope beyond the evidence; or
- an umbrella label would hide a client-relevant named event.

Examples: `ALGS China Team Performance` is not `ALGS Highlight Selection`; `Bloodhound Rework` must not silently disappear inside a multi-Legend `Season 30 Legend Preview` when it has an independent weekly reaction.

### Minimum sufficient specificity

Use the minimum sufficient specific entity/event name that preserves what players are actually judging.

- If removing a qualifier causes a reader to infer a broader set of products/events than the evidence covers, restore the qualifier. Use `Mythic Skippy Alternator`, not a generic `Collaboration Reward Value`, when the evidence evaluates Skippy's appearance, inspections, effects, or execution.
- Do not over-narrow a wider coherent event to one sub-instance when meaningful evidence covers the broader event boundary.
- Keep abstract outcomes such as `Trust`, `Friction`, `Direction`, `Pressure`, or `Value` in the narrative unless the abstract concept itself is directly and repeatedly discussed.

## Content test for every Driver

Write two or three compact sentences that answer all four questions:

1. Who reacted or discussed the topic?
2. What exactly did they welcome, reject, question, report, or compare?
3. Which concrete details explain that reaction?
4. What did the reaction affect: understanding, interest, play continuity, trust, participation, or the ability to form a consensus?

Use bounded subjects such as `部分玩家`, `赛事观众`, `少量玩家`, or `一篇公开搜索可见帖子`. Match the strength of the subject to the evidence.

## Sentiment resolution

Determine sentiment from the direction, breadth, recurrence, source scope, and representativeness of reviewed evidence after the final Driver boundary is fixed. Do not invent a numeric percentage threshold.

- **Positive** — favorable evaluation, approval, anticipation, satisfaction, support, purchase/participation interest, or perceived value clearly dominates. A material minority concern belongs in the narrative as a caveat rather than automatically changing the label.
- **Negative** — frustration, disappointment, distrust, adverse experience, perceived non-viability, reduced value, or another unfavorable orientation clearly dominates. A material minority workaround or positive view belongs in the narrative as a caveat.
- **Neutral** — the discussion is primarily informational, mechanical, explanatory, question-led, descriptive, or otherwise lacks a stable favorable/unfavorable orientation. Neutral is not the midpoint created by cancelling Positive and Negative opinions.
- **Mixed** — Positive and Negative positions are both materially represented in traceable evidence, both are central to the same final Driver, and neither direction clearly dominates. Mixed requires evidence for both directions and must not be used because the evidence is incomplete, the facts are unconfirmed, the model is uncertain, or the writer is reluctant to choose a dominant direction.

Additional rules:

- Separate **evidence confidence** from **sentiment direction**. Missing comment bodies, unconfirmed details, or low evidence confidence may require review or bounded language, but do not automatically produce Neutral or Mixed.
- Future-oriented or speculative discussion can still be Positive or Negative when the orientation itself is clearly favorable or adverse.
- Attach sentiment to the Driver's actual judgment object. A negative underlying problem can coexist with positive sentiment toward an effective response or enforcement action.
- Do not convert a broadly positive Driver into Neutral or Mixed merely because players ask purchase, guarantee, budget, or mechanics questions unless those concerns are materially represented and no direction dominates.
- Do not convert a broadly negative Driver into Neutral or Mixed merely because a smaller group accepts, adapts to, or works around the change.
- Model sentiment is supporting evidence, not the final editorial vote.

## Non-negotiable rules

- Synthesize multiple evidence points into a finding. Do not paste one representative comment and call it a summary.
- Put sample counts, model status, provenance, and unit warnings in the overview or methodology. Do not repeat them in each Driver narrative.
- Do not start a Driver with `在本周有限样本中` or `Within this bounded weekly sample`.
- Do not write `被归入`, `代表性观察涉及`, `model-derived and exploratory`, or equivalent pipeline language in a Driver narrative.
- Do not show `(APEX-Txxx)` in the visible Driver title. Preserve the canonical ID in evidence comments or structured metadata.
- Do not infer causality, platform-wide incidence, or community consensus from a bounded sample.
- Do not infer community-wide trust, monetization intent, churn, or purchase impact from isolated comments. Such conclusions require repeated direct evidence.
- When only one search-visible post supports a Driver, identify it as one post and state the missing-comment or unconfirmed-detail limitation in editorial language.
- Keep direct quotations short and purposeful. Paraphrase the evidence into the report's voice.
- Never rename or alter the frozen canonical topic registry. A report headline may be narrower and evidence-led while retaining the canonical ID in metadata.

## Driver-count gate

- The normal weekly report contains exactly **10 Drivers**. Ten is the editorial standard, not an optional maximum.
- Use 8 or 9 Drivers only when the reviewed evidence genuinely cannot support 10 independent, importance-qualified findings. Never publish fewer than 8.
- Do not reach 10 by splitting one finding into near-duplicates, repeating the same evidence under different headlines, promoting irrelevant/noisy rows, or treating a raw quote as a separate Driver.
- When the report has 8 or 9 Drivers, the preview JSON must contain a top-level `driver_reduction` object with:
  - `target_count: 10`
  - `actual_count` equal to the number of Drivers
  - a specific, evidence-based `reason`
  - `padding_forbidden: true`
  - `excluded_candidates`, with at least one candidate and exclusion reason for every missing Driver
- The reduction audit is internal metadata. Keep it out of visible Driver narratives, but preserve it for review and release validation.
- `--allow-legacy-reference` exists only to validate historical reference files created before this rule. Never use it for a newly generated weekly report.

## W30 workbook contract

- Use one worksheet with English in A:B, a spacer in C, and Chinese in D:E.
- Use rows 1–2 for the bilingual overview, row 3 for headers, and 10 evidence-qualified Drivers in title/narrative pairs at rows `4/5`, `6/7`, `8/9`, `11/12`, `13/14`, `15/16`, `17/18`, `19/20`, `21/22`, and `23/24`.
- Merge each sentiment cell across its Driver pair; the third Driver spans rows 8–10 because row 10 is retained as template spacing.
- If a documented evidence shortage reduces the report to 8 or 9 Drivers, remove only the unused trailing pair or pairs; do not leave blank Drivers between populated rows.
- Keep the Driver title bold, the narrative italic, and the sentiment centered with W30 color semantics.
- Preserve evidence comments and source URLs without exposing raw source paths or local filesystem paths.

## Quality gate

Run:

```bash
python scripts/validate_narratives.py path/to/report.preview.json
```

Before accepting the narratives, verify that:

- the complete Current-week Event / Issue inventory was reviewed before final ranking;
- every enumerated Event / Issue has a traceable `Selected`, `Merged`, `Split`, or `Excluded` editorial disposition before final ranking;
- no unresolved Band-A event was silently displaced by a lower-priority candidate in editorial review;
- each visible Driver is tied to a concrete current-week Event / Issue;
- the selected Drivers are importance-ranked rather than merely evidence-qualified;
- no broad canonical Topic or umbrella Driver has silently swallowed distinct client-relevant events;
- no event has been over-split into duplicate Drivers merely because it has multiple evidence angles;
- no abstract headline overstates what players directly discussed;
- the Driver title preserves the minimum sufficient specific entity/event boundary;
- sentiment was assigned only after granularity was fixed;
- Positive or Negative dominant evidence was not weakened merely because a minority opposing view exists;
- Neutral was not used as a Positive/Negative cancellation bucket;
- Mixed is supported by substantive traceable evidence on both sides and no dominant direction;
- evidence confidence limitations were not silently converted into Neutral or Mixed;
- every current Data Topic still has the canonical editorial disposition and provenance required by the business rules.

The report fails if any Driver contains pipeline boilerplate, visible canonical IDs, missing reaction/impact language, a narrative outside the active contract length, or a bilingual structure mismatch. Fix the narratives; do not weaken the validator to pass a report.

After the narrative gate passes, run the normal workbook contract validation, formula/error scan, archive check, and visual render comparison. Do not publish until both editorial and workbook checks pass.
