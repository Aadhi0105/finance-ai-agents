# Webapp Batch 6B — storage and evidence lifecycle

**12 November 2026 · Private, supervised local operation.**
[Batch 6 roadmap](batch6-operational-readiness.md) · [Operations](batch6a-operational-visibility.md)

This part makes the local workspace footprint visible, defines the pilot's
retention behaviour, and adds a stopped-workspace check of retained evidence.
It does not consolidate existing checkouts, introduce PDF intake, or establish
independent backup protection.

For example, a fictional research assessment retains its original package,
accepted version, permission evidence, pinned working inputs, execution receipt,
registered report and analyst review history. A corrected package adds another
version and a correction link. The earlier report and its inputs remain available
as evidence of the original assessment.

## Live storage view

Connect locally and choose **Storage & evidence**. The page is also available in
the Operations-only diagnostic connection. **Recheck storage** performs a fresh
read; observations older than one minute are labelled. A refresh labels the
previous observation while checking, and a failed request clears it.

The protected `GET`/`HEAD /api/storage` endpoint returns the closed version-1
`keystone.storage` contract, recorded in `keystone/workspace/storage.schema.json`.
The frontend validates its workspace identity, fixed categories, totals, states,
timestamps and false approval/deletion/intake flags. The response is bounded to
32 KB. Existing token, origin and no-store controls apply. There is no mutation
or arbitrary-path parameter.

Open Keystone requires `storage_supported` as well as the earlier operating
capability before reusing a server, so an older process cannot masquerade as a
current storage-capable workspace.

The scan covers the **entire selected private workspace root**, including:

| Area | Retained evidence |
| --- | --- |
| Workspace configuration | Workspace identity |
| Input ledger | Companies, datasets, imports, versions, notes, corrections, decisions and close registries |
| Accepted inputs | Original supported packages, validation and contracts |
| Import staging | Prepared, unfinished and rejected transfer evidence |
| Source permissions | Operator records and supporting files |
| Reports | Catalogue, structured reports and registered artifacts |
| Job ledger | Requests, execution outcomes, events and recovery holds |
| Job evidence | Working input copies and prepared result deliveries |
| Operation evidence | Supervisor receipts, model-usage records and diagnostic files |
| Accounting | Canonical close databases and present companion files |
| Recovery | Current restore receipt, previous receipts and control restore history |
| Runtime | Access key, locks, plotting cache and database journals |
| Unrecognised | Other members, preserved for operator inspection |

Only counts and sizes leave this endpoint. Paths, file names, contents, labels,
notes, credentials and raw exceptions are excluded. Runtime files are counted
without opening their contents. Symlinks, hardlinks, special files and unsafe
permissions are refused. A missing required member makes its area unavailable;
unknown totals remain null. Independent readable areas stay visible.

The scan visits at most 60,000 members, including directories, and never follows
links. If the bound is exceeded, the complete inventory is unavailable. This is
a metadata observation across changing files, not a consistent backup or proof
that every artifact has a valid reference. Files outside this workspace and
external snapshots are not discovered.

## Capacity and retention policy

File bytes are logical sizes, rather than allocated blocks, admission reservations
or disk free space. Operations continues to show the existing separate admission
limits and reservations. Low-space advice begins below 5% of the volume or
100 MB. These observations do not reserve disk space or introduce a new global
workspace quota. Existing count, package, ledger and analysis gates remain in
force; physical disk exhaustion can still occur between checks.

The pilot policy is **preserve until operator review**:

- No automatic expiry, pruning or deletion. Keystone supplies no deletion API.
- New versions, notes, correction links and decisions preserve earlier records.
- Rejected, interrupted, uncertain and delivery-held work remains for inspection.
- A capacity refusal preserves existing evidence and does not release reservations.
- Permission expiry or revocation holds further use and backup where applicable.
  It is not permission to erase evidence, nor a determination of any source-owner
  disposal obligation. Resolve such obligations explicitly with the operator.
- Do not delete a report, an old input version, a ledger row or staging folders
  individually to make room. Related histories and recovery evidence can depend
  on them. Stop new work and arrange authorised retention and verified recovery
  before any separately approved disposal or migration.

There is no expiry schedule or secure-erasure capability in this pilot. A future
deletion feature needs dependency checks, source obligations, approval, an audit
record, backup implications and an explicit policy for the entire evidence set.
The later intake programme must add original documents and extraction/review
lineage to both inventory and snapshots before claiming document retention.

## Stopped-workspace evidence audit

Stop this workspace's server and worker. From the repository:

```bash
.venv/bin/python -m keystone.workspace audit-private --workspace /path/to/workspace
```

The command refuses a held server or worker lease. It joins exclusive checkout
maintenance, opens existing ledgers read-only and performs no recovery,
migration, financial execution, repair, deletion or network/model call. It
creates no workspace files. Direct writers and other checkouts must also be
stopped; they are outside this cooperative gate.

An unreadable hot ledger or uncheckpointed accounting WAL remains unavailable;
the audit does not perform database crash recovery. Use the existing operator
recovery procedure before claiming a verified capture of that state.

The audit checks:

1. Full private file inventory, including unrecognised members.
2. Every retained input object and import receipt; accepted version files,
   contracts, entity/dataset bindings and current source-use policy.
3. Permission record/evidence bytes independently of current-use permission.
4. Notes, correction links and decision histories against saved review scopes.
5. Job admissions/executions, source version bindings, retained working inputs,
   prepared deliveries, operation proofs and registered report artifacts.
6. Canonical accounting state and committed close proof links.
7. Current snapshot permissions and supported snapshot membership.
8. Before/after evidence hashes, with a separate 1 GB content-reading bound.

Runtime contents are excluded from hashing. The receipt gives a bounded summary
and an aggregate evidence digest; it does not disclose paths or file hashes.
`verified` exits 0. Permission `held`, `unavailable`, bounds, corruption, changed
evidence or a live-workspace refusal exit 2. A failed check does not become a
zero count or authorise rerunning the financial work.

The audit checks retained integrity and the supported reference semantics. It
does not authenticate sources, establish financial accuracy, cryptographically
authenticate a local operator, or guarantee that a cooperative local owner
cannot rewrite files and recompute hashes. Failed/interrupted work retains its
original recovery requirements even when its saved evidence can be audited.

## Snapshot and repeated-restore completeness

`snapshot-private` now checks the retained evidence audit inside its exclusive
capture boundary, before and after copying. Unrecognised or inconsistent
evidence refuses publication; earlier snapshots and source files are preserved.
Existing source-use checks and native database checkpoint rules still apply.

Private snapshot inventories now include the current `restore-receipt.json`
and any earlier recovery-receipt archive. On another restore, the incoming
receipt is retained byte-for-byte under
`recovery/restore-receipts/<sha256>.json` in the new destination before issuing
the new restore receipt. The new receipt records this change. It excludes the
superseded root receipt from its final-file map, and accounts for its archived
copy. The original workspace and source snapshot remain unchanged.

Runtime access keys, leases and plotting cache remain outside private snapshot
sources. New restored sessions generate their own local access key; queued
requests remain held under the existing recovery procedure.

Local snapshot/restore is still a same-device engineering check. An independent
encrypted destination, key recovery, clean-machine drill and scope-dependent
source rights remain pending. This part does not grant production release.

## Acceptance evidence

Automated acceptance covers full-root accounting/redaction, private API controls,
strict frontend parsing, unknown/missing/unsafe members, scan/hash bounds,
read-only/live-lease refusal, all saved report families, fresh research and
accounting, review histories, capacity refusal, damaged references, permission
holds, restored evidence and repeated recovery-receipt retention. Existing storage
and workflow disk-fault regressions remain part of the related checks.

The isolated fictional live preview and validation records are kept locally in
`output/storage-6b-preview/`; they are excluded from Git. No existing user
workspace was moved, overwritten or deleted.

Recorded validation on 12 November:

- 332 related backend regressions passed in 546.75 seconds. After the final
  identity/readiness and receipt-archiving additions, 35 focused checks passed
  in 3.68 seconds, including overlapping regressions. Together these cover all
  341 distinct cases in the final related-test collection.
- All 500 frontend tests and the TypeScript/production build passed.
- An actual fictional research report, analyst note and review decision passed
  the stopped audit and a local snapshot/restore audit.
- Browser checks passed for normal access, diagnostic-only navigation, keyboard
  refresh, all 13 inventory areas, and no page overflow at the observed 1280 px
  viewport. No alternate viewport size was claimed.
- All 39 non-runtime evidence files retained identical hashes across browser
  viewing/rechecking/reconnection; the workspace retained exactly one job,
  one analyst note and one decision.
- Git whitespace checks passed. Generated evidence, snapshots, access keys and
  screenshots remain outside tracked changes. These local checks preceded Git
  publication; publication and CI outcomes are recorded by the associated pull
  request for the combined 6A and 6B work.
