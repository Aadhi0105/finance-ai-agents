# Production v1 operations runbook

**Not yet a fully accepted production runbook.** Batch 2 supplies tested local
[snapshot/restore procedures](batch2-storage.md); independent backup configuration
remains outstanding. [Batch 3 procedures](batch3-operation.md) now cover controlled
launch, duplicate IDs, limits, interruption, diagnostics, installation and rollback. Existing agent commands remain in the
[project guide](../../../README.md). Use the scoped commands in those implementation guides; final release acceptance is pending.

| Procedure | Required content and verification | Gate |
| --- | --- | --- |
| Provision | Supported machine/OS/Python, frozen dependencies, disk/access checks, secret provisioning, no public listener | V1-REL-001, V1-ACC-001 |
| Start session | Select correct state/data mode, inspect latest verified independent backup, validate source permissions and cost configuration | V1-DAT-001, V1-EXE-003 |
| Run analysis | Explicit inputs, run identity, expected statuses; prevent concurrent mutation; preserve evidence on interruption | V1-EXE-001/002 |
| Review | Distinguish computation success, financial hold, unavailable source and committed delivery failure | V1-OPS-001 |
| Decide corrections | Inspect exact evidence, record deliberate decision and reason; preserve originals; no independent-authentication claim | V1-ACC-002 |
| End session | Quiesce stores, create and verify independent snapshot, record protection point; failed protection requires visible action | V1-STO-001/002 |
| Diagnose | Locate run/cycle/close and last checkpoint, inspect safe logs, establish whether state committed before retry | V1-OPS-001 |
| Restore | Follow tested manifest procedure into clean environment; verify integrity and agent-specific invariants; no fresh provider/model call | V1-STO-002/003/004 |
| Upgrade | Snapshot, apply supported migration, validate, roll back or restore on failure | V1-REL-002 |
| Share/export | Confirm rights and confidential-content scope; include necessary evidence files without credentials | V1-DAT-001, V1-ACC-002 |

## Pilot protection policy

Target backup at the end of each session that changes persistent evidence and
before migrations or high-consequence correction/close work. Show the last verified
independent protection point; a local output file is not that point. If a required
snapshot fails, pause further mutating production work until protection is restored
or an explicit scope/risk decision is recorded. These are target procedures, not
newly implemented runtime enforcement.

For ordinary process/export failure, recover acknowledged committed records without
financial duplication. For complete loss of the working device, allow at most the
most recent active working day's changes; restore within eight staffed hours from
incident declaration and availability of supported replacement hardware, backup and
keys. Report provisioning delay and total elapsed downtime separately. Do not call
this an always-on SLA. See [storage requirements](storage-and-recovery.md).

## Escalation boundary

The analyst owns the local pilot and release decision. On integrity mismatch,
unknown commit status, source inconsistency or secret exposure, preserve evidence
and stop the affected workflow; do not reset the database or weaken validation.
Implementation support diagnoses from permission-scoped evidence. No external
support/on-call service or automated notification system is promised by v1.

## Prepared dependency procedures

See [backup/key recovery and disaster drill](dependency-closure.md) and
[source-use review](source-use-review.md). User deferred independent backup after
the supplied Desktop folder was confirmed to be on internal storage. Only this Mac
is available. Procedures are prepared, not executed acceptance evidence.

## Start and recovery for the controlled local scope

1. Run `python -m keystone doctor`; resolve drift/access holds before relying on the
   candidate. Confirm explicit state/output paths, source permissions and protection
   status. Deferred independent backup means no production protection claim.
2. Use `python -m keystone.operation AGENT --operation-id UNIQUE_ID -- AGENT_ARGS`.
   Paid models and live data each require a separate opt-in; see the Batch 3 guide.
3. Run `python -m keystone inspect-operation UNIQUE_ID` and inspect native agent
   evidence. Review holds are not system failure; process completion is not approval.
4. For cancellation/unknown state, locate the saved agent cycle/close/attempt before
   deciding on a new operation. Recover committed delivery by its original identity.
5. Include `state/operations` in the reviewed snapshot inventory as role `logs`.
   Never delete a lock or receipt to force a retry.
