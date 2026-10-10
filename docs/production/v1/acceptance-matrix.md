# Production v1 acceptance matrix

Baseline completed 10 October 2026; Batch 2 local evidence recorded in
[storage implementation](batch2-storage.md). **No production gate is marked passed by this
planning batch.** Existing agent acceptance is supporting evidence only.
[Specification](specification.md) · [Evidence inventory](evidence-baseline.md) ·
[Decision register](../decisions/0001-production-v1-boundary.md).

## Rules and responsibilities

M = mandatory for every released capability. C = mandatory when that capability
is included. Deferred capabilities must be explicitly excluded in the release
manifest, not silently waived. Status vocabulary: not assessed, in progress,
passed, failed, blocked, deferred. Below, not assessed means the complete
Production v1 gate has not yet been executed, even if component tests exist.

Implementation owner prepares evidence; analyst accepts scope/usability; an
authorised finance reviewer accepts source reconciliation and Agent 4 company
results. Roles are not claims of appointed external reviewers. Each final result
must include candidate commit/runtime/configuration, data identity, procedure,
expected/actual result, evidence location, reviewer and residual limitations.
Until then release/environment = **unassigned**, sign-off = **none** for every row.

## Shared gates

| ID | Priority / batch | Requirement and acceptance procedure | Pass condition | Existing evidence / owner | Status |
| --- | --- | --- | --- | --- | --- |
| V1-DAT-001 | M / 2 | Inventory access, retention, model processing and sharing permissions for every released source | Documented permitted use; unresolved sources excluded from release | [Data inventory](data-contracts.md), [rights review](source-use-review.md); analyst | blocked |
| V1-DAT-002 | M / 2,4 | Exercise missing/stale inputs, incompatible units/currency/periods, changed definitions and source failures | Explicit refusal/hold; no silent substitution or apparently current result | E01,E02,E04,E05; implementation + financial reviewer | in progress |
| V1-DAT-003 | M / 2 | Trace normalized values to retained input and transformation version | Required provenance complete or explicitly unknown; source-specific tolerances declared before tests | E01–E06; implementation | in progress |
| V1-EXE-001 | M / 3 | Repeat submissions and attempt conflicting writes under the selected concurrency policy | No duplicate consequential state; conflict/replay rules visible; single mutator enforced | E09,E10; implementation | in progress |
| V1-EXE-002 | M / 3 | Interrupt/cancel at model, provider, persistence and delivery boundaries | Known terminal/recoverable state; no unexplained commit or silent refresh on recovery | E09,E10; implementation | in progress |
| V1-EXE-003 | C: live models / 3 | Configure limits; simulate exhausted budget, stalled requests and retry | No new paid work beyond configured admission limits; usage/unpriced usage visible; bounded execution | E09,E10 + D-04; implementation + analyst | in progress |
| V1-STO-001 | M / 2 | Snapshot all authoritative records and companions under maintenance boundary; inject failed capture | Consistent verified manifest; incomplete snapshot never replaces previous good backup | [Storage design](storage-and-recovery.md); implementation | in progress |
| V1-STO-002 | M / 2,5 | Restore on clean supported environment from independent copy without original state | All agent checks in storage design pass; RPO ≤ one active working day, RTO ≤ eight staffed hours under D-02 | E03,E05,E06 only support local recovery; implementation + analyst | in progress |
| V1-STO-003 | M / 2 | Delete/corrupt a snapshot member and restore to a conflicting destination | Missing/corrupt content detected; no silent overwrite; secrets and keys handled separately | Implementation | in progress |
| V1-STO-004 | M / 2,3 | Exercise relocated Agent 2 audits and Agent 3 calendar/index history | Complete evidence associations preserved through documented identity/path strategy | E03,E05; implementation | in progress |
| V1-ACC-001 | M / 3 | Inspect deployed account/file permissions and network exposure; test denied access | Trusted-user boundary matches specification; no unintended remotely exposed application | Implementation + analyst | in progress |
| V1-ACC-002 | M / 3 | Inspect inputs, logs, reports, backups and decision records with seeded secret/adversarial content | No tested secret leakage or executable report content; decisions bind exact reviewed evidence; attribution limits clear | E01,E03,E05,E06 partial; implementation | in progress |
| V1-REL-001 | M / 3 | Install frozen release on clean supported macOS environment and run smoke checks | Reproducible dependency/configuration identity; expected outcomes for every included mode | E07,E10; implementation | in progress |
| V1-REL-002 | M / 3 | Upgrade representative prior state; interrupt migration; execute rollback/recovery | Original evidence retained; explicit compatibility/refusal; usable documented recovery | E09,E10 partial; implementation | in progress |
| V1-OPS-001 | M / 3 | Demonstrate provider failure, stale data, financial hold, model failure, committed delivery failure and backup failure | Distinct actionable statuses, run IDs and operator instructions; no misleading success | E09; implementation + analyst | in progress |
| V1-OPS-002 | M / 3,5 | Measure duration, disk growth and usage on declared pilot workload | Meets workload/runtime/storage limits selected in D-04/D-06; no unsupported capacity claim | Implementation + analyst | blocked |
| V1-UAT-001 | M / 5 | Analyst runs each included workflow, interprets hold, retrieves old evidence and recovers export using runbook | Tasks completed without developer intervention; misunderstandings resolved and retested | E08 supports instructions only; analyst | not assessed |
| V1-REL-003 | M / 5 | Review candidate manifest and applicable gate evidence | Every applicable gate passed; scope/deferred modes visible; analyst signs exact candidate | [Release register](release-evidence.md); analyst | not assessed |

## Agent capability gates

| ID | Priority / batch | Requirement and procedure | Pass condition | Existing evidence / owner | Status |
| --- | --- | --- | --- | --- | --- |
| V1-A1-001 | C: Agent 1 / 4 | Reconcile selected issuer/period matrix against filings and independent calculations | Source-resolution tolerances met; negative/missing/sector cases held correctly; share/currency assumptions reviewed | E01, D-05; financial reviewer | in progress |
| V1-A1-002 | C: Agent 1 / 4 | Inspect desktop/narrow/print output, rebuild and adversarial draft cases | Financial statements remain traceable; unsupported claims withheld; no loss of required evidence through layout | E01,E08; analyst + implementation | in progress |
| V1-A2-001 | C: Agent 2 / 4 | Supervised trial with unchanged/new/stale observations, correction, rejection and restart | Original/effective state preserved; baseline breaches visible; no false compliance/freshness claim | E02,E03, D-05; analyst + financial reviewer | in progress |
| V1-A2-002 | C: Agent 2 / 4 | Independently check diagnostic history and evaluated alert cases | Arithmetic matches; limits explicit; no calibrated-risk claim without separate evidence | E02; financial reviewer | in progress |
| V1-A3-001 | C: events / 4 | Independently verify dates, sessions, return bases/windows and dependence refusals | Arithmetic reconciles; uncertain design cannot become approved inference; descriptive scope preserved | E04; financial reviewer | in progress |
| V1-A3-002 | C: news / 4 | Evaluate frozen labelled relevance/dedup/freshness set and failure-versus-empty cases | Meets predeclared D-05 thresholds; held tone and replay limits preserved | E05; analyst + implementation | blocked |
| V1-A4-001 | C: Agent 4 production / 4 | Reproduce authorised company closes, correction and budget revision against approved controls | Exact-cent arithmetic and agreed source mapping reconcile; controller accepts results and boundaries | E06 synthetic only; authorised finance reviewer | blocked |
| V1-A4-002 | C: Agent 4 / 4 | Validate version conflicts, late correction, failed delivery and restored report history | No lost original evidence; effective lineage correct; identical saved JSON where promised; HTML derivative limits visible | E06; implementation + financial reviewer | in progress |

E01–E11 are defined in [evidence baseline](evidence-baseline.md). D-01–D-07 are
[decisions](../decisions/0001-production-v1-boundary.md). Blocked rows identify
concrete unresolved inputs, not a reason to stop unrelated foundation work.

## Deferred scope

FinBERT production scoring/calibration, automated alerts/scheduling, multiple users,
remote hosting, ERP integration, authenticated multi-person approvals, alternative
currencies/fiscal calendars and predictive return claims have no v1 acceptance
claim. Agent 4 remains a release dependency, not automatically removed from v1;
any partial release requires an explicit scope decision at V1-REL-003.

Batch 2 status note: local fixture tests and restoration support the in-progress
storage rows. No independent destination or clean-machine recovery has been tested;
no source-use permission has been approved. Passing inventory validation is not
financial/data-rights approval. Runtime guard coverage is cooperative CLI maintenance,
not complete V1-EXE single-mutator admission.

Dependency preparation on 10 October: user deferred independent backup after the
supplied folder was identified as internal storage. Key recovery is untested; only
this Mac is available. [Prepared procedures](dependency-closure.md) do not advance
storage gates or resolve V1-DAT-001.

Batch 3 status: [controlled operation](batch3-operation.md) provides local evidence
for admission, explicit duplicate IDs, cancellation, usage limits, private control
records and same-Mac frozen installation/rollback. D-04 usage limits were selected
by the user. Final candidate sign-off, permission-scoped live checks, deployment
review and full workload/capacity acceptance remain outstanding; no gate is passed.

Batch 4 [bounded offline evaluation](batch4-financial-acceptance.md), E11, supports
financial and data rows marked in progress. It does not pass production gates.
V1-A3-002 remains blocked on human-labelled representative quality evaluation;
V1-A4-001 remains blocked on authorised company data/controller review. Retained
issuer/event evidence is not fresh source verification or approval of wider coverage.
