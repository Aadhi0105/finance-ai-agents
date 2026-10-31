# Part 3A — native past-event reports

Implemented 31 October 2026 for registered saved **synthetic** Agent 3 event
studies. The primary report now opens directly inside Keystone, using the same
reader, source controls and interactive chart components as Agent 1. Company news
is a separate workflow and retains its existing saved-report reader until Part 3B.

## The reading experience

| Section | What the reader can establish |
| --- | --- |
| Study summary | Retained case and issuer counts, diagnostic mean CAR, and whether a saved statistical test is available for review |
| What was examined | Recorded method and weighting; case identities, dates, timing review, measurement dates and benchmark basis; requested/contributing/excluded peers and rejected inputs |
| Historical observations | Interactive per-case CAR bars, exact numerical table, diagnostic sample percentiles, and an explicit withheld event-relative path |
| What this means | Abnormal return relative to the saved market model, sample dependence and the limits of historical description |
| Why review is required | Plain-language groups linked to the original findings, plus expandable original check identifiers/statuses/details |
| Saved evidence | Exact values and JSON pointers, registered original downloads, definitions, run identity and file hashes |

The current example records eight synthetic cases from eight issuers and a
diagnostic mean CAR of about **2.25%**. Its statistical inference is unavailable.
The report explains these observations without treating the mean as a forecast,
an announcement's causal effect or financial approval. Execution, evidence checks,
snapshot consistency and financial approval remain separate states.

The bar chart supplies hover/selection labels, keyboard arrows/Home/End,
Previous/Next controls, a persistent selected-value panel and source inspection.
Mixed-sign bars have an explicit zero line and zero axis label. A case identifier
includes its retained position, so repeated issuers remain separate observations.
Missing CAR remains null; a true zero remains zero. The chart and its exact table
use the shared Part 2C components and retain saved decimal precision.

## Data and review controls

Event adapter **1.1.0** adds six source-linked tables: study basis, case metadata,
peer selection, exclusions, original gates and descriptive spread. It uses the
existing schema, with an additional closed `event-study-summary-v1` template.
Each original nonpassing check and inference reason remains reachable, including
unknown identifiers. Readable review topics cover sample/independence, timing,
comparison basis, study design, control studies, inference and unresolved inputs.
Original check details stay in a disclosure rather than dominating the report.

Recorded dates are labelled as recorded metadata. They do not establish an
issuer-confirmed release time, exchange session or verified benchmark. Missing
measurement dates and benchmark details are explicit. Preparation time is never
substituted for an event date. Saved local review attribution does not establish
an authenticated approval.

The adapter checks reported sample counts against retained case/issuer counts;
inconsistent counts withhold affected aggregates. Missing or invalid case values
withhold the mean and sample spread. Spread also requires its recorded sample
count to match. These are presentation consistency gates; the adapter does not
rerun the study or recompute its financial/statistical results.

A saved p-value is retained only as a diagnostic when its numerical range,
inference status, original inference check, sample size/issuer independence,
rejected-input state, significance flag and absence of inference reasons permit
it. Passing that boundary does not override other study or publication checks.
A controlled ten-case test preserves the held state when other checks fail.
Unavailable inference is never displayed as zero or as a neutral result.
Sample percentiles are historical descriptions; future positive-return
probabilities and confidence bands are not introduced by this reader.

**Event-relative path projection is not implemented in this batch**, even for a
future timing-eligible dataset. Both supported adapter versions withhold the
path, and the client refuses populated paths for those versions. A future
implementation requires a new supported projection and an eligible timing/session
fixture, then source and browser reconciliation. This leaves A3A-03 partially open.

## Compatibility and preparation

Registered event adapter **1.0.0** retains its original projection recipe and is
readable in the native reader. Its missing case/method detail is explained;
the browser does not reconstruct it from arbitrary source JSON. Agent 1 adapters
1.0.0/1.1.0 remain supported. News, monitoring and close adapters remain unchanged.

To obtain richer event detail, project an existing registered synthetic workspace
into a **new destination**. Do not overwrite an existing saved workspace:

```bash
.venv/bin/python -m keystone.workspace project \
  --workspace output/workspace-reader-2b2 \
  --destination output/workspace-events-demo
cd web
pnpm test
pnpm run build
cd ..
.venv/bin/python -m keystone.workspace serve \
  --workspace output/workspace-events-demo --port 8781
```

Use the server command only when that port is free. Open
`http://127.0.0.1:8781/#/runs/events-example`. The reviewed local preview uses
`output/workspace-event-3a`; these generated workspaces and screenshots are ignored
outputs, not committed financial evidence. A new workspace can also be generated
through `prepare --native`, using the existing offline synthetic engines.

## Verification and remaining acceptance

- **1,094 Python tests passed**, including 13 added event cases covering source
  parity, repeated issuers, null/missing values, inconsistent samples, unknown
  findings/exclusions, ten-case held studies, invalid/zero p-values, spread scope
  and old/new adapter compatibility.
- **75 frontend tests passed**, including 24 event boundary cases. Wrong source,
  workflow, schema, adapter, references, units, approval or diagnostic visibility
  are refused. Populated paths and invented analyst consensus are refused.
  Null/zero distinctions, exact case identities and uncached abortable reads pass.
- **TypeScript and the production build passed** with the existing lockfile and
  no new dependencies.
- **Desktop browser:** native six-section report, one SVG bar chart, no primary
  report iframe/raster image; exact point/source agreement, keyboard Home/End,
  source return focus, original check disclosure and explicit zero baseline.
- **Narrow browser layouts:** 390px and 320px widths, section Go focus, selected
  chart/source details and return focus; no outer horizontal overflow in inspected
  states. The wide case table scrolls within its container. The viewport override
  was reset. Physical touch and screen-reader user sessions remain pending.
- **Integrity refusal/recovery:** a disposable workspace with changed bundle bytes
  loses the native graph and download controls on recheck. Restoring the original
  bytes and rereading recovers the report. Main/source workspace hashes remain
  unchanged by browser checks.
- **Download limitation:** the application reported a verified download, but the
  browser download event did not complete through the test tool. Browser security
  policy blocked inspection of its internal Downloads page. Completion and the
  saved file's hash were therefore not confirmed for this event download. Existing
  automated size/SHA-256 checks pass; this browser acceptance item remains open.

Human interpretation acceptance, eligible event-path projection, physical-device
accessibility, broad print/export checks and maximum-payload browser timing
remain separate work. Native company news is next. No live source/model calls,
execution/approval controls, source-rights decisions, backup capability or
production-release approval were added by Part 3A.
