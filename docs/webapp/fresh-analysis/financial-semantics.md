# Financial-kit semantics — version 1

**Normative 4A.2 design; not a runtime validator.**
[Specification](../batch4a2-fresh-analysis-contracts.md) ·
[Package schema](financial-kit.schema.json) · [Acceptance](acceptance-matrix.md).

## Identity, dates and numerical representation

- Envelope entity ID resolves to one registered company with a non-null matching
  ticker. Payload entity, ticker, MIC, quote currency and share class agree with
  the envelope. Existing entity records store a ticker, not a verified MIC/share
  register. The first accepted financial kit atomically pins the complete
  declared listing/company-type/security/scope tuple for that entity. Each later
  kit for that entity must match, across datasets, even if the first version's
  permissions are later revoked. The acceptance contract records
  `listing_scope` with `first_version_id` and `scope_sha256`. The digest covers
  the closed object consisting of payload keys `listing`, `company_type`,
  `instrument_type`, `financial_scope`, `currency`, `monetary_unit`, `period_type`.
  Concurrent first acceptance serializes with version admission;
  incompatible scope requires a separately registered entity, not an in-place
  rewrite. Restore retains the first pin and rejects missing/conflicting lineage.
  MIC is a four-character declared exchange identifier, not a discovery request
  or an independently verified listing. Company names alone cannot merge identities. Business type
  is explicitly nonfinancial operating; missing/unsupported type is refused.
- Only consolidated annual periods and one ordinary common-share basis are
  supported. No ADR, preferred, dual-class/conversion, bank, insurer, fund,
  property valuation, stub or quarterly substitution. Analysts must not assert
  the supported business type merely to fit this method.
- All statement/quote monetary amounts use EUR **base units**, never thousands,
  millions, minor quote units or FX-adjusted assertions. Shares are actual
  ordinary-share counts. Scope, unit, currency or identity contradictions reject
  the whole kit, including contradictions in optional supplied groups.
- Financial values are canonical decimal **strings**, maximum 15 integer digits
  and six fractional digits; no exponent, separators, whitespace, leading plus,
  leading zeros, negative zero, NaN, Infinity, booleans or JSON numeric coercion.
  Signed profits/working capital are allowed. Revenue, cash, debt, D&A, capex and
  bridge claims are nonnegative. Quote price/capitalisation/shares, if present,
  are strictly positive. Shares have no fractional part and are at most 10^12.
- JSON Schema validates lexical forms and basic bounds. Python must use Decimal
  for input reconciliation, signs, hashes and exact weight-sum checks. A shared
  analytical function accepting floats needs explicit checked conversion; retain
  original decimals, record calculation/rounding method and refuse nonfinite or
  overflowed output. Do not promise precision beyond the reused function.
- Each period has start/end dates, inclusive length 350–380 days, and a
  `YYYY-MM-DD` closing date. At most ten unique periods in strictly increasing
  order, no overlapping intervals or duplicate closing-calendar years. The final
  record is the current period; no silently skipped malformed older record.
- End/quote dates cannot be after the server's UTC evaluation date. Adjacent
  annual ends 350–380 days apart are comparable. Gaps break growth paths; two
  periods with the same fiscal label do not establish comparability. Source
  period ranges must cover the observations that reference them. No source's
  income/cash-flow/balance observation may borrow another period's figures.
- `published_at` and `retrieved_at` remain independent timezone-bearing source
  instants, or null. Non-null future instants are refused. Publication must not
  follow retrieval if both are supplied. Unknown dates generate review reasons;
  processing/upload time is never an observation or filing date.
- Evaluation date is recorded in readiness and result. Reassess at admission,
  claim and registration; if a date-dependent eligibility decision changes,
  stop as `source_changed` and require a newly reviewed request rather than use
  an obsolete readiness snapshot. Delivery retains that recorded analytical
  date; it does not present old results as today's quote.

Every observation has `value`, `source_id`, `locator`, `missing_reason`. A present
value needs a declared source/locator and null missing reason. Missing means all
three value/source/locator fields are null, plus `not_provided` or `not_disclosed`.
Present zero keeps its source. A source must have a non-null matching category,
owner, period/currency/unit scope and applicable operator permission record.
Unknown date metadata is a review item; unknown origin/rights is a block.

## Statement fields and meanings

All field keys are required in each annual record; unsupported/unprovided values
are explicit missing observations. The current record must have revenue and at
least one of operating income or attributable net income. Older records must
have at least one usable financial observation. A missing component only removes
dependent calculations after the minimum is satisfied.

| Field | Required financial meaning |
| --- | --- |
| `revenue` | Consolidated annual revenue, nonnegative |
| `gross_profit` | Annual gross profit on the same revenue scope; signed |
| `operating_income` | Reported annual operating income; signed; the only EBIT proxy accepted for local FCFF |
| `net_income` | Annual net income attributable to ordinary shareholders; not unadjusted group earnings including other claims |
| `pretax_income` / `tax_provision` | Signed annual pre-tax income and tax expense; same reporting scope/period |
| `depreciation_amortization` | Nonnegative annual D&A; no double counting with capex |
| `capex` | Nonnegative cash capital-expenditure outflow magnitude; convention explicitly `outflow_magnitude` |
| `change_in_working_capital` | Signed operating working-capital balance change; positive absorption, negative release; convention explicitly `balance_change` |
| `total_debt` | Period-end interest-bearing debt including lease liabilities; nonnegative; basis explicitly declared |
| `cash_and_equivalents` | Period-end unrestricted cash and cash equivalents; nonnegative; no automatic addition of investments |
| `noncontrolling_interests` / `preferred_equity` / `other_equity_claims` | Explicit current-period bridge-claim observations; zero is evidence, not a missing-data default |

Provider cash-flow working-capital contributions, signed negative provider capex
and provider EBIT require their own explicit preparation outside this kit. The
adapter must not negate arbitrary local values or apply Yahoo/ASML-specific
adjustments. In version 1 a mistyped convention is refused; data must already
use the declared meanings. Unsupported nonzero/unknown bridge claims hold equity
valuation and EV/operating-income; they do not disappear in a net-debt shortcut.

## Optional quote snapshot

`quote` is null or a single snapshot with the identical listing, EUR/base units,
an ISO observation date, and explicit price, capitalisation and share observations.
All three field keys exist; individual values may be missing, but at least one
must be present. Each supplied component must refer to the declared snapshot
date and share basis; a mixed-date/share-class bundle is refused.

If cap, price and shares all exist, require
`abs(cap - price*shares) <= 0.05 * max(abs(cap), abs(price*shares))` using Decimal.
This is only a consistency screen. Derive no missing cap, share count or price
from the other two in this first version. Quote age 0–7 calendar days relative
to the recorded UTC evaluation date is eligible; older snapshots remain visible
as source evidence but all their dependent metrics are withheld. An absent
snapshot is unavailable. Future dates, contradictory units and reconciliation
failure refuse the package instead of being relabelled stale.

## Financial dependency and availability map

| Result | Inputs / checks | Failure or missing behaviour |
| --- | --- | --- |
| Current figures | Minimum current annual basis; each value sourced | Missing individual figure unavailable; failure of minimum rejects kit |
| Gross/operating/net margin | Corresponding income divided by strictly positive revenue | Nonpositive denominator or missing numerator → unavailable; negative margins preserved |
| Revenue YoY | Current/prior revenue, positive prior revenue, consecutive comparable annual dates | Missing/gapped prior → unavailable, never annualised |
| Revenue CAGR | Latest consecutive positive revenue suffix, at least three observations; exponent `1/(count-1)` | No usable suffix → unavailable with exact coverage; exclude no intervening year silently |
| History charts | Actual dates and values from every supplied period | Missing values are null gaps; no interpolation or synthetic years; one observation is a labelled point |
| Annual P/E | Eligible quote cap / positive current attributable net income | Nonpositive income → not applicable; absent/stale quote → unavailable/withheld |
| EV/operating-income | Eligible cap + debt − cash; current positive operating income; three bridge claims known zero | Unknown bridge → withheld; nonpositive operating income → not applicable; name basis explicitly |
| Base FCFF | Operating income × (1−tax) + D&A − capex − dNWC | Missing component/tax → withheld; nonpositive FCFF → not applicable |
| Conditional DCF equity | Selected/reviewed valid plan, positive FCFF, debt and cash present, three bridge claims known zero | Missing/unsupported bridge → whole DCF section withheld in first slice; no EV-only value disguised as equity |
| DCF per-share | Eligible equity and fresh positive compatible shares | Missing/stale shares → unavailable/withheld per share; retain eligible equity totals |
| Conditional model-value gap | Eligible weighted per-share / fresh compatible positive quote − 1 | Missing/stale price → unavailable/withheld; no label as expected return |
| Distressed scenarios | Any scenario equity below zero | Retain signed equity diagnostic; affected per-share value and weighted per-share/gap withheld; never negative tradeable targets |
| Peers/market history/consensus/brokers | No input contract in 4B | Separate unavailable sections, reason `unsupported_input_group`; no calls or invented results |

Current statements older than 548 days receive a prominent stale-statement review
item. Historical calculations can remain available, explicitly dated; no figure
is called current market evidence. No quote freshness is inferred from filing age.

`available` means a supported calculated/sourced value, not approval. `unavailable`
means missing evidence. `withheld` means a restriction or failed eligibility check.
`not_applicable` means the method/denominator is unsuitable. Requested scope,
availability and financial review are independent: a deliberately excluded DCF
has `requested=false`, `availability=not_applicable`, reason `excluded_by_plan`.
One unavailable metric does not hide other usable section content.

## Complete DCF plan

- `method`: `fcff-linear-fade/1`; end-year discounting. Horizon integer 1–30;
  bool is never an integer parameter. Discount rate in (0,1]; terminal growth
  >−1 and less than discount rate; initial growth >−0.96 and ≤1. Fixed scenario
  deltas bear −0.04, base 0, bull +0.04; each resulting growth must be >−1.
  These are bounded pilot inputs, not economically recommended values.
- All bear/base/bull weights explicitly present, each [0,1], **exact Decimal
  sum one**. Do not silently normalise. Deltas remain fixed in this version
  because the existing function does not accept independent delta overrides.
- `tax_basis`: `explicit_rate` with finite rate [0,1], or `effective_rate` with
  null override and current positive pretax income and tax/pretax in [0,1].
  Tax losses do not imply benefits. No default 25% and no clipping/clamping.
- Nonempty `rationale` records an assumption explanation, not supported business
  prose. Source text/rationale is inert, bounded and excluded from grounded
  findings. No new free-form thesis or custom scenario narrative fields.
- Growth in year t is `h + (g-h)*(t-1)/(n-1)` when n>1. With n=1, h applies once.
  `FCFF_t=FCFF_(t-1)*(1+growth_t)`. Terminal value is
  `FCFF_n*(1+g)/(r-g)` and is discounted n years. Equity is EV−debt+cash only
  after bridge eligibility. Share-count dates/basis remain independently checked.
- Preserve existing engine rounding as recorded methodology: ratios four decimal
  places, monetary scenario totals whole base units, per-share two decimals,
  model-value gap four decimals. Weighted calculations use unrounded underlying
  scenario amounts; never recompute them from rounded displayed targets.
  Series/report values are decimal encodings of saved numerical results, not a
  promise of additional precision. Guard overflow and keep negative equity.

## Reuse boundaries

Reuse `financial_error`, `annual_pair`, `compute_ratios`, and the source-free DCF
math only after explicit local normalization/eligibility. Bind operating income
to the DCF EBIT input with provenance `operating_income_proxy`. Supply every
parameter and an eligible tax rate. Precheck dNWC so the existing function's zero
default is unreachable. Do not change existing CLI default behaviour in 4B.

Annual trend preparation must operate on local observations through a pure
function, not `get_historical_trend`'s provider/fixture acquisition path. Do not
call `peer_outlier_check` because it acquires peers. Add a separate local gate
that re-evaluates the declared scope and reconciles results against original
observations; old `validation.gate.assess` and old native recipes retain their
complete-research requirements. New deterministic templates reference exact
metric/evidence IDs; arbitrary imported prose never becomes a finding.
