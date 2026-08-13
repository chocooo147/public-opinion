# APEX Agent System v1.0

This document freezes the operating architecture and governance boundaries of
the validated APEX Agent System v1.0. It describes how authority, routing,
commands, validation, and escalation work. It does not own production business
parameters.

## 1. Scope Architecture

The APEX workspace has two policy layers:

- `<APEX>/AGENTS.md` is the parent workspace policy. It governs workspace
  boundaries, shared-runtime safety, custom-agent routing, and high-impact
  authority.
- `<APEX>/work/public-opinion/AGENTS.md` is the child production-repository
  policy. Inside the canonical repository it adds source precedence, command
  authority, repository-local execution boundaries, and validation duties.

The child policy may narrow permissions but cannot weaken the parent policy.
If the two layers appear to conflict, the parent continues to control shared
roots and high-impact authority while the child controls repository-local
command selection.

`<APEX>/work/public-opinion` is the only canonical production code repository.
The workspace roots `<APEX>/data`, `<APEX>/models`, and `<APEX>/outputs` hold
shared runtime inputs, frozen assets, evidence, and derived outputs. They are
not alternative code repositories, and they remain governed by the parent
policy even when canonical production code resolves paths into them.

Project-scoped custom-agent definitions live under `<APEX>/.codex/agents/`.
The production repository must be used as the working or explicit project root
for production-relevant commands.

## 2. Primary Orchestrator

GPT-5.6 Sol is the primary orchestrator and final freeze authority. Sol owns:

- intent, scope, and source-of-truth classification;
- ambiguity and policy-conflict resolution;
- architecture and governance decisions;
- business-rule and high-impact decisions;
- delegation packages and agent selection;
- independent review of worker evidence;
- final verification and acceptance;
- production publication or live-switch authority; and
- final GitHub write authority.

A custom-agent PASS is evidence for Sol. It is never automatic authorization
or final acceptance.

## 3. Custom Agents

### `apex_collector`

- Validated runtime: GPT-5.6 Terra, reasoning effort `medium`.
- Scope: bounded collection execution, parser/checkpoint/log inspection, and
  collection-specific verification.
- It must stop on authentication expiry, CAPTCHA or safety verification, rate
  limiting, access control, or material parser/contract changes and return the
  issue to Sol.

### `apex_analyst`

- Validated runtime: GPT-5.6 Terra, reasoning effort `high`.
- Scope: bounded preparation, approved frozen-model inference, dashboard
  construction, evidence-qualified synthesis, and weekly-report candidates.
- It must preserve current data and model qualification limits and cannot
  manufacture evidence, approval, or release readiness.

### `apex_validator`

- Validated runtime: GPT-5.6 Terra, reasoning effort `high`.
- Scope: independent testing, data/model/policy integrity, report validation,
  manifest and public-boundary inspection, and release-readiness checks.
- It is read-first and must report mandatory failures without weakening the
  implementation, contract, policy, or evidence under review.

## 4. Routing Rules

Sol selects the agent that matches a bounded task:

- collection-only work routes to `apex_collector`;
- analysis, dashboard, synthesis, and report-candidate work route to
  `apex_analyst`; and
- independent testing and release-boundary work route to `apex_validator`.

Every delegation defines the objective, allowed paths, forbidden scope,
current sources of truth, expected outputs, acceptance criteria, validation
method, and escalation conditions.

Workers cannot silently replace Sol for architecture, ambiguity, exceptions,
business rules, publication, final GitHub writes, or other high-impact
decisions. A worker role never expands filesystem or operational authority.

## 5. Command Authority

Production and production-relevant commands must come from one of these
current authorities:

1. `config/automation_entrypoints.json`;
2. the canonical production pipeline registered there; or
3. another explicitly approved current command map.

Agents must not scan `scripts/` or `archive/` and infer a production command
from a filename. An unknown or unregistered command returns to Sol for
classification. Historical capability is not current command authority.

## 6. Legacy Isolation

`archive/legacy_scripts/` is non-production and non-executable by default. Its
contents may be used only for explicitly authorized historical audit,
recovery, forensics, or bounded maintenance.

Only Sol may classify and authorize such use. Historical scripts cannot act as
current business-rule authority and cannot create, replace, or publish a
current production release merely because their output names appear relevant.

## 7. Ordering Governance

The current canonical Driver order is produced before workbook construction by
the Skill-reviewed editorial package. The package sequence is the ordinal
editorial decision, based on current-week community impact and importance under
the active report-writing rules.

Machine-verifiable evidence consists of:

- a unique `driver_id` for every Driver;
- a continuous `canonical_rank` sequence;
- `driver_ranking` provenance tied to the current policy, Skill, narrative
  rule, and review state; and
- exact sequence preservation through the builder and downstream validation
  evidence.

The builder validates and preserves the supplied order. It must not calculate,
infer, or silently reorder the ranking. The validator checks provenance,
continuity, ordered identifiers, and sequence preservation.

No numerical composite-influence formula is part of the validated v1.0
mechanism, and no numerical composite score is required. Ranking evidence
explicitly records `score_present = false`. Agents must not invent weights or
describe the system as automatically calculating a top list from such a score.

Reordering Drivers to create a fixed Positive, Neutral, or Negative ratio or
sequence is prohibited.

## 8. Source-of-Truth Precedence

Current machine-readable production configuration has authority over prose
summaries, historical implementations, and archive artifacts. Within the
production repository, use the precedence declared by its `AGENTS.md`, led by:

1. `config/automation_entrypoints.json`;
2. `config/weekly_production_policy.json`;
3. the version/Hash-bound `config/canonical_business_rules.json` selected by
   production policy for Data Topic, Keyword, Heat status, and the
   Data-Topic-to-Driver provenance boundary;
4. `config/weekly_bilingual_report_contract.json`;
5. the active policy-selected Skills and rules; and
6. current formal documentation, tests, and validators in their declared
   roles.

Historical outputs and archived implementations are audit evidence only unless
Sol explicitly classifies a maintenance task. Agents must not silently merge
conflicting rules. An unresolved conflict returns to Sol.

## 9. Ambiguity Escalation

Return control to Sol when any of the following occurs:

- evidence conflicts or the important Driver order cannot be decided
  reliably;
- business rules or current sources of truth conflict;
- a requested production command is unknown or unregistered;
- historical and current behavior disagree;
- model or data qualification is ambiguous;
- a conclusion would exceed the evidence boundary; or
- the requested action is high impact or requires an exception.

An agent must identify the ambiguity and preserve the failure or pending state.
It must not guess, silently reconcile, or weaken a gate.

## 10. High-Impact Operations

Workers must not independently execute or authorize:

- production publication, live switching, or server/infrastructure writes;
- final Git staging, commit, push, merge, rebase, release, or branch deletion;
- business-policy or production-threshold changes;
- report-contract weakening or semantic changes;
- model retraining, replacement, recalibration, or registry changes;
- deletion or replacement of authoritative data or historical evidence;
- permission, authentication, credential, secret, domain, TLS, or service
  changes; or
- historical patch execution against current production.

Preparation or inspection by a custom agent does not authorize the final
operation. These actions return to Sol and also require authority appropriate
to the user's request.

## 11. Validation Flow

The stable production governance flow is sequential:

`Sol → Collector → Collection Gate → Analyst → Analysis/Report Gate → Validator → Release Gate → Sol Final Review`

Production stages do not run in parallel. A mandatory failure stops automatic
progression. Existing validated state may be reused only when the current task
did not change its dependencies and current machine-readable policy still
supports it.

The Release Gate determines readiness; it does not itself authorize
publication. Worker PASS results never skip Sol Final Review.

Data Topics and Weekly Report Drivers are separate product layers:

`Raw Community Data → Data Topics → Evidence / Editorial Synthesis → Weekly Report Drivers`

The Data Topic gate checks the frozen-model transform, canonical mapping,
outlier handling, and dashboard reconciliation. The Driver gate checks real
Data Topic and evidence provenance under the existing editorial contract. It
does not require matching titles, counts, or granularity and must not force a
merge, split, or rewrite merely to make the dashboard resemble the report.
Every current Data Topic must have an editorial disposition and rationale for
direct use, merge, split, exclusion, or omission. This is provenance review,
not a numeric impact score. "Important Topic omission" remains a recorded
editorial review item and is not a machine hard gate unless a future definition,
measurement, and allowed-omission rule receive separate approval.

The systemd timer is an execution scheduler, not a Custom Agent orchestrator.
It runs only the machine preparation phase: preflight, bounded collection,
frozen-model preparation, and creation of an immutable
`awaiting_analyst_synthesis` checkpoint. Sol then orchestrates Collector review
and Analyst synthesis outside systemd. The candidate phase verifies that
checkpoint, builds the report, performs machine validation, deploys an immutable
non-LIVE Review Candidate, sends the Internal Review Email, and stops at
`awaiting_human_approval`. Only after real Human Approval, an independent
Validator receipt, and Sol `approved_for_release` authorization may the publish
phase atomically promote that exact Candidate target, verify LIVE, and send the
Final Delivery Email. No pipeline process may fabricate human approval or Agent
runtime evidence.

## 12. Runtime Model Policy

The validated v1.0 runtime configuration is:

- GPT-5.6 Sol for orchestration, governance, ambiguity resolution, and final
  authority;
- GPT-5.6 Terra with `medium` reasoning for bounded collection execution;
- GPT-5.6 Terra with `high` reasoning for evidence-heavy analysis; and
- GPT-5.6 Terra with `high` reasoning for independent validation.

Terra Max is not the default configuration. Luna is not currently validated by
the `spawn_agent` runtime; this does not mean Luna is permanently unsupported.
Future Luna availability may be tested as a separate maintenance task.

Agents must not switch model family or reasoning configuration during a
production run unless Sol explicitly changes the approved runtime policy.

## 13. Configuration Ownership and Non-Duplication

This document owns operating architecture and governance only. It must not
duplicate volatile business configuration, including sample thresholds,
preferred ranges, source or author thresholds, report-count parameters,
workbook field definitions, model parameters, week identifiers, or current
release values.

Those values remain owned by the current machine-readable policy, report
contract, active Skills, model documentation, and registered command maps. A
change to those owners is not implied by an update to this document.

## 14. v1.0 Acceptance Baseline

The v1.0 freeze is supported by the completed acceptance record:

- Step 1: agent installation, root resolution, and parent/child policy layering
  passed.
- Step 2: legacy audit passed and the canonical production closure contained
  20 files.
- Step 3: legacy archive passed; four approved items were moved, with no
  unexpected move and no permanent deletion.
- Step 4: post-cleanup validation passed; the recorded suite was 91/91 with no
  unexpected legacy regression.
- Step 5: discovery found all three configured custom agents.
- Step 6: collector, analyst, and validator positive routing passed with their
  validated runtime configurations; ordering enforcement passed.
- Step 7: all ten tested authority boundaries passed.
- Step 8: collection, analysis/report, validation, release-gate behavior, and
  Sol final review passed; the final regression baseline was 101/101.

The ordering-enforcement gap is resolved. No production publication, server
write, Git commit, or Git push was part of this acceptance.

## 15. Remaining Known Issues

These items remain outside the Agent System v1.0 freeze and must be handled in
separate, explicitly scoped work:

1. **Heat v1.0 real-input readiness** — Priority: CRITICAL for W33.
   The business rule is approved and hash-pinned as `apex-heat-v1.0` from W32.
   A platform with evidence but missing a required real component blocks its
   platform and composite Heat; no proxy or partial-weight renormalization is
   permitted.
2. **Custom Agent orchestration is external to systemd** — Priority: HIGH.
   The repository validates receipts but cannot spawn Codex Custom Agents from
   a timer. Missing runtime evidence blocks production.
3. **Dirty production worktree needs an authorized archival/commit workflow** —
   Priority: HIGH. Preflight now blocks it; no reset or deletion is authorized.
4. **Historical wording in `docs/PUBLISHING.md`** — Priority: LOW. Blocking
   v1.0: No.
5. **W30 historical artifact regression** — Priority: MEDIUM. Blocking v1.0:
   No.
6. **Outer-workspace legacy candidates** — Freeze-baseline inventory: 46
   candidates. Priority: LOW. Classification: deferred workspace legacy
   cleanup. Blocking v1.0: No.
7. **Luna runtime availability** — Priority: LOW. Classification: future
   runtime optimization. Blocking v1.0: No.

Server troubleshooting, outer-workspace legacy cleanup, Luna retry, and the
other listed issues are not authorized by this freeze task.

## 16. Freeze and Change Control

Freeze status: `FROZEN`.

Freeze authority: GPT-5.6 Sol.

APEX Agent System v1.0 is frozen when the recorded gates remain satisfied and
Sol confirms that the freeze itself changed no business rules, production
policy, report-contract meaning, model/data assets, runtime model family, or
high-impact external state.

Future architecture or runtime changes require a separately scoped review and
new acceptance evidence. Production policy and business changes remain under
their canonical owners and are not silently absorbed into this architecture
document.
