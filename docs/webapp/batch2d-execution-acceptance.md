# Batch 2D — execution and recovery acceptance

**2 November 2026.** Bounded acceptance for the local, single-operator, synthetic
saved-evidence workflows introduced in 2A–2C. This is not production release,
source-rights approval, financial approval or human interpretation sign-off.

The full path is exercised: protected HTTP admission → durable job → native
worker and supervised child → verified staged output → registered report →
native reader. Failure cases preserve identity and evidence. Recovery delivers
verified saved output and never dispatches financial processing again.

## Corrections found during acceptance

### Orphaned running jobs

A hard exit after catalogue replacement could leave the ledger at `running`.
Stopping the server and using the documented recovery command then refused the
job solely because of that recorded state, despite complete verified output.

Delivery recovery now marks the selected orphaned attempt `outcome_unknown`,
with an `interrupted` event, **after acquiring the worker and mutator leases**.
It then applies the existing source, operation-receipt, staging and registration
checks. Complete output can be delivered once under its existing identity;
missing or changed proof remains refused. No browser read changes a status, no
worker is automatically restarted and no processing retry is introduced.

### Late browser actions

A delayed submission acknowledgement or report-open response could navigate back
to its original job after the reader had moved to another page. Page actions now
retain the starting address and navigation revision. Their backend work can
finish, while stale navigation/errors are discarded, including leave-and-return
navigation. Changing selected jobs also invalidates old report-opening state.

### Consistent control reads

The larger full-suite run caught a read race: separate autocommit SELECTs could
read the execution row before a worker commit and its latest event after that
commit. The consistency check then falsely reported an unavailable ledger.
Read-only control connections now begin one SQLite read transaction before
validation and retain that snapshot through record/event delivery. No schema or
write permission changes. A deterministic concurrent-commit regression proves
that state and events remain on the same snapshot and that the next read sees
the committed transition. Existing integrity failures still refuse delivery.

Worker readiness is also sampled once per job/list response, so an exit cannot
mix contradictory liveness and recovery flags across its rows. Replaying a
completed request while the worker is disabled keeps its completed/review outcome
and inspection guidance rather than describing it as newly queued.

### History page transitions

Selecting older history could briefly show the prior page's rows under the new
page label. Page changes now clear those rows and their checked timestamp, mark
the history region busy and show a loading message. Pagination controls wait for
the response, then keyboard focus returns to the history heading. Periodic
same-page refreshes retain their explicitly dated snapshot until rechecked.

## Acceptance matrix

| Case | Automated evidence | Browser / operator evidence |
| --- | --- | --- |
| Five real offline profiles | HTTP admission, real supervised processing, registered native views, every artifact download hash, restart and stable one-attempt identities | All five native report families already opened through 2C; recovered close opened again in 2D |
| Lost admission acknowledgement | A 502 replaces the response after actual admission; resending returns the same job and one processing attempt | Unconfirmed submission retained; **Resend same request** retrieved the original job |
| Late acknowledgement/navigation | Six page-action checks cover current, changed and leave-and-return pages, plus stale/current errors | A three-second delayed acknowledgement left the reader on saved report history |
| Source changes after admission | A valid metadata revision breaks the source pin; no processing dispatch | **Source changed**, no report action; test metadata restored byte-for-byte |
| Processing failure | Real supervisor records a controlled nonzero child exit; no requeue | **Failed · inspect evidence**, no report action |
| Processing deadline | One-second limit records uncertainty; duplicate identity retains one attempt | **Outcome uncertain**, processing limit and inspection guidance remain visible |
| Worker interruption | Existing graceful/hard-exit and lease checks; unfinished orphan recovery is refused | Owned paused worker stopped before processing; stopped-worker/uncertain outcome shown; missing-output recovery refused |
| Delivery failure before registration | Staged output/promoted folder retained; delivery-only recovery registers one result | Delivery hold shown, changed staging refused, exact preserved test bytes restored and recovered |
| Failure after catalogue replacement | Exception and hard exit tested separately; recovery reconciles existing run | Worker stopped with no report action; CLI recovered the same identity twice without changing operation receipt or catalogue bytes |
| Changed staged evidence | Recovery refused until preserved valid evidence is restored | Failed recovery retained `delivery_failed`; later valid recovery displayed its audit event |
| Larger durable history | Thirty sequential protected HTTP failures; 25/5 pages reconcile exactly | Thirty added requests plus five earlier jobs produced 25/10 pages, 35 unique IDs, correct focus and return to latest |
| Concurrent ledger reads | One read snapshot spans execution and event checks while a worker commit waits; the next read sees the complete transition | Large-history polling exercised through the actual API; no approval or retry capability added |
| Access / origin / duplicate boundaries | Existing 64 admission checks and 2C client regressions remain applicable | Repeated server restarts renewed tokens; old access cleared; no token was printed or stored in the browser |
| Backup/restored control and older snapshots | Existing storage/worker regressions cover restored delivery, changed proof and old-queued-snapshot duplicate refusal | No independent-device or clean-machine recovery is claimed |
| Original evidence and financial gates | Original entries/files, output agreement, disabled live/paid access, zero model reservations | All 38 rehearsal jobs stayed within the synthetic scope; original five reports and 30 files preserved |

The automated additions are **14 Python acceptance cases**. The frontend now has
**234 tests**, including the new page-action and pagination-transition cases.
Final validation on 2 November 2026:

| Check | Result |
| --- | --- |
| Full Python regression, offline fixture configuration | **1,277 passed** in 295.43 seconds |
| Interface regression | **234 passed** |
| TypeScript checks and production frontend build | **Passed** |
| Protected local HTTP / browser rehearsal | **38 jobs**, nine registered reports; original five reports and 30 artifacts preserved |
| Master native workspace | All **139 existing files unchanged** |
| Final read-only recovered report | Opened in the browser; no console errors observed |

The Python suite and worker rehearsals were run sequentially because they share
the local execution lock. This validation records software behaviour in the
bounded offline scope; it does not change the release boundaries below.

## Repeat the controlled cases

The failure harness is **test-only** at `tests/workspace_execution_scenarios.py`.
Neither the application API nor the production CLI accepts fault parameters.
The harness requires its private synthetic acceptance marker and a fresh
destination. It copies exactly five registered native example families, preserves
their source files and binds only to `127.0.0.1`.

First build the current frontend, then prepare from a registered native workspace:

```bash
.venv/bin/python tests/workspace_execution_scenarios.py prepare \
  --source output/workspace-native-demo \
  --destination output/execution-acceptance-demo

.venv/bin/python tests/workspace_execution_scenarios.py serve \
  --root output/execution-acceptance-demo --port 8797 --fault delivery_before
```

Open `http://127.0.0.1:8797/#/jobs`, connect with the private token file named at
startup, and submit a saved financial close. Stop this test server before running
operator recovery. Replace the job ID below with the actual saved identity:

```bash
.venv/bin/python -m keystone.workspace recover-job \
  --workspace output/execution-acceptance-demo/workspace \
  --jobs-dir output/execution-acceptance-demo/control \
  --job-id job-REPLACE_WITH_THE_ACTUAL_ID

.venv/bin/python tests/workspace_execution_scenarios.py verify \
  --root output/execution-acceptance-demo
```

Closed scenarios are `none`, `lost_ack`, `slow_ack`, `source_changed`,
`processing_failed`, `timeout`, `pause`, `delivery_before`, `delivery_after`,
and `crash_after_registration`. The timeout case needs a one-second form limit.
The pause case has a bounded 45-second checkpoint. The source-change case alters
only the isolated registration metadata and restores it in a finally block.
The script exposes no browser fault-control endpoint. Use fresh roots to repeat
one-shot acknowledgement scenarios and preserve existing evidence.

For volume testing, start the test server with `--fault processing_failed`, then
in a second terminal run:

```bash
.venv/bin/python tests/workspace_execution_scenarios.py history \
  --root output/execution-acceptance-demo --port 8797 --count 30
```

This sends actual protected local HTTP requests, waits for each controlled
failure and records their distinct identities. It supports 1–35 cases and expects
that failure scenario. It does not seed fabricated successful ledger rows.

Automated commands:

```bash
.venv/bin/python -m pytest tests/test_workspace_execution_acceptance.py -q
.venv/bin/python -m pytest -q
cd web
pnpm test
pnpm run build
```

## Local rehearsal record

Generated evidence lives at `output/job-acceptance-2d/` and remains ignored by Git:

- `acceptance.json`: original five run entries, 30 artifact fingerprints and source
  catalogue fingerprint; `verified.json`: retained identities/outcomes and checks.
- `browser-cases.json`: observed browser cases and identities; `history-http.json`:
  thirty actual HTTP job identities; screenshots: stopped/failed/recovered states.
- `recovery-before.json`: operation and catalogue fingerprints before orphan
  recovery. Repeated recovery preserved both files byte-for-byte.
- `control/`: private ledger, inputs, staged reports and operation receipts.
  Its access token is secret and is not a Git or backup inventory member.

The rehearsal retained **38 jobs**: four `review_required`, 31 `failed`, two
`outcome_unknown` and one `source_changed`. Every job had one claimed attempt;
the changed-source and paused-before-processing cases had no operation receipt.
The workspace contained nine reports: five originals and four new registered
results. No failed or unknown job was promoted to an approved financial result.

The existing `output/workspace-native-4c/` master and 2C rehearsal were preserved.
After checks, the fault server/worker was stopped. A normal read-only server can
serve this acceptance workspace; fault controls do not remain active.

## Remaining boundaries

This acceptance is for the supported local synthetic rebuild/render/replay
profiles. Real-source onboarding, user-authenticated approvals, enterprise access,
live/paid execution, independent encrypted backups, clean-machine disaster
recovery and production deployment remain separately scoped. Human interpretation,
physical accessibility and actual PDF/print acceptance retain their earlier status.
