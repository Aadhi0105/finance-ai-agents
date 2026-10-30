# Part 2A — native report data layer

30 October 2026. Implemented for **explicitly registered synthetic workspaces**.
The browser still displays the original saved HTML. Native layouts and interactive
charts are the next implementation work; this part supplies their data.

## What is available

The backend prepares five native report views: Agent 1 research, Agent 2 monitoring,
Agent 3 historical events, Agent 3 news, and Agent 4 financial close. Each view has
typed decimal values, units, periods, explicit missing/withheld states, source
pointers, grouped review items and ordered sections. Fixed, source-linked text
templates supply observations; free-form saved model prose is not published.

Agent 1 supplies annual history, diagnostic valuation scenarios and assumptions,
peer multiples, prices, moving averages, common-date rebasing, volatility and
drawdown. External consensus has its own availability and currency checks; it is
separate from historical growth and Keystone's valuation. Named broker reports
and ratings remain explicitly uncollected.

Agent 2 separates original selected-cycle observations from effective state at
export. Actual retained triage histories may supply charts. A current observation
or cycle count never becomes an invented history. Correction references remain
saved local attribution, not authenticated approval.

Agent 3 supplies diagnostic historical CAR observations and original gate evidence.
The event-relative path is explicitly withheld in this first adapter version;
verified timing/session projection remains later work. News coverage, retained
headlines, withheld published tone and diagnostic text scores stay distinct.

Agent 4 supplies exact major-unit amounts, account evidence, a retained budget to
actual bridge, and separate provisional forecast values. Missing interval and
probability values remain null. Accounting reconciliation does not approve a
forecast or verify business causes.

## Prepare and read

From the repository root, create a fresh native workspace from the offline engines:

```bash
.venv/bin/python -m keystone.workspace prepare --native \
  --destination output/workspace-native-demo
```

Alternatively, project an existing **registered synthetic** workspace into a new
destination. This copies only registered originals and prepares presentation data;
it does not rerun the agents or fetch new evidence:

```bash
.venv/bin/python -m keystone.workspace project \
  --workspace output/workspace-demo \
  --destination output/workspace-native-projected
```

Both destinations must be new. The projection destination must be outside the
source workspace. The original workspace remains unchanged. Failure can leave an
unpublished partial destination for inspection; it has no usable catalogue and
must not be reused. Choose a new destination for another attempt.

```bash
.venv/bin/python -m keystone.workspace serve \
  --workspace output/workspace-native-demo --port 8776
```

The native JSON is available at
`http://127.0.0.1:8776/api/runs/research-example/report-view` (GET and HEAD).
The other example run IDs are `monitoring-example`, `events-example`,
`news-example` and `close-example`. This endpoint supplies report data; it is not
the finished reader page. Original registered HTML/JSON/PNG downloads remain available.

Default `prepare` without `--native` still creates catalogue v1. A valid v1 run's
native endpoint returns 409 `native_view_unavailable`; its original files remain
usable. There is no automatic directory scan or in-place migration.

## Registration and delivery

Catalogue v2 preserves original `report_id` and adds an explicit `native_view`
descriptor. Each run registers `native-report.json` plus `native-series.json`.
The descriptor identifies the adapter/version and exactly two source artifacts:
the original agent JSON and the retained derived series. The catalogue records
actual byte lengths and SHA-256 hashes for every file. Publication happens last.

Only the operator prepares derived financial/chart series, using the existing
Python definitions. The series artifact records methods, parameters and source
identities. Delivery validates hashes, schema, bounds, cross references, JSON
pointers and agreement with the closed presentation adapter. Reconstructing a
projection for validation maps saved values and fixed text; it does not recompute
moving averages, volatility, a valuation, a forecast or a waterfall.

A bounded in-memory cache holds at most 64 successful validation markers, not
reports or source data. Its identity includes the complete run registration,
view/source hashes and schema digest. Every delivery re-reads and hashes files;
changed content or registration cannot reuse a previous marker. The browser gets
`Cache-Control: no-store`. A detected invalid registered native view blocks
workspace delivery, including direct file downloads; it does not silently fall
back to an apparently valid native report.

Payload limits include 8 MiB per view, 20 charts, 20,000 aggregate points,
5,000 evidence entries, 500 metrics and 20,000 table cells. Oversized projections
are refused rather than thinned. Some sources reach a tighter collection/evidence
limit before the aggregate point maximum. Unknown metric units are explicit and
cannot carry an available numeric result. Unknown monetary currencies are not
silently filled from another field.

## Verification and limits

Local verification on 30 October 2026, Python 3.11: **1,068 tests passed**,
including 36 new native-report cases. A fresh `prepare --native` workspace at
`output/workspace-native-2a-final` returned HTTP 200 for all five native views.
Generated evidence remains local and ignored by Git. No frontend browser
acceptance or remote CI run is claimed for this backend-only change.

`tests/test_native_reports.py` covers actual offline engine output, v1/v2
compatibility, reprojection, source/value/reference/template tampering, unsupported
versions, symlinks, payload limits, failed publication, exact chart-definition
parity and read-only GET/HEAD delivery. Existing workspace tests cover original
HTML links, confined downloads and the local access boundary.

```bash
.venv/bin/python -m pytest -q tests/test_native_reports.py tests/test_workspace.py
```

Hashes establish consistency with the operator's inventory, not source authenticity
or an authenticated signature. An attacker who can replace the entire trusted
workspace and its inventory is outside this local integrity boundary. The retained
series are trusted operator output bound to saved inputs; HTTP delivery does not
independently rerun their financial calculations.

All five outputs remain synthetic, held for review and financially unapproved.
No live provider/LLM integration, browser execution, authentication, multi-user
storage, approval actions or deployment is added. Backup and source-permission
dependencies remain unchanged. Browser layout, accessibility, print and analyst
interpretation acceptance remain pending.
