# Part 2C — interactive Agent 1 charts

Implemented 31 October 2026 for registered saved synthetic research. All eight
Agent 1 numerical series now have native interactive plots inside Keystone.
Parts [2B.1](part2b1-reader.md) and [2B.2](part2b2-research.md) provide the surrounding
reader, evidence checks and supporting sections.

## Delivered plots

| Saved data | Presentation | Meaning retained |
| --- | --- | --- |
| Annual revenue | Bars with a zero baseline | Actual saved years, not forecasts |
| Annual net margin | Line and selected point | Fraction values display as percentages |
| Valuation scenarios | Separate scenario points | Conditional model outputs, not a probability interval or external target |
| Peer multiples | Separate company points | Diagnostic screening, with target identity and peer restrictions |
| Prices and moving averages | Three distinct line styles/point symbols | Saved close and Python-prepared 50/200-observation windows; null warmups stay missing |
| Company versus benchmark | Two rebased lines | Original common-date rebasing; values labelled in index points |
| Annualised volatility | Separate line | Retained 30-observation Python definition |
| Drawdown | Separate line | Saved declines from prior peak; a genuine zero remains zero |

The primary chart is an SVG graph built from numerical data. It is neither a
saved PNG nor embedded source HTML. No plotting dependency, external script,
network acquisition, model call or backend financial calculation was added.
Research adapters 1.0.0 and 1.1.0 remain supported without changing saved artifacts
or creating a presentation revision merely to display the graphs.

## Inspection and accessibility

Mouse movement selects the nearest saved horizontal observation and shows its
label/date, series names, exact formatted values and units in a floating label.
The same selection appears in a persistent panel with a source button for each
series. A selected null point says unavailable, with its original evidence still
reachable. A missing series observation says not retained.

The labelled native range control supports keyboard arrows, Home and End.
Previous/Next buttons provide single-observation stepping; their changes have a
polite announcement. The slider exposes the selected date/category and exact
values through `aria-valuetext`. Source inspection retains the selection and
returns focus to its original Source control. Escape dismisses the floating label.

Touch pointer-down selects without requiring hover. The graph permits vertical
page scrolling. At narrow widths the persistent panel provides point information
without a floating label obscuring the graph; the native range control and step
buttons remain available. Physical touchscreen and screen-reader user acceptance
were not performed on this Mac and remain separate checks.

Legend buttons show/hide individual series, with pressed states and explicit
Shown/Hidden text. Line dashes, marker shapes and names supplement colour. Hiding
a series affects only the plot and its display scale. It does not remove exact
table values, rewrite data, change the report's calculations or upgrade a gate.
An all-hidden plot explicitly asks the reader to select a series again.

Every chart retains its purpose, synthetic basis, local saved review links,
diagnostic status where applicable, axes and an exact numerical table. Tables
expand below the graph and retain 25-row pagination. No data is downsampled.
Axis labels may be compact or scientific notation; point inspection and tables
use the original decimal strings and precision. Long category axis labels may
be shortened; inspection and tables retain their complete identity.

## Geometry and financial boundaries

The browser calculates only display coordinates and labels. Decimal strings are
aligned as integers for vertical scaling so a small difference between large
amounts is not lost through early floating-point conversion. Only a normalised
coordinate ratio becomes an SVG Number. This does not add source precision or
recalculate financial results.

Date rows form a chronological union across the supplied series; dates use actual
calendar spacing. A null or absent point ends a line segment. An isolated saved
point remains visible. No price, window, confidence band or intermediate financial
observation is invented. Bar baselines are zero; other vertical scales follow
the visible saved data and are labelled accordingly. The discrete scenario and
peer charts have no fitted line, forecast or probability band.

Withheld/unavailable charts produce no graphical values or point controls.
Their restriction remains visible beside the review links. Unknown chart types
show an explicit unsupported-plot explanation with the exact table retained.
This renderer currently supports line, bar, discrete scenario and dot plots for
date/category axes. Event-session paths, news visualisations and financial-close
waterfalls remain with the later native readers for those workflows.

## Verification

- **51 frontend tests passed**, including 13 new geometry/data cases: all eight
  chart families, exact input preservation, null/absent gaps, genuine zero,
  signed bar baselines, large close decimal amounts, flat/single-point series,
  withheld/unsupported data, discrete scenarios/peers, date alignment, visibility
  filters and nearest-point selection. A 5,000-point series and the aggregate
  20,000-point allowance retain all points; 20,001 aggregate points are refused.
- **83 workspace/backend tests passed.** Existing source matching, restrictions,
  financial-series parity and old/new adapter checks remain intact. The Python
  financial implementation was not changed in this batch.
- **TypeScript and the production build passed**, using the existing lockfile
  with no added packages.
- **Browser checks:** all eight graphs loaded without report iframes or raster
  images. Mouse selection and keyboard arrows/Home/End changed dates and values;
  the floating label and persistent panel agreed. Escape dismissed the label.
  The saved `652.6162` close and `636.7763180000002` moving average matched their
  source pointers and exact table values. Warmups remained unavailable.
- **Browser controls:** legend hiding retained exact table data, pagination
  advanced to rows 26–50 of 252, and Source return restored focus. The older
  1.0.0 presentation also rendered eight graphs with its original missing-detail
  explanation. Separate synthetic missing-bridge/invalid-peer cases rendered
  zero valuation/peer graphs and explicit withheld states.
- **Responsive checks:** desktop, 390px and 320px widths; plots and selected
  source detail had no outer horizontal overflow. The viewport override was reset.
  Physical touch input, a screen-reader session and largest-payload browser timing
  are not claimed by these checks. Large-payload tests exercise data/geometry.

The browser connection logged asynchronous message-channel errors around a page
reload. Subsequent chart interactions remained functional; no application
exception was identified from those messages. This is recorded separately from
the successful product checks rather than claiming an empty browser log.

The preview uses existing registered evidence at
`output/workspace-reader-2b2`, served locally on port 8778. Build the frontend and
reload the existing report; no re-projection is needed for charts:

```bash
cd web
pnpm test
pnpm run build
cd ..
.venv/bin/python -m keystone.workspace serve \
  --workspace output/workspace-reader-2b2 --port 8778
```

Use the serve command only if that port is not already serving this workspace.
Open `http://127.0.0.1:8778/#/runs/research-example`.

This completes the bounded Agent 1 chart implementation. Human interpretation,
physical-device/accessibility acceptance, native Agent 3/2/4 readers and full
print/export acceptance remain separate work. Financial approval, source rights,
backup availability and production-release status do not change.
