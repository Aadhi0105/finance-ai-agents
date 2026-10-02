# Agent 3 Batch 4 — saved evidence, replay and state consistency

## Implemented scope

Both bounded CLIs now seal terminal attempts into `bundle.json` beside the mutable
`run.json` checkpoint. This includes completed, held, refused, unavailable and
failed attempts, including worker deadlines. Argument parsing and errors before
an attempt is created cannot produce an attempt bundle. An unwritable output
filesystem remains a storage error, not a successful archival operation.

Each version 1 bundle retains:

- A unique attempt ID, separate from its input content fingerprint.
- The exact request and normalized event windows or input articles and saved
  scorer responses, plus peer decisions, review plans and available provider evidence.
- Partial stock/index retrievals with timestamps, price bases, benchmark and
  listing timezone, including evidence collected before a later provider failure.
- Terminal status, exclusions, checks, output and stage history.
- Git commit, source-file hashes, Python and relevant package versions captured
  when the attempt starts. Source hashes identify uncommitted code too.
- A SHA-256 checksum over the complete bundle, including its output.

Writes use atomic, exclusive publication. An identical repeat is harmless;
different content at the same path is refused. The API never overwrites a bundle.
These are filesystem artifacts, not signed or externally immutable records. A
filesystem owner can replace one and recompute hashes; integrity is not source
authenticity. Configured environment credentials are redacted before persistence.
Bundle/checkpoint reads have a 100 MB limit and reject duplicate JSON keys and
nonfinite constants. Raw provider snapshots are normalized returned data, not an
archive of the provider's HTTP responses.

## Offline rebuild and export

With the project environment activated:

```bash
python -m agent3.bundles /path/to/bundle.json --output replay.json --html report.html
```

Track A recalculates statistics, controls and publication gates from saved
normalized return windows using the local deterministic tool, regardless of the
original MCP setting. It retains raw price/date snapshots for inspection but does
not rerun provider retrieval or reassemble windows from those snapshots.
Track B reruns ingest, relevance, clustering, score validation, aggregation and
gates using the saved per-cluster scorer responses. It verifies that each saved
score is bound to the rebuilt cluster. It does **not** rerun FinBERT weights, load
an external dictionary, call a model or retrieve articles.

A replay compares its complete analytical result with the saved result. It reports
`matched`, `mismatch` or `not_rebuildable`. Terminal failure restrictions are
reapplied before comparison. No result can become eligible merely by replaying it.
An attempt that ended before sufficient inputs were retained remains auditable but
is not called a successful rebuild. Legacy Batch 2/3 `run.json` files lack these
contracts and are refused; no missing historical evidence is invented.

Replay records also disclose whether current source hashes and runtime versions
match the original. A changed runtime may still reproduce identical outputs;
otherwise comparison fails. The original source tree/environment is not vendored
into the bundle. To reproduce an old environment, restore its code/dependencies.

Exit codes for this command: **0 matched**, **3 incomplete or mismatch**, **2 invalid
bundle or conflicting export**, **5 unexpected replay/export/index failure**.
A matched held/refused run returns 0 for successful verification, not analytical
publication. The original status remains prominent in the output.

The optional HTML is a separate real-run report using the same gate-aware renderers
as the CLI. It escapes evidence text, displays IDs/hashes/status, and invents no
daily CAAR series or return probabilities. Mismatched replay blocks HTML export;
incomplete evidence allows only a status report. JSON and HTML output files are
write-once. Keep the bundle with exports if someone needs to verify them later.

## DuckDB history and recovery

Outcomes preserve nullable significance: `true`, `false`, and unknown are distinct.
History includes pinned peers, inference state, evidence availability and any
indexed terminal bundle status. Reusing a run ID with changed study, gate or peers
raises a conflict. Identical repeats leave the original timestamp intact. Existing
summary-only rows remain readable and labelled `legacy_summary_only`; their absent
inference state is `unknown`. They cannot silently acquire replacement evidence.

The parent process indexes the sealed bundle after worker completion. A separate
`index-receipt.json` records success or the safe error class. If the database is
locked or unavailable, the bundle survives and the CLI reports that indexing is
pending. Recover the index explicitly:

```bash
python -m agent3.bundles /path/to/bundle.json --index-db state/catalyst.duckdb
```

Indexing checks identity conflicts and compares any existing outcome summary with
the terminal bundle. It labels missing summaries, legacy summaries, matches and
summary conflicts/terminal failures. It never rewrites a summary to hide a failed
attempt. This also covers interruption after the worker committed its summary but
before it finished. `CatalystStore.bundles()` exposes indexed runs for both tracks;
`outcomes_for()` exposes Track A summary history. Recovery rebuilds the index, not
missing summary rows. Retain the bundle files: a database index is not a backup.

Calendar states are limited to `upcoming`, `occurred` and `cancelled`. Missing IDs
raise errors. Normal transitions from upcoming are permitted; changing an identity
or date, or correcting a terminal state, requires an explicit reason. Every change
atomically appends a before/after revision. Repeated identical writes add no
revision. Older calendar rows acquire a recorded before-state at their next change;
unknown earlier history is not invented. This is a local state API, not a scheduler
or a provider calendar ingestion service.

## Showcase and remaining limits

The static showcase now states visibly that **all embedded panels are illustrative
placeholders**. Its Agent 3 chart is labelled as an illustrative drawing, and the
panel publishes no forward scenario. The about page no longer claims these are
real reproducible runs. Actual exported HTML reports stay separate from the demo;
no automatic manifest collector is claimed.

Batch 4 does not establish that Agent 3 is complete for arbitrary companies.
Issuer-checked event dates, US/non-US live acceptance, the unresolved ASML target
assembly, a populated live news feed and actual FinBERT weights remain closure
work. Human peer comparability review, exchange calendar limitations, document-tone
scope and the existing statistical restrictions still apply. No combined Track A/B
report, scheduling or notification delivery is implemented.

## Verification

Batch 4 regressions cover offline replay of both tracks; held, failed, unavailable
and refused attempts; news duplicates/corrections/exclusions; saved scorer failures;
changed inputs and output; write conflicts; HTML escaping; legacy database migration;
tri-state significance; calendar corrections; partial provider evidence; deadline
archival; database recovery; and a real bounded CLI fixture-to-bundle-to-HTML flow.
The previous Batch 1–3 tests are retained. Final local verification on 2026-10-02:

- **726 tests passed in 81.17 seconds**, Python 3.11.9, including 40 Batch 4 regressions.
- Manual event fixture → sealed bundle → matched replay → held HTML report.
- Manual news fixture through the actual bounded CLI → bundle/index → matched
  replay → held HTML report. This check caught and fixed equivalent UTC `Z` versus
  `+00:00` formatting during replay; the CLI regression now uses `Z`.
- Showcase JavaScript syntax and repository whitespace checks passed.
- Browser preview was blocked by the in-app browser's local-file URL policy;
  visual layout is unverified. HTML escaping and held/publication behavior were
  tested without browser access.

Local verification artifacts are under `output/agent3-batch4-verification/`
(ignored by Git). These are fixtures, not live company validation. Live
provider/model acceptance is not inferred from these deterministic tests.
