# Agent 1: evidence and numerical claims (Batch 2)

## Publication contract

The gate assesses a **complete equity-research run**. It requires successful
financials, prices, ratios, DCF, peer screening and consensus retrieval. An
explicitly unavailable consensus result is acceptable only with usable annual
history. Partial/enterprise-only valuations can still be inspected, but cannot
be approved as a complete equity-research report.

Evidence must identify the same company, compatible currencies/units and annual
periods, finite data, and usable quantities. Ratios and DCF are recomputed from
current inputs and declared assumptions without network calls. Peer statistics
are reconciled to retained raw financial/price evidence, including each peer's
company and currency. Historical CAGR must reconcile to its annual revenue data;
current price alone cannot establish analyst consensus. Explicit zero analyst
coverage is rejected. Malformed evidence produces a failed gate.

When the runtime supplies the call log, each result must match its latest
successful call. A refresh of any dependency after a calculation requires that
calculation to be rerun, even if the new numbers happen to be unchanged.
Numerical reconciliation also detects changed financial/price inputs when no
call log is supplied. Batch 3 will address state invalidation and immutable call
snapshots; this gate does not redesign shared RunState.

## Assumptions and dates

DCF forecast parameters identify `caller_supplied` versus `model_default`.
“Caller” can be the LLM; it does not mean a human analyst approved the input.
Model defaults, default tax, assumed zero working-capital change, EBIT proxies,
provider working-capital aggregation limitations, small peer samples,
indeterminate dispersion and differing peer periods require review.
Full-precision tax assumptions are preserved so recalculation is reproducible.

Financial statements older than 548 days require review; missing/invalid or
future target statement dates fail. Live retrieval dates and quote/estimate
observation dates are checked against a seven-day freshness policy. Unknown
observation time is not replaced with retrieval time. These are explicit policy
thresholds, not claims about vendor accuracy. Peer source dates are checked too.
Illustrative fixtures always require review. Current Yahoo adapters expose
unknown quote/estimate observation dates, so their output normally requires
review even when arithmetic reconciles.

Any failure produces `flag_for_review` / low confidence. Any quality warning
produces `flag_for_review` / medium confidence. Only complete evidence without
warnings can be high-confidence / pass. The score remains descriptive; it cannot
override a warning. Confidence measures evidence quality, **not the probability
that an investment conclusion is right**. A large valuation gap, terminal-value
concentration or peer-method divergence is a finding, not an automatic defect.
Margins below −100% are allowed when the calculation reconciles.

## Numerical claims

The former global pool of numbers has been removed. A number occurring somewhere
in a tool result does not support a different metric, company, period or unit.

The LLM writes qualitative prose and selects named evidence markers on separate
lines, for example:

```text
Profitability is a useful support for the thesis.
[[claim:operating_margin]]
[[claim:dcf_value]]
```

Python renders complete labelled sentences from current tool results, retaining
metric identity, company, value, currency/unit, period and exact tool/path in
`validation.note_grounding.evidence`. Percent signs, negative signs, multiples,
currency amounts and percentage-point units are generated deterministically.
The original model text and rendered note are both persisted. Model-supplied
labels beside a marker are rejected, preventing a DCF gap from being relabelled
as an operating margin.

Free-text numerical tokens, common spelled-out numbers, unknown markers, failed
or unavailable metrics and notes with no supported claims fail grounding.
Numbers from earlier calls cannot support a current claim merely because their
values match. Comparing historical call versions would require an explicit
versioned-evidence interface, which is not implemented here.

This is deliberately a constrained numerical-writing interface, not unrestricted
semantic validation. It does not verify qualitative prose, causal claims,
investment recommendations, every linguistic way of expressing a quantity, or
whether the selected evidence makes an argument persuasive. A grounding pass
alone is insufficient: the report path also requires the evidence gate to pass.

## Runtime and compatibility

The live system prompt and offline script use the marker interface. The report
path gates current results and the call log, renders the note, incorporates the
grounding check into the verdict, and persists the evidence alongside the note.
The displayed note is labelled with that verdict. Unsupported text remains
inspectable in review output, not an approved report. Offline runs now normally
produce `report_REVIEW.html`, appropriately reflecting illustrative data and
unreviewed model defaults.

This changes the note-authoring contract: existing free-text numeric notes must
be rewritten with evidence markers. Legacy sidecar rebuilds do not acquire new
validation automatically. Atomic writing, failed chart recovery, stale approved
report cleanup, CLI exit codes and explicit model-completion states remain
Batch 3 work.

Tests cover complete and incomplete evidence, errors, malformed schemas,
non-finite values, stale dependencies, default assumptions, date policy, peer
lineage, raw-number bypasses, signs/currencies, percentage points, wrong-company
claims and sidecar/report integration. They use deterministic local inputs and
require no paid LLM calls.
