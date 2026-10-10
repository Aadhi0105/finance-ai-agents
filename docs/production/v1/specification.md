# Keystone Production v1 specification

Status: **scope baseline; production release not accepted**. Batch 1 of 5.
Baseline completed: 10 October 2026. Repository inspected at `15502439d6d0527ebb45beadc2431f9dfac0ed80`.
The user authorised proceeding with the supervised local defaults. Recovery targets are selected in D-02; final workload/performance targets, data permissions,
and real-company acceptance remain open where
explicitly identified below. Historical “agent v1” acceptance is not platform
Production v1 acceptance.

## Document map

- [Batch 4 financial acceptance](batch4-financial-acceptance.md): frozen offline cases, independent oracles and pending human review.

- [Batch 3 controlled operation](batch3-operation.md): admission, operation IDs, limits, frozen installation and rollback.

- [Dependency closure preparation](dependency-closure.md): deferred external backup, key recovery and disaster drill.
- [Source-use review](source-use-review.md): preliminary rights evidence and unresolved permissions.

- [Batch 2 local storage implementation](batch2-storage.md): commands, relocation and boundaries.
- [Acceptance matrix](acceptance-matrix.md): mandatory gates and evidence status.
- [Evidence baseline](evidence-baseline.md): reusable history and missing proof.
- [Data contracts and inventory](data-contracts.md): candidate universe and sources.
- [Storage and recovery requirements](storage-and-recovery.md): authoritative records and restore design.
- [Operations runbook outline](operations-runbook.md): procedures still to implement/verify.
- [Release evidence register](release-evidence.md): exact release candidate and sign-off.
- [Delivery plan](delivery-plan.md): Batches 2–5 and dependencies.
- [Decision register](../decisions/0001-production-v1-boundary.md): resolved defaults and open decisions.
- [Project guide](../../../README.md): existing commands and agent operating manuals.

## Product promise

Keystone v1 is a supervised financial-analysis tool for one designated analyst
working locally within declared data and analytical boundaries. It produces
traceable results, exposes missing or uncertain evidence, preserves consequential
state changes, and supports tested restoration after operational failure.

Success means the analyst can run a supported workflow, interpret its restrictions,
trace published figures, recover from specified failures, and retain the original
evidence. A successful process exit does not establish source truth or financial
approval. Review-required results are valid outcomes, not defects to suppress.

## Operating boundary

| Dimension | v1 baseline |
| --- | --- |
| Operator | User as designated analyst; financial review remains explicit |
| Environment | Local macOS; exact OS, hardware, Python and package versions frozen for acceptance |
| Interface | Existing CLIs and generated HTML; no new browser application required |
| Access | Trusted OS account and protected local files; no externally exposed application |
| Initiation | Manual; no promise of scheduled monitoring or delivered notifications |
| Concurrency | Single active supported CLI workflow per checkout; direct API/other-checkout writers excluded |
| State | Existing stores remain baseline; storage technology change requires a recorded decision |
| Paid calls | Wrapper default disables paid calls; opt-in request/output/runtime limits selected in D-04; currency billing unpriced |
| Release unit | Capability-specific acceptance; release manifest lists exactly which agent modes are production accepted |

The specification itself does not implement controls. Batch 2 and Batch 3 add the
scoped local implementations linked above; they do not establish independent backup,
authenticated multi-user approvals or a currency spending cap.

## Released capability candidates

| Capability | Proposed v1 behaviour | Required boundary |
| --- | --- | --- |
| Agent 1 | Analyst-reviewed annual operating-company research, explicit peers, conditional DCF, report and saved rebuild | Compatible listing/share basis/currency; unsuitable valuation withheld; no universal issuer coverage |
| Agent 2 | Manually refreshed annual analyst-policy monitoring, explicit corrections, original/effective views and triage recovery | No contractual covenant claim, live scheduling, notification guarantee or provider backfill |
| Agent 3A | Descriptive historical event studies with reviewed input evidence and honest inference holds | No forward-return forecast; dependence/timing/comparability restrictions preserved |
| Agent 3B | Relevant headline organisation and diagnostic lexical tone, saved replay and HTML | No comprehensive feed or calibrated sentiment claim; FinBERT/stub not production modes in this baseline |
| Agent 4 | EUR/calendar-year amount-based closes, versions, corrections and recovery | Production designation requires authorised real-company pilot; synthetic demonstration remains separately labelled |

The specific issuer/period and data-source inventory in [data contracts](data-contracts.md)
is a candidate acceptance set, not an approved universal release list. Later
periods require fresh source review. An agent's successful historical live run
cannot automatically admit its full sector or provider universe.

## Foundational requirements

A. Data: retain source/period/unit/identity semantics, freshness and review decisions;
resolve permitted access, retention and sharing before releasing the source.

B. Execution: stable attempt/run identity, explicit terminal outcomes, bounded work,
retry/cancellation rules, duplicate protection and a tested single-operator policy.
Existing agent-specific exit codes remain; any common status layer must preserve
financial review versus execution failure versus committed delivery failure.

C. Storage: designate authoritative evidence, create consistent recoverable snapshots,
protect backup access, detect missing/corrupt content, rehearse restoration and define
retention/migration. Recovery objectives are selected in D-02 and remain unverified release requirements.

D. Access: validate local account/file/network boundary and handling of secrets and
sensitive reports. Reviewer text remains attribution, not independent authentication.
Do not send confidential pilot inputs to external models without explicit authority.

E. Releases: freeze reproducible dependencies and configuration, identify code and
model settings, validate clean installation, and test upgrade/recovery compatibility.

F. Operations: provide understandable outcomes, source freshness, usage/cost evidence,
failure diagnosis and manual recovery procedures. No unattended support promise.

## Exclusions

Multi-user collaboration, public hosting, customer tenancy, unattended monitoring,
authenticated multi-person approvals, universal FX/fiscal calendars, ERP integration,
automated trading, calibrated predictive performance, and comprehensive news coverage
are excluded. An excluded capability cannot be advertised as released. A future
scope change must add acceptance rows before implementation is treated as complete.

## Acceptance and accountability

The implementation owner prepares changes and evidence; the designated analyst
accepts usability and financial scope. An authorised controller/data owner is needed
for Agent 4 financial acceptance. These are roles, not claims that external reviewers
have been appointed. Automated checks are not independent human sign-off.

Mandatory shared gates apply to every released capability. Capability gates apply
only to included modes, but excluding a mode requires an explicit release decision
and visible manifest/README labelling. No unanswered target, missing dataset, failed
gate, or unavailable historical artifact is treated as a pass.

Batch 1 can be complete with named open decisions and bounded follow-up work.
Production v1 cannot be released while applicable mandatory gates remain unresolved.
[Release evidence](release-evidence.md) defines the final decision record.
