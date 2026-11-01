# Part 4B — native financial close

Implemented 1 November 2026 for registered saved synthetic Agent 4 closes.
All five workflow pages now have native readers. Part 4C remains the separate
cross-agent interpretation, accessibility and export acceptance work.

## What the reader shows

The main example reconciles **EUR 60 budget → EUR 10 sales contribution →
EUR −5 cost contribution → EUR 65 actual**. The cost account itself increased
from EUR 40 to EUR 45: its account variance is positive EUR 5, while its effect
on profit is negative EUR 5. Those meanings remain separate.

1. **Close summary:** entity, close period, budget, actual and actual less budget.
2. **Variance bridge:** interactive SVG waterfall using saved amounts, cumulative
   endpoints and favourable/adverse assessments. Hover/tap or keyboard selection
   exposes the exact amount, start, end and assessment. An exact table follows.
3. **Account review:** searchable account amounts and profit effects, materiality,
   diagnostic availability, selected-account limitations and dated prior variances.
   Full hierarchy and original review metadata remain available in a disclosure.
   The root variance graph uses actual saved periods, including the selected close.
4. **Forecast and limitations:** root and account year-end scenarios, target,
   publication state, interval bounds, probability/outcome, remaining periods,
   method, input basis and assumptions. A closed-year result is explicitly
   distinguished from a forward forecast.
5. **Source versions and close history:** source/version labels, caller-supplied
   budget approval, internal reconciliation checks, original submitted actuals
   delta, effective actuals with winning version IDs, selected budget panel and
   excluded historical periods. The bundle's optional supersedes ID is retained;
   a complete related-close inventory is not invented.
6. **Review requirements:** source, accounting and diagnostic restrictions.
7. **Saved evidence:** original files, exact field references, definitions and
   verified downloads.

Materiality is not significance. An unavailable diagnostic is not classified as
insignificant, and persistence is not presented as a verified business cause.
Budget approval is a saved caller assertion, not an authenticated approval.

## Accounting and data boundaries

`agent4-native-report` **1.1.0** extends the retained **1.0.0** recipe. The shared
view schema remains version 1 and the source family remains `agent4.close/1`.
This implementation retains the existing supported EUR/synthetic admission scope.
Fresh preparations use 1.1.0; old 1.0.0 reports remain readable with explicit
absence of the newer source/account metadata.

Operator preparation validates the frozen bundle, canonical claim registry,
accounting identities, source panels, source versions and forecast input basis.
The retained bridge is also bound to the saved tree's exact steps and endpoints
during delivery. A structurally valid replacement series with altered amounts,
endpoints or assessments is refused. Delivery does not invoke the close engine,
forecast engine, provider or model.

All monetary transformations use exact integer cents / 100. The browser positions
supplied endpoints; it does not recompute financial results or favourability.
The scale includes zero, negative anchors and all cumulative endpoints. Zero
movement has zero height. Wider bridges scroll inside a labelled region with
readable step spacing. Exact labels and tables retain source precision even when
an amount is too small to distinguish visually at the full bridge scale.

Held forecasts withhold published figures. Point-only forecasts withhold interval
bounds and probabilities. Available model estimates remain diagnostic and
uncalibrated, with their saved interval level and assumptions. Closed-year equal
bounds describe the realised saved annual amount; the target outcome has no
remaining forecast horizon. A single landing does not create a future monthly
path. No raw saved SVG or free-form model narrative is injected into the page.

## Complete reading copy

The reading copy includes every retained metric, source-panel row, account,
forecast restriction, chart observation and evidence reference independently of
interactive search, account selection or pagination. Its waterfall retains saved
endpoints and the exact table includes amount, start, end and assessment. Original
HTML remains a verified download. Opening or printing the copy rechecks evidence.

Actual PDF pagination/reconciliation, physical printing, browser saved-download
completion, physical touchscreen/screen-reader sessions and human interpretation
acceptance remain open. The controlled checks below do not close those gates.

## Reproduce controlled acceptance

Choose a new destination; existing source workspaces remain unchanged:

```sh
.venv/bin/python scripts/prepare_close_report_qa.py \
  --workspace output/workspace-news-3b-final \
  --destination output/workspace-close-qa-new

cd web
pnpm test
pnpm run build
cd ..

.venv/bin/python -m keystone.workspace serve \
  --workspace output/workspace-close-qa-new --port 8789
```

Open `http://127.0.0.1:8789/#/runs/close-example`. The helper copies registered
originals unchanged and prepares nine additional saved outputs from the real
deterministic fixture engine: original, corrected January actuals, losses, zero
movement, standalone cost, held forecast, populated model interval, closed year
and 32 account lines. The corrected example retains a one-row submitted delta
and twelve effective actual rows; the June actual remains EUR 65 while the
year-end landing changes from EUR 780 to EUR 800. The original remains unchanged.

Fixtures are labelled synthetic. Their local database is disposable; no provider
or paid model is used. The helper refuses overwrite and child/symlink destinations,
verifies source hashes and publishes its catalogue only after validation.
Automated evidence is in `tests/test_native_close.py` and
`web/tests/close-report.test.mjs`, alongside the existing source-binding,
workspace, accounting and chart suites. No dependencies, execution endpoints,
approval controls, database migration or production permissions are introduced.
