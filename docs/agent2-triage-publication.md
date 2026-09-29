# Agent 2 Batch 3: audited triage and controlled publication

Subsequent update: [correction decisions and triage retry](agent2-review-recovery.md)
extend the original milestone described below.

The monitoring cycle commits before optional model triage. Triage receives a
copy of surfaced rows and histories bounded to that cycle, then releases the
state database lock before calling the model. A later cycle cannot contaminate
its tools or recommendations.

## Publication contract

The model may investigate using inspect_item and recheck_flag and return only
`{"item_ids": ["..."]}`. Every surfaced ID must appear exactly once, with no
unknown IDs or additional fields. A single whole-response JSON code fence is
accepted; surrounding prose and duplicate JSON keys are rejected. Invalid output is review_required and is
withheld. Arbitrary prose, invented numbers, and model recommendations never
reach published commentary. Python computes recommendations for all listed
items, places active breaches first, requires breach escalation even with one
diagnostic, and requires verification of significant anomalies. Threshold
recovery is explicitly distinguished from a current breach. Several diagnostics
from one scalar series do not constitute independent evidence.

This deliberately limits model influence to investigation and ordering within
severity groups. It is not a semantic validator for unrestricted model prose.
Baseline and unchanged breaches can remain suppressed by the existing detection
policy; absence of surfaced alerts is not a declaration that all items comply.

## Execution and audit

Each nonempty triage attempt gets a unique directory under output/monitor-triage,
containing model.json. Atomic checkpoints preserve the fixture/model modes,
source cycle, rows, bounded histories, system prompt, goal, tool schemas, model
responses, tool calls, usage, execution outcome, publication decision and final
commentary. Raw model output is audit material, not an approved report.
Checkpoints are required before model calls; persistence errors halt triage.
A crash may leave a pending/running checkpoint, never a published success.
These local files are not a tamper-proof archive or an automatic retry queue.

Offline mode uses a scripted model. `--once --live` and `--catchup N --live` load
the repository .env without overriding existing environment variables and require
a nonempty ANTHROPIC_API_KEY. Missing credentials fail before advancing the CLI
cycle. Both modes use bundled observations, not live market data. `--run` and
`--loop` run deterministic cycles without model triage and reject --live.

Model failure, interruption, truncation or rejected output preserves the already
committed cycle, withholds commentary and exits the CLI with code 2. Audit-write
failure also exits 2; the last successful checkpoint remains available. Explicit
cycle replay does not rerun triage or incur another model call. No automatic
retry or live observation ingestion is introduced in this batch.

## Verification

Regression tests cover hostile or malformed responses, omitted/duplicated IDs,
breach ordering, recovery, model failures and interruption, required audit
persistence, missing credentials, historical cutoff, real cycle date serialization,
and successful database reopening during triage. A paid live model run was
subsequently verified in [Batch 4 acceptance](agent2-v1-acceptance.md).
