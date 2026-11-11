# Webapp Batch 5C — corrections, replacement inputs and report lineage

**11 November 2026 · Private, supervised local workflow.**
[5A review contracts](batch5a-review-foundation.md) · [5B notes](batch5b-review-workspace.md)

An analyst may discover that a saved report used an incorrect figure or an
incomplete source description. The correction must lead to a separately
validated input and an explicit processing request. An earlier report continues
to explain what was calculated at that time.

For example, fictional Northstar's supplied operating income changes from
EUR 120 million to EUR 130 million while annual revenue remains EUR 1 billion.
The analyst imports the corrected package, inspects those exact input changes,
and records the reason. A separate new analysis calculates an operating margin
of 13%, while the original report retains its 12% margin. Each report has its own
review scope; notes and acknowledgements are not transferred.

## The analyst journey

1. Open the original report's review workspace and choose an available review
   item. The correction reason is attached to that exact item and report scope.
2. Open **A new version. A clear reason.** Inspect/download the original input
   package using the existing version page. Prepare a corrected supported JSON
   package, with `dataset.supersedes_version_id` set to the original version.
3. Have the local operator register valid source-use permission for the corrected
   payload, if its contents changed. Permission records are content-scoped;
   the original permission cannot silently authorise different figures.
4. Follow **Import a corrected package**. The selected dataset is retained and
   the guided inspection refuses a mismatched predecessor. Existing intake
   checks the company/listing, format, source permissions and semantic validity.
   Acceptance saves a new version and starts no job.
5. Return to the original report and recheck correction history. Choose the
   eligible successor. Inspect the paged original/replacement field comparison,
   enter a local analyst label and reason, and record the correction link.
6. Follow **Inspect corrected input & choose processing**. Explicitly choose the
   calculation/replay and its current parameters. Existing job admission checks
   validation, permissions and any accounting predecessor again. A recorded
   correction link does not guarantee that a later processing request is eligible.
7. Open the replacement report. Its lineage points back to the earlier report;
   the earlier report lists the new result. The new review starts separately.

## Supported corrections and limits

All existing private supported JSON package formats can supply a replacement
within the same dataset, entity and format. New annual research, monitoring,
event-window, news-text and close inputs use their existing calculation paths.
Saved-source packages use their existing rebuild/render/replay paths; linking
them does not turn retained evidence into newly acquired observations.

This stage does **not** add an inline financial-value editor, PDF/OCR extraction,
document mappings, provider refresh or automatic source permission. Financial
fields are edited in the structured package and admitted through normal intake.
Analysis assumptions remain explicit choices on the existing processing screen;
recording an input correction neither copies nor approves an earlier run's plan.
Source lineage is distinct from Agent 2 correction decisions and Agent 4's
accounting correction/re-budget semantics. Their existing controls still apply.

Each original input can have one recorded successor. A competing link is
refused; accepted alternative inputs remain available to inspect. Continue a
later correction from a report using the replacement, preserving a chain rather
than overwriting the first relationship. This does not make that successor
financially approved or a global "latest truth".

The comparison includes supported package/source metadata and payload fields.
It excludes the required predecessor pointer itself. At least one further change
is required. JSON pointers distinguish absent fields from explicit null and
escape slashes/tilde characters. Values are displayed as retained JSON text so
large integers and decimal representations are not reinterpreted by the browser.
Long values are labelled truncated and remain complete in the original package.
The comparison describes input changes; it does not predict their effect on
calculated results.

Limits: 200 changed fields per comparison, 500 characters per displayed value,
2,048 characters per field pointer, 2,000 characters per reason, 120 characters
per local label, 200 correction records per workspace, 16,384 bytes per request
or saved record and a 2 MB response. The existing input-ledger storage limit
remains 64 MB. Exceeding comparison limits holds the correction link and keeps
the accepted input available; it never truncates the list silently.

## Contracts, access and durable recording

- `GET` / `HEAD /api/runs/{id}/review-corrections` provides incoming/outgoing
  correction links, affected original reports, replacement reports and eligible
  successor versions. The optional `replacement_version_id` query selects a
  verified field comparison.
- `POST` at the same route requires explicit private
  `--enable-review-corrections`, current local-token/same-origin access and one
  `Idempotency-Key` header. Manual servers default to history reads only.
- [Request schema](../../keystone/workspace/review/correction-request.schema.json)
  and [record schema](../../keystone/workspace/review/correction.schema.json)
  are strict version-1 contracts. Browser-supplied times, identities, approval
  flags and extra request fields are refused.

The request binds the report snapshot, target scope, replacement dataset/version,
replacement contract/payload hashes and the complete comparison hash. The server
rechecks both versions, validation and current source permissions under the same
ledger write transaction used for revocation. No permission is minted or copied.

The existing private `inputs.sqlite3` stores immutable `review_correction` and
`review_correction_receipt` objects atomically. A failure between inserts rolls
back both. Same-key/same-body retries return the original record; changed-body
or changed-report use of the key conflicts. Two racing keys cannot attach two
successors to the same input. IDs, sequence and time are server-assigned. The
local analyst label remains `local_operator_unverified`.

Recording a correction link creates neither a review decision nor a review note.
The existing review-activity overview continues to reflect notes until the
separate 5D disposition workflow is implemented.

Original inputs, report artifacts, operation receipts, calculations and notes
are unchanged. Correction links do not mark requirements resolved, change job
outcomes, release withheld values or grant financial approval. Affected-report
lists are derived from exact retained input version IDs, without editing the
reports or claiming that every report is financially invalidated. Every linked
report is checked against its current source and job lineage before delivery.

## Lost replies, history and recovery

One in-memory pending correction retains its original body and submission key
across report navigation/disconnect. A lost or malformed reply stays
unconfirmed. Rechecking saved history can confirm a matching receipt without
another POST; **Retrieve / retry same correction** reuses the original identity.
An initial definitive refusal can be acknowledged before editing. A later
refusal cannot discard an already uncertain submission. Pending metadata is
hidden without access and cannot be posted into a different workspace. Late
responses cannot confirm another connection.

Keep the original tab open while a correction is unconfirmed. A full page reload
or tab closure loses the in-memory retry identity; inspect retained history
before submitting anew. Unsaved explanation drafts are not durable. Confirmed
correction records persist across reload and reconnect.

An unrelated report or a newer input does not change an earlier record's source
binding. Later review-definition changes preserve the earlier snapshot's history
without importing its review state into the current scope. A stale new correction
is refused. Missing or changed evidence/receipts holds delivery rather than
repairing the record silently.

The existing private snapshot inventory includes the input ledger. Snapshot and
restore validation additionally checks record/receipt pairing, hashes, ordering,
unique predecessor links, original report bindings, both input contracts and the
saved comparison. Restore retains the original correction identity and retry
receipt, rotates connection credentials and preserves existing queue holds. It
starts no agent. Independent-device backup and clean-machine disaster recovery
remain deferred release dependencies.

## Verification and remaining work

Automated checks cover input comparison, exact bindings, stale/invalid/approval
attempts, source and replacement permission withdrawal, concurrent retries,
atomic rollback, source-permission non-inheritance, corruption, snapshot/restore,
all five saved workflow families, explicit research recalculation and independent
review scopes. Browser checks use an isolated fictional Northstar workspace;
generated packages, reports, tokens and screenshots remain ignored by Git.

Recorded validation: 216 distinct related backend cases passed across the
211-case broader regression run, four additional boundary/accounting cases and
the final 96-case review run (these runs overlap). All 409 frontend tests and
the TypeScript/production build passed. The final read-path check verifies one
full catalogue validation per lineage request while retaining each linked run's
source authorisation and file checks.

Formal durable review dispositions, reopening decisions and full review-flow
acceptance remain **5D**. This implementation is not authenticated financial
approval, a production release or issuer-data accuracy certification.

The ignored `output/analyst-review-5c-preview` evidence folder retains test/build
logs, `browser-check.json` and `correction-lineage.jpg`. The actual webpage
rehearsal refused an unrelated predecessor package, imported the authorised
successor without execution, showed the three changed fields, saved one
correction and explicitly requested a new analysis. It verified the original
12% margin against the replacement's 13%, separate notes/review scopes,
ungranted financial approval, links after full reload/reconnection and no
horizontal overflow at the default 576-pixel side-panel width. Hashes for all
22 original input/report/operation files remained identical. Both runs reserved
zero model requests/output tokens and had live data disabled.
