# APEX Task State

## Handoff

- From: Account A
- To: Account B
- Date: 2026-08-15
- Purpose: Codex account handoff
- ACCOUNT HANDOFF: PASS
- PRODUCTION STATE RECONCILIATION: PENDING
- Blocker: The reconciler is locally implemented and approved; Account B must
  execute it on the server and perform the required read-only post-check.

This file is intentional handoff metadata. It is not product code, UI code,
data, a release artifact, or a production authorization.

## Repository

- Workspace path: `/Users/choco/Documents/APEX`
- Canonical repository: `/Users/choco/Documents/APEX/work/public-opinion`
- Current branch: `chore/development-worktree-recovery-20260813`
- HEAD: `8a368cd648bde3b44daf675f8dc8fc3768d2ae2f`
- HEAD subject: `feat: add side-effect-free weekly status reconciler`
- Implementation commit: `8a368cd648bde3b44daf675f8dc8fc3768d2ae2f`
- Working tree after implementation commit: one intentional untracked metadata
  file, `TASK_STATE.md`
- Staged changes before handoff metadata commit: none
- Unstaged tracked-code changes: none
- Untracked files in canonical checkout before handoff metadata commit:
  `TASK_STATE.md` only
- Untracked classification: `intentional handoff metadata file`; do not treat it
  as a product-code dirty state
- Status-only reconciler implementation commit:
  `8a368cd648bde3b44daf675f8dc8fc3768d2ae2f`
- Handoff metadata commit: pending

Other existing worktrees are separate and were not changed:

- `/Users/choco/Documents/APEX/work/w32-ui-integration-20260813`:
  `release/w32-publisher-fix-20260814`, HEAD `522f320`; existing modified
  `scripts/rollback_protected_site.py` and untracked
  `tests/test_rollback_protected_site.py`
- `/private/tmp/apex-w32-download-candidate-20260815`:
  `release/w32-download-dynamic-20260815`, HEAD `c51c1e0`; existing modified
  `outputs/release_check.json`
- `/private/tmp/apex-w32-page-candidate-20260814`:
  `chore/w32-page-candidate-20260814`, HEAD `4ea97a8`; clean at last inspection

## Current Release State

- Current release week: `2026_W32`, 2026-08-03 through 2026-08-09
- W33: not complete; no complete W33 input is available in the recorded state
- Next scheduled target recorded by the production workflow: W33
- Production filesystem pointer, read-only server check:
  `/srv/apex-site/current -> /srv/apex-site/releases/2026_W32_965987e98488`
- Candidate filesystem pointer, read-only server check:
  `/srv/apex-site/candidate -> /srv/apex-site/releases/2026_W32_f37407cd5df7`
- Application service: `apex-app-auth.service` active
- Weekly timer: `apex-weekly-pipeline.timer` active
- Weekly timer next run: `2026-08-17 00:15 CST`
- Public status endpoint `/srv/apex-status/weekly.json` reports a different
  state: current LIVE `2026_W32_df19e000e6cf`, review candidate
  `deployed_not_live`, and latest run `2026_W32_20260814T145947` waiting for
  human approval
- Public status conclusion: `/srv/apex-status/weekly.json` is a stale snapshot;
  it does not reflect the confirmed current or Candidate filesystem pointers.
- Production state conclusion: the filesystem pointers and public status
  endpoint remain inconsistent until Account B executes the approved
  status-only reconciler. The production state is therefore
  `PRODUCTION STATE RECONCILIATION: PENDING`.
- Legacy: prior W31/W32 releases and rollback evidence remain preserved. No
  cleanup or deletion was performed.

## Completed and Approved

The following are recorded as completed or approved within their stated
evidence boundaries:

1. Root and child `AGENTS.md` policies were read. Existing long-term rules are
   complete; neither file was modified.
2. Canonical production command authority was confirmed as
   `config/automation_entrypoints.json` -> `ops/production/weekly_pipeline.py`.
3. Current canonical Git branch, HEAD, staged changes, unstaged changes,
   untracked files, worktrees, and recent key commits were inspected.
4. W32 dashboard source recovery and Topic/Driver provenance rendering are in
   the current canonical branch through commits `5967788` and `ba1049c`.
5. Local W32 formal-release evidence records Candidate identity
   `2026_W32_965987e98488`, public manifest SHA-256
   `965987e98488e0666a472b91150c6ba1f8d8ba2bba293df613359f9ffba386c9`, formal
   Agent/Sol authorization, and successful authenticated live verification.
   This remains recorded evidence and is not treated as a final reconciliation
   of the conflicting public status endpoint.
6. The 2026-08-15 dynamic-download revision was isolated in revision
   `6acb4cf`; its W32 Candidate was recorded as
   `2026_W32_f37407cd5df7`. Candidate server verification passed and the LIVE
   pointer was recorded unchanged.
7. Anonymous Candidate boundary checks passed: the review login shell was
   reachable and protected report/data paths were not anonymously accessible.
   Authenticated acceptance for the newest dynamic-download Candidate remains
   pending.
8. Existing W32 focused UI/download checks and release checks were recorded as
   passing. No tests were rerun during this handoff audit.
9. Account B server access was verified as `B SERVER ACCESS = PASS`; the
   `apex-app-auth.service` and `apex-weekly-pipeline.timer` are active, and the
   next timer run is `2026-08-17 00:15 CST`.
10. Account B production execution capability was verified as
    `B PRODUCTION EXECUTION CAPABILITY = PASS`; the B session can access the
    `apex` service user, production interpreter, and canonical entrypoint. The
    weekly pipeline was not invoked.
11. Read-only reconciliation confirmed `/srv/apex-status/weekly.json` is a
    stale snapshot, while `current` is `2026_W32_965987e98488` and `candidate`
    is `2026_W32_f37407cd5df7`.
12. Account A implemented and locally approved the independent status-only
    reconciler. It is registered with no publish authority and does not replace
    `ops/production/weekly_pipeline.py` as the canonical production entrypoint.

## Status-only Reconciler Handoff

- implementation: PASS
- tests: PASS (17/17)
- side-effect-free verification: PASS
- changed files:
  - `config/automation_entrypoints.json`
  - `scripts/reconcile_weekly_status.py`
  - `tests/test_status_reconciler.py`
- Runtime write boundary: only `/srv/apex-status/weekly.json`, using a
  same-directory temporary file, complete write, `fsync`, `os.replace`, and
  cleanup.
- Runtime read boundary: current/candidate pointers, public manifests, explicit
  publish/deploy receipts, live/candidate verification, latest pipeline state,
  and existing public status context.
- Latest pipeline state is context/safety evidence only; current and Candidate
  identities are independently cross-checked from their pointers, manifests,
  receipts, and verifications.
- B next task: perform a read-only inventory of the five evidence paths, then
  execute the registered status-only command. Afterward re-read current,
  candidate, manifests, receipts, and `/srv/apex-status/weekly.json`. Do not
  deploy, publish, rollback, or run the weekly pipeline.

## Current Implementation

- The canonical checkout is the clean development branch shown above and
  contains the W32 dashboard/provenance implementation.
- The newest dynamic-download implementation is not the current canonical
  checkout; it exists in isolated release worktrees and has a server Candidate
  only.
- The current branch is not identical to the isolated W32 publisher-fix or
  dynamic-download release revisions. Do not infer that an isolated Candidate
  is represented by the current checkout.
- The production pipeline is phase-gated: prepare, candidate, then publish.
  Candidate artifacts do not become LIVE without the required approvals and
  exact-artifact verification.
- The status-only reconciler is a separate maintenance entrypoint. It may only
  rebuild `weekly.json` from validated read-only evidence and has no publish
  authority.
- The requested `docs/data_quality_rules.md` does not exist in either the
  workspace docs or canonical repository docs. The actual quality authorities
  are `config/quality_rules.json`, `docs/DATA_DICTIONARY.md`,
  `config/weekly_production_policy.json`, and the report contract.

## Validation Status

| Area | Status | Evidence boundary |
|---|---|---|
| UI (prior W32) | PASS | Recorded authenticated W32 live interaction checks passed, including W32 selection, Topic/Driver drawer, report download, and logout/privacy flow. |
| UI (newest dynamic-download Candidate) | PENDING | Login shell and anonymous boundary passed; authenticated page, download, Topic/Driver, and logout acceptance remain pending. |
| interaction | PENDING | Earlier W32 live interaction evidence is recorded; newest dynamic-download Candidate still needs authenticated page, download, Topic/Driver, and logout checks. |
| tests | FAIL | Focused checks passed, but the supported full selected set retains one pre-existing narrative-rules packaging mismatch and one environment skip. No test rerun in this audit. |
| status-only reconciler | PASS (17/17) | Focused reconciler tests cover identity cross-checks, fail-closed behavior, atomic write cleanup, no release-side-effect dependencies, and registry authority. |
| reports | PASS | W32 report build/contract evidence records a valid report with 8 drivers; W33 report generation was not run. |
| deployment | PENDING | Filesystem pointers resolve to W32 LIVE/Candidate targets, but stale `/srv/apex-status/weekly.json` still needs the approved reconciler to be executed by B. |
| production acceptance | BLOCKED | The newest dynamic-download Candidate remains pending authenticated acceptance; no server-side reconciliation was executed in this handoff. |

## Frozen Constraints

- Do not modify, retrain, replace, recalibrate, rename, or delete the frozen
  BERTopic model, topic registry, mapping, raw data, annotated data, or
  historical evidence.
- Preserve the distinction between real bounded samples, public-search sample
  observations, mixed incomparable units, simulated data, model output, and
  formal statistics.
- Do not add B站 comments and 小黑盒 visible posts into a formal cross-platform
  total.
- Keep Data Topic and Weekly Report Driver as separate provenance layers.
- Preserve the bilingual single-sheet report contract, evidence-qualified
  driver rules, and the 8-10 driver limit without padding or unsupported causal
  claims.
- W32 and later use the approved `apex-heat-v1.0` rule; W25-W31 Legacy Heat is
  not recalculated or rewritten. Missing real components or proxy Heat block
  release.
- Use only the canonical production entrypoint and its serial fail-closed
  gates. Do not infer production authority from legacy or one-off scripts.
- Candidate and LIVE must remain separate. A Candidate may be promoted only
  after exact-artifact verification, required human approval, independent
  validator evidence, and Sol authorization.
- Do not treat a successful subset, local artifact, server symlink, or preview
  hash alone as complete production acceptance.
- Keep credentials, cookies, tokens, browser sessions, private evidence, and
  personal absolute paths out of public artifacts and Git.

## Known Issues

1. `/srv/apex-status/weekly.json` remains a stale snapshot until B executes the
   approved reconciler: current is `2026_W32_965987e98488` and Candidate is
   `2026_W32_f37407cd5df7`, while the file reports older state.
2. The newest dynamic-download Candidate is not yet authenticated-accepted.
3. The supported full selected test set has a pre-existing narrative-rules
   packaging mismatch and one environment skip; this was not changed here.
4. W33 readiness is blocked at the first direct dependency: Topic/Driver
   relation generation is W32-only, and complete W33 input is absent.
5. `docs/data_quality_rules.md` is missing; do not create a substitute without
   explicit scope.
6. A separate release worktree contains existing uncommitted rollback code and
   test work. It is outside the canonical checkout and must be preserved.

## Pending Work

1. Account A code handoff: commit and push the approved status-only reconciler
   and the handoff metadata on this branch.
2. Account B may then perform a read-only inventory of the evidence paths and
   execute that reconciler on the server.
3. After execution, Account B must perform a fresh read-only check of
   `current`, `candidate`, `/srv/apex-status/weekly.json`, manifests, and
   receipts.
4. Once all state sources are consistent, continue the newest Candidate
   acceptance.

## Do Not Do

- Do not modify product code, UI, data, models, report semantics, validators,
  contracts, or server configuration as part of this handoff. The only registry
  change is the approved status-only maintenance entrypoint recorded above.
- Do not manually modify `/srv/apex-status/weekly.json`.
- Do not rerun the weekly pipeline to refresh status.
- Do not redeploy, publish, or rollback W32.
- Do not commit or push unrelated worktree or historical changes. The approved
  reconciler files and this handoff metadata are the only files in scope for
  the A-to-B commit/push.
- Do not deploy, promote, rollback, delete, clean, or switch a release.
- Do not treat the untracked `TASK_STATE.md` as a product-code dirty change;
  it is intentional handoff metadata.
- Do not treat the public status endpoint or filesystem pointer alone as the
  final production truth while they disagree.
- Do not use W32 as a substitute for W33.
- Do not alter either `AGENTS.md` unless a future audit proves a missing rule.

## Recommended Next Action

Account B's first action after receiving the pushed commit is a read-only
inventory of the current/candidate evidence paths, followed by the registered
status-only reconciler. Then B must repeat the read-only
pointer/status/manifests/receipts verification. Do not publish or modify the
server release state.

## Evidence

### Rules and source of truth

- `/Users/choco/Documents/APEX/AGENTS.md`
- `/Users/choco/Documents/APEX/work/public-opinion/AGENTS.md`
- `/Users/choco/Documents/APEX/work/public-opinion/config/automation_entrypoints.json`
- `/Users/choco/Documents/APEX/work/public-opinion/config/weekly_production_policy.json`
- `/Users/choco/Documents/APEX/work/public-opinion/config/weekly_bilingual_report_contract.json`
- `/Users/choco/Documents/APEX/work/public-opinion/config/workflow_v1.json`
- `/Users/choco/Documents/APEX/work/public-opinion/config/quality_rules.json`
- `/Users/choco/Documents/APEX/work/public-opinion/docs/PRODUCTION_RUNBOOK.md`
- `/Users/choco/Documents/APEX/work/public-opinion/docs/PUBLISHING.md`
- `/Users/choco/Documents/APEX/work/public-opinion/docs/MODEL_VERSION.md`
- `/Users/choco/Documents/APEX/work/public-opinion/docs/DATA_DICTIONARY.md`
- `/Users/choco/Documents/APEX/work/public-opinion/docs/AGENT_SYSTEM.md`
- `/Users/choco/Documents/APEX/work/public-opinion/scripts/reconcile_weekly_status.py`
- `/Users/choco/Documents/APEX/work/public-opinion/tests/test_status_reconciler.py`

### Git and local state

- Current branch and HEAD: `chore/development-worktree-recovery-20260813`,
  `8a368cd648bde3b44daf675f8dc8fc3768d2ae2f`
- Implementation commit: `8a368cd648bde3b44daf675f8dc8fc3768d2ae2f`
- Key commits: `8d3ac63`, `5967788`, `ba1049c`
- Remote baseline: `origin/main` at `143bd3b`
- After the implementation commit, canonical `git status` contained only this
  intentional handoff metadata file; it is now staged for the separate metadata
  commit.
- Existing planning/evidence records:
  `/Users/choco/Documents/APEX/findings.md` and
  `/Users/choco/Documents/APEX/progress.md`

### Release and validation evidence

- `/Users/choco/Documents/APEX/outputs/w32_live_authorization_20260814/agent_runtime_receipt.json`
- `/Users/choco/Documents/APEX/outputs/w32_live_authorization_20260814/collector_review.json`
- `/Users/choco/Documents/APEX/outputs/w32_live_authorization_20260814/analyst_review.json`
- `/Users/choco/Documents/APEX/outputs/w32_live_authorization_20260814/validator_review.json`
- `/Users/choco/Documents/APEX/outputs/w32_live_authorization_20260814/sol_release_review.json`
- `/Users/choco/Documents/APEX/outputs/w32_formal_release_20260811_v2/W32_FORMAL_RELEASE_AUDIT.md`
- `/Users/choco/Documents/APEX/outputs/w32_page_candidate_20260814/release_corrected/2026_W32/candidate_verification.json`
- `/Users/choco/Documents/APEX/outputs/w32_page_candidate_20260814/release_corrected/2026_W32/candidate_deploy_receipt.json`
- Local validation: `/Users/choco/Documents/APEX/.venv-bertopic/bin/python -m unittest tests/test_status_reconciler.py tests/test_weekly_production_ops.py -v` — 17/17 passed.
- Local side-effect verification: fixture snapshots changed only the test
  `weekly.json`; atomic temporary files were cleaned on success and simulated
  replace failure.

### Server read-only evidence, 2026-08-15

- `readlink -f /srv/apex-site/current` returned
  `/srv/apex-site/releases/2026_W32_965987e98488`
- `readlink -f /srv/apex-site/candidate` returned
  `/srv/apex-site/releases/2026_W32_f37407cd5df7`
- `systemctl is-active apex-app-auth.service` returned `active`
- `systemctl is-active apex-weekly-pipeline.timer` returned `active`
- `systemctl list-timers --all apex-weekly-pipeline.timer` reported next run
  `2026-08-17 00:15 CST`
- `/srv/apex-status/weekly.json` returned current LIVE
- `2026_W32_df19e000e6cf`, review candidate `deployed_not_live`, and latest run
  `2026_W32_20260814T145947` with `awaiting_human_approval`; this was confirmed
  to be a stale snapshot
- B server access: `PASS`
- B production execution capability: `PASS`
- Current pointer: `2026_W32_965987e98488`
- Candidate pointer: `2026_W32_f37407cd5df7`
- Status-only reconciler implementation is local and approved; no server
  execution was performed in this handoff.

### Post-write verification (completed)

- Completed: re-read this file from the canonical repository root.
- Completed: ran `git status --short --branch`.
- Completed: checked staged, unstaged, and untracked entries.
- Completed: `git diff --name-only -- AGENTS.md` returned no changes.
- For untracked `TASK_STATE.md`, ordinary `git diff` is not applicable; its
  content was verified by direct re-read and required-section checks instead.
- Confirmed `TASK_STATE.md` is handoff metadata and is intentionally included in
  the separate handoff metadata commit; no other worktree changes were staged.
