# Webapp Batch 6E — recovery and support

**14 November 2026 · Supervised, single-operator local pilot.**
[Batch 6 roadmap](batch6-operational-readiness.md) · [Open Keystone](open-keystone.md)

Recovery & support connects saved operating states to a careful next step. An
operator can distinguish a request that never started, an attempt whose outcome
is unknown, a complete saved result whose delivery failed, and an input whose
acceptance was interrupted. These cases require different procedures.

For example, a fictional research calculation can finish and save its complete
result proof, then fail to register the report. Delivery recovery verifies that
saved result and registers it, without calculating it again. If a different
attempt stops before a complete proof exists, the same command refuses recovery;
that uncertain original must not be treated as never started.

The batch adds a protected read-only guidance page, a simpler private recovery
command, enforced stopped-server/worker guards, immediate offline audit of a fresh
restore, and this operator runbook. It reuses the existing proof-based recovery
and new-directory restore engines. It introduces no automatic repair, retry,
queue release, deletion or financial approval.

## Recovery & support in the app

Connect to the selected private workspace and choose **Recovery & support**.
**Recheck recovery guidance** reads current operating records. The prior observation
is explicitly labelled while a recheck is pending, and removed on failure. There
is no automatic polling. Timestamps include seconds.

The page lists up to ten job/import cases per page, links each case to its saved
original, and explains the procedure's limits. Historical failed/rejected records
remain history; their presence alone does not declare the current app broken.
Unreadable counts remain unknown, and readable cases are marked as an incomplete
inventory when other records cannot be checked. Successful deliveries remain in
Reports and do not appear as recovery cases merely because they need financial
review.

The page is available in **Open Operations only** mode with the same local key.
In that mode, it shows opaque references and guidance; reconnect normally to open
full job/import records. This is a navigation mode, not a separate access role.

Job-history reads also tolerate normal transaction-file cleanup during a worker
commit. The file's presence and private-file properties are checked with one
metadata probe: an already removed companion is absent, while a linked, exposed,
hard-linked, non-file or unreadable companion still refuses the read. SQLite's
locking, database validation and single-snapshot record/event checks remain in
force. This prevents normal DELETE-journal removal from appearing as damaged
saved history; it does not retry calculations or ignore a real storage error.

`GET/HEAD /api/recovery` returns the closed, workspace-bound recovery contract.
It reuses bounded verified Operations observations. It accepts no query parameters
or mutation, runs no recovery command, and returns no source figures, names,
paths, logs, command strings or credentials. The client bounds the response at
700 KB and rejects extra fields, mismatched guidance/state/counts, duplicate IDs,
foreign workspace identity and invented protection claims. Late or oversized
responses cannot revive a disconnected view.

Guidance is an inspection route, **not a recoverability certificate**. Current
source permissions, input bindings, producer/code identity and result proofs are
rechecked by the actual operator command.

## Choose the procedure from the saved state

| Saved state | Next step | Boundary |
| --- | --- | --- |
| Restored `queued` request with a restoration hold | Inspect the exact never-started request; deliberately release only after current checks pass | Release changes the hold, not the attempt count; a later enabled worker can execute it |
| Ordinary `queued` request | Inspect the original request and worker readiness | Another request creates separate work |
| `running`, owned worker available | Follow the same job and recheck Operations | Process availability is not calculation progress |
| `running`, worker unavailable | Stop the owner and inspect the interrupted attempt/proof | No assumption that it failed before committing |
| `delivery_failed` | Stop writers; inspect/recover the saved delivery | No new financial calculation; recovery can refuse |
| `outcome_unknown` | Preserve the uncertain attempt and verify its saved proof | Missing proof does not justify resetting the attempt |
| `source_changed` | Resolve current source/version/permission/code checks before considering a separate new request | Do not edit the original admission or bypass the hold |
| `failed`, ordinary analysis | Inspect the original evidence; supported complete proofs may be deliverable | No automatic retry |
| `failed`, close workflow | Determine committed versus uncommitted accounting state first | A failed process is not proof of no accounting commit |
| Import `reserved`/`receiving`/`validating` | Follow the original receipt; preserve its identity after lost acknowledgement | Input acceptance is not financial execution |
| Import `interrupted`/`delivery_failed` | Stop writers and inspect verified prepared input | Recovery never repeats validation; incomplete preparation refuses |
| Import `rejected` | Read the validation receipt and deliberately inspect a corrected import if needed | Historical rejection does not trigger an automatic resend |

## Before operator recovery

Use the exact supported checkout/installation and Python environment. Record the
symptom and original request/import identity privately. Stop the owning Open
Keystone terminal and its worker, and wait for shutdown. Stop other cooperative
writers and supervised descendants; direct APIs and other checkouts remain an
explicit operator responsibility. Do not remove lease files or terminate an
unidentified process.

Private recovery commands now first acquire the existing session lease, then
the worker lease, before opening the input store for explicit journal recovery.
An active server or worker refuses recovery. The existing maintenance/mutator
gate also refuses a surviving supervised validator or financial child that still
holds its lease. The server lease remains held for the command's duration, so
the supported server cannot acquire that same session while recovery runs.

The guard does not start a background worker, generate a key, choose an
authoritative workspace or enable a browser recovery action. A failed command
returns a stable safe error and exit 2; preserve its evidence. An inspection may
record an orphaned running attempt as `outcome_unknown` before refusing a missing
proof. Thus a nonzero result is not a promise that no control state changed.

The following examples contain deliberate placeholders. Replace them with the
exact existing paths and IDs; do not paste placeholders unchanged. Run from the
selected Keystone application directory.

## Recover a private saved job delivery

```sh
.venv/bin/python -m keystone.workspace recover-private-job \
  --workspace "/CHOSEN/PRIVATE_WORKSPACE" \
  --job-id job-EXACT_SAVED_ID
```

Exit 0 returns the recovered result identity with financial approval false. Exit
2 means it was not confirmed recoverable; inspect its original saved state.
The same verified delivery can be recovered repeatedly without another attempt.
The operation receipt retains its original bytes; recovery does not rewrite an
uncertain original receipt as though it had completed normally.

The older spelling remains supported for private workspaces and applies the same
stopped guard and fixed reports/control relationship:

```sh
.venv/bin/python -m keystone.workspace recover-job \
  --workspace "/CHOSEN/PRIVATE_WORKSPACE/reports" \
  --jobs-dir "/CHOSEN/PRIVATE_WORKSPACE/control" \
  --job-id job-EXACT_SAVED_ID
```

The older synthetic-workspace recovery spelling retains its existing behaviour.
Do not point a private recovery at an arbitrary control directory.

For a committed close, the existing engine may regenerate derivative report
files from the frozen verified close result if those files were not completed.
It never repeats `execute_close` or the accounting commit. The output remains a
review-required report, not financial sign-off.

If a close has no commit, use the separate existing no-commit procedure only
after the operator has inspected its outcome:

```sh
.venv/bin/python -m keystone.workspace release-uncommitted-close \
  --workspace "/CHOSEN/PRIVATE_WORKSPACE" \
  --job-id job-EXACT_SAVED_ID
```

This checks and resolves an uncommitted close intent. It is not a requeue or
financial execution. A real commit, unsupported profile or unverifiable outcome
refuses the no-commit action.

## Recover prepared input acceptance

```sh
.venv/bin/python -m keystone.workspace recover-import \
  --workspace "/CHOSEN/PRIVATE_WORKSPACE" \
  --import-id import-EXACT_SAVED_ID
```

The same stopped guard now runs before opening input journals. Complete prepared
input is verified and accepted once, preserving the original import identity.
There is no rerun of the validator or financial engine. A missing, incomplete,
changed or ineligible preparation remains refused. Repeated recovery of the
accepted import returns its existing receipt.

## Snapshot, restore and inspect a new copy

First stop all relevant writers and inspect the original workspace:

```sh
.venv/bin/python -m keystone.workspace audit-private \
  --workspace "/CHOSEN/PRIVATE_WORKSPACE"
```

The stopped audit returns exit 0 only for `verified`; `held`/`unavailable` returns
exit 2. It is read-only and does not establish financial accuracy or backup.
Unreadable input journals require explicit supported startup/operator recovery;
ordinary inspection must not silently make a writable journal rollback.

For a new permission-checked snapshot, select an explicitly authorised destination:

```sh
.venv/bin/python -m keystone.workspace snapshot-private \
  --workspace "/CHOSEN/PRIVATE_WORKSPACE" \
  --destination "/CHOSEN/SNAPSHOT_DIRECTORY"

.venv/bin/python -m keystone verify "/EXACT/RETURNED_SNAPSHOT"
```

Use the exact returned snapshot directory. Permission holds, incomplete retained
references, active writers or changed bytes can refuse capture. Local folders
are local snapshot tests, regardless of their names.

Restore to an unused destination, preserving the original and snapshot:

```sh
.venv/bin/python -m keystone.workspace restore-private \
  "/EXACT/VERIFIED_SNAPSHOT" \
  --destination "/NEW/UNUSED_RESTORED_WORKSPACE"

.venv/bin/python -m keystone.workspace audit-private \
  --workspace "/NEW/UNUSED_RESTORED_WORKSPACE"
```

Restoration now creates a **fresh empty session-lock file** in the new copy.
The snapshot still excludes runtime keys/leases; no old lease ownership or key
is restored. This new empty file lets the stopped audit and guarded operator
commands work immediately, before any server is opened. The restore still uses
its original atomic new-directory publication and failure preservation.

Compare the last acknowledged inputs, report bytes, notes/decisions, request and
attempt identities, and applicable accounting state against the verified recovery
point. New work after that snapshot is a reconciliation requirement, not an
automatic merge of two directories.

For initial inspection, start the restored workspace without a worker:

```sh
.venv/bin/python -m keystone.workspace serve \
  --workspace "/NEW/UNUSED_RESTORED_WORKSPACE" \
  --port 8894
```

Choose a free local port deliberately. The server writes a new access key. It
does not enable admission/imports or processing unless explicitly requested.
An interrupted running request stays uncertain; restored queued requests retain
their holds. Stop this inspection server before any operator recovery command.

Release one exact never-started restored request only after deliberately reviewing
the intended authoritative copy, current source, code/producer and input checks:

```sh
.venv/bin/python -m keystone.workspace release-restored-job \
  --workspace "/CHOSEN/RESTORED_WORKSPACE" \
  --job-id job-EXACT_SAVED_ID \
  --reason "Record the specific local review that permits this request"
```

Release leaves the request queued with attempt zero and `processing_started=false`.
A later enabled worker may execute it. Source/code drift or prior attempt files
refuse release; do not weaken the check. Queue release is not financial approval.
Do not select a rehearsal copy as authoritative merely because a drill passed.

## Offline troubleshooting and requesting support

The browser cannot diagnose a server that cannot start. Use this sequence from
the chosen application directory:

1. Preserve the original workspace, installation and any failure evidence. Record
   the symptom, time and command/task that failed privately.
2. Check the supported installation without installing or migrating:
   `.venv/bin/python -m keystone.installation doctor`. A held identity, dependency
   or build requires the [6C setup/update procedure](batch6c-installation-and-updates.md).
3. If local control is busy, return to the original owning terminal. Confirm which
   workspace/port it owns and stop it normally when appropriate. Never delete
   leases, force-unlock state, kill an unidentified process or choose a new
   workspace as a workaround for missing history.
4. For invalid access, stop the owner, inspect permissions and restart; reconnect
   with the new access file. There is no browser-stored credential to recover.
   See [6D](batch6d-access-and-privacy.md).
5. For capacity or missing/changed records, stop writers and use the stopped
   evidence audit. Preserve the last good snapshot; do not remove evidence to
   make space. Resolve source-use holds through the explicit permission procedure.
6. If the app opens, use Operations, Installation & updates, Storage & evidence,
   Access & privacy, then Recovery & support. Record observations before choosing
   the procedure for the exact original request.
7. Review the [redacted check](batch6d-access-and-privacy.md) before sharing it.
   It contains fixed privacy-control states and a timestamp, not the complete
   job diagnosis. A support request can describe the symptom and failed step.
   Keep original logs, names, paths, credentials and financial documents private
   unless that exact transfer is separately authorised.

There is no automatic support upload, message, telemetry or browser repair. Raw
logs and original reports are not made safe by the redacted diagnostic feature.

## Independent protection and recovery targets

The page explicitly reports independent backup, encryption/key recovery and
clean-machine recovery as **not verified here**. It does not inspect a drive or
promote a release gate. The user deferred the external destination; none is
configured or copied by this batch.

The existing proposed local-pilot targets remain at most **one active working
day of acknowledged work lost**, and **eight staffed recovery hours once the
required hardware, verified backup and keys are available**. These are targets,
not measured production guarantees. Acquisition delay and total downtime must be
recorded separately. Source retention/backup rights must permit the exact copy.

Use the [dependency-closure procedure](../production/v1/dependency-closure.md) to
verify an actual physically independent encrypted destination, independently
recover its unlocking secret, and rehearse on a second supported machine. A new
directory, fresh environment or another folder on this Mac cannot establish
survival of losing this device.

## Recorded local acceptance

The offline fictional rehearsal used preserved local snapshots and distinct
seed, visible, trial and corrupted-test directories. No existing user workspace,
source permission or authoritative selection was changed. Evidence remains under
ignored `output/recovery-6e-preview/`.

Verified outcomes include:

- Live-server, live-worker and surviving-mutator refusal before opening input
  journals; private root and legacy reports/control spellings share the guard.
- Immediate stopped audit after fresh restore, without creating a key or server.
- A failed fictional research delivery recovered repeatedly to the same result,
  retaining attempt one and identical original operation-receipt bytes; recovery
  called neither the financial operation dispatcher nor calculator.
- An interrupted attempt without complete proof remained `outcome_unknown`, with
  no second attempt. A restored queue release left attempt zero and no processing.
- Source/code drift refused queue release. A separately prepared matching-source
  trial passed the same explicit checks without bypassing the producer binding.
- Modified inventoried snapshot data was refused without publishing a destination;
  an existing destination and the original verified snapshot were preserved.
- Browser inspection showed the three held/uncertain/delivery cases, links to the
  exact original request and a zero-attempt restored queue. Keyboard refresh and
  the expanded support instructions fit the observed 576 px viewport.

The related backend regression run passed **312 cases** across recovery,
restoration, lifecycle, onboarding, research, close, installation/update and
privacy. All **33 final focused recovery cases** passed; the stopped-mutation
and fresh-restore audit pair also passed separately. All **612 frontend tests**
passed, including 41 new recovery cases;
TypeScript checking and the production build passed.

Closure validation also passed **154 focused backend cases** for transaction-file
cleanup and related access/recovery paths, and **94 affected cases under a
separate Python 3.12 environment**. The controlled commit regression reproduced
the former history-read failure before the fix and passed afterwards. Fifteen
companion-file cases retain rejection of unsafe mode bits, links, hard links,
directories and unreadable files across the three SQLite companion names.

All **58 saved evidence files** in the visible rehearsal copy retained identical
hashes after browser observation. It retained four jobs, no running job and one
held queued request at attempt zero. The separate trial, rather than the visible
copy, exercised explicit recovery and release. These checks are local engineering
acceptance, not issuer/financial sign-off or disaster recovery.

Batch 6's bounded implementation can proceed to Batch 7 pilot scope, analyst
acceptance and release-evidence preparation. External protection, source rights,
real-company close data and final acceptance remain scope-dependent holds. The
six document/PDF intake parts still precede the broader backend programme.
