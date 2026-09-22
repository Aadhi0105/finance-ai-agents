# About this showcase

**Keystone is a platform of four finance AI agents on one shared analytical spine.**
The governing rule across all of them: the language model *orchestrates and explains*,
but every number is computed by deterministic Python — and, at the output boundary,
mechanically checked against those computations. The model never does the math.

---

## What you're looking at

These are **precomputed runs** on a small, curated set of large-cap European names —
generated locally, not run live in your browser. *(Live, type-any-ticker analysis is
a planned next stage.)* Each run is real: live financial data, deterministic
valuation and statistics, and the model's written analysis grounded against the
computed figures.

Every panel is tagged with its **run timestamp, data-as-of date, and the commit** it
was generated on, so what you see is reproducible, not a mock-up.

---

## The four agents

**Agent 1 — Equity Research.** Enter a company; get financials, ratios, an
FCFF/WACC discounted-cash-flow valuation (bear/base/bull), a peer-multiple check
against a curated peer set, and a written analyst note. The three names shown are
deliberately different — a semiconductor-equipment maker (ASML, Amsterdam), a rail
manufacturer (Alstom, Paris), and an enterprise-software firm (SAP, Frankfurt) —
across three exchanges and three very different financial profiles, to show the
valuation and peer logic doesn't break across them. Notably, they reach **three
different verdicts**: one screens materially *over*valued on DCF, one *under*valued,
one roughly *fair* — the tool isn't wired to a house view.

**Agent 2 — Covenant Monitoring.** A stateful surveillance engine that watches
credit covenants across cycles and surfaces only what changed. The featured
scenario shows a leverage ratio *drifting toward* its threshold — flagged as an
early warning several cycles **before** the hard breach, with a countdown to
breach — alongside a covenant that resolves and one that breaches outright.

**Agent 3 — Market / News Intelligence.** An event-study engine (Track A) that
measures whether earnings events actually moved peer stocks, with an always-on
**placebo** falsification test, and a validation gate that *holds* a result for
review when the evidence is thin or confounded. It reports honest nulls rather than
manufacturing signals.

**Agent 4 — FP&A / Variance.** Budget-vs-actual variance decomposed into
price/volume/mix/rate/spending drivers, rolled through a P&L hierarchy that
reconciles to the penny at every level, and classified on a materiality × abnormality
grid — including the "small in euros but a real statistical break" early-warning
quadrant that simple threshold systems miss.

---

## Honest limitations — shown on purpose

The edge of this project is honesty, so the things below are surfaced deliberately,
not hidden:

- **The FP&A agent runs on a synthetic company.** Real budget-vs-actual data is
  internal to a firm; a synthetic dataset is the standard, honest way to demonstrate
  FP&A tooling.
- **DCF is a transparent scaffold, not a house model.** It uses stated, visible
  assumptions (a growth fade to a terminal rate, a fixed discount rate,
  analyst-assigned scenario weights that are *not* empirical probabilities). Where
  the DCF diverges sharply from the market price, that gap is shown as *a finding to
  explain*, not a verdict — and for thin-margin or turnaround names the scaffold's
  growth assumptions are deliberately generic.
- **Peer sets are curated inputs.** Comparables are pinned per name; the tool reports
  when a peer set is small or skewed rather than pretending otherwise.
- **The model's written note is mechanically grounded — and flagged when it isn't.**
  Every figure in the note is checked against what the tools computed. When the model
  editorialises with a number it wasn't given — an invented threshold, a
  self-computed ratio in its "what would change my view" section — the run is marked
  **FOR REVIEW** rather than published as an approved report. Some of the reports
  here carry that review flag on purpose: it's the clearest proof that the grounding
  gate has teeth on real output. An approved report is one where *every* stated figure
  traces back to a computation.

> The model may tell you what to look at and why. Deterministic code owns the
> calculations, the state, and the gate that decides whether the result is fit to
> publish.
