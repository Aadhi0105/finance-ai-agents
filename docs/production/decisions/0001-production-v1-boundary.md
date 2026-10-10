# Production v1 decision register

Updated 10 October 2026. User authorised Batch 1 with the proposed supervised-local
defaults, confirmed no authorised Agent 4 dataset, and delegated recovery-target
selection. “Selected” means a requirement decision, not implementation acceptance.

| ID | Decision | Status / rationale | Owner and resolution point |
| --- | --- | --- | --- |
| D-01 | Agent 4 real-company dataset and finance reviewer | Blocked: user confirms dataset not yet available. Keep synthetic validation; do not call it company production acceptance | User/data owner; before V1-A4-001. Explicit partial-release decision if still unavailable |
| D-02 | Recovery targets | Selected by delegated judgement: process/delivery failures preserve acknowledged commits; total device loss may lose ≤ one active working day's changes; RTO ≤ eight staffed hours after incident declaration and supported replacement hardware/backup/keys are available | Implementation measures in Batch 2 and Batch 5; analyst accepts evidence |
| D-03 | Independent backup destination, encryption/key recovery, retention and data rights | User selected local build/test only in Batch 2; independent destination, encryption/keys and retention remain open. No external copy, purchase or automatic expiry authorised | User + implementation; Batch 2 before real protection claim |
| D-04 | Workload, runtime and paid-call budget | Open: choose representative pilot workload and per-run/session limits; record token/unknown-price behaviour; no fabricated numeric cap | Analyst + implementation; Batch 3 before live-model acceptance |
| D-05 | Final issuer/period cases, evaluation sample and tolerances | Open: start from existing candidates, freeze source-resolution tolerances/labelled-set thresholds before evaluation | Financial reviewer + analyst; before Batch 4 measurements |
| D-06 | Exact deployment environment | Selected local macOS/single trusted OS user/CLI plus HTML; exact hardware/OS/Python/dependency identity still open | Implementation + analyst; Batch 3 clean installation |
| D-07 | Concurrency/storage technology | Selected v1 policy: single active mutating workflow, existing stores as baseline; enforcement unimplemented; no immediate database replacement | Implementation; Batch 2 design, Batch 3 conflict tests |

## Recovery tradeoff

Zero data loss on total device destruction would require stronger independent
protection before acknowledging each saved result. For a supervised local pilot,
one active working day's exposure plus end-of-session verified independent backup
is a proportionate initial target. This is not a promise that current local commits
survive device loss. Ordinary process/export failure still must not discard committed
financial state. Define protection-point visibility and failed-backup handling in
[the runbook](../v1/operations-runbook.md).

A working day means an active analyst day, not an unrestricted number of future
sessions: backup after each mutating session and do not continue mutating production
work after a failed required backup without an explicit decision. RTO covers recovery
work once prerequisites are present; report equipment/key acquisition and overall
elapsed downtime separately. No 24/7 SLA or zero-loss claim is implied.

## Change control

Record date, rationale, user direction and affected acceptance IDs when changing a
decision. Requirements cannot be weakened after an observed failure merely to mark
it passed. Source permission, confidentiality and real-company approval cannot be
inferred from possession of a file. Open decisions block only their dependent work.
