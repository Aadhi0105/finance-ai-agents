# Agent 2 batch 2 — durable state and recovery

The cycle ledger is separate from observation history. Every successfully processed
cycle commits a saved result, including cycles with an empty watchlist, missing
values, duplicate data or review-held items. The next automatic cycle advances
from the maximum ledger/history cycle, so stale cycles cannot prevent later fresh
observations from being reached.

## Atomicity and replay

A process lock on the canonical database path covers opening the database, reading
prior state, calculating, rendering the deterministic report, committing and closing.
All cooperating StateStore users use this lock, including state display and model
triage; the reset command uses the same lock. Waits are bounded to ten seconds.
The lock does not coordinate applications that bypass StateStore and open DuckDB
independently, and it is intended for a local filesystem, not distributed storage.

Observation history, current state, full diagnostic payloads, review holds and the
cycle result commit in one transaction. Rendering and strict-JSON serialization
happen before that transaction. Exceptions and KeyboardInterrupt roll back writes;
a killed process releases its OS lock, and DuckDB recovers the uncommitted transaction.
A failure does not claim a successful ledger entry, so retry uses the same next
cycle. Failed-attempt/model execution audit is a separate batch 3 concern.

`run_cycle(asof_cycle=N)` replays a committed N from the ledger without fetching or
recalculating inputs. Its result sets `replayed=true`; CLI replay does not re-run
model triage. A future N performs catch-up and records the gap. A skipped cycle or
pre-ledger cycle without a saved result cannot be replayed. Automatic invocations
allocate successive cycle numbers: two automatic ticks are not duplicates just
because they overlap in wall-clock time. Use an explicit cycle ID for idempotent retry.
A changed watchlist does not change a replayed result; use a new cycle to assess it.

## Observations and corrections

Exact repeated observation values with the same item/date/definition are recorded
as duplicate coverage, not appended again. Changed values for an already-seen date,
older unrecorded observations and changed covenant definitions are quarantined as
review-required. Their candidate and prior evidence are saved in the ledger and a
persistent review queue; history and current state are preserved.

A pending review holds that item on subsequent cycles, including when a newer
observation arrives. Other valid items continue processing. There is deliberately
no automatic rewriting of past observations, reclassification of past alerts or
silent acceptance of a correction. A reviewed replacement definition can begin a
new series under a new item ID, preserving the old series and its audit. In-place
approval/backfill of corrected history is not implemented by this batch.

A conflict reaching the low-level history writer raises instead of silently
ignoring different contents. Threshold/anomaly/drift/probability details are saved
in `observation_details`; `get_observation_evidence` retrieves the detached JSON
payload. `get_run` retrieves the complete cycle result and report. Original tables
remain available to existing consumers.

## Coverage and migration

No-new-observation reports explicitly say compliance was not reassessed. Missing,
duplicate, correction and pending-review reasons are shown separately. Quiet
reports refer only to assessed observations; they do not assert that all covenants
are safe. Baseline/known-stable suppression policies remain unchanged.

Existing databases acquire the ledger/detail/review tables without dropping or
rewriting historical rows. Sequence allocation falls back to legacy history, but
missing legacy diagnostic payloads and cycle reports remain unavailable; they are
not reconstructed or claimed as original evidence. Existing inconsistent legacy
history is not automatically repaired.

## Paths and operation

The default database is `state/monitor.duckdb` under the repository, and the fixture
path is also repository-relative. Explicit relative database paths resolve against
the caller's directory; bare filenames and directories with spaces work.

```bash
python monitor.py --once --db /path/to/monitor.duckdb
python monitor.py --catchup 5 --db /path/to/monitor.duckdb
python monitor.py --state --db /path/to/monitor.duckdb
python monitor.py --cron --db '/path/with spaces/monitor.duckdb'
```

Generated cron commands quote the repository, interpreter and database paths.
The optional `--db` is also honored by sequential and looping modes. No automation
is installed by these changes. Lock files may remain after exit: do not manually
remove a lock file while another process may be using the database.

## Verification

`tests/test_agent2_batch2.py` exercises stale/missing progression, empty watchlists,
explicit replay and catch-up, corrections and definition holds, diagnostic retention,
legacy migration, bare filenames, conflicting duplicates, report failure, exceptions
and interrupts after each write stage, review-queue rollback, a hard process kill,
parallel processes, CLI execution outside the repository and quoted cron paths.
All databases used for verification are temporary; existing monitoring state is
not modified. Model-publication grounding and live-mode honesty remain batch 3.

Verification on 28 September 2026: **25 new recovery tests passed**. Twelve
complete cycles matched between local and MCP execution, including cycles beyond
the fixture's last observation, full ledger round trips and explicit replay.
Local records are retained in `output/agent2-batch2/`.

Full regression suite: **461 passed** on Python 3.11.9.
