# v1 authoritative storage and recovery requirements

Status: requirements baseline plus Batch 2 local implementation. See
[implemented commands and boundaries](batch2-storage.md). Independent-device
protection and final release acceptance remain unverified. [Specification](specification.md) · [Matrix](acceptance-matrix.md).

## Authoritative record map

| Workflow | Primary record | Companion evidence required | Regeneration limits |
| --- | --- | --- | --- |
| Agent 1 | Per-run `model.json` with saved inputs and execution | Original HTML/charts when historical presentation must be retained; release/configuration identity | Rebuild revalidates/renders with current code; not a byte-identical original report guarantee |
| Agent 2 | Selected DuckDB: original cycles, observations, current state, review queue and decisions | `output/monitor-triage/` audits, exact watchlist/reference versions and exported snapshots | Current HTML can be regenerated, but original-versus-effective state and audit associations must remain clear |
| Agent 3 | Sealed `bundle.json` per terminal persisted attempt | `run.json`, source/evidence retained by bundle, outcome/calendar database and revisions, exports | Bundle index can be rebuilt; calendar/history is not wholly replaceable by an index. Replay uses retained windows/scores, not fresh providers |
| Agent 4 | DuckDB saved runs, version panels, lineage, attempts, delivery records and heads | Original submitted files, release/configuration identity, JSON and complete report folders | Stored JSON recovery can be byte-identical; current HTML/navigation is derivative and may differ |

Code stored in Git is not a backup of ignored `output/` or `*.duckdb` files.
A second copy on the same physical disk is not protection against loss of that disk.
Local hashes do not authenticate an actor who can rewrite both content and hashes.

## Required logical layout

Define separate roots for application release, working state, evidence/artifacts,
configuration references, logs, and backup destination. Preserve a manifest of the
physical paths until a portable identity scheme is implemented. Do not relocate
existing databases as a documentation-only cleanup.

Agent 2 currently associates triage audits using resolved database path and cycle
digest. A restore to a new path can omit valid historical audits. Batch 2 must
resolve this explicitly: preserve the supported path, or implement a controlled,
tested portable identity/association mechanism. Never rewrite old evidence silently.

## Consistent backup procedure to implement

1. Acquire a coordinated maintenance boundary and prevent new mutating work.
2. Finish or explicitly interrupt active work under its agent-specific policy;
   close/checkpoint stores using supported database operations.
3. Capture the complete authoritative set and companion files into a staging snapshot.
   Do not copy an active database blindly and assume it is consistent.
4. Create a manifest with schema/release/configuration identity, file identities,
   hashes, sizes, included runs/entities, timestamp and any exclusions.
5. Verify the staged set, publish the completed snapshot atomically, and retain the
   previous verified snapshot if any step fails.
6. Copy to the selected independent failure domain with appropriate access/encryption.
   Only then declare the protection level actually achieved.
7. Record backup outcome separately from analytical success. Failed backup must be
   visible and must not be reported as successful protection.

No secrets should be included in an ordinary export/backup by accident. Document
credential re-provisioning and encryption-key recovery separately; an encrypted
backup without recoverable keys is not a successful recovery design.

## Recovery objectives and retention

Selected target (D-02, 10 October 2026): for total working-device loss, RPO is at
most one active analyst working day's changes. RTO is at most eight staffed hours
from incident declaration once a supported replacement environment, independent
backup and keys are available. Record provisioning delays and full elapsed downtime
separately. These targets are not currently proven and are not a 24/7 service SLA.

For process/export failures, acknowledged committed financial state must remain
recoverable without duplication. End each mutating session with a verified independent
snapshot; also snapshot before migration/high-consequence changes. Expose the last
protected point and stop further mutating production work after a required backup
fails, pending recovery or an explicit decision. Local commits alone do not satisfy
device-loss protection. Destination, encryption/key recovery and retention remain
open in D-03. Test target compliance through a clean-environment restore.

Until retention is approved, Batch 2 must not introduce automatic destructive
expiry. Expiry must account for original evidence needed by corrections and later
reports, data-source rights, confidential-data commitments and backup copies.

## Restore acceptance exercise

Restore to an empty supported environment without reading the original working
state. Retrieve credentials through the documented separate process. Verify the
manifest and detect deliberately missing/corrupt files. Check:

- Agent 1 saved evidence remains inspectable and rebuild keeps original restrictions.
- Agent 2 original cycles, effective corrections, pending reviews and triage links agree.
- Agent 3 bundles replay as expected and outcome/calendar history remains complete.
- Agent 4 source versions/lineage and saved closes reconcile; JSON delivery remains
  identical where promised, and full HTML history/evidence navigation works.
- No restore triggers a new paid call or silently refreshes provider data.
- Conflicting destination state is refused or handled by an explicit safe procedure.
- Observed lost data and recovery duration meet the selected objectives.

Keep the restore transcript, checks, snapshot identity and measured duration in
[release evidence](release-evidence.md). A same-directory file-export retry alone
does not satisfy this gate.

## Upgrade and migration boundary

Record supported schema/release pairs. Back up before migration; preserve originals;
validate migration against old snapshots and partial-failure cases. A rollback plan
must address data/schema changes, not only checking out older code. Existing refusal
of ambiguous legacy records remains valid until a reviewed migration exists.

Technology baseline: retain current local stores while evaluating this workload.
No server-database migration is authorised by this planning document. Reconsider
storage architecture before shared multi-user writes in Production v2.
