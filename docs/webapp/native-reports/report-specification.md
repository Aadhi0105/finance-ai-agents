# Native report specification

Version: proposed 1.0 · 30 October 2026 · design only.

## 1. Purpose and boundaries

The reader must be able to identify the report's question, main observation,
supporting evidence, limitations and next review question without interpreting a
terminal log. The primary report renders as native Keystone components, with
interactive numerical charts and source-linked tables.

This refinement uses the existing saved calculation results. Python owns
financial/statistical calculations and publication eligibility. The browser owns
presentation and inspection. Neither formatting nor an interactive chart grants
financial approval. Unsupported conclusions remain withheld.

The first implementation serves explicitly registered synthetic runs. Real-data
onboarding requires its existing source-use and authorisation controls; a broader
schema vocabulary is not permission to import external or internal datasets.
There is no provider/model call when opening a report.

## 2. Shared reading structure

| Layer | Required content | Reader's question |
| --- | --- | --- |
| Identity | Report title, entity/listing, financial period or event scope, source classification, preparation time | What exactly am I looking at? |
| Review notice | One concise, prominent notice and the material limitations | What prevents ordinary reliance on this result? |
| Summary | Two to four supported observations or an explicit explanation of why a summary is unavailable | What did the run establish? |
| Key figures | A small set of figures with units, period and evidence access | What are the important amounts or measures? |
| Analysis sections | Workflow-specific charts, tables and short explanations | What supports those observations? |
| Review requirements | Grouped reasons, affected sections and concrete review questions | What needs to be checked next? |
| Evidence and methodology | Sources, calculation basis, exclusions, run/version identity, replay and integrity details | Can I trace and reproduce the result? |

A sticky section navigation may link to report sections; it must not create a
second competing application navigation. Opening evidence returns the reader to
the same section and context. The original saved HTML is an optional export, not
the primary report iframe. No HTML scraping is used to populate native sections.

## 3. State and disclosure rules

Keep the following concepts separate:

- **Execution:** the engine's recorded state, including completed, held, refused,
  unavailable, failed or unknown. Do not turn an Agent 3 `held` result into
  `completed` merely because it contains calculated numbers.
- **Evidence checks:** passed, held for review, or unavailable, mapped from the
  relevant engine and local workspace review policy.
- **Financial approval:** false throughout this unauthenticated local interface.
  “Passed evidence checks” must never be labelled “Investment approved”.
- **Integrity:** artifact bytes match, are unchecked, or are invalid. Matching a
  saved hash does not authenticate an issuer or prove the financial data is true.
- **Availability:** an individual figure/section is available, unavailable,
  withheld or not applicable. A valid diagnostic can exist while publication is
  held. Missing data and a withheld result retain distinct explanations.

Do not display the current Agent 1 heuristic confidence label or quality score as
investment certainty. Agent 3's `p_value=null` becomes “Statistical inference is
unavailable” with a plain-language reason; it does not become zero significance.

### Warning grouping

Group related checks under data basis, observation dates, valuation assumptions,
peer comparability, statistical eligibility, narrative support, or delivery.
Every original check remains reachable. Each group identifies affected sections.
Its wording must explain the impact without implying that satisfying one minimum
condition resolves all other checks. For example, increasing an event sample to
ten does not itself establish valid timing, independence or comparability.

The report notice remains visible independently of the audit drawer. An affected
valuation/chart also carries a local restriction. Grouping must not lower severity,
remove an exclusion, change the source verdict, or manufacture an approval action.

## 4. Narrative and analyst content

### Supported narrative in this refinement

Use deterministic, evidence-linked templates for observed amounts, changes,
comparisons and definitions. Each numerical insertion names a metric/evidence
reference; the browser does not assemble financial conclusions from arbitrary
strings. Current held material is described as diagnostic or illustrative.

Examples of eligible content, with the relevant evidence and scope attached:

- “The saved annual inputs show revenue of €32.67bn.”
- “The illustrative interest-coverage observation is 2.1× against a 3.0× floor.”
- “The synthetic close records €65 actual profit against a €60 budget.”
- “Eight synthetic event cases produced a diagnostic mean abnormal return of
  about +2.25%; statistical inference remains unavailable.”

Definitions and review questions are distinguishable from factual findings.
They may explain operating margin or ask whether peers are economically suitable;
they must not assert an unverified business cause. Causes such as pricing power,
customer loss or delivery delays require source evidence supporting that claim.
An LLM draft or a URL alone does not satisfy the existing qualitative controls.

### Three separate analyst areas for Agent 1

| Area | First-refinement behaviour | Additional capability required |
| --- | --- | --- |
| Keystone assessment | Supported observations, explicit assumptions, limitations and review questions | Rich causal/business interpretation requires a sourced claim/review mechanism |
| Market consensus | Display available targets and revenue/EPS estimates with currency, period, coverage and known date limitations | A populated real-data panel requires an authorised source and usable retained estimates |
| External research | Clearly state that named-broker reports and ratings were not collected | Separate authorised document/rating ingestion, attribution and claim support |

The current ASML fixture has `available=false` consensus. Its page must say
“Analyst estimates were unavailable in this saved run.” It must not suggest that
Keystone's DCF is an external price target or that historical CAGR is a forecast.
A live model draft is not a broker recommendation. Buy/hold/sell labels are not
introduced by this refinement. Human-authored assessments need separate identity
and review attribution before a future application can present them as approved.

## 5. Interactive chart rules

Charts use actual saved observations or backend-derived series tied to saved
evidence. Hover, keyboard focus and touch selection expose the same information:
point label, date/period or relative position, series name, exact value, unit,
and evidence access. Information cannot depend on colour or hover alone.

Each chart includes a short purpose statement, a data basis, any material local
restriction, a legend, clear axes, and an accessible numerical table. Tooltip
precision and table precision must reconcile. Compact labels such as €32.67bn
must still permit inspection of the full underlying value.

| Chart family | Supplied data | Important restriction |
| --- | --- | --- |
| Annual history | Saved annual revenue and margin observations | Actual periods; gaps remain gaps; no forecasts added |
| Price and benchmark | Aligned observations and Python-derived rebased values | Same common start date, compatible basis, known exclusions |
| Moving averages | Python-derived series using the existing window definitions | Unfilled windows are null; no browser financial recalculation |
| Volatility/drawdown | Existing Python calculations as separate, labelled panels | Volatility annualisation and drawdown definitions remain explicit |
| Valuation scenarios | Saved bear/base/bull per-share values and assumptions | Scenario weights are assumptions, not measured probabilities |
| Peer comparison | Saved eligible multiples and peer evidence | Show exclusions, period differences and screening-only status |
| Event diagnostics | Saved per-event CAR and eligible event-window observations | Held data stays diagnostic; unverified timing stays visible |
| News evidence | Coverage counts and permitted text-tone measures | Held published tone stays null; no neutral/trading label inferred |
| Close bridge | Python-produced exact budget/actual steps and account labels | Colour follows saved favourable/adverse meaning, not sign alone |

Do not interpolate missing prices, invent an event path, add confidence bands
when no eligible interval exists, or plot withheld values as zero. The current
event fixture lacks verified window timing: its native example therefore uses
per-event diagnostic bars and withholds a dated event-path chart.

Selecting a point, toggling a series, or changing the visible date range is
inspection. Changing peers, assumptions or sample inclusion requires a new
controlled calculation and immutable result. A display filter must not silently
recalculate the report's mean, CAGR, risk estimate or publication state.

## 6. Visual and accessibility principles

Extend the existing forest-green navigation, neutral backgrounds, restrained gold
accents and editorial headings. Share report headings, spacing, units, source
links, tables, chart legends and status treatments across workflows. Use readable
body text, aligned numbers, useful whitespace and limited emphasis.

Keep workflow-specific meaning: a financial-close bridge, a price chart and a
news timeline should not be forced into one generic chart. Agent 3's workflows
have separate titles, questions and section outlines. Do not put hashes, raw
JSON or internal check codes ahead of the reader's main observation.

Desktop and narrow layouts retain the same evidence and restrictions. Wide tables
may scroll inside labelled containers. Graphs have keyboard/touch alternatives,
visible focus and reduced-motion support. A report can be read without opening
every audit detail; all material restrictions remain visible.

## 7. Original evidence, exports and compatibility

Preserve original records and hashes. Any native projection is derived, versioned
and separate from the sealed source. Do not overwrite model.json or bundle.json
to make the new page work. Old unsupported schemas show a clear unsupported-view
state with the registered original artifact available for inspection/download.

Keep the existing file inventory and confinement controls. An eventual native
view is another explicitly registered artifact served through a read-only route.
This part proposes that route; it does not add it. Native chart scripts execute
as trusted application components. Original exported HTML retains its separate
sandbox and script restrictions.

Printing/export should present the same values, periods, restrictions and evidence
references. Static chart exports may remain available alongside the interactive
screen. No new PDF renderer or export service is selected in Part 1.

## 8. Completion boundary

Part 1 completes when the layouts, source mappings, schema examples and acceptance
criteria are internally consistent and reviewable. Subsequent parts implement
and verify the native pages. Full external research ingestion, arbitrary model
prose publication, browser execution, editable assumptions, authentication,
provider permissions, backup and deployment are not implementation deliverables
of this report specification.
