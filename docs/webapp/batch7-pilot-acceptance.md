# Webapp Batch 7 — pilot scope and acceptance

Prepared 16 November 2026. **7A is prepared; the analyst trial, operational
rehearsal and readiness decision have not been performed by this batch.**
All 24 checks start **not assessed**, with no assigned release candidate.

This pilot asks whether one analyst can use the current application, understand
its reports and preserve/recover the resulting evidence within a small declared
workload. It builds on the [Batch 6 implementation](batch6-operational-readiness.md)
and [Batch 5 review workflow](batch5d-review-decisions.md). Historical test passes
are supporting evidence, not answers to new analyst tasks or release sign-off.

| Part | Deliverable | Current state |
| --- | --- | --- |
| **7A — Scope and acceptance** | Declared workload, expected results, acceptance matrix, evidence format and unresolved dependencies | Prepared by this change |
| **7B — Analyst usability and interpretation** | Fresh fictional workspace, task cards, actual analyst answers, observed usability problems and retests | Not assessed |
| **7C — Operational acceptance** | Candidate-bound access, failure, storage, recovery and update evidence; measured bounded workload; targeted fixes and retests | Not assessed |
| **7D — Evidence and readiness decision** | Reconciled final evidence pack and an explicit scoped analyst decision | Not assessed |

## Scope selected for this pilot

| Dimension | Included |
| --- | --- |
| Purpose and operator | Private personal evaluation; one analyst on this Mac |
| Supported environment | macOS on Apple silicon; Python 3.11; Node 24; pnpm 11.25.0; exact patch/OS versions recorded at freeze |
| Application | Committed frontend/backend, selected through the existing launcher or documented private server procedure |
| Access | Loopback only, existing local token and file boundary; local possession is not authenticated identity |
| Data | Fictional, structured, content-scoped inputs; local processing, retention and backup permissions recorded explicitly |
| Workflows | Agent 1 research; Agent 2 supplied-history monitoring; Agent 3 historical events and supplied news text; Agent 4 synthetic close |
| Execution | Five initial calculations, then one deliberately requested research correction calculation; sequential, one mutator |
| Review | Sources, charts, complete reading copies, exact-version notes/decisions, correction lineage and saved history |
| Recovery | Stopped, verified local snapshot/restore and recovery of already proved delivery in isolated copies |

Excluded: live provider acquisition, paid model calls, current-market/company
claims, external sharing, remote hosting, multiple users, authenticated approvals,
automatic scheduling, ERP integration and PDF/document extraction. The supplied
monitoring workflow does not validate the separate persistent CLI monitoring
cycle. Historical events and document tone do not forecast returns. Fictional
permission records establish no real provider entitlement.

The pilot may demonstrate a useful **offline supervised tool**. It cannot approve
company financial results or establish production readiness. The
[Production v1 matrix](../production/v1/acceptance-matrix.md) retains all its
existing statuses and separate sign-off requirements.

## Frozen workload and expected results

Use a **new isolated workspace**. Preserve existing demos, user inputs, reports
and earlier trial records. No workspace or source relocation is part of 7A.

The base workload contains **five datasets, six accepted input versions and six
calculation requests**: one per workflow plus the research successor. All six
results must have their registered evidence retrieved and checked. Fault,
capacity, restoration and update rehearsals use additional isolated copies and
are reported separately; they do not inflate or replace this base workload.

These are evaluator oracles, not a claim that a new calculation was run in 7A.
In 7B prepare separate task cards without these answers. Record what the analyst
understood before looking at the oracle or offering corrective help. Record prior
familiarity; this is a supervised self-evaluation, not a blinded independent study.

| Workflow and retained source fixture | Expected observations and limits |
| --- | --- |
| Research — [financial kit](fresh-analysis/examples/complete-kit.json) | FY2023–2025 revenue EUR 800m, 900m and 1bn. FY2025 EBIT EUR 120m / revenue 1bn = 12% operating margin. Effective tax 25m / 100m = 25%; FCFF = 120m × 0.75 + 20m − 25m − 5m = EUR 80m. Earlier optional cash-flow components remain missing. Explicit valuation assumptions remain conditional. Consensus and named-broker reports are unavailable in this kit. |
| Research successor — derived from that kit | Change only FY2025 operating income to EUR 130m, with a new source locator/version and a recorded fictional correction reason. Holding the other supplied inputs constant gives margin 13% and FCFF EUR 87.5m. Record the mechanical inconsistency of changing EBIT without restating other financial statements: this tests lineage/arithmetic, not a reconciled company restatement. Link the successor, then explicitly request a calculation. Original review/history remains accessible; the new result needs its own review. |
| Monitoring — [observations](../../fixtures/local_workflows/monitoring.json) | Below-3 policy against leverage 2 → 3.5 → 3.5: new breach, then stable active breach. Coverage changes from 4 to missing: latest coverage is unavailable, never silently 4. Explain observation dates, supplied policy and supplied-history scope. |
| Events — [return windows](../../fixtures/local_workflows/events.json) | One event/issuer, zero controls; supplied model has intercept 0.0005 and beta 1.2. Abnormal returns 1%, 2%, 3% sum to CAR 6%. Unverified date/provenance/design and the small sample keep inference held. This is descriptive historical arithmetic. |
| News — [articles and word list](../../fixtures/local_workflows/news.json) | Frozen cutoff 31 October 2026, 12:00 UTC; five articles include one stale, one unrelated, one duplicate pair and one relevant unscored story. The scored story has two positive matches / six words = 1/3. No matching tone is unavailable, not neutral. Do not promote the small, incomplete diagnostic into publishable aggregate sentiment. |
| Close — [monthly budget and actuals](../../fixtures/agent4/close-june.json), wrapped using the supported fresh-close request | January–June budget profit 36,000 cents, actual 39,000 cents; sales variance +6,000 cents, cost variance +3,000 cents and profit variance +3,000 cents. A cost increase contributes negatively to profit. Explain any forecast assumptions. The fixture's `approved` budget flag is not authenticated/controller approval. |

Before hashing/admitting the fictional research kit, a preparer may set its
fictional quote observation/source period/locator to the day before the trial
freeze. Record that transformation and the prepared bytes in the input manifest.
This creates new fictional test data, not a refreshed market observation. Do not
alter an accepted version, clear synthetic warnings or refresh a real source.
News uses its historical cutoff unchanged. If a delay makes the quote stale,
preserve the resulting hold or prepare a newly identified candidate/input record;
do not silently edit dates beneath existing results.

Tolerances are declared before measurement: source decimal values and close
integer cents must match exactly; ratios and event returns allow absolute error
at most 1e−9; conditional DCF arithmetic allows the larger of one base-currency
unit or 1e−9 relative error. DCF comparison must use an independent calculation
with the exact frozen method/assumptions recorded in its evidence. Display
rounding allows half one unit of the final displayed digit, with exact-value
evidence still available. An expected hold/unavailable result passes only if the
analyst identifies it accurately; process completion alone never passes a task.

## Predeclared trial limits

These are initial acceptance targets for this small sequential trial, **not
measured performance, a production SLA or resolution of the global capacity
dependency**. At the start of 7B the analyst confirms the precise scope and trial
budget. If a target is unsuitable, revise/version the protocol before that
candidate's measurements. Never relax an existing threshold to convert a failure
into a pass.

| Measure | Target and measurement boundary |
| --- | --- |
| Ordinary protected read | At most 12 seconds from request to complete response; include report/history and actual evidence downloads |
| Write confirmation | At most 75 seconds from explicit save/submit to complete acknowledgement; record uncertainty/retry separately |
| Calculation delivery | At most 120 seconds from submit to terminal state for each of six sequential calculations, including queue and result delivery; explicitly select a 120-second job limit |
| Workspace growth | Peak logical file bytes minus pre-import workspace baseline at most 100,000,000 bytes; retain baseline/peak/final observations, with no deletions to meet the target |
| Usage | Zero provider requests, model requests and model output tokens; verify request profiles/receipts and network-denial evidence |
| Other disk use | Separately report staged installations, caches, downloaded copies, snapshots and fault/update workspaces; they are not hidden inside the growth claim |

Measure user-visible timings with a monotonic clock and retain the underlying
requests/receipts. Report each observation and the maximum, not just an average.
For peak bytes use a documented inventory sampling cadence plus sizes at each
accepted import, terminal calculation and evidence/review checkpoint; label the
sampling limitation. Engine timeout is not evidence of actual end-to-end time.
Do not include deliberate fault cases as successful ordinary-read measurements.

## Acceptance matrix

[protocol.json](pilot/protocol.json) is the structured register of these checks,
their full pass conditions, production crosswalk and dependencies. All checks are
required for this specific pilot decision; none is passed by creating this plan.

### 7B — analyst tasks

| ID | Task | Required evidence |
| --- | --- | --- |
| P7-UAT-01 | Open and identify the pilot | Selected version/workspace, scope/budget acknowledgement and explanation of the local boundary |
| P7-UAT-02 | Research: periods, figures and source | Analyst's period/figure answers, exact source trace and missing-data explanation |
| P7-UAT-03 | Research: conditional value and unavailable research | Assumption/model-value explanation; consensus and broker availability accurately identified |
| P7-UAT-04 | Monitoring: stable breach and missing observation | Breach transitions, missing coverage and limits of the supplied policy/history |
| P7-UAT-05 | Events: historical arithmetic and held inference | CAR reconciliation, method/provenance restrictions and no predictive conclusion |
| P7-UAT-06 | News: coverage, duplicates and unavailable tone | Five-record reconciliation, tone calculation, missing score and cutoff explanation |
| P7-UAT-07 | Close: reconcile budget and actual | Exact-cent bridge, cost/profit signs and conditional forecast explanation |
| P7-UAT-08 | Record and revisit review decisions | Exact-scope question, change request, reopen/acknowledgement, retained history and attribution limits |
| P7-UAT-09 | Link a correction and deliberately rerun | Both versions/results, changed fields, explicit request, 13%/87.5m reconciliation and separate review |
| P7-UAT-10 | Navigate complete evidence and reconnect | All five families: keyboard chart selection, exact figure/source, complete copy, original history, reconnect and date-basis explanation |

### 7C — operator checks

| ID | Check | Required evidence |
| --- | --- | --- |
| P7-OPS-01 | Freeze installation and supported configuration | Candidate/source/build/lock/config/input identities, exact environment, clean doctor/build receipts |
| P7-OPS-02 | Verify local access and private delivery | Denied access/cross-origin cases, exposed/changed key and rotation checks, private/no-store delivery and redaction test |
| P7-OPS-03 | Replay a request without duplicate consequence | Same-key replay, changed-body conflict, one attempt/result and concurrent history read during commit |
| P7-OPS-04 | Handle uncertain and stale review saves | Lost response/reconnect retains exact retry; changed/stale writes refuse without loss or redirection |
| P7-OPS-05 | Keep source-use and stale-data holds | Expiry/revocation/tamper refusals for dependent actions and backup; retained history and explicit missing/stale state |
| P7-OPS-06 | Enforce declared input and storage limits | At-bound/one-over cases, queue/evidence capacity and injected write failure; no truncation, partial acceptance or deletion |
| P7-OPS-07 | Recover a complete saved delivery | Two delivery recoveries, attempt one, original receipt and zero financial dispatch/calculation calls |
| P7-OPS-08 | Hold unknown outcomes and inspect close commits | Missing/changed proof refusal; stopped-server/worker/mutator safeguards; explicit committed-versus-no-commit close inspection |
| P7-OPS-09 | Restore complete local evidence into a new copy | Quiescent snapshot, fresh audit before startup, exact history/accounting comparison, rotated key/held queue, corrupt/conflicting restore refusal |
| P7-OPS-10 | Rehearse an isolated update and recovery | Separate candidate/previous installations, injected failure, preserved original evidence and explicit recovery with no automatic activation |
| P7-OPS-11 | Use operational and support guidance | Normal/held/failed/unreadable pages, offline runbook, truthful unknown counts and inspected redacted diagnostic |
| P7-OPS-12 | Measure the exact sequential trial workload | All six identities, timings, baseline/peak/final disk observations and zero-usage proof against declared targets |

### 7D — evidence review

| ID | Check | Required evidence |
| --- | --- | --- |
| P7-REV-01 | Assemble version-bound evidence | Complete current 7B/7C results, expected/actual observations, actor, dates, hashes, limitations and preserved retest history; readiness decision still pending |
| P7-REV-02 | Record the scoped readiness decision | Explicit human decision for the final candidate, residual dependencies, allowed use and suspension conditions |

## Candidate and evidence rules

The planning baseline is `2b8229685dabac6a13376ee1b6d8ed70efd6aaeb` (merged
6D/6E), **not a frozen 7B candidate**. Commit the 7A specification before selecting
the trial build. At 7B setup freeze a clean committed candidate, full source and
frontend-source digests, dependency-lock digest, configuration digest, exact
OS/Python/Node/pnpm versions and input-manifest digest. Retain build/site identity
and installation/doctor receipts as evidence. Complete the OPS-01 freeze
prerequisite before analyst execution; its full acceptance is reviewed in 7C.

The configuration manifest includes enabled features, loopback address, execution
profiles/limits and permission records without credentials. The input manifest
identifies each original and prepared fixture, the research successor, each
transformation, units/periods/source policy, SHA-256 and byte size; append resulting
accepted version/request/result identities to separate evidence without rewriting
the frozen manifest. A source fingerprint identifies bytes, not authenticity or
rights. Retain historical candidate records when fixes require a new commit,
configuration, protocol or inputs; affected checks require retest against the
new candidate. Explain any carried-forward evidence explicitly in 7D.

Use [record.template.json](pilot/record.template.json) and its
[strict schema](pilot/record.schema.json) for a **private local record**, outside
Git. Retain the original blank template in Git. Each check records actual words,
actor role/local label, start/end dates, help needed, outcome, evidence references
and blocking reason where applicable. Append attempts in time order; retain
failed and assisted attempts when retesting. Never put keys, passwords, `.env`,
raw personal diagnostics or real-source content into the public repository.

An analyst must perform and interpret analyst tasks. An operator prepares/runs
controlled technical checks. One person may perform both roles in separate
attempts; this does not establish independent review. The developer may prepare
instructions and supporting engineering evidence, but cannot answer the analyst
questions and record them as that person's unaided result. Reading the task card
and existing runbook is allowed; ad-hoc assistance or intervention is recorded and
requires an unaided retest before a final pass. The earlier deferred interpretation
review remains deferred until applicable 7B answers are actually recorded.

Check the specification/blank record from the repository root:

```bash
.venv/bin/python scripts/check_workspace_pilot_spec.py
```

For a later filled record use `--record /absolute/private/location/record.json`.
Its containing directory must be private (`0700`), and the record/evidence files
private (`0600`). Evidence uses relative `evidence/...` paths, regular files with
no symlinks/hardlinks, per-file size at most 20 MB and unique total evidence at
most 50 MB. These are **evidence-record limits**, separate from application input
or workload capacity. Reference small receipts/reconciliations or hashed manifest
summaries; the complete original reports/workspaces remain separately retained.

The checker is read-only: it validates the 24 IDs, all 26 production mappings,
protocol/schema hashes, candidate completeness, attempt sequencing, claimed actor,
assistance and retained evidence bytes. It rejects premature pass records and
approval flags; validation prints counts, not private observations. A valid file
does **not** prove the observations true, installed bytes match the supplied
candidate hashes, identities are authenticated, past attempts were never deleted,
or required evidence is substantively sufficient. A local operator can edit the
file. Human review of originals, procedures and candidate binding remains required.

The evidence record deliberately cannot grant pilot/financial/production approval.
In 7D a separate explicit human pilot decision must identify the final candidate,
protocol, pre-decision record/evidence manifest hashes, date, actor, allowed scope,
unresolved dependencies, conditions and suspension triggers. First freeze the
pre-decision pack with 7B/7C and REV-01 results, leaving REV-02 explicitly pending.
Then record the human decision, and append its receipt/hash as REV-02 evidence in
a successor record that retains the pre-decision pack. The decision references
that earlier immutable pack, avoiding a circular hash of itself. The final pack
indexes both records and the decision; it cannot silently replace either.
Missing/failed/blocked required checks mean **hold**. A scope reduction requires a revised protocol and new record,
not omission of a failed check. A new major misunderstanding, changed source
rights, uncertain accounting result or loss of evidence suspends use pending review.

## Dependencies preserved

| ID | State and effect |
| --- | --- |
| DEP-BACKUP | Independent encrypted backup deferred: no external drive available. Same-device copies cannot protect against device loss. |
| DEP-KEYS | Independent recovery of backup-unlocking secrets unproven. Keep secrets separate from data; no password/key is requested here. |
| DEP-DR | Clean-machine recovery blocked: only this Mac available. Earlier targets of at most one active working day of data loss and eight staffed hours to recover remain targets, not proven capability. |
| DEP-RIGHTS | Real provider access/retention/processing permissions unresolved, including Yahoo. This synthetic pilot does not authorise them. |
| DEP-FPA | Authorised company budget/actuals and controller acceptance absent; synthetic close only. |
| DEP-NEWS | Representative human-labelled real-news quality evaluation not assessed; no production accuracy claim. |
| DEP-ACCESSIBILITY | Physical touch, screen reader, PDF reconciliation and physical printing remain separately unassessed. Desktop keyboard tasks do not close them. |
| DEP-CAPACITY | Wider capacity and service targets not assessed. This small pilot does not close Production v1's capacity gate. |

The structured production crosswalk includes all **26** existing gate IDs.
Mappings are supporting-only, blocked by external evidence or outside this pilot.
They do not rewrite the [production matrix](../production/v1/acceptance-matrix.md)
or silently waive mandatory gates. In particular, zero paid work does not validate
paid-call limits; local restoration does not pass independent recovery; a synthetic
close does not pass company acceptance; a token-count example does not validate
real-news quality. Earlier component evidence remains linked for traceability.

## 7A completion and the 7B handoff

7A is complete when this scope, expected results, predeclared targets, all 24
checks, all 26 production mappings and eight dependencies are present; the blank
record validates; negative record tests reject stale/incomplete/unsafe claims;
and the read-only planning preview agrees with the files. The preview is an
isolated **plan review**, not a new product screen and never a display of filled
private analyst records. All trial checks remain not assessed.

Next, 7B prepares the committed candidate, frozen fictional inputs and answer-free
task cards, then asks the analyst to use Keystone directly and record actual
answers. No new live source or paid request is necessary. Targeted fixes must be
visible, versioned and retested; no acceptance is inferred from a successful
demonstration alone.

After Batch 7, preserve the agreed repository-navigation/branch/local-storage
organisation milestone. Document/PDF intake remains a distinct six-part programme;
complete all six parts before the [broader backend enhancement programme](post-intake-backend-roadmap.md).
7A moves no files or workspaces and does not start either programme.

### Verification of this preparation

The specification checker reports **24 not assessed**, candidate **unassigned**
and both approval flags **false**. The 50 focused validator tests pass, including
stale fingerprints, incomplete candidates, unknown/duplicate IDs, assisted passes,
changed evidence, unsafe file references and attempted approval promotion. All
24 documented matrix rows match the structured register; 77 local documentation
links across this page, the Batch 6 roadmap and README resolve. The public plan
preview was checked for expansion, keyboard collapse and dependency navigation.
These are checks of the preparation tooling, not passes of the 24 pilot tasks.
