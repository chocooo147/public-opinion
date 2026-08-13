# APEX Production Repository Agent Policy

## 1. Production-tree scope

This file applies to the Git repository rooted at this directory and to every
descendant directory unless a deeper `AGENTS.md` provides a narrower rule.

This repository is the canonical APEX production code tree. It inherits the
workspace policy at `../../AGENTS.md`. The parent policy owns agent routing,
shared-runtime safety, and high-impact authority; this file owns
repository-local source precedence, command authority, and execution
boundaries.

Nothing in this file grants permission to modify outer shared data, models, or
historical outputs. Those paths remain governed by the parent workspace policy
and the current repository path configuration.

## 2. Source-of-truth precedence

Agents must read current project files rather than rely on copied rules in
prompts, old outputs, or memory.

When instructions overlap, use this precedence:

1. `config/automation_entrypoints.json` for the active production entrypoint,
   stage authority, and legacy/non-production exclusions.
2. `config/weekly_production_policy.json` for current production gates and
   bindings to other policy-owned resources.
3. `config/weekly_bilingual_report_contract.json` for the current report
   contract.
4. The active project Skill and references selected by current production
   policy.
5. Current formal documentation under `docs/`.
6. `README.md` for general repository usage.
7. Current tests and validators as executable verification.
8. Historical reports, archived outputs, repair scripts, supplements, patches,
   and old logs only as audit evidence or explicitly authorized maintenance
   inputs.

If current sources conflict and this order does not resolve the conflict
safely, stop the affected stage and return the issue to Sol. Do not invent a
combined rule.

## 3. Canonical command authority

Before a production or production-relevant task:

1. Read `config/automation_entrypoints.json`.
2. Use the entrypoint and stage commands it currently authorizes.
3. Read the current policy, contract, Skill, documentation, and validators
   required for the requested stage.
4. Run commands from this repository root or pass this directory explicitly as
   the project root.
5. Resolve shared data, model, and historical-output paths through the current
   project path mechanism and its supported environment overrides.

Do not scan `scripts/` and infer production commands from filenames. Command
discovery must use `config/automation_entrypoints.json` and the canonical
pipeline, or another explicitly registered current command map. Do not run
production code with the outer workspace directory as the production root. Do
not rewrite a relative path until its configured base and environment-override
behavior have been established.

## 4. Historical and one-off commands

Files identified as legacy or one-off by the current automation configuration
are not production defaults.

`archive/legacy_scripts/` is non-executable by default and is not current
business-rule authority. Historical or unknown commands must return to Sol for
classification and explicit authorization.

Likewise, week-specific repair, patch, rectification, supplementation,
finalization, migration, or historical builder scripts must be treated as
maintenance tools unless a current canonical source explicitly promotes them.

Use such a command only when Sol has classified the task as a bounded audit,
repair, migration, or maintenance operation. A historical tool must not create,
replace, or publish a current production release merely because it can produce
similarly named artifacts.

## 5. Agent execution boundaries

All agents remain inside the objective, paths, outputs, validation method, and
escalation conditions delegated by Sol.

### Sol

Sol selects the task type, resolves ambiguity and current-rule conflicts,
defines write scope, reviews evidence, controls high-impact operations, and
owns final acceptance.

### `apex_collector`

The collector may perform only bounded collection-stage work and
collection-specific inspection or verification. It must not broaden source or
time scope, bypass platform protections, reinterpret measurement units, alter
business rules, continue into analysis or publication, or convert a blocked
collection into success.

### `apex_analyst`

The analyst may perform only bounded preparation, approved model application,
dashboard/report construction, and evidence synthesis. It must use the current
policy-selected model and report paths, preserve source limitations, and stop
when evidence or approval is insufficient. It must not change canonical
semantics, retrain or replace models, weaken validation, or publish.

### `apex_validator`

The validator is independent and read-first. It may run or inspect the current
tests, validators, integrity checks, release-boundary checks, and explicitly
authorized live verification. It must classify blocking findings honestly and
must not change the implementation or rules under review merely to obtain a
pass.

Agent role labels never expand filesystem scope or high-impact authority.

## 6. Repository write boundary

For an authorized implementation task, edit only the files Sol or the user
placed in scope. Preserve unrelated uncommitted work.

- Treat authoritative inputs as immutable unless a current canonical workflow
  explicitly creates a new derived artifact.
- Prefer versioned or timestamped outputs over silent replacement.
- Do not modify policy, contracts, validators, or model/data definitions to
  make an output pass.
- A mandatory failure stops automatic progression to later stages.
- A command completing successfully is not by itself proof that the resulting
  artifact or release is valid.

Writes outside this repository, including writes to shared runtime roots,
require explicit scope and remain subject to the parent policy.

## 7. High-impact operations

Return the following to Sol:

- Git add, commit, push, merge, rebase, force operations, release creation, or
  branch deletion;
- production deployment, remote-server writes, or switching a live release;
- deletion or replacement of authoritative data, models, registries, or
  historical evidence;
- permission, credential, authentication, secret, domain, TLS, web-server, or
  service configuration changes;
- changes to production policy, report contracts, model semantics, or data
  definitions.

Inspection and preparation do not authorize the final operation. External or
remote writes also require the user's request to place that action in scope.

## 8. Rule ownership

This file defines agent behavior inside the production repository. It must not
duplicate business thresholds, workbook layout facts, report-count rules,
model parameters, or other values owned by current configuration, contracts,
Skills, model documentation, or validators.

When such a rule changes, update its canonical owner rather than copying the
new value into this file. Modify this file only for production-tree scope,
command authority, agent execution boundaries, escalation, or verification
responsibility.

## 9. Final review

Sol must independently inspect the evidence appropriate to the task before
declaring it complete. A custom-agent status or a successful subprocess exit is
not sufficient acceptance evidence.
