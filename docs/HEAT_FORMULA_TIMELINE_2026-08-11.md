# APEX Heat Formula Timeline — W25–W32 Historical Fact Audit

## Decision status and scope

This document remains the immutable historical-fact audit that preceded the
Heat v1.0 decision. On 2026-08-11, the business owner separately approved
`apex-heat-v1.0` effective from W32. That later decision does not change the
historical findings below and does not authorize any W25–W31 recalculation.

Two states must not be conflated:

1. **Release-time state**: the implementation used when each week was first
   published as the current week.
2. **W32 final-live retained history**: release `2026_W32_364349f21f50`
   recalculated W28–W31 with its five-component proxy. Therefore the W28–W31
   scores visible inside the final W32 five-week window are not the same values
   that those weeks displayed when first released.

## Competing implementation comparison — no candidate selected

| Observed implementation | Actual formula | Inputs / weights | Normalization | Historical use | Approval status |
|---|---|---|---|---|---|
| `formal_auxiliary_metrics_v1` | `0.50 × weekly_share×100 + 0.30 × video_count/week_max_video_count×100 + 0.20 × creator_count/week_max_creator_count×100` | share 50%, video breadth 30%, creator breadth 20% | Per-week maxima for video and creator breadth; score rounded to 2 decimals | Separate W25–W28 auxiliary artifact only; 52/52 rows exactly reproducible | Not proven to be the website Heat rule |
| count/engagement historical proxy family | W29–W30: `clamp(18 + 2.8×count + 7×ln(1+likes+comments))`; W31: `clamp(18 + 8×count + 7×ln(1+likes+comments))` | count coefficient changed from 2.8 to 8; engagement logarithm coefficient 7; intercept 18 | No cross-topic normalization; rounded integer, clamped 0–100 | W29, W30, W31 release-time platform Heat | Not approved; the coefficient changed |
| five-component display proxy | `clamp(0.35×coverage + 0.25×volume + 0.20×influence + 0.10×engagement + 0.10×growth)` | components themselves are count/WoW proxies in the W32 builder | Each proxy clamped 0–100; fixed count denominators/affine transforms; combined Heat count-weighted | W32 final release, including recalculated W28–W31 retained history | Not approved; component labels do not prove formal business meaning |

The older W25–W28 builder forms a fourth historical behavior rather than a
coherent candidate: it stored the five display components but supplied Heat
independently. Bilibili used
`clamp(52 + 1.25×weekly_share_percent + 0.4×video_count)`; Heybox used
`clamp(18 + 10×visible_post_count + 7×ln(1+likes+comments))`, with zero when no
visible post existed. Combined Heat was count-weighted from platform Heat.

## `formal_auxiliary_metrics_v1` facts

- Source artifact:
  `<APEX>/outputs/formal_auxiliary_metrics.json`
  (generated `2026-07-18T03:32:14.756107+00:00`).
- Builder:
  `<APEX>/scripts/build_formal_auxiliary_metrics.py`,
  SHA-256 `3f26363f2ced2047b60aa3b6146d8d014006812cf3f2878799fdb4a152ff598a`.
- Primary metric input:
  `outputs/apex_topic_weekly_final.json`; independent video/creator counts and
  `weekly_share` are grouped by W25–W28.
- Exact self-recalculation: **YES, 52/52** rows, zero difference.
- Dashboard use: **NO evidence of use**. The W25–W28 dashboard metadata states
  `qualified_for_formal_auxiliary_reporting=false`, and the historical builder
  explicitly did not load this artifact into the model-only dashboard.
- Dashboard comparison: **0/52** Bilibili Topic-week Heat scores match the
  auxiliary score. Dashboard minus auxiliary differences range from +19.01 to
  +49.38 points across W25–W28.

## HEAT FORMULA TIMELINE — release-time state

Topic score arrays below are the website's default **综合** Heat values in
canonical Topic order (`APEX-T001` onward). Platform-level inputs and scores are
retained in the named artifacts.

### W25

- Heat Source Artifact = `outputs/dashboard_data_apex_W25_W28.json`, SHA-256
  `3bf5c0fcb9a58646bf07f8c914111cc3c88772feb86a4b87b8acdf6b6fd1fdf2`
- Calculation Implementation = historical builder independent Heat: Bilibili
  share/video formula; Heybox visible-post/log-engagement formula; count-weighted
  combined score
- Formula Version = unversioned historical builder; not
  `formal_auxiliary_metrics_v1`
- Inputs = Bilibili `weekly_share`, `video_count`; Heybox `count`, `likes_count`,
  `comment_count`; combined platform counts
- Weights = Bilibili intercept 52, share coefficient 1.25, video coefficient
  0.4; Heybox intercept 18, count coefficient 10, log-engagement coefficient 7
- Normalization = integer rounding and clamp 0–100; no weekly-max Heat
  normalization
- Stored Component Fields = per platform
  `video_coverage_score`, `creator_coverage_score`, `discussion_coverage`,
  `discussion_volume_score`, `influence_score`, `engagement_score`,
  `growth_score`; these did **not** calculate stored Heat
- Stored Heat Score = `[70,69,70,79,66,61,60,70,58,54,65,63,56]`
- Can Recalculate Stored Heat Exactly = **YES**; 26/26 platform scores and
  13/13 combined scores
- Difference = 0 under actual builder; differs from the page's five-component
  equation and all 13 Bilibili scores differ from formal auxiliary v1

### W26

- Heat Source Artifact = same W25–W28 artifact
- Calculation Implementation / Formula Version / Inputs / Weights /
  Normalization / Stored Component Fields = same release-time historical
  builder as W25
- Stored Heat Score = `[70,76,68,62,77,64,60,64,63,61,59,63,58]`
- Can Recalculate Stored Heat Exactly = **YES**; 26/26 platform and 13/13 combined
- Difference = 0 under actual builder; page equation mismatch; 0/13 Bilibili
  scores match formal auxiliary v1

### W27

- Heat Source Artifact = same W25–W28 artifact
- Calculation Implementation / Formula Version / Inputs / Weights /
  Normalization / Stored Component Fields = same release-time historical
  builder as W25
- Stored Heat Score = `[76,73,71,71,65,54,66,60,67,62,59,58,58]`
- Can Recalculate Stored Heat Exactly = **YES**; 26/26 platform and 13/13 combined
- Difference = 0 under actual builder; page equation mismatch; 0/13 Bilibili
  scores match formal auxiliary v1

### W28

- Heat Source Artifact = same W25–W28 artifact
- Calculation Implementation / Formula Version / Inputs / Weights /
  Normalization / Stored Component Fields = same release-time historical
  builder as W25
- Stored Heat Score = `[81,68,73,58,61,69,65,58,56,62,61,68,65]`
- Can Recalculate Stored Heat Exactly = **YES**; 26/26 platform and 13/13 combined
- Difference = 0 under actual builder; page equation mismatch; 0/13 Bilibili
  scores match formal auxiliary v1

### W29

- Heat Source Artifact = `outputs/dashboard_data_apex_W25_W29.json`, SHA-256
  `8fb3702ba5f086eb731a9f8b0996b906f74144562e47913b706bb65e36dacb3f`
- Calculation Implementation = platform proxy
  `clamp(18 + 2.8×count + 7×ln(1+likes+comments))`; combined count-weighted
- Formula Version = unversioned W29 builder; outer builder SHA-256
  `4934ebfaf7226475aec79947d01cbb4c7648fce627b089b37faa004eae62a58a`;
  published by commit `7bed6341d0aae7dfb24691bdf05421a64456a148`
- Inputs = per-platform record/post count, likes, comments; combined platform counts
- Weights = intercept 18; count 2.8; log engagement 7
- Normalization = integer round/clamp 0–100 per platform; no cross-topic
  normalization; combined rounded to 2 decimals
- Stored Component Fields = same five display proxy fields, independent of Heat
- Stored Heat Score = `[78.12,92.14,66.0,52.0,45.0,74.33,48.17,52.0,52.12,48.0,53.75,36.0,31.0]`
- Can Recalculate Stored Heat Exactly = **YES**; 26/26 platform and 13/13 combined
- Difference = 0 under W29 builder; page 35/25/20/10/10 explanation did not
  compute these scores

### W30

- Heat Source Artifact = `outputs/dashboard_data_apex_W25_W30.json`, SHA-256
  `b277a613b2104cd9caefcaf965fb6805e27990494d212bef9f011b791f77e88a`
- Calculation Implementation = same `18 + 2.8×count + 7×ln(1+engagement)`
  proxy as W29
- Formula Version = unversioned W30 builder; outer builder SHA-256
  `3405294db52ebb9b9d93959d2dbae2e739a8935c8991799526b5230db08707b2`;
  published by commit `9888f2b233946c913ddbe7866bdef94799db6cad`
- Inputs / Weights / Normalization / Stored Component Fields = same as W29
- Stored Heat Score = `[72.8,64.0,95.08,55.0,0,52.33,56.0,54.0,37.0,62.67,58.33,41.0,37.0]`
- Can Recalculate Stored Heat Exactly = **YES**; 26/26 platform and 13/13 combined
- Difference = 0 under W30 builder; page equation mismatch remains

### W31

- Heat Source Artifact = W31 live release
  `2026_W31_91899f27ddb4/dashboard_data_apex_W27_W31.json`, SHA-256
  `74e35340c136cc7244b16d1bc6ee78cc85954bc1e6f93464232dd372e8725698`
- Calculation Implementation =
  `clamp(18 + 8×count + 7×ln(1+sum(raw likes)+sum(raw comments)))`;
  unlike W29/W30, zero-count platform metrics retain the intercept value 18
- Formula Version = unversioned W31 implementation in
  `weekly_release_common.py` at commit
  `143bd3b7919d7dbd16d67c64dcbb3e4529251848`
- Inputs = canonical-Topic source records, per-record likes/comments, platform
  record count; combined platform counts
- Weights = intercept 18; count 8; log engagement 7
- Normalization = integer round/clamp 0–100; no cross-topic normalization;
  combined rounded to 3 decimals
- Stored Component Fields = five count/WoW proxy fields stored independently
- Stored Heat Score = `[90.0,100.0,100.0,94.571,34.0,54.0,65.0,57.0,49.0,80.0,95.667,52.0,74.0]`
- Can Recalculate Stored Heat Exactly = **YES** from archived W31 source records;
  26/26 platform and 13/13 combined
- Difference = 0 under W31 implementation; the count coefficient changed from
  2.8 to 8, while the page still described the five-component equation

### W32

- Heat Source Artifact = final live W32 release
  `2026_W32_364349f21f50/dashboard_data_apex_W28_W32.json`, SHA-256
  `905ee86173759f4de880781666ac1848ea1c62ab6c43ba34be900b64ad70a12f`
- Calculation Implementation = five count/WoW-derived platform components with
  35/25/20/10/10 weights; combined Heat count-weighted from platform Heat
- Formula Version = described by the release audit as canonical at that time,
  but unversioned in the artifact and not backed by a recorded Git revision
- Inputs = platform count, prior-week count/WoW, and derived component fields;
  no raw views/influence measure is used by this implementation
- Weights = coverage 35%, volume 25%, influence proxy 20%, engagement proxy 10%,
  growth proxy 10%
- Normalization = fixed denominators/affine transforms, integer round/clamp
  0–100 per platform; combined rounded to 3 decimals
- Stored Component Fields = all five fields per platform; combined stores Heat
  without a parallel five-component vector
- Stored Heat Score = `[25.0,49.071,29.0,32.0,37.636,49.0,26.0,36.0,25.0,41.5,31.0,41.0]`
- Can Recalculate Stored Heat Exactly = **YES**; 24/24 platform and 12/12 combined
- Difference = 0 under the W32 release implementation; however
  `release_context.source_revision` is null, so the exact production source Git
  revision cannot be proven

### Release-time stored platform score vectors

These vectors use the same Topic order as each week's comprehensive vector and
complete the stored-score inventory for the platform switcher.

| Week | B站 Heat | 小黑盒 Heat |
|---|---|---|
| W25 | `[70,68,70,79,66,61,60,70,58,54,66,63,56]` | `[0,79,0,0,0,0,0,0,0,0,48,0,0]` |
| W26 | `[70,75,68,62,78,64,60,64,63,61,55,63,58]` | `[0,83,0,0,60,0,0,0,0,0,71,0,0]` |
| W27 | `[77,70,71,71,65,54,66,60,67,62,59,58,58]` | `[61,94,0,0,0,0,0,0,0,0,0,0,0]` |
| W28 | `[82,68,73,58,61,69,65,58,56,62,63,57,65]` | `[54,72,0,0,0,0,0,0,0,0,45,90,0]` |
| W29 | `[79,95,66,52,45,73,45,52,52,48,54,36,31]` | `[65,35,0,0,0,77,64,0,53,0,52,0,0]` |
| W30 | `[76,68,98,62,0,49,56,54,37,69,54,41,37]` | `[68,40,63,34,0,54,0,0,0,31,67,0,0]` |
| W31 | `[100,100,100,100,34,54,65,57,49,80,100,52,74]` | `[60,18,18,62,18,18,18,18,18,18,61,18,18]` |
| W32 | `[25,54,29,32,39,49,26,36,25,44,31,41]` | `[16,31,19,16,24,19,19,19,19,29,19,19]` |

## W32 final-live retained-history rewrite

Within final W32 release `2026_W32_364349f21f50`, all stored platform Heat
scores for W28, W29, W30, W31, and W32 exactly match the five-component proxy:

| Week inside W32 release | Exact platform recalculation |
|---|---:|
| W28 | 26/26 |
| W29 | 26/26 |
| W30 | 26/26 |
| W31 | 26/26 |
| W32 | 24/24 |

This proves the final W32 builder normalized retained history; it does not prove
that the formula was an approved canonical business rule.

## Earliest rule fork

- Earliest UI implementation fork = commit
  `4f4536cc9131e17c57361e2175792c722e8a9f5e` on 2026-07-16 introduced the
  35/25/20/10/10 explanation and a frontend fallback, while also accepting an
  already-stored `heat_score` without recomputing it.
- First affected real historical week = **W25**. Commit
  `f9fd2897d55bb2204c2f5c7089cb7e61018236ce` first published the W25–W28
  dashboard artifact on 2026-07-18; its stored Bilibili Heat came from the
  independent share/video builder, not the displayed five-component equation.
- Real-platform consolidation commit
  `a485251a5e157420273d940f4b968bf933bf60fd` retained that independent Heat
  behavior.

Therefore:

`earliest fork = W25 / f9fd289 (with UI cause introduced at 4f4536c) / historical builder independent heat versus displayed five-component formula`.

## Classification by week

- W25 = historical builder independent heat; page explanation mismatch
- W26 = historical builder independent heat; page explanation mismatch
- W27 = historical builder independent heat; page explanation mismatch
- W28 = historical builder independent heat; page explanation mismatch
- W29 = proxy heat; page explanation mismatch
- W30 = proxy heat; page explanation mismatch
- W31 = changed proxy heat; page explanation mismatch
- W32 = five-component proxy heat; exact to that release, but source revision
  unprovable and canonical business approval unproven

No week in this evidence set establishes a uniquely approved canonical Heat
rule. The three candidate families remain pending business review.
