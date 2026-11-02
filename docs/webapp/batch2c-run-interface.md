# Batch 2C — Run interface and saved job history

Implemented **2 November 2026** for the local synthetic workspace. This is the
browser interface over [2A admission](batch2a-job-admission.md) and the
[2B worker](batch2b-background-execution.md). Execution profiles and financial
approval boundaries are unchanged.

## Use the interface

1. Open **Run & jobs**. Availability shows requests disabled, queue only, worker
   available, worker stopped, or unavailable.
2. When admission is enabled, connect using the current local job-access token
   from the private file named at server startup. This is separate from provider
   and AI credentials. The password field clears when connection begins.
3. Select a workflow, eligible registered native source, and processing limit
   of 1–600 seconds. **Run from this saved evidence** on a report preselects it.
4. **Start saved run**, or **Queue saved run** when no worker is enabled. Follow
   its recorded outcome and events. Admission does not prove processing/delivery.
5. **Open report** rechecks the inventory and navigates to the validated result.
   Registration also triggers an inventory refresh. Financial review stays required.

Research rebuilds saved models, monitoring/close render snapshots, and events/news
replay retained bundles. Successful runs register separate results and preserve the
original financial record. Fresh company queries, live/paid execution, arbitrary
commands/paths, uploads, approvals and browser cancellation/recovery are absent.

## Start the application

Build the interface using the [workspace guide](batch1-report-workspace.md).
From the repository root, prepare a new native workspace if needed:

```bash
.venv/bin/python -m keystone.workspace prepare --native \
  --destination output/workspace-native-run-demo
```

Preparation preserves existing destinations. Skip it when reopening an existing
registered native workspace, and substitute that workspace's path below.

```bash
.venv/bin/python -m keystone.workspace serve \
  --workspace output/workspace-native-run-demo --port 8765 \
  --enable-job-admission --enable-worker \
  --jobs-dir state/workspace-jobs
```

Open `http://127.0.0.1:8765/#/jobs` while the server runs. Read the current token
from the private file named at startup and enter it in the password field; never
paste it into a chat, URL, Git, screenshot or shared log. Provider keys are unnecessary.

Keep used control directories bound to their original workspace. Use a new
private directory for another workspace; preserve existing ledgers and evidence.
Omitting `--enable-worker` permits queueing only. Omitting both opt-in flags retains
the default read-only server. The browser cannot enable a worker. Use the exact
execution-server address: the Vite development proxy does not rewrite browser
Origin to grant execution access.

## Access, submissions and reloads

The token lives in application memory, never browser storage, URLs, request bodies
or rendered errors. Only protected local API requests carry its Authorization
header. Internal navigation retains access. **Clear local access**, document
reload and page departure clear access; they do not cancel saved jobs. Server
restart rotates the token, and refused access removes protected job content.
Late responses cannot restore a cleared session. This is single-operator local
access, not enterprise authentication or authenticated financial approval.

Before its first POST, the client freezes the request and creates one request key.
The submit control locks synchronously. Connection loss, deadlines, malformed
responses and ambiguous errors preserve that identity in memory. **Resend same
request** uses the identical body/key to retrieve an existing admission or submit
once. There is no automatic POST retry or replacement of an unresolved request.

Only recognised, status-matched pre-admission refusals permit **Edit refused
request**: invalid/oversized/unsupported format, unavailable source or capacity
refusal. Store errors and identity conflicts remain unresolved. After access
expiry, reconnect before resending with the existing identity.

A reload loses an unresolved browser-side identity while the server may already
have admitted it. The interface tells the reader to reconnect and inspect history
before new work. It claims neither persisted browser identities nor cross-tab
deduplication.

## Recorded progress and outcomes

Visible Run pages poll every three seconds, with one scheduled refresh at a time;
hidden pages pause periodic updates. Manual rechecks remain available. API waits
have a 12-second client deadline, separate from a job's processing limit. Queue
waiting, source preparation and registration are outside the 1–600 second limit.

The timeline shows confirmed ledger events: admission, claim, verified inputs,
prepared output, registration, and recovery/failure events. No percentage or
expected finish time is invented.

| Outcome | Interface behaviour |
| --- | --- |
| Queued | Explain worker availability; no result link |
| Running | Show confirmed stages and preparation/processing/registration scope |
| Review required / completed | Offer only the validated result route; financial approval stays false |
| Source changed | Explain the mismatch before processing |
| Failed | Ask the operator to inspect private evidence before new work |
| Outcome uncertain / delivery failed | Preserve identity; explain inspection and delivery-only recovery; no processing retry |
| Running with worker unavailable | Request operator inspection |

History is newest first, 25 jobs per page, with **Older jobs** and **Back to
latest**. Pagination returns keyboard focus to its heading. Deep job addresses
survive reloads; reconnect to inspect the selected ledger. Late responses for
another page, job or session are ignored. Failed protected reads clear old content
and report actions. Safe error messages never reproduce raw server text or paths.

Client validation checks supported versions, fixed profiles/limits, request fields,
states, financial restrictions and identities. Result routes are derived from
validated job IDs and must match the response. Backend authorisation, source pins,
durable state and financial processing remain authoritative.

## Implementation and verification

- `web/src/execution/job-data.ts`: contract validation and readable guidance.
- `web/src/execution/job-client.ts`: in-memory access, request identity, deadlines
  and stale-response protection.
- `web/src/execution/ExecutionWorkspace.tsx`: forms, stages, details, history and
  result navigation; `execution.css` integrates responsive styling.
- `web/tests/job-execution.test.mjs`: contract, uncertain submission, access,
  deadlines, pagination and response-race checks.

Local checks: **227 interface tests**, including **38 execution checks**;
TypeScript/production build passed. The existing workspace/admission/worker subset
passed **126 Python tests**. No backend or dependency change is introduced.

Browser rehearsal used a copy of the 139-file, 32-report QA workspace at
`output/job-interface-2c/workspace`. All five workflows were submitted through the
actual interface and their native results opened. A sixth request stayed queued
without a worker, then completed with its original identity after restart. All
six remained financially unapproved. Original entries/artifacts and the master
workspace were preserved. Generated receipts, screenshots, ledger and tokens stay
ignored by Git.

Reload/reconnect, explicit clearing, invalid tokens, restart/token expiry, source
preselection, recorded stages and keyboard interaction were checked. Job/form
pages fit measured 320px/390px widths without document overflow; history scrolls
inside its panel. The local rehearsal receipt records desktop measurements.

[2D now records the broader browser-to-worker failure/recovery acceptance](batch2d-execution-acceptance.md),
including interruption/delivery scenarios and history volume. It also corrects
late-response navigation and adds an explicit history-page loading state.
Human interpretation,
physical accessibility, actual PDF/print acceptance, real-source rights,
independent backups and production deployment retain their separate status.
