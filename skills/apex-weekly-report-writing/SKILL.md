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
4. Build a complete **Current-week Event / Issue inventory** from the current-week Data Topics and evidence before final Driver ranking. This is an editorial grouping layer, not a new canonical Topic and not a change to the frozen topic registry.
5. Normalize each Event / Issue into a concrete **Driver Candidate** and assign a qualitative Priority Band using the Selection Ladder below. Evidence qualification only makes a candidate eligible; it does not guarantee inclusion. Do not invent a numeric impact score.
6. Apply the Selection Gates before final selection: concrete object/event, current-week trigger, client relevance, evidence breadth, context integrity, specificity, and operational-issue restraint. Evergreen help, narrow recurring subissues, and abstract synthesis must not displace stronger named weekly events merely because they are evidence-qualified.
7. Resolve **granularity** before sentiment: merge evidence only when it evaluates the same concrete subject and current-week trigger with one coherent player judgment; keep distinct named events separate when they have independent reactions or client implications. Restore the minimum sufficient specific entity/event name when a broader title would mislead the reader.
8. Complete the **Event Coverage editorial review** before final ranking. Every enumerated Event / Issue must end with an editorial disposition of `Selected`, `Merged`, `Split`, or `Excluded`, with traceable rationale. Band-A events are a mandatory editorial-review priority: lower-priority candidates should not be finalized while a Band-A event remains unresolved. Broad semantic similarity or category overlap does not count as event coverage. This is an editorial workflow rule, not a new machine high-impact hard gate.
9. Resolve sentiment only after the final Driver boundary is fixed. Use `Positive`, `Neutral`, `Negative`, or `Mixed` according to the active report contract. Determine dominant sentiment from reviewed evidence, keep evidence confidence separate from valence, and preserve meaningful minority views as caveats. Mixed is a high-threshold state, not an uncertainty fallback.
10. Select the final Driver set and rank it by editorial importance. The normal report contains 10 distinct Drivers; use 8 or 9 only when the reviewed evidence cannot support 10 without artificial splitting, duplication, or noise. Final ranking happens after candidate quality, coverage, granularity, and sentiment review.
11. Write the Chinese narrative first, then write an equivalent English narrative. Use two or three compact sentences by default when the evidence needs that space. Hard length validation must follow the active report contract: at least one sentence per language and 20–75 English words under contract `1.2-narrative-length`. Do not impose a stricter hard minimum or pad the narrative mechanically.
12. Check every Driver against the content and quality gates below, then run `scripts/validate_narratives.py` on the preview JSON.
13. Render the completed workbook and visually compare it with the W30 asset before release.

## Editorial Selection Ladder

Use the ladder qualitatively. It is a priority framework, not a numeric score.

### Band A — Must Compete

Named current-week changes, products, modes, mechanics, Legend/weapon reworks, monetization objects, or named esports events/team outcomes with material player reaction.

Examples include a specific Legend rework, loot-system change, ammo rework, named skin or Heirloom pack, and China-team performance in a named tournament.

Every plausible Band-A event must receive a final editorial disposition. If it is excluded, the reason must be explicit and evidence-based.

### Band B — Strong Candidate

Named recurring system or competitive issues with a clear current-week trigger or enforcement event and meaningful player-experience impact, such as ranked matchmaking, anti-cheat enforcement, input-policy debate, or a material current-week technical problem.

Band-B items remain eligible, but they should not automatically outrank unresolved Band-A events.

### Band C — Contextual Candidate

Event-linked creator/community content, explainers, information, or utility tied to a named current event and providing distinct client value.

Creator content is not categorically low priority. It may qualify when it is clearly bound to a named collaboration, tournament, release, or other current-week event.

### Band D — Normally Demote

Evergreen help, generic settings/new-player questions, narrow recurring subissues without a material current-week trigger, peripheral content/meta discussion, or abstract synthesis that is not itself the concrete discussion object.

Examples of abstract interpretations that normally belong in the narrative rather than the Driver title include `Trust`, `Friction`, `Uncertainty`, `Pressure`, or generic `Direction`.

## Selection Gates

A Driver Candidate must pass the following editorial checks before it can displace stronger candidates:

1. **Concrete object / event** — the reader can tell exactly what is being discussed.
2. **Current-week trigger** — persistent issues must have a reason they belong in this week's report.
3. **Client relevance** — the item materially affects player experience, product perception, purchase/participation decisions, or esports/community understanding.
4. **Evidence breadth** — the conclusion is supported by coherent evidence broad enough for its stated scope; one isolated anecdote cannot be inflated into a broad Driver.
5. **Band-A coverage** — all plausible Band-A events have a recorded editorial disposition before lower-priority items consume final slots.
6. **Context integrity** — semantically similar but different subjects or contexts must not be substituted for each other. China pro-team tournament performance is not generic creator performance.
7. **Specificity** — do not generalize a named product/event into a category that implies unsupported products or events.
8. **Operational-issue restraint** — server/access/reliability issues remain eligible, but they do not automatically outrank named release, product, gameplay, or esports events unless the reviewed evidence shows they are the more material weekly development.

## Event Coverage Gate

- Maintain an internal Event / Issue inventory before final ranking. This does not add a visible workbook field or create a new canonical Topic.
- Every enumerated Event / Issue must receive a final editorial disposition: `Selected`, `Merged`, `Split`, or `Excluded`.
- `Selected` must resolve to the final Driver carrying the event.
- `Merged` must identify the target Driver and explain why one Driver preserves the event without losing a distinct client-relevant judgment.
- `Split` must identify the child Drivers and explain why distinct player reactions or conclusions require separation.
- `Excluded` must state why the event does not deserve a final weekly slot despite being identified in the inventory.
- Before lower-priority candidates are finalized, every Band-A event must receive explicit editorial review and disposition. Before final ranking, no enumerated event may remain silently unresolved in the editorial synthesis.
- Partial semantic overlap does not count as event coverage. A broader umbrella Driver may represent multiple events only when the merge is explicit and traceable.
- Continue to satisfy the canonical `data_topic_editorial_review` disposition/provenance contract for every current Data Topic. Event coverage is an additional editorial control inside `evidence_and_editorial_synthesis`, not a replacement for the canonical Data Topic disposition. It must not change `machine_hard_gate: false`, create a numeric high-impact definition, or add a new machine-required schema/release blocker without separate canonical approval.

## Granularity and Driver-boundary rules

One Weekly Driver should represent one bounded player judgment object: a concrete event, product, mechanic, mode, tournament/team outcome, or issue that supports one coherent reaction → reason → impact conclusion.

### Merge when

- evidence clusters evaluate the same concrete subject/event;
- they share the same current-week trigger/change;
- they support one coherent dominant player judgment and client takeaway; and
- a secondary cluster is mainly a cause, caveat, reason, or impact of the same event rather than an independently discussed object.

Do not consume multiple Driver slots merely because one event has several impact dimensions.

### Keep separate when

- the concrete named subjects/events differ, even when they share a parent Data Topic or category;
- a named rework, product, mechanic, or tournament outcome has an independent player reaction and conclusion;
- merging would blur materially different player decisions or client implications; or
- combining would broaden the scope beyond the evidence.

### Naming boundary

Use the minimum sufficient specific entity/event name that preserves what players are actually judging. If removing a qualifier would make a reader think additional products, skins, creators, teams, or events are included, restore the qualifier.

Do not over-narrow a weekly event to one sub-instance when the evidence and client takeaway cover the wider event boundary. Higher-order interpretations belong in the narrative unless the abstract concept itself is repeatedly and directly discussed.

## Content test for every Driver

Use two or three compact sentences in each language by default when needed for clarity. Hard sentence and English-word limits must follow the active report contract; under `1.2-narrative-length`, each language needs at least one sentence and English must contain 20–75 words.

The narrative should answer all four questions:

1. Who reacted or discussed the topic?
2. What exactly did they welcome, reject, question, report, or compare?
3. Which concrete details explain that reaction?
4. What did the reaction affect: understanding, interest, play continuity, trust, participation, purchase judgment, or the ability to form a consensus?

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
- Neutral is used for informational/no-stable-valence discussion rather than as a positive-negative cancellation bucket;
- Mixed is used only when both directions are materially represented and neither dominates, and never as an uncertainty fallback;
- each Chinese and English narrative satisfies the active report contract's sentence and word limits; under `1.2-narrative-length`, each language has at least one sentence and English contains 20–75 words;
- every current Data Topic has the required canonical editorial disposition and provenance.

The report fails if any Driver contains pipeline boilerplate, visible canonical IDs, missing reaction/impact language, sentence/word length outside the active contract, excessive unsupported claims, or a bilingual structure mismatch. Fix the narratives; do not weaken the validator to pass a report.

After the narrative gate passes, run the normal workbook contract validation, formula/error scan, archive check, and visual render comparison. Do not publish until both editorial and workbook checks pass.
