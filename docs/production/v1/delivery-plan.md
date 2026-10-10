# Production v1 delivery plan

[Specification](specification.md) · [Acceptance matrix](acceptance-matrix.md).
Foundation work applies across agents; each agent receives separate capability
acceptance. No autonomous deployment, paid-service purchase or private-data transfer
is authorised by this plan.

| Batch | Work | Deliverables / completion evidence | Dependencies |
| --- | --- | --- | --- |
| 1 — Scope and evidence baseline | Establish single-analyst boundary, candidates, gates, source/state inventory and decisions | This documentation package, validated references, explicit open dependencies; completed 10 October 2026 | User defaults and recovery preference incorporated |
| 2 — Data and durable storage | Resolve source-use evidence; define portable workspace/manifest; implement consistent snapshots, independent protection, restore and retention policy | V1-DAT-001/003 and V1-STO-001/003/004 evidence; first full V1-STO-002 rehearsal; invalid-input contract cases | D-03 destination/keys/retention; source rights. No blind live DB copies or automatic retention deletion |
| 3 — Controlled operation and release | Enforce mutator policy, cancellation/duplicate rules, cost limits, safe logs/access, frozen installation, migration/rollback, actual runbook | V1-EXE, V1-ACC, V1-REL-001/002, V1-OPS evidence on supported macOS | Storage design, D-04 workload/cost, D-06 hardware; clarify target before claiming performance |
| 4 — Agent financial/data acceptance | Freeze evaluation cases and tolerances; run issuer checks, monitoring trial, event/news benchmark and authorised FP&A pilot | V1-A1 through V1-A4 evidence and V1-DAT-002; independent expected values; remaining holds explicitly retained | D-05 benchmark design; D-01 company data/controller; permitted sources |
| 5 — Supervised pilot and release | Designated analyst completes run/review/recovery tasks; clean restore and release installation rehearsal; final gate review | V1-UAT-001, final V1-STO-002, V1-OPS-002, V1-REL-003 and signed release manifest | Applicable gates passed; explicit decision if any capability remains excluded |

## Batch 2 starting order

1. Inspect actual persistent paths and confidential-data boundaries without opening
   secrets; define manifest coverage and backup consistency invariants.
2. Select an independent backup destination and key-recovery procedure with the user.
   Build local disposable snapshot tests meanwhile; do not call them disaster recovery.
3. Resolve Agent 2 moved-path audit association and Agent 3 calendar/index preservation.
4. Implement quiesced snapshot/verification and safe empty-destination restore.
5. Inject missing/corrupt member, disk/delivery failure and interrupted capture cases.
6. Rehearse restored agent invariants and measure RPO/RTO against D-02.
7. Freeze retention/source policies before enabling any deletion or distributed copy.

Source-permission work can proceed alongside storage design. Rights-dependent live
checks wait for permission evidence. Agent 4's missing dataset does not block fixture
storage/recovery work, but it does block its real-company production designation.

## v2/v3 transition discipline

Preserve stable run/entity identities, versioned schemas, evidence boundaries and
agent-specific recovery semantics now. Do not build speculative tenancy or distributed
workers into v1. Before v2, reconsider writer concurrency, backend-enforced access,
authenticated approvals and job ownership. Before v3, separately accept tenant
isolation, entitlements, capacity, service commitments and customer support.

## Batch 2 progress — 10 October 2026

The user selected local-only implementation and testing, with independent destination
selection deferred. [Local inventory, snapshot and restore tooling](batch2-storage.md)
is implemented, including Agent 2 audit-origin preservation and Agent 3 index-path
relocation with original evidence retained. Local rehearsal is supporting evidence;
V1-DAT-001 and independent-device V1-STO-002 remain open. Do not label all Batch 2
release conditions passed merely because its local implementation tests succeed.

## Batch 3 local implementation — 10 October 2026

[Controlled-operation guide](batch3-operation.md) documents the supervised wrapper,
checkout-wide CLI lease, durable operation IDs, selected usage/deadline limits, safe
control receipts, diagnostics, hash-pinned local installation and additive upgrade/
rollback rehearsal. Production gates remain in progress; independent protection,
source approval and final release/capacity acceptance are not silently waived.

## Batch 4 bounded offline evaluation — 10 October 2026

[Financial acceptance](batch4-financial-acceptance.md) freezes retained-source and
synthetic cases, independent calculation tolerances and explicit negative outcomes.
Human news labels, source permissions, company FP&A data and financial reviewer
sign-off remain dependencies. Engineering evidence can be completed without falsely
claiming those release conditions are satisfied.
