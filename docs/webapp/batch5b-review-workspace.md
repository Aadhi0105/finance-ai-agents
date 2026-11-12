# Webapp Batch 5B — analyst review workspace and saved notes

**11 November 2026 · Private local implementation.**
[5A contracts](batch5a-review-foundation.md) · [Open Keystone](open-keystone.md)

An analyst can now work through a report's review subjects, inspect their sources
and keep questions and follow-up work beside the exact evidence. This implements
the review workspace. [5C](batch5c-corrections-lineage.md) adds a separate input
correction workflow; [5D](batch5d-review-decisions.md) adds formal saved review dispositions.

## Analyst journey

Open a native report, choose its review section and **Open review workspace**.
The list starts with saved review requirements. Filter by area or search for an
input, mapping, assumption, section or issue. The selected item shows its scope
and restrictions. Links open the relevant section or expand original financial
findings. Source references can be searched/paged without dropping any; inspection
uses the existing verified evidence reader and return-focus control.

Enter a local analyst label, choose **Observation**, **Question** or **Follow-up
work**, and write a note. Up to ten source references can be attached. Drafts are
not saved automatically. Switching items within the report preserves their
drafts; unsaved drafts are not persisted across leaving/reloading the report.
Saving records an immutable note. Add a further note to clarify one; this stage
provides no edit/delete operation, source override or approval checkbox.

The notebook lists notes for the selected item and all notes for the scope.
Older-scope notes remain separate. A new financial input produces a different
report/notebook, rather than inheriting another report's review activity.
Notes are private workspace records, not additions to the original HTML or its
reading/print copy. Controlled review exports belong to a later stage.

## Activity is not a decision

The 5A snapshot and its zero-decision progress protocol remain unchanged. The
notebook separately reports analyst activity: no current-scope notes means
`not_started`; at least one current-scope note means `in_review`. An unavailable
notebook is shown as unavailable, never inferred to be empty or complete.

Every saved requirement remains pending. Notes do not resolve source issues,
release withheld values, accept financial mappings, authorise statistical
inference, change job outcomes or grant financial approval. The analyst label is
explicitly `local_operator_unverified`, not enterprise authentication/sign-off.

## Contracts and protected delivery

- `GET` / `HEAD /api/runs/{id}/review-notes`: verified current-scope notes and
  separate earlier-scope history, with recording capability and activity state.
- `POST /api/runs/{id}/review-notes`: private, explicitly enabled, same-origin,
  bearer-token-protected submission with one `Idempotency-Key` header.
- [Note request schema](../../keystone/workspace/review/note-request.schema.json)
  and [saved note schema](../../keystone/workspace/review/note.schema.json) use
  version 1. Wire types are strict; extra request fields are refused.

Only private servers started with `--enable-review-notes` accept writes. Open
Keystone supplies the flag and verifies it at readiness. Manual servers without
the flag can read saved notes. Synthetic catalogues have read-only empty
notebooks. This capability is independent of import/job/worker admission.

Requests bind the exact snapshot, target ID and target scope hash. Attached
references must belong to the selected available target. Every operation checks
the current registered report, retained files, private input version, job lineage
and source-use permissions. The write rechecks scope under the input ledger's
write transaction, serialising it with permission revocation.

A saved note preserves the complete run/input/artifact binding, original request,
target title/kind, server-assigned ID/sequence/time and local attribution. Text
remains plain data, not HTML, executable instructions, model prompts or source
corrections. Reads/writes perform no analysis or acquisition.

## Durable writes and uncertain outcomes

The existing private `inputs.sqlite3` stores append-only `review_note` and
`review_note_receipt` objects. Both are committed together using its existing
private-file checks, immediate SQLite transaction, DELETE journal and EXTRA
synchronous durability. A failure between inserts rolls back both. There is no
new database, browser-supplied path or runtime schema migration.

Submission identities are workspace-wide. Replaying the same key and exact
request returns the original note; reusing it for another body/run conflicts.
The receipt fingerprint includes the run and full request. Correlation hashes,
rather than raw retry keys, accompany saved notes. Keys/tokens are not written
into URLs, HTML attributes, logs or browser persistence.

One in-memory pending submission survives report navigation and disconnect.
It retains the original body/key, hides metadata without local access and
cannot be replayed into another workspace. Lost/malformed responses remain
unconfirmed. The interface can inspect the original submitted text, retrieve
saved history or retry the identical submission. A matching saved receipt can
confirm a note without another POST. No automatic new-key retry occurs.
Full page reload or tab closure loses an unconfirmed in-memory retry identity;
inspect saved history before submitting anew. Confirmed notes persist in the
workspace ledger and are loaded again after reconnecting.

A first definitive refusal can be acknowledged before editing; current-scope
text is restored to its draft. A refusal after an uncertain outcome cannot discard
the original identity. After review-definition changes, a committed note can
still be retrieved with its original identity while current source access remains
valid; it stays earlier-scope history. A stale new submission is refused.
Unresolved cases remain held for operator inspection, not guessed successful.

## Storage and recovery

Private snapshots already inventory the input ledger. Validation now also checks
paired notes/receipts, record hashes, per-run sequences, workspace, request
fingerprints and registered report bindings. Current-scope subject metadata is
revalidated. Missing/corrupt pairs or changed bindings refuse reads and
backup/restore; they are not silently repaired or discarded.

Restoration preserves original note bytes and retry receipts while retaining the
existing new-token and held-queue rules. It executes no agent. This remains local
restoration evidence; independent backup, encryption/key recovery and clean-machine
disaster recovery retain their separate dependencies.

Limits: 2,000 characters per note; 120 per analyst label; ten attached references;
16,384-byte request/record bounds; 100 notes per report across review scopes;
1,000 per workspace; and the existing 64 MB input-ledger ceiling. Existing notes
are preserved on capacity refusal. Notebook reads stay below the 2 MB ceiling.
Source lists page at ten entries; paging/search changes no retained data.

## Verification and preview

Backend checks cover rollback, lost-response replay, same-key concurrency, scope
changes, invalid/approval-promoting requests, current permissions, transport
bounds, capacity, corruption and restoration. All five saved-report workflows
are exercised through the authenticated private note interface. Engine/network
guards and before/after evidence hashes verify that notes execute no analysis
and do not modify source/report files.

Frontend checks cover bindings, plain text, pending-request freezing, late
responses, cross-workspace refusal, authentication transport, same-key retry,
receipt reconciliation and actual report-section anchors. Charts/review tools
load separately from the initial connection screen.

The isolated fictional preview uses `http://127.0.0.1:8870/` and
`output/analyst-review-5b-preview/workspace`. Generated notes, reports, connection
tokens, logs and browser evidence are private and ignored by Git.

Recorded verification: **181 related backend tests passed**, **all 386 frontend
tests passed**, and TypeScript checking/production build passed. The initial
application bundle is approximately 399 kB; report/review tools load separately.
The browser inspected an exact revenue source, preserved its draft on return,
attached that source, saved one follow-up note and found it again after a full
reload/reconnection. Analyst activity became in-progress; financial approval and
publication restrictions were unchanged. Original input, report and operation
file hashes matched their pre-note baseline; model requests remained zero.
The ignored preview folder retains `browser-check.json` and `review-workspace.jpg`.
