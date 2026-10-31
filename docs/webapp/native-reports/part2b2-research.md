# Part 2B.2 — Agent 1 supporting analysis

Implemented 31 October 2026 for registered saved synthetic workspaces. This
extends [Part 2B.1](part2b1-reader.md) with native supporting sections inside the
existing Keystone shell. [Part 2C](part2c-charts.md) subsequently adds interactive plots.

## Delivered sections

| Section | What the reader can inspect |
| --- | --- |
| Business performance | Saved financial measures, annual revenue and margin history, exact values and financial periods |
| Valuation and assumptions | Diagnostic scenarios, weighted per-share value, separate unlevered FCFF input, saved growth/discount assumptions and their source, enterprise-to-equity bridge and model basis |
| Peer comparison | Saved P/E screening, target/included/excluded roles, financial periods, quote observation dates, quote currency and restrictions |
| Saved market context | Dated quote, benchmark and history basis; saved price/moving-average, common-date rebased, volatility and drawdown numerical tables |
| Market consensus | External estimates with provider period and known analyst coverage, or an explicit unavailable/withheld state |
| External research | Explicit broker-report/rating availability; no invented recommendations or documents |

Every financial table uses the backend's decimal strings and source references.
Long tables have 25-row pages with a total count and previous/next controls; no
saved point is discarded. Source inspection includes exact point values and
missing warmup observations. Table regions can scroll horizontally within the
page and have captions and row/column headings. Mobile section selection uses a
labelled selector and an explicit Go action. Local review links open the relevant
saved review groups and preserve their original findings. Methodology and plain
definitions remain available under evidence.

This is presentation of saved analysis. It does not generate an investment thesis,
broker recommendation or fresh market observation. Scenario weights are stated
assumptions, not estimated probabilities. Reported free cash flow and the model's
FCFF input retain their distinct definitions. Missing consensus is not filled by
DCF or historical growth. Invalid/nonpositive supplied analyst coverage withholds
the associated estimate. Unknown counts remain unknown.

## Versioned saved-data extension

Research adapter **1.1.0** adds the saved bridge, model basis, peer metadata, quote
and consensus coverage through the existing report schema. It performs no new
financial calculation. Invalid/missing equity bridges or incompatible valuation
currency withhold every equity-value representation, including the earlier
weighted figure and scenario series.

Research adapter **1.0.0** remains supported using its original projection recipe.
Opening an existing workspace does not upgrade or write it. The reader explicitly
identifies richer bridge/peer/quote detail absent from that older presentation.
Other workflow adapters remain unchanged. Reprojection into a fresh destination
is required to gain 1.1 detail:

```bash
.venv/bin/python -m keystone.workspace project \
  --workspace output/workspace-reader-2b1 \
  --destination output/workspace-reader-2b2
.venv/bin/python -m keystone.workspace serve \
  --workspace output/workspace-reader-2b2 --port 8778
```

The example source path must already contain a registered synthetic workspace.
Alternatively use `prepare --native --destination` with an unused destination.
Build the frontend as described in the [frontend guide](../../../web/README.md).
Open `http://127.0.0.1:8778/#/runs/research-example` for the local preview.

The client validates the full analysis fields it uses: chart points and axes,
table columns/cells, references, section/analyst areas, missing states and diagnostic
labels. Unsupported broker-document availability is refused because this format
does not carry broker documents. The backend remains the financial/source authority.
All earlier fresh-read, hash/size download checks and changed-evidence refusal
behaviour remain in place.

## Verification and limits

- Full Python suite: **1,081 passed**, including 12 new adapter cases covering
  saved bridge amounts, conditional equity eligibility, peer metadata, valid and
  invalid analyst counts, and old/new research adapter compatibility.
- **38 frontend boundary tests passed**, covering both adapter versions, financial formatting,
  chart/table references, retained point unions, null versus zero, diagnostic
  restrictions, estimate attribution and evidence delivery. The implementation
  record also includes a successful TypeScript check and production build.
- Browser review used the full registered synthetic workspace: all supporting
  sections loaded with no report iframe; valuation, peer periods/currencies and
  quote dates matched the saved record. Price-table pagination advanced from
  rows 1–25 to 26–50 of 252. Point evidence displayed the exact `567.6766` value
  and null moving-average inputs. Returning restored focus to its Source control.
  Local valuation review links opened the related review groups.
- Desktop layout and 390px/320px widths were inspected. Mobile Go moved focus to
  the chosen section; wide tables remained contained and the outer page had no
  horizontal overflow. The inspected browser reported no warning/error logs.

- A separate controlled synthetic browser case displayed a saved EUR 650.00
  per-share external estimate, 12 analysts and an explicitly unknown estimate
  horizon, while broker research remained uncollected. This was a test-only
  source variation reprojected into its own workspace, not fresh market evidence.
- All 31 files in the original preview workspace still matched their pre-check
  SHA-256 values after projection and browser review.

The default preview has unavailable consensus and no broker research. Controlled
exclusion/eligibility cases are covered in automated data tests; this does not
claim a completed human interpretation trial or live market acceptance.
Frontend fixtures are reduced boundary captures, not complete
registered workspaces or independently verified company evidence.

Part 2C implements pointer/keyboard chart inspection and touch-capable controls;
physical-device acceptance is recorded separately in its guide. Native readers
for the other agents, cross-agent reader acceptance and print/export acceptance
remain later work. No provider/model calls, execution/approval controls, source-use
permissions, deployment or independent-backup capability were added.
