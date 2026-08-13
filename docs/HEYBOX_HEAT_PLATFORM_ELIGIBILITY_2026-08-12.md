# Heybox Heat Platform Eligibility Policy

Status: approved and machine-enforced
Policy version: `apex-heat-platform-eligibility-v1.0`
Effective from: `2026_W32`

## Approved eligibility

- `B站`: `ELIGIBLE`
- `小黑盒`: `INELIGIBLE_REACH_UNAVAILABLE`

A platform is Heat-eligible only when Discussion Intensity, Discussion Breadth,
Engagement Depth, Reach, and Momentum all have approved real inputs. The
approved Xiaoheihe web collection surface does not provide reliable views,
exposure, or Reach, so Xiaoheihe Platform Heat is stored as `null` and displayed
as `N/A`. Zero, defaults, proxies, and legacy fallbacks are forbidden.

Xiaoheihe remains in Data Topics, keywords, sentiment, evidence, and Weekly
Report Driver synthesis. Ineligibility affects Heat only.

## Composite Heat

Composite Heat aggregates only eligible platforms. With only Bilibili eligible,
Topic Heat equals Bilibili Heat, the Bilibili weight is `1.0`, and
`heat_platform_coverage` is `partial`. An ineligible platform is excluded before
the weight denominator is calculated and is not treated as a blocked eligible
platform.

An eligible platform with evidence but a missing required Component continues
to fail closed. Restoring Xiaoheihe eligibility requires a separate business
approval after reliable Reach becomes available.

## Formula boundary

This policy does not change Heat v1.0:

`0.35 Discussion Intensity + 0.30 Discussion Breadth + 0.20 Engagement Depth + 0.10 Reach + 0.05 Momentum`

W25-W31 remain untouched Legacy Heat. The eligibility policy applies from W32
and continues for W33 and later.

## W32 verification

- Bilibili: 12/12 active Topics calculated from all five real Components.
- Xiaoheihe: 12/12 Topic entries have `heat_score = null`, display `N/A`, and
  declare `INELIGIBLE_REACH_UNAVAILABLE`.
- Composite: 12/12 Topic Heat scores equal Bilibili Heat with Bilibili weight
  `1.0` and `heat_platform_coverage = partial`.
- Independent recalculation: PASS.
- Legacy weeks present in the five-week candidate (W28-W31): semantic hashes
  unchanged. No W25-W27 historical artifact was opened for write or regenerated.
- W32 non-Heat semantic hash: unchanged.

Machine evidence is stored in
`outputs/heat_platform_eligibility_20260812_v2/` outside the production Git
worktree.
