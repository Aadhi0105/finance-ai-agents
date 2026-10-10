# Production v1 release evidence register

Status: **not released; no production sign-off**. Batch 1 completed 10 October 2026.
Scope baseline inspected at commit `15502439d6d0527ebb45beadc2431f9dfac0ed80`.
This hash identifies the inspected implementation, not a newly accepted release.

## Candidate record to complete

| Field | Current value |
| --- | --- |
| Release tag / candidate commit | Unassigned |
| Accepted agent modes / issuer-period scope | Unassigned; candidates in specification/data inventory |
| Exact macOS, hardware, Python, dependency lock identity | Unassigned |
| Model IDs, prompts, provider/configuration identities | Unassigned |
| RPO / RTO requirement | ≤ one active working day of device-loss changes / ≤ eight staffed recovery hours under D-02; not yet measured |
| Independent backup destination and key recovery | Deferred by user; actual device and key recovery unverified, D-03 |
| Applicable matrix results | No complete Production v1 gate passed |
| Authorised Agent 4 dataset | Not available; user confirmed dependency |
| Analyst / financial-review sign-off | None |
| Release decision | Not eligible yet |

## Evidence record format

For each matrix ID retain: exact candidate and environment; input/source manifest
and permissions; predeclared expected outcome/tolerance; command or manual procedure;
actual result; timestamp; checksums or protected artifact references; reviewer and
limitations. Reference evidence through a stable manifest, not only a developer's
absolute local path. Keep confidential data and credentials out of Git.

## Batch 1 completion record

Delivered specification, acceptance matrix, source inventory, authoritative storage
map, recovery requirements, evidence baseline, operating outline, decision register
and implementation sequence. Existing evidence is explicitly partial/historical.
User confirmed no authorised Agent 4 dataset yet and delegated recovery-target choice.
The selected recovery target is a design requirement, not a passed test.

Documentation validation completed: 80 relative file/anchor links checked across
the root guide and nine planning documents; 26 unique acceptance IDs and their
references verified; whitespace check passed. The root navigation subsequently
adds the valid `production-v1-planning` heading link. Decision references map to
D-01 through D-07 in the register. Only documentation changed.
No runtime tests, paid model calls, live provider validation, backup creation or
restore rehearsal are claimed by Batch 1.

## Final release decision

Before release, populate all candidate fields, pass every applicable mandatory
matrix row, resolve or explicitly exclude blocked capabilities, complete user tasks,
and obtain sign-off against the exact candidate. Record accepted limitations and
conditions that suspend use. Any later code/configuration/model/data change must
identify which evidence needs rerunning; old approval does not automatically transfer.

## Batch 2 local verification — 10 October 2026

- Full repository regression suite: **959 tests passed**, including **29 new local
  storage tests**. No paid model or live provider calls were used for these checks.
- Example inventory validation reports unresolved metadata/permissions and explicitly
  returns `release_approved: false`.
- Four-agent fixture rehearsal restored 67 files with the original source directory
  moved aside. Agent 1 rebuild used a separate working copy and retained review;
  Agent 2 state and audit export matched; Agent 3 calendar/revisions and replay
  survived relocation; Agent 4's 14 closes plus auxiliary gap evidence matched,
  with identical recovered saved JSON and working regenerated HTML.
- A rehearsal exposed an incorrect README rebuild example (`--output` is not accepted
  with Agent 1 rebuild). The example now documents working-copy/in-place behaviour.
- Relative documentation links and whitespace checks passed. Runtime code is still
  an uncommitted candidate; manifest source hashes and dirty-worktree indication
  distinguish it from the inspected main commit.

The acceptance summary under `references/acceptance/production-storage-2026-10-10.json`
records the final same-device run. Original generated artifacts remain in ignored
local output. This evidence does not satisfy independent-device/clean-machine recovery,
source-rights approval, an eight-hour measured disaster RTO, real-company FP&A, or
Production v1 sign-off. These remain explicit matrix dependencies.

## Dependency preparation — 10 October 2026

Prepared [backup/key recovery and disaster-drill procedures](dependency-closure.md)
and [source-use review](source-use-review.md) against merged Batch 2 commit
`9584b25a804d907c66f28d993ebc27bb28616988` (PR #27). The earlier uncommitted
candidate description records the state at the time of local testing.
Desktop/Keystone resolved to `/dev/disk3s5` on `/System/Volumes/Data`.
DiskManagement was unavailable, so encryption was not verified. User then deferred
independent backup. No copy, device change, new restore or runtime test occurred.
Only the original Mac is available. No acceptance gate is advanced.

## Batch 3 local verification — 10 October 2026

[Controlled operation](batch3-operation.md) and the
[machine-readable evidence](../../../references/acceptance/production-operations-2026-10-10.json)
record this uncommitted candidate against main `9584b25`. Runtime source hashes
identify the tested changes independently of the unchanged base commit.

- Full suite in the fresh hash-verified environment: **984 passed in 112.35 seconds**.
- After final directory durability/evidence-location updates: **26 operation tests
  passed in 23.03 seconds**, including one newly added durability regression.
- An earlier serialized clean-environment check passed all 50 then-existing storage
  and operation tests. Verification runs must not overlap in one checkout: the
  admission lock correctly refuses competing test processes.
- New checks exercise real CLI conflict/worker inheritance, reused operation IDs,
  private artifacts, deadline descendant cleanup, SIGTERM cancellation, preservation
  of committed DuckDB data while an uncommitted transaction is interrupted, safe
  control logs, live-data admission and mocked paid-call refusal/usage limits.
- Fresh local installation used pinned wheel hashes, no index during installation,
  and passed dependency consistency checks on macOS 26.6.1 arm64 / Python 3.11.9.
- Prior-state rehearsal used an archive of main `9584b25`, whose commit identity was
  verified from the Git archive. The archive lacks `.git`, so its snapshot correctly
  records a null source commit; the separate archive identity is retained in evidence.
- Current code rebuilt research, replayed news, recovered close output and advanced
  monitoring from 10 to 11 cycles. Snapshot rollback restored 10 cycles without
  changing the backup. The prior code then read that state and recovered identical
  Agent 4 saved JSON. No financial schema migration was introduced.
- Controlled CLI smoke returned the expected review-required result; inspection
  confirmed its evidence location and zero paid requests.

Package downloads were the only new external retrieval for these checks. No paid
model call, new live financial/news retrieval, external backup or device change was
performed. Temporary installation/previous-release files remain local test artifacts,
not independent backups. Final production candidate sign-off and the outstanding
matrix dependencies remain open.

## Batch 4 bounded financial checks — 10 October 2026

The [frozen plan](../../../fixtures/production_v1/batch4-plan.json),
[scope and tolerances](batch4-financial-acceptance.md) and
[committable result](../../../references/acceptance/production-financial-2026-10-10.json)
record this offline evaluation against application main `53aa8fd874f7b9340e59bc85cb80feecf7dd9aa2`.
The evaluator and new harness tests are uncommitted candidate additions identified
by source hashes. No production financial logic was modified.

- All five evaluation sections passed their scoped offline checks.
- ASML retained issuer arithmetic and three margins reconciled. Four independent
  Decimal DCF cases cover twelve scenario valuations and six negative boundaries.
- Stadler's three ratios and fourteen declared workflow/contract scenarios passed,
  including controlled correction approval/rejection and unchanged original replay.
- Two retained event bundles passed independent raw-price/OLS validation across
  10 event windows and 10 control windows; held exports remained held.
- All 32 synthetic news cases matched. Across 40 entity decisions: 13 true positives,
  27 true negatives, zero false inclusions and zero false exclusions. These are
  assistant-authored contract labels, not real-feed accuracy results.
- Agent 4's 14 synthetic closes and auxiliary gap case passed the existing independent
  exact-cent controls, including corrections, rebudget, delivery recovery and history.
- Selected regression suite: **309 passed in 32.76 seconds**, including **8 new
  acceptance-harness tests**. Injected wrong DCF values and false news inclusions
  were detected by the evaluator. This was not a new full-repository test run.
- A separate 40-headline retained-data pack is awaiting human labels. Predictions
  are hidden and raw headlines remain in ignored local output, not this evidence file.

No new financial/news retrieval or paid model call was made. The unchanged frozen
plan passed its final run after adding an explicit close-count assertion and dirty
worktree provenance. Historical source checks, synthetic corrections and synthetic
company data do not substitute for source permissions or human financial approval.
V1-A3-002 and V1-A4-001 remain blocked; other supported financial/data rows remain
in progress. No production gate or release is marked passed.
