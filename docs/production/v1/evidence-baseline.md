# v1 evidence baseline

Inspected at `1550243`, 5 October 2026. No new financial/model/live acceptance was
run during Batch 1. “Reusable” means useful supporting evidence, not a passed
platform release gate. Locally ignored artifacts cited by old documents have not
been verified as accessible, complete, or backed up during this batch.

| Evidence ID | Existing record | Reuse | Missing or fresh evidence needed |
| --- | --- | --- | --- |
| E01 | [Agent 1 acceptance](../../agent1-v1-acceptance.md), [issuer controls](../../agent1-issuer-and-claims.md) | Calculation/refusal/claim boundaries; selected live cases and ASML filing checks | Candidate dataset matrix, fresh environment/run provenance, complete report usability and recoverable raw evidence |
| E02 | [Agent 2 acceptance](../../agent2-v1-acceptance.md), [live observations](../../agent2-live-observations.md) | Local/MCP monitoring and Stadler FY2025 baseline/duplicate observations | Sustained supervised trial; realistic diagnostic evaluation; source permissions |
| E03 | [Agent 2 correction/retry](../../agent2-review-recovery.md), [HTML](../../agent2-operational-reports.md) | Original/effective histories, decisions, frozen-cycle retry and report controls | Whole-environment restore, moved-path audit association and user acceptance |
| E04 | [Agent 3 closure](../../agent3-closure-validation.md) | Five issuer-dated ASML and five NVIDIA event checks, independent calculations and MCP/replay | Broader data/timing/action boundaries; no claim that validation-only plans are research approvals |
| E05 | [Agent 3 news](../../agent3-live-news-recovery.md), [bundles](../../agent3-batch4.md) | Populated feeds, failure-versus-empty controls, replay/export | Human-labelled quality benchmark, usage rights, full storage restoration; real FinBERT remains excluded |
| E06 | [Agent 4 closure](../../agent4-closure-validation.md), [reports](../../agent4-operational-reports.md) | 14 synthetic closes plus gap case, independent oracle, local/MCP parity and delivery recovery | Authorised real-company pilot; whole-device restore; forecast calibration not established |
| E07 | [CI workflow](../../../.github/workflows/ci.yml), [requirements](../../../requirements.txt) | Existing regression workflow on Python 3.11/3.12; historical latest closure count 930 | Frozen release dependencies, clean macOS installation, release/upgrade/rollback evidence; no current rerun claimed |
| E08 | [Agent manuals](../../../README.md), PR #26 documentation validation | Commands, 117 link checks and offline starter/replay/recovery checks from preceding session | Production operating runbook and independent operator tasks; documentation checks are not financial approval |
| E09 | [Agent 1 execution](../../agent1-execution-reporting.md), [Agent 2 state](../../agent2-state-recovery.md), [Agent 3 execution](../../agent3-batch2.md), [Agent 4 close](../../agent4-close-recovery.md) | Agent-specific checkpoints, locks, versioning and interruption controls | Platform-wide concurrency policy, cancellation/duplicate failure matrix and selected recovery objectives |

## Evidence handling rules

Historical counts/dates remain historical. Reuse tests and oracles, but run the
applicable release checks against an identified candidate. Older batch documents
may describe later work as planned; use their subsequent acceptance records to
interpret current behaviour. Never relabel a former defect as still open without
checking its fix, or relabel a retained limitation as fixed merely because tests pass.

For every future gate, record exact commit, runtime/dependencies, configuration,
model/provider settings, dataset hash/period, procedure, expected and actual result,
limitations and reviewer. Provider snapshots may need protected storage rather than
Git. Missing evidence must be regenerated within permitted scope or marked missing;
an old path printed in a document is insufficient.

The latest PR CI passed before this planning batch. Repository tests do not prove
fresh live availability, financial calibration, external access permissions, or
whole-system recovery. Batch 4 will select independent financial review evidence;
Batch 5 will select human operating acceptance evidence.
