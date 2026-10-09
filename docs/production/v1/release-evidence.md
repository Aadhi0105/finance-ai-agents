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
| Independent backup destination and key recovery | Unassigned, D-03 |
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
