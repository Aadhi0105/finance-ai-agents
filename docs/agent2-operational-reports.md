# Agent 2 operational reports

Export a portable, read-only HTML report from an existing monitoring database:

```sh
python monitor.py --db state/stadler-live.duckdb --report output/stadler-monitor.html
```

Select an original saved cycle and, optionally, a custom triage audit directory:

```sh
python monitor.py --db state/stadler-live.duckdb --report output/stadler-cycle-2.html --report-cycle 2 --audit-dir output/monitor-triage
```

Open the resulting HTML file in a browser. It is standalone, with no remote scripts,
fonts, model calls or provider requests. Export again to refresh the snapshot.
The default selects the latest saved cycle. A missing database or requested cycle
is rejected; an initialized empty database produces an explicit empty report.

## Report sections

- Original saved cycle: baseline/gap notices, prominent cycle status, skipped or
  held observations, assessed values and expandable original evidence.
- Current effective state: latest dated observations as of export, including
  retirement status. This is separate from the selected historical cycle.
- Pending corrections: previous/proposed values, observation date, reason and
  review ID. Approval and rejection remain in the existing CLI workflow.
- Decision history: reviewer attribution, reason, effect and expandable before/after
  histories. Original saved reports remain unchanged.
- Triage attempts: failed/completed attempts linked to the selected database and
  original cycle, timestamps, reasons, audit evidence and validated commentary.

Threshold requirements use “At or below” / “At or above”, matching the calculation's
inclusive boundary. Values are rounded for display; exact inputs and diagnostic
availability remain in evidence. Missing probabilities are labelled unavailable.
Live annual data is explicitly described as analyst-policy monitoring, not proof
of contractual covenant compliance. Fixture reports are clearly illustrative.

## Audit association and limits

New normal CLI triage attempts record the resolved database path and a digest of
the original cycle. Explicit retries already record this context. Export includes
only matching audit files from the selected directory. Old unlinked audits or
records from a moved database cannot be safely attributed and are omitted, with
an explicit no-linked-audits message when appropriate. Unreadable JSON audits
produce an incomplete-history notice. A running attempt is not treated as success.
Raw audit details may contain unvalidated model text and are labelled accordingly;
only completed, published commentary appears in the main attempt body.

The exporter uses a read-only database connection under the existing process lock,
and atomically replaces only the chosen HTML output. It does not advance cycles,
change decisions, restate observations, retry triage or migrate legacy schemas.
Use a database initialized by the current monitoring application. The complete
local evidence is embedded in the export; sharing the HTML also shares that evidence.

## Validation

Targeted reporting/recovery/state tests cover preservation of original runs,
approved and rejected corrections, HTML escaping, audit provenance, withheld
commentary, empty/missing databases, cycle selection, CLI export, unavailable
observations and threshold direction. Browser inspection at 1280 and 390 CSS pixels
confirmed contained tables, long-name wrapping, an expandable before/after history
and working navigation to retry history. Tables intentionally scroll within their
sections at narrow widths. This is not a cross-browser accessibility certification.

The illustrative showcase's drift start now consistently reads cycle 7, three
cycles before the cycle-10 breach; its local label explicitly says illustrative.
Scheduling, notifications and interactive browser approvals remain outside this batch.
