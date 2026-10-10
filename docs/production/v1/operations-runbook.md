# Production v1 operations runbook — procedure outline

**Not yet a fully accepted production runbook.** Batch 2 supplies tested local
[snapshot/restore procedures](batch2-storage.md); independent backup configuration
and Batch 3 operating controls remain outstanding. Existing agent commands remain in the
[project guide](../../../README.md). No invented backup/release command is provided.

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
