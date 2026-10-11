# Batch 5 — offline pilot preparation and release review

Prepared 11 October 2026. User selected one offline session across all four agents,
using synthetic inputs and saved evidence. **Preparation and engineering rehearsal
are distinct from analyst acceptance. Production v1 remains unreleased.**

## Scope and evidence

The preparation command creates new isolated state, reports, snapshots, operation
receipts and an analyst working copy. It runs the existing all-agent local storage
check, then the same-candidate stored-evidence recovery check. The latter reuses the
upgrade test machinery, but both sides use current code: this is not a new
prior-version upgrade validation. Original generated state is moved aside before
restore. All copies remain on this Mac.

The bounded workload contains one fixture research run and rebuild, ten synthetic
monitoring cycles followed by one controlled cycle, one fixture news bundle and
calendar revision/replay, fourteen synthetic FP&A closes plus a gap case, report
recovery, and local snapshots/restores. Three controlled recovery operation receipts
are separately snapshotted and restored byte-for-byte. Preparation uses direct
acceptance APIs as well as controlled CLI calls; it is not an all-CLI operator trial.
Agent 3 event arithmetic retains Batch 4 evidence; this rehearsal does not freshly
validate issuer event dates or exercise a live event retrieval.

Timing and logical file sizes are measurements of this one preparation workload.
They include duplicate recovery copies and exclude installation/cache storage,
analyst time and general workload growth. No performance threshold has been accepted;
D-04/D-06 capacity acceptance remains open. Local restore time is not disaster RTO.
No new provider retrieval or paid model call is requested.

## Run preparation

From the repository, use the frozen supported Python environment and a **new** output
path. Finish other acceptance scripts or mutating workflows before running it.
The existing environment can be used only after doctor reports ready for local checks.

```bash
python -m keystone doctor
python -m scripts.check_keystone_pilot --output output/production-pilot/my-session
```

The runner refuses an existing output directory and stops on a failed check. Its
`pilot.json` retains completed steps, safe error type, source hashes, environment,
base commit and dirty-worktree indication. A failure or missing prerequisite never
becomes a passed release. This preparation command is an engineering harness, not
the supervised wrapper: its direct checks do not have a global 600-second deadline.
Do not run it against operational state. Preserve failed output and use a new path
for an intentional repeat.

The pending manifest copies all 26 gate identities and their historical statuses;
**candidate statuses start unassessed**, with empty evidence/reviewer fields. It
always leaves accepted capabilities empty and release approval false. It is not an
authenticated approval system or an automatic release evaluator. Final acceptance
requires the review procedure below, not changing one Boolean in this file.

## Analyst trial

After preparation, open `analyst-tasks.md` in the generated folder. It contains exact
commands tied to that folder, unique operation IDs and the selected interpreter.
Run them **one at a time** and record observations in `analyst-results.json`.
Do not execute this file as a script. Never reuse operation IDs by deleting receipts.

| Task | Operator demonstrates |
| --- | --- |
| UAT-01 | Recognises environment readiness versus financial/release approval |
| UAT-02 | Rebuilds a research report, interprets its hold, traces a figure |
| UAT-03 | Understands duplicate-operation refusal and preserves original evidence |
| UAT-04 | Locates the operation receipt, evidence and paid-usage counters |
| UAT-05 | Retrieves monitoring cycle 9 and distinguishes breach from triage state |
| UAT-06 | Replays saved news and explains fixture cutoff and held tone |
| UAT-07 | Recovers saved close output by run ID without repeating the close |
| UAT-08 | Restores locally to a new directory and understands the device-loss limitation |

Record actual outcome, evidence path, elapsed time and any assistance for every task.
Use status `passed`, `failed`, `blocked` or `not started`; leave unanswered fields
empty. A developer-run smoke check cannot fill these observations for the analyst.
If assistance is needed, record the misunderstanding, improve the instructions and
repeat that task on a new prepared working copy. Research rebuilds use copies;
monitoring and close report tasks read saved state. Runtime operation receipts live
in `state/operations` and must be included in the eventual complete protection plan.

This starter trial does not cover every final UAT requirement: reviewed correction
approval/rejection, live unavailable/stale inputs, issuer event interpretation and
permission-scoped company workflows require their own applicable evidence and
hands-on tasks before V1-UAT-001 passes. The eight tasks are not a waiver of those
requirements. Financial review and source approval remain separate from usability.

## Final release procedure

1. Freeze a clean committed candidate, lock identity, configuration and included
   capability/issuer-period list. Preparation against dirty sources is engineering
   evidence only; rerun affected checks for the selected candidate.
2. Link each applicable matrix gate to its exact expected/actual result, protected
   inputs and hashes, runtime, timestamp and named reviewer. Historical component
   checks do not automatically pass the candidate gate.
3. Complete financial review, representative human-labelled news evaluation and
   authorised company FP&A validation for included capabilities. Any excluded
   capability needs the user's explicit scope decision and visible documentation.
4. Resolve source permissions and independent encrypted protection/key recovery;
   test clean-machine restoration and record provisioning delay separately from
   staffed recovery time. No independent destination is currently authorised.
5. Complete operator tasks, deployment/access review, measured capacity targets,
   clean installation and applicable upgrade/rollback evidence. A fresh virtual
   environment on this Mac does not satisfy clean-machine disaster recovery.
6. Only when all applicable gates pass, record analyst and financial sign-off against
   the exact candidate and issue its release manifest. Do not create a production
   tag or call v1 released while mandatory requirements remain unresolved.

See the [acceptance matrix](acceptance-matrix.md), [release register](release-evidence.md),
[dependency procedures](dependency-closure.md) and [runbook](operations-runbook.md).
