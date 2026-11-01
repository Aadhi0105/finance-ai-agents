# Webapp Batch 2A — controlled job admission

Implemented 1 November 2026. This is the backend admission layer for a local,
single-analyst synthetic pilot. [Batch 2B](batch2b-background-execution.md) now adds
the explicitly enabled worker, execution receipts and delivery recovery. This guide
records the admission-only baseline. It accepts and durably records bounded requests;
the background worker and report registration are Batch 2B. Accepted jobs remain
**queued**, with `worker_enabled: false`. No agent starts when a request is accepted.

The existing report workspace stays read-only by default. Operators explicitly
enable admission at startup. There is no Run button or token-entry interface yet;
those controls belong to Batch 2C.

## Purpose and first supported work

For example, an analyst requests a rebuild of the registered `research-example`.
The server validates that run and its saved artifacts, assigns a job ID and a
future operation ID, and persists both with the request and evidence identities.
A repeated click/network retry using the same request key returns that same job.
Changing the timeout or source while reusing the key produces a conflict.

The initial closed profiles rebuild/replay **registered saved synthetic evidence**:

| Workflow | Profile | Evidence retained at admission |
| --- | --- | --- |
| Research | `rebuild-saved-research` | Saved analysis/model and its registered artifact inventory |
| Monitoring | `render-saved-monitoring` | Retained monitoring snapshot; rendering is separate from a new cycle |
| Past events | `replay-saved-events` | Sealed historical-event bundle and registered native recipe |
| Company news | `replay-saved-news` | Sealed news bundle; saved scores keep their existing restrictions |
| Financial close | `render-saved-close` | Saved close bundle; rendering is separate from committing another close |

Native-view registration is required, including a supported recipe and matched
source artifacts. A legacy-only report can still be read but cannot be admitted
as one of these jobs. A matched admission is not a fresh market observation or
financial approval. Early-failed/held saved records preserve their own limitations;
admission alone does not prove a subsequent replay will succeed.

The request contains only a schema version, workflow, registered run ID and optional
execution timeout. Commands, paths, executable arguments, output directories, credentials,
live/model switches, approval decisions and profile overrides are refused.

## Start the opt-in local backend

Prepare a native workspace using the existing operator command if needed, then:

```bash
.venv/bin/python -m keystone.workspace serve \
  --workspace output/workspace-native-4c \
  --port 8793 \
  --enable-job-admission \
  --jobs-dir state/workspace-jobs
```

Substitute an existing registered native workspace when that QA example is absent.
The server binds to **127.0.0.1**. It prints the private token-file **path**, never
the token itself. The selected control directory must be outside the report
workspace and private to the current OS user. The default is `state/workspace-jobs`.
`--jobs-dir` requires the explicit admission flag.

The control directory contains:

- `jobs.sqlite3`: durable job identities, requests, source pins and admission events;
- `access-token.key`: the current server's private bearer token;
- `session.lock`: the server's exclusive lease for this ledger.

Directories are private and files are owner-only. Symlinks, public control
directories, linked files, unknown database versions and a ledger bound to another
workspace path are refused. A second server cannot take over the same ledger or
rotate its active token. Startup rotates the token after acquiring that lease;
the job history remains intact. Stop the server before moving/restoring its ledger.

## HTTP contract

| Endpoint | Behaviour |
| --- | --- |
| `GET /api/execution` | Public local capability summary: admission enabled/disabled, supported profiles, ceilings and worker-disabled scope; no token or filesystem path |
| `POST /api/jobs` | Protected admission; 202 for a newly committed job, 200 for an identical replay |
| `GET /api/jobs` | Protected newest-first job list; `limit` 1–100, default 25; opaque `before` cursor from `next_cursor` |
| `GET /api/jobs/{job_id}` | Protected saved job and its admission event |

Job GETs also support HEAD. Other job mutations are refused. The report, artifact
and inventory routes keep their existing read-only behaviour. Workspace metadata
separately exposes `job_admission_enabled` and `job_worker_enabled`; its `read_only`
field continues to describe the saved report catalogue.

Protected requests require `Authorization: Bearer <local token>`. POST additionally
requires the exact configured `Origin` (for this command, `http://127.0.0.1:8793`),
`Content-Type: application/json`, and one `Idempotency-Key` header. Browser fetch
metadata, when supplied, must agree with the same-origin boundary. The configured
Host is pinned for job requests. No CORS permission or token-discovery endpoint is
introduced. Keep the token out of URLs, Git, browser storage, logs and shared text.

Request example (the key belongs in the header, not in this body):

```json
{
  "schema_version": 1,
  "workflow": "research",
  "source_run_id": "research-example",
  "timeout_seconds": 120
}
```

The schema version defaults to 1 and timeout to 600 seconds. Integer fields are
strict; unknown/duplicate JSON fields, invalid workflow/run pairs, compressed
payloads, unsupported media types and bodies over 4,096 bytes are refused. Request
keys are 8–96 ASCII letters/digits/underscore/hyphen, beginning with a letter or
digit. A UUID is suitable. Duplicate security/idempotency headers are refused.

The server returns a `Location` for the saved job, `replayed`, `worker_enabled`,
and an explicit waiting-for-worker message. The job records:

- server-generated `job_id` and reserved `operation_id`;
- normalized request and request fingerprint, profile/version and admission time;
- source run fingerprint, native registration and all registered artifact hashes,
  sizes, names and IDs;
- `input_validation: matched_at_admission`, with live data, paid models, worker
  execution and financial approval all false;
- the shared supervised-operation ceilings of 12 requests, 48,000 reserved output
  tokens and at most 600 seconds. Disabled paid access is retained.

No capability token, raw key, shell command, arbitrary path or source document body
is written into the ledger. Idempotency keys are stored as hashes. An identical
replay returns the original admission even if source evidence later changes; it
does **not** claim that the source is still matched. New admissions with changed
evidence are refused. The worker must revalidate every pin before execution in 2B.

## Persistence, conflicts and failure behaviour

SQLite supplies transactional uniqueness and serializes the short control writes.
The ledger uses DELETE rollback journals and `synchronous=EXTRA`; there is no
unmanaged WAL dependency. A job and its admission event commit in one transaction.
The server responds with acceptance only after commit. Reads use read-only SQLite
connections. Schema, workspace binding, database checks, event consistency and
record hashes are checked; failures produce neutral errors without source data,
SQL messages, paths or credential values.

Twenty pending jobs and 1,000 retained jobs are the v1 ceilings. Because 2A has no
worker, every admitted job remains pending and the effective capacity is twenty.
There is no expiry, automatic deletion, requeue, cancellation or retry endpoint.
Repeating an existing request remains available at capacity. A different request
with the same key is a 409 conflict. A new key intentionally creates another job;
this is not semantic deduplication across different keys or independent ledgers.

HTTP control writes join the same maintenance/mutator locks used by supervised
CLI operations and snapshots. The thread-safe control lease avoids the CLI gate's
process-wide environment/umask changes. Busy control returns a bounded 503 and
`Retry-After`, with the same request key usable on retry. A lost response after
commit is recovered by that key, not by creating a new job ID. Missing or corrupt
history in a used control directory is refused instead of silently creating an
empty queue. Never remove its ledger/locks as a retry procedure.

This is a local capability for a trusted OS user, not enterprise authentication,
user roles or authenticated approval. Local applications with access to the token
have the same admission capability. Cross-machine/team access remains separately
scoped.

## Local backup and restoration

The existing explicit-inventory snapshot tool can cover `jobs.sqlite3` as a **file**
with role **logs**; its `database` kind is specifically for DuckDB financial stores.
Control writes participate in its exclusive maintenance gate. A ledger-only local
snapshot/restore test verifies that jobs, events and duplicate-request history
survive restoration into a new control directory for the same workspace path.

Select the ledger file explicitly, alongside the separately declared report/input
evidence. Do not inventory the entire control directory: the secret token is
deliberately refused by the backup tool. New server startup issues a fresh token.
Do not copy an active SQLite journal or treat an arbitrary file copy during writes
as a tested snapshot. Restoring older control history can lose newer identities;
reconcile post-snapshot work before enabling any future worker. Rebinding to a
different workspace path requires separately designed recovery; it is refused here.

This local check leaves independent backup, encryption/key recovery and
clean-machine disaster recovery at their existing deferred/pending status.

## Acceptance

`tests/test_workspace_jobs.py` covers actual HTTP handlers over real registered
offline outputs for all five families; no worker/model/provider may be invoked.
It tests strict requests, origin/token boundaries, concurrent/repeated/conflicting
submission, capacity/pagination, source changes, restart/token rotation, private
and unsafe paths, transactional rollback, malformed/missing ledgers, read-only
delivery, CLI opt-in and gate-aware snapshot/restore. The existing workspace and
supervised-operation regression suites remain applicable.

Bounded local acceptance also used a real server on port 8793 against the 32-run
native synthetic workspace. All five baseline profiles returned 202 for admission,
200 for identical replay and 409 for a conflicting request key. Unauthorised access
returned 403. After stopping and restarting the server, all five job/operation
identities were retained and replay created zero extra jobs. All 139 workspace
files remained unchanged. The isolated server was stopped after the check;
`output/job-admission-2a/receipt.json` retains the ignored local smoke receipt.
No agent or paid/provider call was started.

Final validation on 1 November 2026:

| Check | Result |
| --- | --- |
| Complete Python regression suite | **1,236 passed** |
| Job-admission subset | **64 passed**, included in the complete suite |
| Existing interface tests | **189 passed** |
| TypeScript and production frontend build | Passed; no dependency changes |
| Actual HTTP admission and process restart | Five profiles, duplicate/conflict/access boundaries and stable IDs passed |
| Existing report evidence | All 139 local QA files unchanged |

These results establish bounded local admission and persistence. They do not
establish background execution, multi-user authentication or production release.

Batch 2B must add supervised background execution, pre-execution pin validation,
private working copies, explicit outcome/recovery states and safe report
registration. It must preserve the possibility of a financial commit before
delivery failure. Batch 2C adds the interface; 2D validates the full workflow.
Human report interpretation, physical accessibility and actual PDF/print acceptance
remain open as recorded in the native report acceptance pack.
