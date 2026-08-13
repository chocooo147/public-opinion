# APEX Rule & Workflow Integrity Remediation — 2026-08-11

## Scope boundary

This remediation restores rule consistency and fail-closed enforcement. It does
not redefine Topic, Keyword qualification, Heat, Weekly Driver ranking, the
frozen model, the Weekly Report Skill, authentication, or W32 evidence.

Product layers remain separate:

`Raw Community Data → Data Topics → Evidence / Editorial Synthesis → Weekly Report Drivers`

- Data Topics are fine-grained dashboard structures produced from mapped,
  non-outlier records under the frozen model contract.
- Weekly Report Drivers are editorial syntheses backed by real Data Topics and
  evidence. Titles, counts, and granularity do not have to match Data Topics.
- The validator must not fail solely because the dashboard and report differ.

## Implementation status

1. **Topic / Keyword / Heat machine policy — IMPLEMENTED.**
   `config/canonical_business_rules.json` is bound by version and SHA-256 from
   `weekly_production_policy.json`. Production preparation, dashboard metadata,
   preflight, and validator all load the same binding.
2. **Heat input semantics — BLOCKED — BUSINESS APPROVAL REQUIRED.** No formula,
   inputs, or weights were selected. Misleading proxy labels are removed from
   the active method UI, and new formal publication is blocked.
3. **Five low-quality terms — IMPLEMENTED.** Exact exclusions for 以为、有没有、
   原来、问问、直接 cover week keyword stats, Topic descriptors, Topic keyword
   lists, platform keyword stats, search inputs derived from those fields, and
   historical Topic chains. The broader stopword policy was not expanded.
4. **Topic method drift — IMPLEMENTED.** The page now describes the actual
   frozen per-text transform, canonical mapping, and outlier exclusion. It no
   longer claims title/intro/transcript ingestion, cross-video consensus-based
   Topic qualification, or Heat-based Top-10 Topic selection.
5. **Clean Git reconstruction — IMPLEMENTED AS A GATE.** Source commit/branch/
   clean state is recorded. Production and revision preflight plus validator
   reject a dirty or unprovable source. The current dirty worktree remains
   preserved and therefore cannot yet pass this gate without a separately
   authorized archival/commit workflow.
6. **Agent Runtime Receipt contract and gate — IMPLEMENTED.** Exact
   Collector/Analyst/Validator models, efforts, stages, runtime evidence, and
   Sol authorization are validated. systemd remains a machine scheduler, not a
   Custom Agent orchestrator. External Sol/Agent orchestration supplies receipts
   at resume and publish gates; the pipeline never fabricates them.
7. **Editorial Package source contract — IMPLEMENTED WITH CHECKPOINTS.** The source is the
   Analyst working from current-week Data Topics and evidence, followed by the
   existing human approval gate before report build. No default, historical
   package, or automatic approval is used. systemd stops at an immutable
   `awaiting_human_approval` checkpoint. Resume verifies that checkpoint and
   approval without recollection, builds and machine-validates the candidate,
   then stops at `awaiting_validator_sol_approval`. Publication requires the
   independent Validator receipt plus Sol final approval.
8. **Current live vs latest run — IMPLEMENTED.** Public status schema v2 exposes
   `current_live_release` separately from `latest_pipeline_run` and preserves
   the live release when a later run fails.
9. **Registry / Mapping Hash pins — IMPLEMENTED.** Registry and mapping expected
   SHA-256 values are policy-owned and independently checked.
10. **Independent Validator checks — IMPLEMENTED.** Data Topic IDs/counts are
    reconciled to mapped non-outlier records; visible Keyword paths are scanned
    using canonical policy; Driver Topic/evidence provenance is checked without
    enforcing title/count/granularity equality. Heat blocks because no approved
    formula exists. No numeric high-impact threshold was created: every Data
    Topic instead requires an editorial disposition and rationale, and important
    omission remains a recorded editorial review item rather than a machine
    impact-score gate.
11. **MODEL_VERSION / Runbook / Agent docs — IMPLEMENTED.** Prose now defers to
    machine policy and documents the current domain-sentiment path, 15-video
    gate, Topic/Driver boundary, Heat block, status split, and runtime gap.
12. **Versioned page methodology — IMPLEMENTED.** New releases embed only public
    versioned rule metadata; the page renders Topic/Keyword/Heat explanations
    from it. Internal regexes and private paths are not exposed.
13. **W33 preflight — IMPLEMENTED.** The prepare gate verifies Git source, rule
    and model-asset bindings, platform readiness, and Heat approval before live
    collection. Resume and publish independently check checkpoint, Editorial,
    Human Approval, Agent receipt, and Sol authorization conditions. Preflight
    does not replace later quality gates.
14. **Manual revision provenance — IMPLEMENTED.** Revision mode requires reason,
    replaced automatic stages, reused artifact hashes/source stages, and rerun
    stages. A controlled recovery cannot be recorded as the scheduled run.
15. **Command classification — IMPLEMENTED.** Current production, stage
    component, production gate, and historical-forbidden-by-default commands
    are machine classified in `automation_entrypoints.json`.
16. **Frozen BERTopic binary — NO CHANGE REQUIRED.** Not modified.
17. **Formal Agent model/effort — NO CHANGE REQUIRED.** Terra medium/high/high
    assignments are unchanged.
18. **Weekly Report Skill — NO CHANGE REQUIRED.** Not modified.
19. **Driver ranking/reduction/approval contract — NO CHANGE REQUIRED.** Not
    modified.
20. **Public privacy/authentication — NO CHANGE REQUIRED.** Whitelist privacy
    scan and server-side application authentication are unchanged; Nginx Basic
    Auth was not re-enabled.
21. **W32 evidence and report hashes — NO CHANGE REQUIRED.** Existing W32
    evidence artifacts were not edited or regenerated.

## Heat decision package

### Historical audit state before Heat v1.0 approval

The historical audit now traces W25–W32 release-time Heat and the W32 retained-
history rewrite. `docs/HEAT_FORMULA_TIMELINE_2026-08-11.md` records every source
artifact, input, coefficient, normalization, stored score, exact recalculation,
and difference. None of those historical implementations became Heat v1.0.

### Existing Competing Rules

- `formal_auxiliary_metrics_v1`: weekly share/video/creator breadth at 50/30/20;
- historical count/log-engagement proxy family, whose count coefficient changed;
- five-component count/WoW proxy weighted 35/25/20/10/10;
- W25–W28 historical builder behavior that stored components while supplying
  Heat independently.

### Resolved canonical decision

The business owner subsequently approved `apex-heat-v1.0`, effective from W32:
discussion intensity 35%, discussion breadth 30%, engagement depth 20%, reach
10%, and momentum 5%. The exact input, transformation, missing-value, platform
aggregation, and history-boundary contract is hash-pinned in
`config/heat_v1.json`. Historical proxies remain audit evidence only.

### Current decision status

Heat v1.0 is approved. The production gate now blocks on version/hash mismatch,
missing real component inputs, proxy use, or a failed independent
recalculation—not on business approval status.

## Verification

- Full repository suite: 126 tests run, 125 passed, 1 documented sandbox-only
  local-socket test skipped, 0 failures.
- Python compilation, JSON parsing, `git diff --check`, and the static release
  check passed.
- A W33 prepare preflight intentionally failed closed. It confirmed the
  canonical rule hash plus registry and mapping Hashes, then blocked preparation
  for unresolved Heat, missing current Bilibili/Heybox readiness evidence, and
  the preserved dirty source tree. No W33 approval checkpoint, Editorial
  Package, or Agent Runtime Receipt exists yet; those later-stage gates therefore
  remain not ready without being misreported as prepare-stage execution errors.
- In-app browser visual acceptance is not claimed: the browser plugin could not
  reach the temporary local preview in this sandbox. UI behavior is covered by
  DOM/source contract tests, but final interactive browser acceptance remains a
  separate step before any production publication.
