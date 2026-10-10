# Batch 2 dependency closure preparation

Reviewed 10 October 2026 against merged implementation `9584b25a804d907c66f28d993ebc27bb28616988`.
Status: **procedures prepared; independent protection and production permission not accepted**.

After the supplied path was identified as internal storage, the user explicitly
chose to defer independent backup and finish local preparation. No external copy
is part of this step. The external-drive procedure remains a future recommendation.

| Dependency | Decision / evidence | Remaining acceptance |
| --- | --- | --- |
| Independent destination | User selected an encrypted external drive. Supplied Desktop/Keystone resolves to `/dev/disk3s5`, mounted at `/System/Volumes/Data`, on this Mac | Identify an actual separate physical device and verify its encryption; the supplied folder is not independent |
| Encryption and keys | Recommended procedure below; no password collected or settings changed | Verify encrypted volume and demonstrate recovery without this Mac's saved credentials |
| Disaster recovery | User has only this Mac; prepare locally | Replacement-machine drill remains pending; local restore cannot pass V1-STO-002 |
| Source permissions | Preliminary evidence review completed in linked register | Approve each specific use or exclude that source from the release; V1-DAT-001 remains blocked |

The filesystem check was read-only. Disk Utility's command interface could not access
the DiskManagement framework in this execution environment, so encryption was not
verified. No backup was copied to the supplied folder, no external device was
formatted, and no protection point was advanced.

## Independent backup and key recovery

**Recommended:** an existing APFS encrypted external drive for the macOS-only pilot,
disconnected after verification and kept separately from the Mac. This recommendation
is not a claim that a drive is configured. One drive still leaves a single backup
medium failure risk; a later second rotation would reduce it.

1. Identify the mounted volume and underlying physical device, not just its folder
   name. Record a non-secret volume UUID, capacity, free space, external-device
   status and encryption status. Confirm the mount is present immediately before
   writing; never create a missing `/Volumes/...` directory as a fallback.
2. Confirm an encrypted filesystem through Disk Utility and test a lock/unlock cycle.
   Unlock interactively; never put a password in commands, logs, Git or chat.
   Apple's [Disk Utility procedure](https://support.apple.com/en-is/guide/disk-utility/dskutl35612/mac)
   for formatting with encryption erases the device. Existing contents must be
   protected and any destructive setup separately authorised. This preparation
   does not authorise erasure.
3. Store the external-volume password in a password manager recoverable without
   this Mac, with a separate protected offline recovery record. Test access to that
   record without relying on this Mac's Keychain. A FileVault recovery key for the
   Mac is not the external APFS volume password. Record only the custodian, recovery
   method, date and result; never record the secret in repository evidence.
4. Review a real snapshot inventory using [Batch 2 commands](batch2-storage.md).
   Include authoritative stores and evidence companions; exclude credentials and
   unrelated material. Confirm source retention and backup permissions first.
5. Quiesce all writers, including direct APIs and other checkouts. Capture to the
   verified mounted destination and verify the returned snapshot. Restore to a
   new empty local test location and perform the agent checks below. The utility
   does not encrypt data or certify physical independence; filesystem protection
   and this evidence record supply those separate checks.
6. Record snapshot ID, manifest hash, source commit/environment, last committed
   business records, capture/verification times and device identity. Only a verified
   independent copy advances the protection point. Safely eject and store apart.

Back up after each mutating session and before migrations or consequential correction
work. A failed required backup pauses further production mutation unless the analyst
records an explicit risk decision. The target is at most one active working day's
loss. This procedure is manual; automated enforcement is future work.

**Retention proposal, not yet adopted:** keep the most recent verified snapshot,
previous verified snapshot and pre-migration recovery point, subject to each dataset's
permitted retention. Set a bounded retention period and capacity budget after measuring
actual snapshots and reviewing rights. No automatic deletion is enabled. Stop on
insufficient space; do not delete the only good copy to make a new one.

## Recovery drill

Preparation on this Mac can test manifests and agent recovery, but cannot establish
survival of device loss. Preserve the earlier local fixture evidence; do not relabel
it as a clean-machine test. A fresh directory or virtual environment still depends
on the original hardware and is not the final acceptance drill.

When a second supported Mac is available:

1. Declare a simulated incident and record the last acknowledged business state and
   independent protection point. Make original state inaccessible without deleting
   it. Acquire the release source/package independently of the lost checkout.
2. Record hardware, macOS, Python, frozen dependencies and configuration identities.
   Reproducible installation remains a Batch 3 dependency. Retrieve the encrypted
   drive password through the independent recovery procedure, not the original Mac.
3. Verify the snapshot before restoring to an unused destination. Reject corruption,
   incomplete manifests and destination conflicts. Provision new API credentials
   separately only if needed later; recovery validation itself uses no providers
   or paid models.
4. Agent 1: rebuild a working copy, preserving saved input and review holds.
   Agent 2: compare cycles, original/effective history and associated audit exports.
   Agent 3: verify calendar revisions, relocated evidence associations and offline
   replay. Agent 4: compare close/version lineage and identical saved JSON; check
   regenerated HTML as a derivative. Use the existing fixture rehearsal as a
   procedure baseline, then test the accepted real inventory.
5. Record every expected/actual result and differences. Measure lost committed work
   against the protection point, not snapshot duration. Measure recovery time from
   incident declaration once supported hardware, backup and keys are available;
   target eight staffed hours. Record acquisition delay and total downtime separately.
6. Analyst signs the exact release/environment and restored evidence. Failed checks
   leave V1-STO-002 open and preserve the previous good copy.

## Evidence record to complete

- Destination physical identity, encryption verification and date: pending.
- Independent key-retrieval and unlock test (no secrets): pending.
- Inventory/source permission approval and retention decision: pending.
- Snapshot ID/hash, last committed records and verified protection point: pending.
- Clean-machine environment, restore results, measured RPO/RTO and reviewer: pending.

See [source-use review](source-use-review.md), [acceptance matrix](acceptance-matrix.md)
and [decision register](../decisions/0001-production-v1-boundary.md).
