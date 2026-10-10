# Batch 2 — local inventory, consistent snapshots and restoration

Implemented 10 October 2026. **Local engineering acceptance only.** The user chose
to build/test locally and select an independent backup destination later. No data
was sent to a remote service or copied to an external drive. Device-loss RPO/RTO,
external encryption/key recovery, source-use permissions and real-company FP&A
remain unaccepted release dependencies.

## What is implemented

`keystone/contracts.py` validates an explicit source inventory and dataset contracts.
Each source has a destination-relative identity, absolute origin, kind and role;
every source must be covered by a dataset declaration. Contracts record source,
classification, period, currency, units, permission evidence and freshness policy.
Pending permission/unknown semantics remain visible release holds. A valid inventory
is not authenticated permission or source truth and does not validate the financial
contents of arbitrary files. Existing agent financial contracts still apply.

`keystone/storage.py` captures exactly the declared source set, with hashes, sizes,
source paths, data contracts, code/runtime identity, and explicit lock-file exclusions.
It is not automatic discovery of every database on the device. The operator must
include all authoritative state, original inputs, configuration/references, companion
audits and reports needed for the intended scope. Multiple databases are separate
entries; never select a tree containing databases or WAL files.

`keystone/maintenance.py` adds a shared activity lock to the normal Agent 1–4 CLI
entry points, Agent 3 workers and bundle export. Snapshot/restore take the exclusive
lock and fail fast if these commands are active. This is a maintenance boundary,
not Batch 3's single-mutator admission system: normal agent activities can still
coexist under shared locks.

Direct Python APIs, acceptance scripts, other checkouts and manual file editors do
not automatically participate. Stop those writers before supplying `--quiescent`.
The snapshot additionally holds each declared database's application lock and native
DuckDB writer connection, checkpoints it, and keeps it open until capture finishes.
Before/after inventory hashes detect observed uncoordinated file changes; this does
not promise isolation from a hostile local account or a writer that bypasses the
maintenance boundary. No live WAL-dependent database is copied blindly.

## Commands

Run from the repository with its Python environment. Copy and edit the example
inventory outside confidential source folders; never put credentials in it:

```bash
python -m keystone validate-plan config/storage-inventory.example.json
```

The example intentionally reports permission/metadata holds. Replace its absolute
paths and dataset declarations before capture; add every relevant agent source.
`validate-plan` checks contracts, not path existence or snapshot completeness.

Stop direct/API/other-checkout writers, then use a local destination outside all
source roots. These paths are placeholders:

```bash
python -m keystone snapshot /path/to/inventory.json \
  --destination /path/to/local-snapshots --quiescent
python -m keystone verify /path/to/local-snapshots/SNAPSHOT_ID
python -m keystone restore /path/to/local-snapshots/SNAPSHOT_ID \
  --destination /path/to/new-restored-directory
```

Snapshot IDs are unique. Restore requires a **new** destination and never merges
into existing state. All commands exit 0 on successful operation and 2 on refusal
or failure; argparse usage errors also exit 2. A pending-permission inventory may
be preserved locally but is never reported as release approved. CLI failures give
safe action/error categories rather than echoing potentially sensitive exceptions.

## Publication and data handling

Files and containing snapshot/restore directories are created with restrictive
permissions; staged files and directories are flushed before publication. The
manifest and file hashes are verified before atomic directory publication. Failure
removes this operation's staging area and preserves prior completed snapshots.
A crash may leave `.incomplete-*` or `.restore-*` staging; these are not completed
snapshots. No command auto-deletes old backups or implements retention expiry.

Known secret/environment file names, symlinks, hardlinks, special files, path
traversal, overlapping inventories and destinations are refused. This is not a
content-based secret scanner: review the inventory and artifacts before backup.
Saved financial reports and raw model audits can be sensitive. Data is not encrypted
by this utility; use it only within the authorised local access boundary until an
independent encrypted destination and key-recovery process are selected.

The manifest seal detects content damage, not a malicious owner recomputing hashes.
Verification checks every member and rejects missing/extra files. A failed final
filesystem durability step may leave a published directory but reports failure;
verify it before use. No successful device-loss protection is claimed.

## Controlled relocation

Restoration first reproduces snapshot bytes, then performs two documented mutable
metadata changes in the staged copy:

- Agent 2 records prior database paths in `monitor_metadata.restored_audit_origins`.
  Report association accepts those origins only with the original cycle digest.
  This preserves historical audits without rewriting them. It is local recovery
  provenance, not an authenticated identity or permission bypass. Original cycles,
  decisions and observations remain unchanged.
- Agent 3 changes index paths only when the indexed bundle is included, has valid
  integrity, and matches attempt ID, bundle digest and input fingerprint. Missing
  or mismatched indexed bundles refuse the restore. Calendar, revisions, outcomes,
  bundles and original run evidence are retained unchanged.

`restore-receipt.json` records the original manifest identity, exact relocations,
and final file hashes. The source snapshot remains immutable. Agent 1 saved rebuild
still revalidates with current code; Agent 4 HTML remains a derivative view. Neither
becomes a byte-identical HTML guarantee. Agent 4 saved JSON retains its existing
byte-identical delivery contract.

## Verification and release boundary

The complete suite passed 959 tests, including 29 new storage regressions.
Regression tests cover inventory/path controls, corruption, missing/extra members,
quiescence, concurrent CLI refusal, changing sources, simulated disk failure,
Agent 2 corrections and original audit association, Agent 3 calendar/replay/index
preservation, and Agent 4 saved JSON plus HTML recovery. The local rehearsal runner
exercises all four agents with synthetic fixtures and saved evidence; see the
[release register](release-evidence.md) for actual results.

```bash
python -m pytest tests/test_production_storage.py
python -m scripts.check_keystone_storage
```

The local rehearsal uses a new directory and makes the original source directory
unavailable before restoration. It still uses the current installed environment
and same storage device. It is not a clean-machine disaster-recovery drill or proof
of an eight-hour recovery objective. Run actual independent-device recovery and
permission-scoped pilot acceptance before passing V1-STO-002 or V1-DAT-001.
