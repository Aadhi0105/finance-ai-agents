# Agent 2: correction decisions and recovery

Held observations can now be inspected, approved or rejected through explicit
commands. Decisions require a review ID, reviewer name and reason. They are
recorded locally and are not authenticated signatures or a tamper-proof archive.
No existing live observation is approved automatically by installing this change.

## Inspect and decide

Use the database belonging to the monitored watchlist. These commands need neither
a provider connection nor an API key:

```bash
python monitor.py --reviews --db state/stadler-live.duckdb
python monitor.py --review-decisions --db state/stadler-live.duckdb

python monitor.py --approve-review REVIEW_ID --reviewer 'Analyst name' \
  --reason 'Verified corrected observation against source' --db state/stadler-live.duckdb

python monitor.py --reject-review REVIEW_ID --reviewer 'Analyst name' \
  --reason 'Candidate is unsupported; retain prior observation' --db state/stadler-live.duckdb
```

Copy the full review_id from --reviews. It identifies the exact saved hold, not
simply an item whose pending proposal could have changed. Repeating an identical
decision is idempotent. A conflicting decision for an already-decided ID or a
stale/unavailable ID is refused. The recorded decision is not editable through
these commands; a later differing observation creates a new review.

A rejection leaves current values and history unchanged, releases the hold and
suppresses only that exact proposed date/value/definition if it recurs. Coverage
then says rejected_candidate, not compliant. A different candidate is assessed
normally. A live run may still return review exit 3 when it has no accepted new
reading; rejection does not certify freshness or compliance.

## What approval changes

For a corrected value on an existing date, approval replaces that value in the
**effective** history. For a previously unrecorded older date, it inserts the held
observation in reporting-date order. All observations in the affected series are
recalculated with the same threshold, classification and statistical routines as
normal monitoring. The latest reporting date remains the current observation,
regardless of when a backfilled value was received.

The decision saves the complete before and after histories, including diagnostic
payloads. The active history, current state, decision record and hold removal commit
in one transaction under the database lock. A failure or interruption rolls them
all back. Other items are unchanged. Legacy series lacking complete observation
evidence are refused rather than reconstructed without an audit trail.

**Completed cycle results, reports and old model audits remain unchanged.** They
record what the monitor knew at the time. --state reads the effective current
view; --review-decisions explains how it differs from the original reports.
Restated classifications are not silently substituted into old alerts, and no
notification or model call is triggered by approval.

The hold's original candidate remains fixed while pending. Later blocked ticks
are not automatically ingested on approval. A new ordinary refresh resumes from
the effective state. Bulk historical-provider backfill is not implemented.

## Changed definitions

A changed threshold, metric, ticker or other series definition must not rewrite
past covenant terms. Approval therefore requires a new item ID:

```bash
python monitor.py --approve-review REVIEW_ID --replacement-item-id NEW_ITEM_ID \
  --reviewer 'Analyst name' --reason 'Approved revised monitoring definition' \
  --db state/stadler-live.duckdb
```

This creates a new baseline under the approved definition and retires the old
series without deleting its history. Update the watchlist to use NEW_ITEM_ID for
that definition before the next refresh. The command does not edit configuration
files. If the old ID remains in the watchlist, the run reports retired_definition
and does not continue evaluating it. --state explicitly labels retired series.

Approving a monitoring-policy change does not establish a contractual covenant.
Issuer-reconciliation failures, unavailable inputs and stale periods are coverage
failures, not overridable pending corrections. Resolve the provider/reference
problem first; the review workflow does not bypass ingestion validation.

## Retry model triage without another data fetch

```bash
python monitor.py --retry-triage 9 --db state/stadler-live.duckdb
python monitor.py --retry-triage 9 --live --db state/stadler-live.duckdb
```

The first command uses the scripted model. The second explicitly makes paid model
calls and requires the existing API-key configuration. Each invocation creates a
new unique audit; this is an explicit retry/new attempt, not automatic resumption
of a partially completed model conversation. It may be used after a failed,
interrupted or withheld attempt, or to deliberately repeat a completed attempt.
No-surfaced-item cycles require no model call.

New cycles save the exact history used for their surfaced flags. A retry uses
those frozen inputs and the original flags even if corrections have since changed
effective history. Published retry commentary says it concerns original evidence,
not current state. Audit metadata records a digest of the saved cycle and the local
database path. The database lock is released before the model runs. Retries neither
advance the cycle nor fetch provider data, and do not overwrite earlier attempts.

Older cycle records without frozen history can use bounded stored history only
before any review decisions exist. After a decision, such legacy retries are
refused; inspect the original model audit instead. Missing legacy evidence is never
invented. A failed retry exits 2 and preserves the cycle; the prior successful
checkpoint remains available if audit persistence later fails.

## Verification

Tests exercise changed downstream breach classifications, independently checked
OLS drift after restatement, historical insertion, rejection/reappearance, definition
replacement with a live watchlist, stale IDs, required attribution, idempotence,
concurrent approval, transactional rollback after a state write, CLI commands,
original-history retry after correction, model failure and legacy refusal. Tests
use isolated databases; no production review decisions or live API calls are made.

Verification on 29 September 2026: **537 full-suite tests passed**, including
18 recovery tests. The bounded twelve-cycle local/MCP acceptance run also passed
with nine triaged cycles per transport, saved-cycle replay and catch-up. Its local
record is `output/agent2-acceptance/ed5ceedde3b7442fb2419d1b47ce7425/summary.json`.
This batch exercised scripted retry and failure paths; it made no paid model calls.
