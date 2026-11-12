# Post-intake backend enhancement programme

**User decision · 11 November 2026 · Important sequencing commitment.**

The user instructed: “We will implement this right after we finish the all the
6 intake parts.”

Complete all six parts of the agreed document/PDF intake programme first.
Immediately afterwards, begin the broader backend enhancement programme
described below. Keep the earlier agreed development roadmap leading into intake.
Only an explicit user change should alter this ordering.

## Scope to retain

1. **Shared financial-data foundation.** Extend the existing contracts into a
   consistent cross-agent representation of company identity, financial periods,
   currencies, units, measurement definitions, source evidence and revisions.
   Retain conflicting and restated observations with their original context.
2. **Integration of completed document intake.** Build on the six intake parts:
   connect extracted/reviewed figures, document locations and uncertainty to the
   shared data foundation and agent calculations. Preserve the completed intake
   capabilities as the starting point for this programme.
3. **Controlled external-data connections.** Introduce consistent provider
   adapters, source-use checks, freshness policies, normalisation, request limits
   and clear unavailable/conflicting-data outcomes. Yahoo is a possible provider
   connection; provider selection and permitted use remain explicit decisions.
4. **Permanent data storage and recovery management.** Separate working data
   from code checkouts; retain documents, inputs, reports, notes and execution
   evidence through upgrades. Define retention, migration, encryption/key recovery
   and complete restoration. Evaluate a shared operational database when the
   workload warrants it. The user's independent-backup deferral remains in place;
   this decision supplies no independent-device recovery acceptance.
5. **More capable background execution.** Support bounded multi-stage jobs,
   safe checkpoints, cancellation, scheduling and appropriate concurrency.
   Coordinate writes sharing company/accounting state. Preserve duplicate
   protection and inspect uncertain financial commits before further execution.
6. **Deeper analysis and evidence-aware AI.** Expand financial coverage through
   benchmarked capabilities, such as additional currency/fiscal-period support,
   richer peer/consensus inputs and evaluated sensitivity/forecasting methods.
   Use controlled AI for request interpretation, proposed mappings and grounded
   explanations while retaining deterministic financial calculations and review.
7. **Individual identities, permissions and approval authority.** Prepare company
   login, per-person roles and access to particular companies/datasets/actions.
   Bind consequential decisions to verified actors and exact evidence versions.
   Keep local attribution, review dispositions and financial approval distinct.
8. **Operational visibility and repeatable deployment.** Connect execution logs,
   performance measures, source health, storage/backup status and usage evidence.
   Provide tested installation, configuration, data upgrades and rollback for
   each supported enterprise or hosted deployment environment.

## How to apply the sequence

Backend changes necessary to implement an intake part remain within that part's
scope. At completion of intake Part 6, carry forward those implemented foundations
and start the remaining broader backend work as the next major programme.

The architectural starting recommendation is one organised Python backend with
clear internal modules and a background worker. Select storage and execution
technologies against the actual workload and deployment requirements. Detailed
implementation batches and acceptance criteria will be defined for this programme
when it begins.
