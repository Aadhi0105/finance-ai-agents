# Agent 4 Batch 4 — saved operational reports and browser acceptance

Implemented 5 October 2026. This batch addresses the waterfall and report-delivery
scope of audit A22–A24 and remaining A16 presentation work. It does not complete the
separate controlled close-sequence acceptance or establish forecast calibration.

## Create or recover a report

Run a synthetic example from the repository root:

```bash
python -m agent4.close --input fixtures/agent4/close-june.json \
  --db state/agent4-report-demo.duckdb --output-dir output/agent4-report-demo --html
```

Export HTML from an existing committed close, without recalculating its statistics:

```bash
python -m agent4.report --db state/agent4-report-demo.duckdb \
  --run-id close-june --output-dir output/agent4-report-demo
```

The command returns the absolute `html_path`. Open that file directly in a browser;
no server, JavaScript, internet connection, provider, or model is required. Keep the
whole `reports-<fingerprint>/` folder when copying a report: it contains related
close pages, their JSON evidence and a file-hash manifest. Reports contain financial
inputs; decide who should receive the folder before sharing it.

`agent4.close --html` preserves the existing 0/2/3 exit conventions: a failed HTML
export after accounting commit reports `committed_delivery_failed` and can be
retried. The separate report command exits 0 on successful delivery and 2 on failure.
It refuses a missing database rather than creating a misleading empty state file.
Use `--recover` for older saved requests; changing the demo's new `data_kind` field
under an existing run ID is correctly treated as a request conflict.

## Report contents

- Company, close date, currency, frequency, run ID and clearly scoped check status.
- Close budget, actual and variance; an exact waterfall with a numeric table.
- Review-priority coverage, including material lines with unavailable significance.
- Root and account forecasts with target, direction, remaining horizon, available
  range, probability type and assumptions. Held forecasts publish their reason,
  with no invented landing or probability. No saved forecast is a separate state.
- Expandable account claims, prior observations, diagnostic limitations and references.
- Budget/actual source labels and version IDs, completeness, history budget basis,
  excluded periods, and an evidence download.
- Separate **original submitted actuals delta** and **effective actuals used** tables.
  Restated values retain their winning source-version identity.
- Close/forecast history with selected-run indication, correction links and the
  budget/actual basis for every row. Related reports are exported together, so the
  navigation never relies on an unexported sibling file.

`data_kind: synthetic` is explicit provenance supplied in the request; otherwise the
report says source authenticity is unverified. Only `synthetic` and `unverified` are
accepted. The input's budget approval remains a caller assertion. Passing internal
accounting and canonical-claim checks does not authenticate a ledger, prove business
causation or establish a calibrated forecast.

## Waterfall corrections

The renderer validates the supplied result tree and asserts that budget plus every
step equals actual. Bounds include zero and every cumulative endpoint. Loss-making
anchors and sign crossings stay inside the viewBox. Zero changes use a line rather
than a fictitious minimum-size amount bar.

Internal steps use each child's signed variance **in the displayed node's units**.
This is important for cost roots: an increased cost moves the amount upwards but is
coloured adverse. Leaf charts use their actual driver values, including a nonzero
rounding residual exactly once. Internal residuals are refused because the child
steps already own them. Dimensions are validated before rendering.

Charts include an accessible title/description. Numbered steps map to full account
names and exact amounts, cumulative endpoints and favourable/adverse labels in the
table. The chart keeps a 13px text size and a readable minimum slot width. Narrow
screens scroll chart/table regions instead of shrinking the SVG to unreadable text.
Long names wrap in tables and account headings. Regions and disclosures support
keyboard interaction and visible focus.

## Saved-evidence publication boundary

The renderer checks bundle/request hashes, schema and run identity, result-tree
accounting, registry consistency and canonical commentary. It reconciles displayed
close totals, prior histories and forecast inputs to the frozen source panels.
Contradictory evidence is refused; it does not create an apparently successful HTML
report. It never executes a saved SVG: it builds a new validated chart from saved
numbers and escapes all source text. A restrictive content policy blocks scripts
and external resources.

Statistical diagnostics and projections are retained from the saved close, not
recomputed using today's engine. The HTML is a derivative view and may change when
the renderer changes; the original JSON bundle remains unchanged. Local digests are
integrity checks, not authenticated signatures against an actor replacing all data.

The export includes every saved close for the selected entity at export time. That
set is a navigation snapshot, not a claim that an original report used later data.
Each snapshot has its own content-derived directory. Export stages and fsyncs all
files before atomically renaming the directory. Existing identical exports replay;
conflicts are refused. Failed delivery records and later retries preserve committed
financial state. This local exporter uses POSIX file locking, as does Batch 3.

## Acceptance evidence

`python scripts/check_agent4_reports.py` generates an isolated synthetic database and
linked browser gallery. Cases include an original/corrected close, losses, 24 long
account names, a held account forecast, an eligible uncertainty range, zero movement,
a standalone cost account, and empty/held/error presentation states. The last three
are explicit renderer previews, not fabricated successful closes; invalid CLI inputs
still fail closed with a structured error.

Browser checks used the Codex in-app browser at measured **1280×900** and **390×844**
viewports. The narrow pages measured 390px document width; chart text remained 13px
and scrolled inside its container. The loss bridge stayed visible. Keyboard chart
scrolling, account disclosure and original/corrected navigation worked. The original
forecast remained €780 and the corrected forecast €800. Uncertainty showed an 80%
range with an uncalibrated probability label; held/unavailable values remained clear.

Automated regressions cover loss/crossing/zero/large-offset geometry, leaf residuals,
cost-root signs, invalid inputs, escaping, source/registry contradictions, version
navigation, failed delivery/recovery, conflicting exports and both CLI paths. Validation completed on 5 October 2026: **926 repository tests passed**, including
**30 new Batch 4 cases**. After the final table-label and export-manifest polish,
the 30 Batch 4 cases passed again. The reviewed browser console reported no errors.
Generated gallery, evidence bundles and screenshots are retained locally under
`output/agent4-batch4/` (not committed). Desktop and narrow captures are
`report-desktop.jpg` and `report-narrow.jpg`; measured browser observations are in
`browser-checks.json`.

The showcase now describes Agent 4's separate saved reports accurately. It does not
embed a synthetic run into the existing illustrative showcase or imply live data.

## Remaining work

The next acceptance task is the controlled, independently reconciled close sequence
from the audit: initial budget, multiple closes, one-off and persistent changes,
missing/late input, restatement, formal re-budget, year-end and delivery retry.
Real internal-company validation requires an authorized dataset if one is available.
Forecast calibration, ERP connections, scheduling, fiscal calendars and interactive
approval services remain outside this batch. Browser checks are bounded acceptance,
not a formal accessibility certification or exhaustive cross-browser test.
