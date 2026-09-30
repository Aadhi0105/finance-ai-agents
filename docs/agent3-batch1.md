# Agent 3 Batch 1: bounded historical event analysis

> Follow-up: [Batch 2](agent3-batch2.md) supersedes the live-adapter, CLI configuration and recovery limitations recorded below. This file preserves the Batch 1 milestone.

This batch fixes the event-study calculation boundary and blocks unsupported publication. It implements the financial/statistical portion of the September 2026 audit. News scoring and the live LLM peer adapter remain later work.

## Supported behavior

- Earnings events only. The positional `event_type` is a hypothesis/display ID, not a selector for mergers, guidance or arbitrary news events.
- Fixed daily windows: **250 estimation returns [-280,-31]**, then the event's **three returns [-1,+1]**. The old README's [-250,-30] convention was incorrect.
- OLS abnormal returns and the historical **equal-event-weighted** CAR mean retain full precision internally. Firms with more accepted events contribute more weight; both event and issuer counts are reported.
- Exact Student-t p-values, cutoffs and intervals share one implementation with Agent 2 drift. Significance uses the unrounded p-value. Confidence interval levels are honored.
- Input checks reject booleans, missing/empty/wrong-size windows, nonfinite values, impossible total-loss-or-worse simple returns, and returns above 100 (a deliberate extreme-data review boundary, not a claim that such corporate actions cannot occur). A singular/nearly constant benchmark cannot silently become beta zero.
- Duplicate issuer/anchor records and overlapping windows within an issuer are rejected and counted. Cross-issuer overlapping windows and repeated issuers make inference unavailable.
- Data from at least ten distinct, single-event issuers with nonoverlapping windows, complete review evidence and usable variance can receive independent-event inference. This is a **minimum eligibility rule, not a power guarantee or proof of independence**. Sampling assumptions still require a documented review.
- Pooled quarterly panels remain useful descriptive history, but get **no t-test/sign-test claim and no iid bootstrap interval**. Clustered/block inference is explicitly unsupported in this bounded batch; no small-cluster certainty is invented.
- Historical quantiles are not forward calibration. No output is called CALIBRATED. Held runs retain their distribution only under `diagnostic_distribution`; the normal distribution field is empty. Brief, scan and CLI enforce the same hold.

## Live date, price and benchmark policy

Yahoo earnings timestamps retain their original timezone and provenance. They are converted to the listing timezone before date extraction. They remain **unverified**: a timezone conversion cannot repair a wrong provider estimate. A sourced reviewed event list can replace the provider's selection. This prevents the ASML regression where a July 13 provider value selected a window excluding the issuer's July 15 release.

A confirmed `before_open` or `during_session` release anchors on the first observed trading session on/after its exchange-local date. An `after_close` release anchors on the following observed session. A weekend never snaps backward. Mapping more than four calendar days is rejected. An unknown session is held. Original release timestamp, effective anchor, all window dates, source/review evidence, benchmark, return basis and timezone are carried into per-event results.

Price dates must be unique/ascending and prices finite/positive. Both series are aligned by date. Asymmetric missing bars and gaps containing an intervening weekday are flagged; that includes holidays until the calendar is independently resolved. **There is no claim of a complete exchange-holiday calendar.** Such cases remain under review rather than silently counting a multi-session return as a normal one-day observation. Live fetching excludes the current local day's potentially unfinished daily bar.

Known suffixes supply an unverified default benchmark and timezone; unsupported suffixes require a study plan. A plan must explicitly identify compatible stock/benchmark return bases (`price_return` or `total_return`) and provide the review source. `auto_adjust=True` is requested only for a declared total-return series. The reviewer must check what an index actually measures: auto-adjusting a price index does not turn it into a total-return index. A reviewed plan is a recorded **human attestation**, not automatic issuer, benchmark or economic-comparability verification.

Ordinary live runs generate diagnostic controls at least 30 calendar days from supplied earnings dates. Those controls are unverified and cannot become a clean placebo test. Reviewed controls may be supplied, but a supplied control near an earnings date is rejected. Source completeness and other contemporaneous events require review. An unavailable/degenerate placebo cannot pass; a valid nonsignificant control is described as undetected, not proof of no effect.

## Commands

From the repository root, using its environment:

```sh
.venv/bin/python -m agent3.run_live ASML.AS semicap_earnings --peers ASM.AS BESI.AS
```

This commonly produces a **held descriptive** result because provider dates, generated controls, comparability and repeated-firm independence are unresolved. A successful fetch is not an approved study. The target's inclusion and all failed/excluded peers are reported.

For an explicitly reviewed plan:

```sh
.venv/bin/python -m agent3.run_live ASML.AS semicap_earnings --peers ASM.AS BESI.AS --study-plan path/to/reviewed-plan.json
```

The plan's company keys must match the exact requested uppercase target-plus-peer universe. Multiple listings cannot masquerade as separate issuers. Explicit peer lists are bounded and validated. The model proposal method defect from audit F06 is deferred to Batch 2; use `--peers` for live work in this batch.

Exit statuses: 0 = eligible historical result; 2 = refused at assembly; 3 = held for review. Configuration exceptions are still raised; broader recovery and operator-facing error handling are Batch 2. The CLI does not load `.env`; set environment variables explicitly when needed. MCP is optional through `AGENT_STATS_VIA_MCP=1`; the same pure event contract is enforced for nested returns locally and over MCP.

## Reviewed plan schema

The following describes fields, not a preapproved plan. Do not copy placeholder review assertions into a real study.

```json
{
  "schema_version": 1,
  "event_class": "earnings",
  "hypotheses": ["semicap_earnings", "another_planned_hypothesis"],
  "comparability_review": {
    "reviewed_by": "Reviewer name",
    "reviewed_at": "2026-09-30T00:00:00Z",
    "rationale": "Document business mix, instrument identity, reporting cadence, size and the chosen weighting",
    "source_url": "https://issuer-or-research-source.example/evidence"
  },
  "sampling_review": {
    "reviewed_by": "Reviewer name",
    "reviewed_at": "2026-09-30T00:00:00Z",
    "rationale": "Define selection, independent sampling assumptions, predeclared universe/windows and exclusions"
  },
  "companies": {
    "ASML.AS": {
      "issuer_id": "stable-issuer-identifier",
      "benchmark": "^AEX",
      "timezone": "Europe/Amsterdam",
      "stock_return_basis": "price_return",
      "benchmark_return_basis": "price_return",
      "benchmark_review": {
        "reviewed_by": "Reviewer name",
        "reviewed_at": "2026-09-30T00:00:00Z",
        "rationale": "Why this benchmark and return basis fit this listing",
        "source_url": "https://benchmark-source.example/methodology"
      },
      "reviewed_events": [
        {
          "release_timestamp": "2026-07-15T07:00:00+02:00",
          "session": "before_open",
          "reviewed_by": "Reviewer name",
          "reviewed_at": "2026-09-30T00:00:00Z",
          "rationale": "Confirm actual timestamp/session from the issuer; date-only guesses are insufficient",
          "source_url": "https://issuer-source.example/release"
        }
      ],
      "reviewed_controls": []
    }
  }
}
```

Supply a company record for every selected ticker. `reviewed_controls` uses the same timestamp/session/review fields and documents why that control date is suitable. If no reviewed events are supplied, the provider dates remain unverified. Empty controls trigger the unverified diagnostic generator. The illustrative single-company plan above cannot meet independent-event inference requirements.

A plan declares the complete family of hypothesis IDs; the gate uses its size for Bonferroni adjustment, retaining full precision. The legacy numeric count cannot replace a plan or undercut its size. Re-running peer selections/windows after looking at results is exploratory; changing a JSON declaration is not a preregistration service. Full durable run evidence and replay remain Batch 4.

## Acceptance coverage

Tests cover exact critical values and decisions across degrees of freedom, independent NumPy OLS, malformed/boolean/nonfinite input, duplicates and overlapping anchors, repeated-firm simulations, no iid interval for dependent panels, timezone and release-session anchors, the issuer-date override seam, exact window endpoints, data-gap flags, benchmark and plan contracts, declared multiplicity, held renderer/CLI behavior, nullable inference in state, and actual local/MCP parity.

Existing tests that expected weekend releases to move backward were corrected to the new explicit anchoring policy. The formerly conditional publication assertion now always checks the actual held rendering. Existing scorer tests retain their Track B scope.

Remaining batches: working audited LLM peer proposal and complete operator recovery (2); news correctness (3); durable bundles/replay, full state-conflict semantics and showcase disclosure/export (4). Calendar uncertainty, unverified economic comparability and unresolved dependence stay visible and block approval until supported; they do not receive optimistic fallback values.

## Validation recorded for this batch

- Full local suite: **586 passed** (Python 3.11.9); 49 added regression cases.
- Live ASML/ASM/BESI check: **36 events, 3 issuer groups**, held for review. Unknown significance remained NULL in temporary DuckDB state; the normal scenario distribution was suppressed.
- The observed ASML provider timestamp `2026-07-13T20:00:00-04:00` converted to July 14 in Amsterdam and remained unverified. The separate sourced-override regression anchors the issuer's July 15 date; conversion alone is not presented as issuer verification.
- Local/MCP parity passed for valid independent evidence, controls and malformed nested boolean returns.

Older database rows are not retroactively reinterpreted; this batch preserves unknown inference for new records. Complete history migration, immutable replay bundles and broader state recovery remain later work.
