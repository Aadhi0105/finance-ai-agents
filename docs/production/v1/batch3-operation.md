# Batch 3 — controlled local operation and release preparation

Implemented 10 October 2026. **Local engineering acceptance; no production release
sign-off.** Independent backup, clean-machine recovery, source-use permission and
real-company Agent 4 acceptance remain dependencies. No database schema migration
is introduced by this batch.

## Operator entry point

Use the repository's Python environment from the repository directory:

```bash
python -m keystone doctor
python -m keystone.operation agent1 --operation-id research-asml-001 -- \
  --offline ASML.AS --output output/pilot-research
python -m keystone inspect-operation research-asml-001
```

An Agent 1 fixture result normally exits 3 (review required). It is not an approved
financial report. The wrapper prints the operation receipt and next action; use
explicit agent output/state paths to find the authoritative report and saved run.
It suppresses child stdout/stderr rather than collecting potentially sensitive
provider messages. Existing per-agent JSON/audits/reports remain the evidence to
inspect; wrapper success alone never establishes financial approval.

Supported entry names: `agent1`, `agent2`, `agent3-events`, `agent3-news`,
`agent3-bundles`, `agent4-close`, `agent4-report`. Everything after `--` is passed
to that agent. Existing argument semantics remain in the individual READMEs.
Agent 2 scheduler/reset modes are refused within this boundary.

## Admission and repeated commands

Normal Agent 1–4 CLI entry points now hold one exclusive mutator lease per checkout,
as well as the shared maintenance gate. Even read/report commands are serialized
conservatively. Snapshot/restore retains exclusive maintenance admission. Busy
commands fail rather than queue indefinitely. Child workers inherit the open lease;
an environment variable alone is not the lease. Never delete lock files to unblock
an active process. New CLI-created files inherit a private umask; existing artifacts
are not recursively permission-changed.

The wrapper requires a unique operator-chosen operation ID. Once allocated, it
cannot run again, regardless of changed arguments, failure, cancellation or crash.
It records a request fingerprint and structured state/output locations, not raw
arguments or prompts. This prevents
repeated submission of the same ID, not semantically equivalent work submitted
under a different ID. Agent cycle/close/version rules remain responsible for
business-level replay and conflicts.

Direct Python APIs, scripts bypassing the gate and other checkouts remain outside
this cooperative boundary. Use one checkout for the supervised pilot. It is not
security isolation against the trusted OS user. Legacy CLI commands participate
in admission but do not gain wrapper operation IDs, deadlines or budget ledgers.
Use the wrapper for the controlled operating scope.

## Paid calls and live data

User selected: paid calls disabled by default; opt-in ceilings of **12 requests,
48,000 reserved output tokens and 600 seconds per operation**. Lower limits are
allowed. Paid calls require `--allow-paid-model`; provider retrieval separately
requires `--allow-live-data`. Neither flag establishes source-use permission.
No rights-dependent live acceptance was run in this batch.

The shared Anthropic adapter reserves each request before network access; it checks
the total request/output allowance, deadline and a 100,000-byte serialized input
limit per request. Output reservations use requested maximum tokens and are never
refunded. SDK automatic retries are disabled. Responses record known input/output
and cache-token usage. A failed/unknown-usage call keeps its reservation and stops
further paid calls in that operation. Restarting with a new ID is an explicit new
allowance, not a daily/account spending limit.

All usage is labelled **unpriced**: these limits are not a currency spending cap,
provider billing reconciliation or a guarantee of known charges after interruption.
An organisation/account budget and pricing policy remain separate if required.
Budget refusals retain a specific reason (disabled calls, deadline, request/output
limit, input size or unresolved usage) alongside counters. No prompt, tool payload,
credential or raw exception is stored in the control log.
Native agent evidence may still contain sensitive financial text; review it before
sharing or backing up. Optional FinBERT is not included in the frozen pilot runtime.

## Cancellation and recovery

The wrapper bounds the worker process group. Deadline, Ctrl-C or SIGTERM terminates
workers and records `outcome_unknown`, preserving the possibility that financial
state committed before delivery. It never automatically repeats a mutation. A killed
supervisor can leave an admitted/running receipt: `inspect-operation` reports that
as unresolved and directs inspection, without trusting a potentially reused PID.
The inherited lease continues to block competing work while a worker holds it.

| Receipt | Operator action |
| --- | --- |
| completed | Inspect agent evidence and financial holds before use |
| review_required / incomplete | Review retained evidence; do not publish as approved |
| unavailable | Inspect saved attempt/bundle, provider failure and freshness; no fixture substitution |
| committed_delivery_failed | Agent 4: recover saved close using its run ID; do not repeat the close |
| failed_inspect_state / outcome_unknown / unresolved | Inspect cycle, close or attempt first; recover saved delivery if committed; decide explicitly whether a new operation is warranted |
| refusal / control failure | Check existing ID, lock, policy and receipt; failure alone does not prove the agent never committed |

Control records live under `state/operations/<operation-id>/`. Include that tree as
role `logs` in the explicit backup inventory, together with all agent evidence and
stores. Losing it loses duplicate-ID history. Restoring an old snapshot rolls back
that history too: reconcile external actions/charges and post-snapshot work before
reusing any identities. Do not delete receipts as a routine retry procedure.

## Frozen installation

`requirements-macos-arm64-py311.lock` pins runtime and test/install tooling with
wheel SHA-256 hashes. Accepted local test environment: Apple Silicon macOS 26.6.1,
CPython 3.11.9. This is a target-specific lock, not a Linux/Intel compatibility promise.
The broad requirements files and existing CI remain development compatibility checks.

On a supported Mac, use a fresh environment outside an existing installation:

```bash
python3.11 -m venv .venv-pilot
.venv-pilot/bin/python -m pip install --require-hashes -r requirements-macos-arm64-py311.lock
.venv-pilot/bin/python -m pip check
.venv-pilot/bin/python -m keystone doctor
```

Doctor reports version mismatches, lock hash, platform, commit/dirty state and selected
local permission checks. It does not inspect secret contents, scan all historical
reports, prove installed package bytes, or certify source rights/network exposure.
The tested fresh environment was installed from downloaded wheels with hash checking
and no package index access during installation. It is still on the same Mac.
Protect/archive the release source, lock and permitted install artifacts separately
before claiming independent recovery; temporary downloaded wheels are not a backup.

## Upgrade and rollback procedure

1. Stop every writer. Record current release/configuration and verify a complete
   pre-upgrade snapshot. Until independent protection is configured, this is only
   a local engineering rehearsal, not an accepted production upgrade procedure.
2. Install the candidate into a separate environment, retain the previous checkout
   and environment, and run doctor. Restore the snapshot into a new candidate state
   directory; do not trial a release on the only authoritative copy.
3. Run agent-specific stored-evidence checks and a controlled synthetic mutation.
   This batch adds operation records and locks, not financial schema changes.
   Any future schema migration needs its own version/refusal and interruption tests.
4. On failure, stop the candidate and restore the pre-upgrade snapshot to another
   new directory. Use the prior code/runtime with restored state. Never assume
   older code can read a database already migrated by newer code. Account for any
   acknowledged work since the snapshot before selecting rollback as authoritative.
5. Retain failure evidence and sign the exact candidate only after applicable gates
   pass. Do not auto-delete the old environment, backup or operation receipts.

The `scripts.check_keystone_upgrade` rehearsal reads a snapshot generated by the
prior release, exercises current stored evidence and a new monitoring cycle, then
restores the original 10-cycle state without overwriting either copy. Existing
storage tests cover interrupted/failed capture and corrupt/conflicting restoration.
There is no new schema migration to claim interruption acceptance for.
