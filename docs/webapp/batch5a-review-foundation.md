# Webapp Batch 5A — review structure and states

**11 November 2026 · Implemented foundation, read-only delivery.**

An analyst needs to distinguish acceptance of an input for processing, execution
of a calculation, review of the resulting evidence, and financial approval.
Batch 5A adds an executable review model and an overview in the native report's
existing review section. It does not record analyst decisions or modify reports.

## The four independent states

| Dimension | Meaning in this implementation |
| --- | --- |
| Input acceptance | `accepted_for_processing` for an authorised private dataset version, otherwise `retained_evidence` for the synthetic saved-report catalogue. Neither verifies financial truth. |
| Execution | The exact registered run outcome; reading a review does not change it or start a job. |
| Analyst review | `not_started` until a later feature durably records review events. A missing response is unavailable, never an inferred unreviewed or approved state. |
| Financial approval | Always false. A local access token or typed reviewer label does not establish authenticated approval authority. |

The existing evidence/publication gate is retained separately. No review state
can release withheld values, remove restrictions, change source permissions or
approve statistical inference. Import validation and valuation assumption
acknowledgements retain their original, narrower meanings.

## Review subjects

The projection creates three shared subjects, one per retained report section,
and one per retained review issue:

| Kind | Scope |
| --- | --- |
| `source_inputs` | Retained source basis and input evidence. Private inputs remain pinned to their exact dataset version. |
| `financial_mappings` | Saved field links and transformations connecting report figures to retained evidence. These are not document-extraction mappings or proof of accounting correctness. |
| `calculation_assumptions` | Retained assumption/policy metrics and relevant method sections; explicitly not recorded if unavailable for this presentation. |
| `report_section` | One exact section, including its availability and linked restrictions. An unavailable financial section can still be inspected as an unavailable section. |
| `review_issue` | One saved requirement and its linked sections, evidence and explanation. Acknowledging it records understanding, not resolution of its underlying restriction. |

The complete native presentation is bound even when a section has no direct
metric references. Original files, numerical results and financial checks are
unchanged. Legacy reports without a registered native presentation cannot acquire
an invented review scope; their existing original-report path remains available.

## Version binding

Runtime contracts are in [the review package](../../keystone/workspace/review/):

- [Snapshot schema](../../keystone/workspace/review/snapshot.schema.json):
  `keystone.review-snapshot`, schema 1, policy `review/1.0.0`.
- [Decision schema](../../keystone/workspace/review/decision.schema.json):
  `keystone.review-decision`, schema 1; reserved for later durable writers.
- [Decision reducer](../../keystone/workspace/review/contracts.py): pure, bounded
  validation and reduction; no storage, network, agent execution or approval.

A snapshot binds the workspace identity, complete registered run identity,
every artifact hash, native presentation hash, and (where present) dataset,
input version, input contract and request fingerprint. Run identity also covers
the adapter/method versions, accounting origin and producer provenance retained
by the existing contracts. Each subject has its own scope hash. The snapshot ID
hashes the full snapshot definition, excluding only its own ID.

Changing evidence, a selected input, request, presentation, subject definition or
review policy requires a different snapshot. A decision must match both the
snapshot ID and its subject's scope hash. Unknown, duplicate, stale, out-of-order,
unrecorded-subject and approval-promoting events are refused. A new input version
does not retroactively invalidate an unchanged historical report's own review.

Hashes establish consistency, not authenticity or permission. The API reloads
the catalogue, verifies the native report and rechecks private source versions,
job lineage and current source-use permissions before providing a snapshot.
Adding an unrelated report does not change a private report's review identity.

## Future decision states, already enforced by the pure model

Every available subject starts `pending`; an absent subject is `not_recorded`.
Supported event dispositions are `acknowledged`, `changes_requested` and
`reopened` (which returns that subject to pending). Subjects are independent.

| Overall analyst state | Reduction rule |
| --- | --- |
| `not_started` | No recorded decisions. |
| `changes_requested` | At least one currently effective request for changes. |
| `in_review` | Decisions exist and available subjects remain pending. |
| `reviewed_with_limitations` | Every available subject is acknowledged; the source and publication restrictions still apply. |

Events require an ID, ordered snapshot-scoped sequence, timezone-aware time,
explanation and reviewer attribution marked `local_operator_unverified`.
A subsequent acknowledgement can record that an analyst understands/accepts a
limitation; it cannot declare that source evidence was corrected. Corrections
will need the separate version-creation workflow in 5C. Reopening preserves the
preceding events rather than editing them.

There is **no event writer, decision file or database migration in 5A**. Before
using the reducer in a later stage, the writer must authenticate local access,
reload the authorised current scope, assign time/sequence, preserve append-only
events, enforce retries and handle durable-write failures. It must not trust
browser-supplied hashes as authority. A deliberate protocol/version change will
be needed to enable writes; the 5A snapshot explicitly fixes
`decisions_enabled=false`.

## Delivery and interface

`GET` / `HEAD /api/runs/{run_id}/review` returns a snapshot and zero-event
progress. It supports the existing synthetic native and authenticated private
catalogues. Query parameters are refused. POST/PUT/PATCH/DELETE remain refused
by the shared read boundary. A missing native view, changed file or revoked
source permission fails closed. Responses are uncached and use the existing
same-origin/loopback and private-token controls.

The overview shows the four states, the five subject groups, outstanding subject
counts and a collapsed exact-version record. It offers no approval checkbox or
inactive decision controls. Existing source findings remain below it. The client
checks the inventory, native-view hash, input version, subject coverage,
references, fingerprints and zero-event profile. Stale/unsupported responses
show an unavailable state with recheck, without inventing review completion.

The projection permits at most 223 subjects (three shared, 20 sections and 200
issues), 2 MB of review response and 2,000 events in the pure reducer. Oversized
responses are refused rather than silently truncating requirements. Reads
perform no financial computation or external requests and persist no review data.

## Scope boundaries and next stages

- **5B:** the analyst review workspace, notes and evidence navigation.
- **5C:** [implemented corrections, new input versions and affected-report lineage](batch5c-corrections-lineage.md).
- **5D:** durable review dispositions and complete acceptance of the review flow.
- **Document intake:** future document candidates and mappings need their own
  contracts and evidence locations; no PDF/OCR or provider acquisition is added.

No changes are made to existing catalogue/native-report versions, accounting
state, job outcomes, permission records or restored queue holds. No new recovery
inventory is needed for the read-only projection. Later stored decisions will
require explicit storage, snapshot and restore support before they are enabled.

## Verification

The backend tests cover all five workflows, legacy and private fresh families,
independent state transitions, stale input/request/presentation/workspace bindings,
unrecorded subjects, invalid approval attempts, schemas, read-only HTTP, unchanged
evidence and private permission revocation. Frontend tests cover the corresponding
15 captured fictional presentations, scope/ref/hash substitutions, missing review
subjects, inherited decisions, transport limits and abort handling.

Recorded checks: **313 related backend/workspace tests passed**, followed by
**43 final focused review tests passed** (overlapping coverage, not additive).
**All 363 frontend tests passed**, and TypeScript checking and the production
build passed. Review code loads separately from the initial application bundle.
Runtime literal types are also checked explicitly: numeric zero cannot substitute
for boolean false, and boolean true cannot substitute for integer schema 1.

The isolated browser preview uses fictional Northstar inputs at
`http://127.0.0.1:8868/`, under
`output/analyst-review-5a-preview/workspace`. Generated inputs, tokens, reports
and browser evidence are private/ignored. These checks do not establish issuer
accuracy, authenticated financial approval, source entitlement or production
release readiness.

The browser requested a new fictional analysis and opened its report. The new
overview displayed input accepted / execution completed / review not started /
approval not granted; all five groups, eight sections and three saved review
requirements were present. Exact-version disclosure opened/closed correctly,
with no horizontal overflow in the overview at the normal side-panel width.
The observed snapshot matched the retained run and input; the operation reserved
zero model requests and had live data disabled. The screenshot and check receipt
are `review-overview.jpg` and `browser-check.json` in the isolated preview folder.
