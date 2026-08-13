# APEX Heat v1.0 Implementation — 2026-08-11

## Decision and boundary

- Canonical rule: `apex-heat-v1.0`.
- Canonical file: `config/heat_v1.json`.
- Effective from: `2026_W32`.
- Legacy through: `2026_W31`.
- W25–W31 recalculation and artifact mutation: forbidden.
- Frontend recalculation, legacy fallback, task-specific Heat, and proxy fill:
  forbidden.

## Exact formula

`Heat = 0.35 × Discussion Intensity + 0.30 × Discussion Breadth +
0.20 × Engagement Depth + 0.10 × Reach + 0.05 × Momentum`

Discussion Breadth is
`0.60 × independent content-source breadth + 0.40 × independent participant breadth`.

Every raw metric uses Tukey-IQR winsorization. Long-tail metrics then use
`log1p`. The same-platform/same-week Topic cohort uses population z-score,
clipped to `[-3, 3]`, and maps to `0–100` as
`clamp(50 + clipped_z × 50/3, 0, 100)`. Zero-dispersion cohorts receive 50.
Momentum uses the relative Topic share change, clipped to `[-2, 2]`; a new or
zero previous baseline is missing, not maximum growth.

Platform Heat is calculated independently. Composite platform weights are
`sqrt(valid evidence count) / sum(sqrt(valid evidence count))`. A platform with
zero evidence is not applicable. A platform with evidence but a missing
required component blocks Composite Heat; weights are not redistributed.

## W32 actual input audit

Canonical derived source artifacts:

- Bilibili SHA-256:
  `c3dd316aa5a8d5ce9722c785c85b387a17d02dc877504589d76753ea12fec940`.
- Heybox SHA-256:
  `51bf99816d4c9d079f4e525781cda2f12bee3f87ada25902d73c4c4051d22aab`.

Bilibili has 117 mapped, non-outlier comments across 12 Data Topics, 18
independent mapped video sources, and complete participant identity coverage
(117 distinct commenter identifiers). Comment likes are present on every
mapped record. Positive real `views` exist for every mapped video source; the
deduplicated mapped-source view total is 1,825,194. Every active Bilibili Topic
has a non-zero W31 baseline. All five Bilibili components are therefore
available.

Heybox has 10 mapped public-search post cards across 3 Data Topics. Real card
likes and comments are present, so Discussion Intensity, independent-source
breadth, and Engagement Depth are available. The source has no participant
identity fields and all stored `views` are 0 with no provenance proving real
exposure collection. Therefore participant breadth and Reach are missing.
T002 and T005 also have no non-zero W31 Heybox Topic baseline, so Momentum is
missing; T011 Momentum is available.

No missing field was replaced by comment count, post count, views proxy, or a
renormalized platform weight.

## W32 result

- Bilibili: 12/12 active Topic Heat scores calculated and independently
  reproducible.
- Heybox: 0/3 evidenced Topic Heat scores complete; real-input blocks remain.
- Composite: 9 Bilibili-only Topics are reproducible with Bilibili weight 1.0;
  T002, T005, and T011 are blocked because Heybox has evidence but lacks
  required real components.
- W32 release readiness: **BLOCKED**.
- Independent calculation integrity: **PASS** — stored fields match fresh
  source recomputation; the only blockers are declared real-input gaps.

Versioned evidence is stored under
`outputs/heat_v1_implementation_20260811/` in the shared APEX evidence root.
The candidate retains exact before/after hashes for W28–W31; all four match.
W25–W27 are outside the W32 five-week candidate and were never opened for
write. No W25–W31 report, dashboard source, raw input, Topic, Keyword, Evidence,
Driver, or narrative artifact was modified.
