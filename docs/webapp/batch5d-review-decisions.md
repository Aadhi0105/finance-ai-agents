# Webapp Batch 5D — saved analyst decisions and review-flow acceptance

**12 November 2026 · Private, supervised local workflow.**
[5A scopes](batch5a-review-foundation.md) · [5B notes](batch5b-review-workspace.md) ·
[5C input corrections](batch5c-corrections-lineage.md) · [Open Keystone](open-keystone.md)

An analyst can now record what they decided about a particular report item,
explain why, and revisit that decision later. The explanation, exact report
version and earlier decisions remain available. This completes the bounded
Batch 5 review workflow; it does not grant authenticated financial approval.

For example, fictional Northstar's report shows a 12% operating margin. You save
a note questioning operating income, then **Request changes**, attaching that
note. You import an authorised corrected input and record its correction link.
That link leaves the original decision at **Changes requested**. After an explicit
new analysis, the replacement report shows 13% and starts a separate review.
You can acknowledge what you reviewed on either report, or reopen an item when
new questions arise. The original 12% report and its history remain intact.

## What the analyst does

1. Open a native report and choose **Review priorities / requirements**, then
   **Open review workspace**. Select a review item and inspect its saved evidence.
2. Save an observation or question if helpful. Use the existing correction panel
   when revised structured inputs are needed. These are separate saved records.
3. Under **Your review decision**, choose **Acknowledge item**, **Request changes**
   or **Reopen item**. Enter your local analyst label and explanation.
4. Optionally attach saved notes or correction links for this exact item and
   scope. Confirm the report/item boundary, then **Save review decision**.
5. Inspect the latest explanation, immutable history and overview counts.
   **Earlier decisions** reads the next history page; **Latest decisions** or
   **Recheck review decisions** returns to the latest consistent history.

Acknowledgement means that the item and its limitations were reviewed. It does
not certify source accuracy, release withheld figures, resolve an agent's
underlying evidence gate, or change an accounting decision. A correction link
does not acknowledge or reopen an item automatically. New calculations still
need explicit admission through the existing job interface.

## States and exact scope

| Item state | Meaning |
| --- | --- |
| Awaiting review | Available subject without a decision, or explicitly reopened |
| Acknowledged · restrictions remain | Acknowledgement recorded for this exact subject |
| Changes requested | A recorded request remains the latest decision |
| Not recorded | No available subject; it cannot be acknowledged |

| Overall disposition progress | Rule |
| --- | --- |
| Not started | No current-scope decisions |
| In progress | Decisions exist and available items remain pending |
| Changes requested | At least one available item has an active request for changes |
| Reviewed with limitations | Every available subject is acknowledged |

Existing note activity can show **In progress · notes recorded** before a formal
disposition is saved. Notes never count as acknowledgements. Missing or invalid
journal/notebook delivery shows unavailable/checking status, rather than assuming
a clean review. Financial approval remains **Not granted** in every state.

Decisions bind the workspace, report, registered files, input dataset/version,
processing request, presentation and exact review-subject hash. A second report
using the same input starts separately. Changed review definitions retain earlier
scope history without carrying its progress forward. Earlier-scope records are
labelled historical; only current-scope events contribute to current status.

Repeating the current item state with a new submission is refused. An initially
pending item cannot be reopened. Reopening an acknowledged or change-requested
item records a new event and returns it to awaiting review. Earlier records are
never edited or deleted by this workflow. There is no bulk acknowledgement.

## Protocol, recording and access

The existing version-1 `/review` scope protocol remains unchanged, including its
read-only `decisions_enabled: false` and zero-event progress. It describes the
immutable review definition. Actual saved disposition progress is delivered by a
separate `keystone.review-journal`, `dispositions/1.0.0` protocol:

- `GET` / `HEAD /api/runs/{id}/review-decisions` returns current progress, the
  latest decision per current subject and one page of immutable records.
- `POST` at the same route requires private `--enable-review-decisions`, current
  local-token/same-origin access and one `Idempotency-Key`. Manual servers default
  to history reads. Public synthetic catalogues have explicit read-only journals.
- [Request schema](../../keystone/workspace/review/disposition-request.schema.json)
  and [record schema](../../keystone/workspace/review/disposition-record.schema.json)
  define strict version-1 records. Extra fields, supplied approval/identity/time,
  stale scope, stale history and invalid attachments are refused.

Each request includes the last observed per-report journal ordinal
(`expected_sequence`). A new decision from a stale tab is refused so it cannot
silently overwrite a later review action. Recheck history, acknowledge a definite
refusal, and reconsider the draft. The server never rebinds a request automatically.

The existing private `inputs.sqlite3` ledger atomically stores a
`review_decision` and `review_decision_receipt`. IDs, time, per-report ordinal and
per-scope event sequence are server assigned. Source checks and writes use the
same ledger write gate as permission revocation. Attached records must match the
exact run, snapshot, item and hash; correction replacements retain their own
permission checks. Withdrawing relevant source permission holds delivery/writes.

Same-key/same-body retries return the original record, including after subsequent
events or a changed review definition. Changed body/report use conflicts. One
receipt and record commit together or neither commits. Local labels are explicitly
`local_operator_unverified`; access tokens do not establish enterprise reviewer
identity, role separation or authenticated sign-off.

Limits: 1,000 decisions per report across scopes, 2,000 per workspace, 1,600
characters per reason, 120 per label, up to 10 notes and 5 corrections per decision,
16,384 bytes per request/record, and a 4 MB journal response. The existing 64 MB
input-ledger limit also applies. History uses 25-record pages, newest first, and
revision-bound cursors. A concurrent new decision invalidates an older page
request; recheck latest history. No history list is silently truncated. These
are bounded local-pilot limits, not multiuser service capacity claims.

## Interrupted saves, snapshots and restoration

A pending submission keeps its exact body and key in tab memory across report
navigation and disconnect. Another decision cannot replace it. A lost, malformed
or approval-promoting acknowledgement stays unconfirmed. Retrieve saved history
to confirm a matching receipt or use **Retrieve / retry same decision**. This
reuses the original request, including its original observed history version.
A late failure cannot undo a confirmation already found in saved history.

An initial definite refusal may be acknowledged to restore/edit the draft.
A later refusal does not discard an earlier uncertain outcome. Disconnect hides
pending metadata; another workspace cannot receive it. Late responses cannot
confirm a different connection. A matching record outside the visible page can
be retrieved by the original same-key retry or through the relevant history page.

Keep an unconfirmed tab open. Full reload/tab closure loses the in-memory retry
identity and unsaved drafts; inspect retained history before submitting anew.
Confirmed decisions survive reload/reconnect. Browser persistent storage does
not retain credentials, explanations or retry identities.

Private consistent snapshots already include the ledger. Backup and restoration
now validate decision/receipt pairing, hashes, ordered transitions, exact report
bindings, linked records and reduced progress. Restore retains identities and
retry receipts, rotates connection credentials and starts no agent. Corruption
holds delivery and snapshot preparation rather than silently repairing history.
Independent-device backup, encryption/key recovery and clean-machine disaster
recovery remain separate deferred release dependencies.

## Bounded acceptance matrix

| Acceptance area | Verification |
| --- | --- |
| Native report families | Research, monitoring, events, news and close saved reports accept exact-scope dispositions; fresh calculations covered for all five families |
| Independent states | Acknowledge, request changes, reopen and all-available-items acknowledged; financial approval/gates remain unchanged |
| Corrections and reruns | Note and correction attachments, explicit replacement calculation, separate new review and original history retained |
| Stale or conflicting work | Stale report/history, repeated states, wrong report/target, unknown attachments and competing new keys refused |
| Reliable saves | Same-key concurrent replay, atomic rollback, uncertain outcomes, double clicks, malformed replies and late responses |
| Access and permission | Local authority, origin checks, disconnect, wrong workspace and source/replacement permission withdrawal |
| Complete history | Ordered current/earlier scopes, 25-record pages, stable revision, capacity/response-size refusal without evidence loss |
| Recovery | Corrupt records/receipts held; private snapshot restore retains progress/IDs/retries without calculation |
| Financial evidence | Review writes preserve original reports, input files, operation evidence and committed close accounting state |

Browser acceptance uses an isolated fictional workspace. Generated packages,
tokens, reports, screenshots and test logs remain in ignored
`output/analyst-review-5d-preview`. Automated checks establish the local mechanism;
they do not replace the deferred analyst interpretation trial, issuer accuracy
review, source licensing or enterprise permissions. PDF/document intake and the
broader backend programme retain their agreed later sequencing.

### Recorded verification

247 distinct related backend cases passed across the review, recovery, launcher,
workspace and onboarding runs, including 30 disposition-specific cases. The
first combined run had 29 correction-fixture setup refusals while a preview
calculation held the shared maintenance gate. Those cases were rerun without
simultaneous preview writes; the 112-case regression rerun passed, followed by
the linked-note/correction restoration case. All 435 frontend tests and the
TypeScript/production build passed. These run counts overlap; they are not a
claim that the entire repository suite was rerun.

The actual browser journey saved a question and change request, imported and
linked the corrected package without automatic execution, reopened the item
with its correction attached, and acknowledged all 14 available subjects.
The overview showed **Reviewed with limitations** and **Financial approval:
Not granted**. Reopening returned it to **In progress**. A 27-event rehearsal
verified both the 25-record latest page and the two earliest records, with the
latest overall state retained on either page.

An explicit replacement calculation produced a 13% operating margin against the
original 12%, with zero inherited decisions/notes and a linked original report.
Full reload/reconnection retained all 27 original decisions, the note and
correction. All 22 original input/report/operation files remained byte-identical.
Both jobs reserved zero model requests/output tokens. The default 576-pixel
side-panel width had no horizontal page overflow. Ignored evidence includes
`browser-check.json`, `integrity-check.json`, `review-completed.jpg`,
`review-decisions.jpg` and the test/build logs.
