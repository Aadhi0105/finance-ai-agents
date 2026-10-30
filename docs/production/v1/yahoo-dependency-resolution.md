# Yahoo dependency: resolution plan and provider assessment

Assessed 13 October 2026 for one individual's private personal evaluation of
Keystone. The user confirmed **no existing data licence**. Status: **awaiting
provider entitlement and coverage evidence; dependency not yet resolved**.
This is an engineering procurement assessment, not a legal approval.

**30 October routing update:** the [final Yahoo enquiry](yahoo-finance-enquiry.md)
records a verified Finance Help Contact Us entry point requiring a Yahoo ID.
The developer invitation below remains historical search-index evidence; its direct
submission form was not verified in the assistant's live browser inspection.
The subsequent user screenshot evidenced the general Email form; the user reports
submitting the short routing request and losing its case number. A substantive
reply/API-team referral remains pending; the detailed enquiry is still unsent.

## Recommended decision

Seek an applicable Yahoo Finance API agreement first. The 13 October assessment
identified a developer/API interest invitation in the
[official plan comparison FAQ](https://finance.yahoo.com/about/plans/compare/);
use the 30 October routing update above for the next contact step.
An enquiry route is not a licence or a promise of API availability. The developer
invitation was available through the search index; direct retrieval returned
HTTP 429, and its linked form destination was not verified. Do not guess a
contact address or buy a consumer subscription as a substitute for API rights.
An eventual API grant must identify authorised endpoints; it does not automatically
approve existing yfinance calls.

Use EODHD as the first alternative to evaluate if Yahoo cannot supply a suitable
offering. Obtain written scope and sample coverage before choosing or purchasing.
No replacement is selected and no budget has been authorised. The review-ready
[provider enquiry](provider-permission-enquiry.md) contains the actual intended
workflow and questions. The detailed enquiry remains unsent; the user-reported
short Yahoo routing submission is recorded in the update above.

## Comparison

| Route | Evidence and limitation | Decision |
| --- | --- | --- |
| Yahoo Finance developer enquiry | Historical indexed FAQ invites developer/API interest; its direct form is unverified. The user reports submitting a short routing request through general Finance support. No account-specific Finance grant, endpoint list, quote or retention permission established. | Await referral or response: potentially avoids migration, but may still require an official adapter. |
| EODHD | [Terms](https://eodhd.com/financial-apis/terms-conditions) permit nonprofessional personal storage and analysis, with restrictions on distribution. Eligibility is framed around personal investment activities; software evaluation needs confirmation. Backup, news and post-cancellation treatment remain unresolved. [Pricing](https://eodhd.com/pricing) lists monthly EOD at $19.99, fundamentals at $59.99 and All-in-One at $99.99; fundamentals alone excludes EOD prices. | Preferred fallback for a written quote and sample assessment. Confirm the complete endpoint package, taxes, add-ons and downstream rights; these prices are not a purchase recommendation. |
| Twelve Data | [Terms](https://twelvedata.com/terms), sections 2.3(g), 12.5 and 16, constrain retention and require deletion after termination, with limited exceptions. Exact instrument and field coverage remains unverified. | Secondary candidate. Keystone's historical evidence and backups would require an expressly suitable retention arrangement or a separately designed deletion lifecycle. |

Prices and public terms are review-date observations, not negotiated entitlements.
An exchange coverage claim does not prove coverage of a particular security,
statement field, consensus series or news publisher. EODHD's source/accuracy
qualifications also require endpoint-level provenance checks before financial use.
Do not silently substitute an indicative/CFD series for the requested equity or index.

## Minimum technical fit

These requirements come from Keystone's existing contracts, not provider promises.

- **Identity:** ASML on Euronext Amsterdam, Stadler Rail on SIX in CHF, and NVIDIA
  in the US; explicit listing, currency, exchange and symbol mapping. For the
  existing peer workflow, also assess ASM, BESI and Lam Research. No ADR substitution.
- **Annual financials:** aligned income statements, cash flows and balance sheets;
  revenue/prior revenue, gross profit, operating income/EBIT, net income, tax,
  pretax income, depreciation/amortisation, capex, free cash flow, debt, cash,
  working-capital change and share counts. Preserve period, currency, units,
  restatements and nulls. Reconcile capex and working-capital signs explicitly.
- **Prices and events:** dated historical prices, splits/dividends and documented
  adjustment basis; earnings/event dates with provenance. Assess the exact AEX
  and S&P 500 price-return benchmark series separately, including index rights.
- **Consensus:** period-specific revenue/EPS estimates, analyst counts, targets
  and as-of dates where supplied. Missing information must remain unavailable,
  with the existing review holds, rather than fabricated defaults.
- **News:** headlines, summaries/snippets if permitted, publisher URLs and
  publication timestamps for the intended issuers. Rights to price data do not
  approve news text. Publisher restrictions must follow the retained records.
- **Operations:** documented rate limits, error handling, timestamps and stable
  source identifiers sufficient for reproducible reports and offline replay.

Agent 1 uses financial, price, peer and consensus data. Agent 3 uses market/event
and news feeds. Agent 2 consumes research baselines, so their provenance follows
through monitoring. Agent 4's company budget/actuals dependency is separate.
Replacing Yahoo does not clear issuer-filing, event-source, benchmark, news-publisher
or company-data permissions automatically.

## Implementation after a suitable offer

1. Record the governing account/region agreement, exact datasets/endpoints,
   authorised purpose, retained fields, backups, retention/termination obligations,
   attribution, reviewer and date. Keep private agreements outside public Git.
2. Present the complete recurring cost and restrictions for user approval before
   purchase. Obtain an authorised sample covering the three primary listings.
3. Implement a provider adapter behind the existing normalized contracts. Remove
   implicit Yahoo fallback from the selected workflow and make unsupported
   coverage visible. Preserve issuer reconciliation and financial review holds.
4. Validate sample financials against issuer evidence; verify listing/currency,
   units, periods, sign conventions, adjustments, missing estimates, stale data,
   rate-limit failures and news timestamps/deduplication. Validate local report
   rebuilding and backup/restore under the agreed retention rules.
5. Run a bounded, explicitly authorised live acceptance run. Update source
   permission records and only those release gates whose evidence is complete.

External model transfer is excluded from this proposed initial workflow. Existing
live model modes can transmit source data to Anthropic; local output paths alone
do not make those modes local-only. This document adds no runtime enforcement.

## Closure evidence required

The dependency is resolved only when the chosen route has an applicable grant,
verified required coverage (or explicit accepted scope reductions), approved cost,
a tested adapter and an evidence-backed retained-data lifecycle. A sales response,
paid key or successful API call alone is insufficient. Until then, continue the
synthetic/offline rehearsal; V1-DAT-001 remains blocked.
