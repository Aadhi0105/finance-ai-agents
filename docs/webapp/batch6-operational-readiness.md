# Webapp Batch 6 — operational readiness

This retains the agreed roadmap following Batch 5's analyst review workflow.
Its objective is dependable installation, operation, updates and recovery for
the declared local pilot. Completing one part is not a production-release claim.

| Part | Scope | Status |
| --- | --- | --- |
| **6A — Operational visibility** | Application checks, job stages/outcomes, failures, capacity and actionable operator diagnostics | [Implemented local scope](batch6a-operational-visibility.md) |
| **6B — Storage and evidence lifecycle** | Full workspace footprint, preserved history, stopped evidence audit, snapshot completeness and explicit no-deletion policy | [Implemented local scope](batch6b-storage-and-evidence.md) |
| **6C — Installation and updates** | Offline staged setup, source/runtime/build identity, compatibility gates and snapshot-copy update/recovery rehearsal | [Implemented local scope](batch6c-installation-and-updates.md) |
| **6D — Access and privacy controls** | Local access, tokens/secrets, private delivery, source permissions and diagnostic redaction review | Planned; existing protections remain in force |
| **6E — Recovery and support** | Interrupted work, restoration, troubleshooting and explicit independent-backup/key/clean-machine requirements | Planned; reuse existing recovery evidence |

Another operator should ultimately be able to follow the supported procedures to
install, run, diagnose and restore Keystone. The unavailable external drive is a
deferred dependency; local restoration does not establish device-loss protection.

Batch 7 then defines the pilot scope and acceptance criteria, runs analyst
usability/interpretation and operational rehearsals, and assembles the evidence
for an explicit release decision. Authorised sources, real-company close data
and disaster recovery remain scope-dependent requirements.

The later six-part document/PDF intake programme retains its own scope. Complete
all six intake parts before starting the [broader backend enhancement programme](post-intake-backend-roadmap.md).
Repository housekeeping and local consolidation remain a later, separately
verified milestone after Batches 5–7; this part moves no existing user workspace.
