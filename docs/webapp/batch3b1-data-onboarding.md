# Webapp Batch 3B.1 — private saved-input backend

**2 November 2026.** Implements the first backend slice of
[3A](batch3a-input-contracts.md). The existing synthetic web interface remains
available. The new private workspace exposes a protected backend API; its browser
onboarding/reader connection is implemented separately in [3C](batch3c-browser-onboarding.md). The private root page says so instead
of showing synthetic labels against imported records.

This slice accepts the five saved-evidence families, not arbitrary financial
spreadsheets or fresh raw Agent 4 close requests. Imports do not run jobs. New
closes are implemented separately in [3B.2](batch3b2-fresh-close.md); this guide
records the saved-input slice and its original verification. Wider browser and
portable-restart acceptance is recorded in [3C](batch3c-browser-onboarding.md) and [3D](batch3d-onboarding-acceptance.md).

## Implemented flow

1. The operator prepares a fresh, private workspace. Existing destinations are
   preserved. Root/data directories use `0700` and files use `0600`.
2. Protected requests create a company or explicit group and a typed dataset.
   Research/news need a company ticker; event studies need a peer group. Monitoring
   can bind a single company or an explicitly enumerated watchlist. Grouping is
   ownership/scope metadata, not issuer merging or comparability approval.
3. The operator installs a local permission record and its evidence outside the
   HTTP API. The record binds workspace, entity, exact canonical payload hash,
   source category/provider/owner, intended private personal evaluation use,
   review/expiry, and separate retention, processing, backup, model and sharing rights.
4. Preflight binds the dataset, envelope declarations, expected package bytes/hash
   and payload hash to one durable request identity. Missing/denied/expired or
   mismatched rights are refused before a payload is accepted.
5. The receiver checks bounded bytes and actual envelope/payload hashes before
   persisting them. An owned offline subprocess then validates the specific saved
   family and consumed native shape. Eligible input is not yet a report or a job.
6. Accepted versions retain original package bytes, canonical payload, context,
   validation/producer evidence, preflight and the effective input contract.
   Explicit v2 jobs pin that version and run the existing supervised offline spine.
7. Verified results append a new v3 native report with dataset/version/job lineage.
   All private metadata, input/report files and job reads require the local token.
   Financial approval, provider acquisition and paid models remain disabled.

The receiver serialises active intake and enforces 20 MB, parser depth/value/row/
text bounds and a transfer deadline. It briefly holds at most one bounded package
in memory so different content cannot be written merely by claiming a permitted
payload hash. Incomplete or unpermitted bytes are discarded from memory; their
control receipts remain. Full authorised bytes that fail later semantic checks
remain in private staging for inspection and count against capacity.

The semantic validator has a separate 60-second supervised limit. A job's explicit
processing limit remains at most 600 seconds. Capacity reserves include staging
and derived copies; no evidence is automatically deleted to make room.

## Source families

| Format | Action | Important boundary |
| --- | --- | --- |
| `agent1.model/2` | Revalidate and rebuild saved research | Does not fetch statements or recompute every original analytical tool |
| `agent2.snapshot/legacy-1` | Render the recognised unversioned monitoring snapshot | Does not append observations, advance cycles or approve imported corrections |
| `agent3.events-bundle/1` | Verify and replay retained event calculations | Does not establish release authenticity or assemble new provider prices |
| `agent3.news-bundle/1` | Verify and replay retained news/scores | Does not retrieve stories, load model weights or score fresh text |
| `agent4.close/1` | Validate/render the frozen close against saved panels | Does not commit budget/actuals or calculate a new accounting close |

Malformed formats, workflow/identity/currency disagreements, unsupported versions
and replay mismatches are refused. Supported empty monitoring exports and incomplete
terminal news/event evidence can be retained with explicit eligibility holds.
They cannot start a job requiring complete selected/replay inputs.

Native adapters `2.0.0` support private catalogue v3 and derive labels from the
bound effective classification. Existing synthetic adapters and catalogues remain
unchanged. Source-use permission is an operator attestation, not source authenticity,
financial accuracy or an authenticated reviewer signature. An uploaded `synthetic`
or `approved` flag grants neither rights nor financial approval.

## Commands and access

From the repository root, prepare a new destination:

```bash
.venv/bin/python -m keystone.workspace prepare-private \
  --destination state/workspaces/analyst-demo --name 'Local analyst workspace'

.venv/bin/python -m keystone.workspace serve \
  --workspace state/workspaces/analyst-demo --port 8798 \
  --enable-imports --enable-job-admission --enable-worker
```

The server prints only the private token-file path. Keep its contents out of chat,
Git, URLs, browser storage, logs and screenshots. Use the current token in an
`Authorization: Bearer ...` header and the exact local Origin for mutations.
Restart rotates it. The default private server still requires access for reads;
omitting the three opt-ins enables no import, submission or processing.

Private control has a fixed `control/` sibling of `reports/`; `--jobs-dir` is not
accepted for this mode. Serve the workspace root, not its `reports/` subdirectory.
The original synthetic `prepare`, `project` and `serve` paths retain their scope;
`project` refuses private catalogues instead of relabelling them.

After preparing actual operator-reviewed JSON and evidence files, use:

```bash
.venv/bin/python -m keystone.workspace install-source-permission \
  --workspace state/workspaces/analyst-demo \
  --record /path/to/reviewed-permission.json --evidence /path/to/permission-evidence.pdf
```

These paths are placeholders. The record is the strict `Permission` model in
`keystone/workspace/onboarding/contracts.py`; rights are not inferred from a source
URL, possession of a download, a subscription or the example test records.
Installing or revoking permission has no browser write route. CLI revocation
uses `revoke-source-permission --workspace ... --permission-id ... --reason ...`.
It adds a hold; it does not erase original inputs or issue a new financial decision.

## API contract

All data and mutation routes below require access; `/api/execution` is the public
fixed-capability exception. Small control bodies are bounded UTF-8 JSON. Requests
cannot supply filesystem locations, executable names or arbitrary profiles.

| Route | Contract |
| --- | --- |
| `GET /api/execution` | Public fixed capability/schema/limit information only; no private names or remaining counts |
| `POST /api/entities` | `{name, kind, ticker, members}` with server-generated ID; bounded immutable scope |
| `POST /api/datasets` | `{entity_id, title, workflow, payload_format}`; supported matching family |
| `GET /api/entities`, `/api/datasets` | Bounded newest-first pages; `limit` 1–100 and opaque `before` |
| `POST /api/imports` | `Preflight`: schema 1, dataset ID, expected package bytes/hash, canonical payload hash and exact envelope metadata without payload; `Idempotency-Key` required |
| `PUT /api/imports/{id}/package` | One uncompressed JSON envelope; same request key; no arbitrary multipart files or byte-range resume |
| `GET /api/imports`, `/api/imports/{id}` | Protected receipts; no financial content in errors |
| `GET /api/datasets/{id}/versions` | Accepted immutable versions, opaque paging; never a directory scan |
| `GET /api/datasets/{id}/versions/{version}` | Effective contract, validation, classification and file proofs; current rights/integrity checked |
| `GET .../versions/{version}/files/{name}` | Explicit registered input member, final byte recheck, attachment delivery |
| `POST /api/jobs` | Job request v2 with workflow, timeout and tagged `{kind: dataset_version, dataset_id, version_id, contract_sha256}` source; request key required |
| Existing job/report read routes | Protected; report origin and exact run fingerprint must match the recorded completed delivery |

The literal `kind` value in the tagged source is the string `dataset_version`.
Job-request v1 retains its existing saved-run meaning in synthetic workspaces.
Private response schema versions are explicit; current synthetic frontend validators
do not silently accept private data. There is no browser permission override,
financial approval, recovery, cancellation, provider or paid-model endpoint.

Original generated HTML is download-only in this mode. Uploaded HTML is not a
supported source. API errors return fixed codes/messages, not raw input, stack
traces, SQL or paths. Imported text and source references remain inert data.

## Identity, interruption and recovery

Same key + same preflight/body returns the original import identity; changed
descriptors conflict. A new key with identical effective content resolves to the
same dataset version and records a separate duplicate receipt. A changed contract
creates a new immutable version. Supersession never rewrites earlier bytes or
changes an already submitted job's source.

Restart holds receiving/validating imports as interrupted, and does not automatically
validate, accept or dispatch them. File promotion precedes the ledger acceptance
commit. A private prepared journal binds that boundary so either-side failures can
recover once from complete unchanged proof. Missing/changed proof remains refused.

Explicit startup/operator actions also permit SQLite to roll back an interrupted
uncommitted registry transaction under the maintenance controls. Ordinary input
inspection and HTTP reads remain read-only. A forced-exit test spills dirty pages
to disk, verifies that inspection changes no bytes, then checks startup restores
the last committed entity/dataset and subsequent HTTP reads leave files unchanged.
The validator has its own process deadline as well as its supervisor's timeout,
so losing the HTTP process does not leave its validation lease unbounded.

Stop the private server before operator acceptance recovery:

```bash
.venv/bin/python -m keystone.workspace recover-import \
  --workspace state/workspaces/analyst-demo --import-id import-REPLACE_WITH_SAVED_ID
```

This does not rerun validation or financial processing. Repeating successful
recovery returns the same accepted version. A mere receiving/partial attempt with
no prepared proof cannot be promoted through this command. Explicit transfer retry
uses the existing identity and a new private staging member after full rechecks.

Job delivery recovery retains the 2D command and leases. For a private workspace,
use its exact `reports/` path as `--workspace` and its `control/` path as `--jobs-dir`.
Recovery verifies current source/policy scope and saved operation/output proof;
it never dispatches the calculation again.

## Snapshot coverage and current restore boundary

After stopping the server, local capture is available:

```bash
.venv/bin/python -m keystone.workspace snapshot-private \
  --workspace state/workspaces/analyst-demo \
  --destination output/private-local-snapshots
```

The explicit inventory covers the descriptor, SQLite input registry, accepted and
staged bytes, permission records/evidence, reports, job ledger, working copies and
operation receipts. Rotating access tokens and lock files are excluded. The
session lease requires the server to stop; maintenance excludes mutators during
capture. Backup rights are checked under that exclusive gate before and after
copy, alongside file integrity. A backup hold refuses capture instead of silently
omitting affected inputs.

This is **local snapshot evidence**. Generic restore into a fresh destination can
verify retained input versions, but the job ledger retains its original absolute
workspace binding. Automatic adoption into a new path is refused. The explicit `restore-private` command in [3D](batch3d-onboarding-acceptance.md) now verifies and rebinds copied control metadata, reconstructs fixed empty directories and holds queued work for operator review. Generic restore still does not adopt the queue. Do not replace metadata or create a fresh ledger to bypass a refusal. Independent encrypted-device backup and clean-machine recovery
remain deferred/open as previously recorded.

## Verification and repeatable engineering rehearsal

Focused tests are in `tests/test_workspace_onboarding.py`: five actual supervised
saved-source profiles, private reads/mutations, duplicate identities/versions,
source classification, revocation/expiry, changed files and final downloads,
close-family/currency/identity boundaries, transfer/validation deadlines, prepared
delivery recovery, owned background execution and local snapshot/input restoration.

The test-only TCP harness exercises a real local server and its owned worker:

```bash
.venv/bin/python tests/workspace_onboarding_scenarios.py \
  --source output/workspace-native-demo \
  --destination output/onboarding-backend-rehearsal --port 8798
```

Choose an existing registered synthetic native source and a new destination.
The harness creates five fictional content-scoped policy records, uses the protected
API for entity/dataset creation, imports all five formats, submits explicit jobs,
checks native report/download agreement and preserves every source file. It stops
its server/worker on completion. These test records establish no real-source rights.
Generated ledgers, tokens and receipts remain ignored by Git.

Final local verification on 2 November 2026:

| Check | Result |
| --- | --- |
| Full Python regression, offline configuration | **1,321 passed** in 350.23 seconds |
| New onboarding and registry crash-recovery cases | **44 passed**, included in the full run |
| Existing frontend regression | **234 passed** |
| TypeScript and production frontend build | **Passed** |
| Actual protected local server and owned worker | Five accepted inputs, five explicit jobs and five native reports; each job claimed once and held for financial review |
| Source preservation | All **139** files in `output/workspace-native-4c/` unchanged |
| Scope controls | Unauthenticated private reads refused; live acquisition disabled and zero model requests reserved |
| Schema/example and documentation | Runtime/documented envelope copies agree; example validates structurally; 24 local documentation links resolve |

The ignored local TCP evidence is `output/onboarding-backend-3b1/receipt.json`,
with original fingerprints in `source-before.json` and private input/job/report
records under `workspace/`. Its server and owned worker were stopped on completion.
The separate forced-exit regression verifies the final startup recovery correction.
No provider permissions or financial approval are established by the fictional
test policy records. Access tokens and generated files remain excluded from Git.

Subsequent browser interaction and explicit portable recovery are recorded in [3C](batch3c-browser-onboarding.md) and [3D](batch3d-onboarding-acceptance.md);
fresh-close processing remains 3B.2. No real-company or production acceptance gate
advances from this engineering rehearsal.
