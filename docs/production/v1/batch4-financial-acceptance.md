# Batch 4 — bounded financial and data acceptance

Prepared and executed 10 October 2026. **Offline engineering evidence complete for
this evaluation set; production financial acceptance remains open.** This batch adds
a frozen plan, independent calculation checks, an evaluator, and a blind news review
pack. It does not expand supported company coverage or grant source-use permission.

## Frozen scope and thresholds

The [plan](../../../fixtures/production_v1/batch4-plan.json) was completed before
its first evaluation. Its SHA-256 is
`5360ea173751f61212d6bc6180dc522f60f76df6eca8c6500a10a46714a06f29`.
The runner rejects plan or declared-source changes. Expectations were authored before
executing the cases; synthetic examples are contract checks, not unseen market-quality
evidence. Do not modify this plan to turn a failed run into a pass. Version a new
plan, explain the change, and retain the former result if scope needs adjustment.

| Check | Predeclared tolerance / expected outcome | Rationale |
| --- | --- | --- |
| ASML selected FY2025 issuer fields | EUR 100,000 absolute | Existing reference contract; one EUR 0.1 million displayed unit, not a universal materiality threshold |
| Stadler FY2025 reference fields | CHF 1,000 absolute | Existing reference expressed from CHF thousands |
| FCFF from retained ASML lines | EUR 0.01 absolute arithmetic difference | Numerical reconciliation of retained inputs; not an assertion of cent-accurate source disclosure |
| Displayed ratios | 0.000051 absolute | Half the four-decimal display increment plus floating-point allowance |
| Unrounded monitoring ratios | 1e-12 absolute | Arithmetic equality using the same declared units |
| DCF enterprise/equity values | EUR 0.51 absolute | Half the integer currency display increment plus allowance |
| DCF per-share values | EUR 0.0051 absolute | Half the two-decimal display increment plus allowance |
| Event alpha, beta and CAR | rtol 1e-10 / atol 1e-12 | Existing independent raw-price/OLS oracle; date/window identities exact |
| Synthetic news rules | Every frozen expected decision must match | Zero tolerated rule violations in this deliberately small contract set |
| Agent 4 | Exact cents; 14 saved closes plus gap case | Existing independent control ledger; no relative financial epsilon |

## Cases and what they establish

**Agent 1.** Retained ASML FY2025 issuer/provider references reconcile after the
explicit operating-income and working-capital normalization. The evaluator computes
FCFF directly from retained issuer lines using Decimal arithmetic, verifies debt and
cash-flow identities, and independently checks three margins. A separate Decimal
cash-flow oracle checks bear/base/bull valuations over 1-, 5-, 10- and 30-year horizons,
including the debt bridge and weighted per-share result. Boundary cases cover
negative FCFF, a financial-sector company, missing capex/debt, currency mismatch and
unsupported qualitative claims. Current shares/prices, forecasts and the complete
issuer filing are not newly certified. AAPL/RIVN/BRK-B historical acceptance does
not become fresh issuer acceptance through these generic boundary cases.

**Agent 2.** Three Stadler ratios are recomputed from the retained reference using
independent numerator/denominator arithmetic. The workflow exercises baseline
breaches, repeated observations, outage preservation, stale/future/quarterly or
unreviewed periods, currency/unit mismatch, issuer mismatch, original replay and
approved/rejected corrections. Inputs are constructed offline from the reference;
they are not freshly fetched provider snapshots. The correction examples deliberately
change assets within the existing source-resolution tolerance. They test mechanics,
not a claim that Stadler restated its accounts. “Synthetic acceptance harness” in
decision attribution is not a human finance approval. Existing diagnostic regressions
provide further arithmetic/refusal coverage, not calibrated risk probabilities.

**Agent 3 events.** The retained ASML and NVIDIA issuer-validation bundles are
hash-checked and passed through the existing independent raw-price oracle: release
anchors/sessions and windows must match, returns are recomputed from prices, and
OLS/CAR results must reconcile. Offline replay must match and held distributions
remain withheld. Dates are compared with retained source-checked plans; this is not
a new visit to issuer websites or human approval of an investment study.

**Agent 3 news.** Twenty synthetic relevance cases, six freshness cases and six
conservative duplicate cases cover provider-tag/body-only false inclusions, ticker
boundaries, aliases/cashtags, exact seven-day cutoff, future/missing dates, punctuation,
negation, numbers and aged copies. Two entity labels per relevance case yield a
40-decision confusion table. Fixture tone must remain held. These assistant-authored
labels are not human annotations and the resulting match rate is not live accuracy.

**Agent 4.** The existing independent exact-cent oracle reruns 14 synthetic closes,
restatement, formal rebudget, missing-input rollback, delivery recovery, historical
immutability and the auxiliary gap case. Authorised real-company data and controller
sign-off remain absent; V1-A4-001 stays blocked.

## Human news evaluation still required

The local blind pack contains all 40 input records from the two selected retained
ASML/NVIDIA retrievals, including records the application excluded. It shows no
application prediction. It preserves source-bundle hashes, raw indices and input
hashes. Local files are under `output/production-financial/news-human-review-ready/`:
`review.html` for reading and `labels.json` for recording decisions. Raw headlines
remain outside Git. The committed evidence holds only their source identities/counts.

Label relevance to the target issuer from the headline, duplicate groups and timestamp
validity. Use `true`, `false` or `"uncertain"` for relevance/time validity; use the same
group ID for duplicates and a unique group ID for a singleton. Record reviewer,
review date and rationale for uncertain cases. Never silently treat uncertainty as
negative. Freeze the completed label file before comparing it with application output.

Recommended next evaluation scope: expand, with permitted sources, to at least 100
records across multiple retrieval dates and at least two issuers, with at least 30
positive and 30 negative human-labelled entity decisions. Proposed acceptance targets
are precision ≥95%, recall ≥90%, zero false duplicate merges that discard changed
numbers/negation, and exclusion of every confirmed future/stale item. These are
**proposals requiring analyst review before real-feed evaluation**, not thresholds
already accepted or achieved. Report sample counts, uncertainty and errors alongside
rates; this small retained pack cannot establish provider coverage, missed stories,
language coverage or market-wide performance. Do not tune on this set and then call
it an independent held-out evaluation.

## Run and evidence

```bash
python -m scripts.check_keystone_financial --output output/production-financial/NEW_RUN
python -m pytest tests/test_production_financial_acceptance.py
```

Use a new output directory. The command runs offline under the checkout admission
gate and retains each section's result, plan hash and evaluator identity. Retained
bundles are local prerequisites: a missing bundle is a blocked section, never an
automatic provider fetch. Do not run acceptance concurrently with another mutating
workflow. Direct test APIs use isolated temporary stores.

The [evidence record](../../../references/acceptance/production-financial-2026-10-10.json)
and [release register](release-evidence.md) record actual outcomes and limitations.
No application financial logic was changed to fit this benchmark. Source-use approval,
human financial review, a representative labelled news benchmark and authorised
company FP&A acceptance remain required before passing the dependent production gates.
