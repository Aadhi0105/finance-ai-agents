# Native report page outlines

Design outlines · 30 October 2026. [Part 2B.1](part2b1-reader.md) implements the
Agent 1 summary/key-figure foundation. [Part 2B.2](part2b2-research.md) implements
supporting sections and exact tables. [Part 2C](part2c-charts.md) adds Agent 1
interactive plots. These outlines still describe the broader finished reports:
[Parts 3A](part3a-events.md) and [3B](part3b-news.md) implement event/news reports. Agents 2/4,
eligible event-path projection and wider reader/export acceptance remain later work.

These outlines describe reading order and content, not final pixel measurements.
Every page stays within Keystone's existing shell. The primary report consists
of native components. A registered original report/export is available through
an evidence action. Desktop section navigation becomes a usable section selector
or anchor list on narrow screens; it does not hide review requirements.

## Shared frame

```text
KEYSTONE SIDEBAR       Report title / company / selected period
                      Source basis · execution · evidence review

                      [Concise material review notice]

                      SUMMARY: what the saved run establishes
                      Key figures with units and periods

                      Section navigation
                      Findings / Charts / Assumptions / Review / Evidence

                      Workflow-specific sections
                      - short explanation
                      - interactive chart or financial table
                      - source link and local restriction

                      Review requirements and next questions
                      Evidence / methodology / original artifact downloads
```

Execution, evidence eligibility, financial approval and hash consistency have
separate meanings. Technical hashes and full internal findings belong in the
evidence area. “Review required” stays visible in the report header and in any
restricted section. Expanding evidence must not replace the analyst's page with
a raw JSON document unless the reader explicitly requests the original download.

## Agent 1 — company research

**Question:** What do the saved financial evidence, comparisons and stated
valuation assumptions establish about this company?

```text
ASML — Company research
Annual period ending 31 December 2025 · synthetic demonstration
Execution: completed       Evidence: review required

NOTICE: illustrative inputs; valuation and comparison restrictions apply

RESEARCH SUMMARY
  Two to four source-linked observations
  Material uncertainty / next review question

KEY FIGURES
  Revenue | Operating margin | Cash-flow measure | Valuation status
  Every figure carries its period and unit

BUSINESS PERFORMANCE
  Revenue history        [interactive bars + exact table]
  Margin history         [interactive line + exact table]
  Supported explanation of changes; causes only when sourced

VALUATION AND ASSUMPTIONS
  Saved bear / base / bull results [interactive comparison]
  Scenario-weighted value | saved quote/date if usable
  Growth / discount rate / terminal assumptions / source of each assumption
  Enterprise-to-equity bridge; explain any withheld valuation

PEER COMPARISON
  Company and peer multiples [interactive points + table]
  Selected / excluded peers, period and economic-comparability limitations

MARKET CONTEXT
  Saved price vs benchmark | moving averages | volatility | drawdown
  Shared date/point inspection, explicit coverage and gaps

MARKET CONSENSUS
  Available external targets / revenue / EPS estimates
  Source, known date limits, analyst coverage and estimate periods
  Or: 'Analyst estimates were unavailable in this saved run'

EXTERNAL RESEARCH
  'Named-broker reports and ratings were not collected in this run'

REVIEW PRIORITIES
  Assumptions | source/observation dates | peers | unresolved claims

EVIDENCE AND METHODOLOGY
  Original saved inputs, model record and export downloads
```

For the current fixture, the supported narrative can explain €32.67bn revenue
and a 34.60% operating margin, labelled as synthetic. The saved scenario-weighted
per-share value is a conditional model result requiring review, not an external
analyst target. Historical growth remains labelled historical.

Keystone assessment may initially consist of supported facts and review questions.
A complete investment thesis needs additional source-backed qualitative content.
The consensus section remains present even when unavailable, so readers can tell
that the input is missing. Company background, risks, catalysts and causal
explanations are shown only where supported; do not invent descriptive prose to
fill a professionally styled page.

**Acceptance question:** Can the reader distinguish the company's observed
performance, Keystone's assumptions and external analysts' expectations?

## Agent 3A — past event reactions

Implemented for registered synthetic studies in [Part 3A](part3a-events.md), with
adapter 1.1.0 context tables and compatibility for 1.0.0. The event-relative path
remains withheld; projection of an eligible verified path is not yet implemented.

**Question:** What happened in the retained historical event cases, and what can
the study support?

```text
Past event reactions — semiconductor earnings example
Historical scope / event type / selected universe · synthetic demonstration
Execution: held            Evidence: review required

NOTICE: historical diagnostics only; no forward-return forecast

STUDY SUMMARY
  Eight retained synthetic event cases from eight issuers
  Diagnostic mean abnormal return about +2.25%
  Statistical inference unavailable; explain the material reasons

WHAT WAS EXAMINED
  Included/excluded companies and cases
  Event definition, timing basis, benchmark and observation coverage

HISTORICAL OBSERVATIONS
  Per-case abnormal-return bars [interactive; exact values on inspection]
  Event-window paths only when verified alignment permits them
  Available descriptive spread with appropriate diagnostic labelling

WHAT THIS MEANS
  Explain abnormal return, event window and averaging in plain language
  Distinguish observed sample description from inference and prediction

WHY REVIEW IS REQUIRED
  Sample / dependence | timing | comparison basis | study design / controls
  Each group links to original checks and affected figures

EVIDENCE AND METHODOLOGY
  Case table, exclusions, market-model details, replay and integrity records
```

For the current example, a concise explanation is: “Eight synthetic cases have a
diagnostic average accumulated abnormal return of about +2.25%. Statistical
inference remains unavailable, and the study does not predict the next event.”

The fixture contains numerical return observations but lacks verified event-window
timing. A per-case bar chart is supportable as a restricted diagnostic; a verified
calendar path is not. The page must not imply that adding two cases alone resolves
timing, dependence, benchmark, peer and control-study restrictions.

**Acceptance question:** Can the reader explain why a historical positive average
is different from a statistical conclusion or a future-return forecast?

## Agent 3B — company news

Implemented for registered synthetic news in [Part 3B](part3b-news.md), with
adapter 1.1.0 context and 1.0.0 compatibility. Real-source published-tone acceptance
remains separate; synthetic tone stays withheld.

**Question:** Which relevant stories were retained, what was excluded, and what
text-tone conclusion, if any, is supported?

```text
Company news — Example Rail
Saved cutoff / freshness window / text scope · synthetic demonstration
Execution: held            Evidence: review required

NOTICE: invented headlines; published tone withheld

NEWS SUMMARY
  Coverage, relevant retained stories and known limitations
  Published tone: withheld, with reason

RETAINED STORIES
  Headline | source | publication time | retained text scope
  Source link where legitimate; relevance and duplicate grouping details

COVERAGE AND EXCLUSIONS
  Retrieved → relevant → clustered records
  Excluded records and reasons; retrieval failure differs from a valid empty feed

TONE EVIDENCE
  Permitted text-tone result, scorer and scope
  Diagnostic scores only in a clearly labelled diagnostic area when held

REVIEW AND EVIDENCE
  Scorer restrictions, text/language limitations, original records and replay
```

The current example's published level is null and its diagnostic mean is 0.0.
The reader sees “Tone withheld”, not “Neutral”. Record clusters do not establish
independent stories. Document tone does not establish company-specific sentiment,
an earnings surprise or a trading recommendation.

**Acceptance question:** Can the reader distinguish news coverage, document tone
and an investment conclusion—and identify when no published tone is available?

## Agent 2 — financial monitoring

**Question:** Which saved observations breach the selected policy or require
investigation, and what changed at the selected cycle?

Order: selected cycle and data mode → exception summary → item table → selected
item evidence → eligible observation history → pending correction information →
original cycle/effective-state distinction → methodology and downloads.

The item table shows entity, metric, observation date, value/unit, threshold,
direction and saved classification. Highlighting Acme's 2.1× interest coverage
against a 3.0× floor opens its evidence. History charts use actual saved
observations; a snapshot containing only the current row does not justify an
invented history. Pending corrections remain informational; there is no approval
or correction submission control in this refinement.

**Acceptance question:** Can the reader identify the observation date and policy,
then distinguish a newly surfaced issue from an ongoing breach or later correction?

## Agent 4 — financial close

**Question:** How did actual results differ from budget, and what does the saved
close establish?

Order: entity/close/versions → result summary → budget/actual/variance → interactive
bridge → material account evidence → forecast and its separate limitations →
source versions and close history → evidence downloads.

The synthetic example starts with €60 budget profit, €65 actual profit and a
favourable €5 variance. The bridge shows a €10 sales contribution and a €5 adverse
cost contribution, each tied to its saved account evidence. An account's display
sign and favourability follow the existing profit-impact convention.

Forecast values use their own period/basis and cannot be presented as part of
the single-month variance. An unavailable interval remains absent with an
explanation. Accounting reconciliation does not establish a business cause,
external ledger authenticity or forecast calibration.

**Acceptance question:** Can the reader reconcile the bridge and distinguish
amounts established by the close from a provisional forecast?
