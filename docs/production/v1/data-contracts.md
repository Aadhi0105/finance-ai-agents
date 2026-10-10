# v1 data contracts and candidate inventory

Status: inventory baseline with a strict Batch 2 snapshot-contract validator;
not provider permission or new issuer certification. See [Batch 2 commands](batch2-storage.md).
See [specification](specification.md), [matrix](acceptance-matrix.md), and
[decisions](../decisions/0001-production-v1-boundary.md).

## Shared contract to establish

Each released input must identify the issuer and listing separately where relevant,
source/provider, retrieval instant, observation/reporting period, available publication
instant, units, currency, transformation/formula version, and source reference/hash.
Retrieval time must not substitute for a missing publication time. Preserve unknowns.

Record provider values separately from normalized values and adjustments. Define
rounding/tolerances per source resolution before comparison. Agent 4 ledger arithmetic
uses exact cents; an issuer filing displayed in thousands needs a different input
reconciliation tolerance. Do not adopt one arbitrary epsilon for all finance.

Missing, stale, changed-definition and corrected observations require explicit outcomes.
No silent fixture fallback, cross-period substitution, currency conversion, share-class
substitution or reclassification of history as consensus is permitted.

## Inventory

| ID | Dataset / source | Current evidence | Intended v1 use | Outstanding acceptance |
| --- | --- | --- | --- | --- |
| D01 | Agent 1 bundled ASML/peer fixtures | `fixtures/ASML.AS.json`, `ASM.AS.json`, `BESI.AS.json`, `LRCX.json` | Offline demonstration/regression only | Label synthetic evidence; fixtures do not approve live coverage |
| D02 | ASML.AS FY2025 issuer and provider comparison | [Issuer reference](../../../references/issuer/ASML.AS-2025-12-31.json), [provider reference](../../../references/issuer/ASML.AS-provider-2026-09-26.json) | Candidate Agent 1 anchor case | Recheck retained evidence availability, dated prices/shares and proposed release period |
| D03 | AAPL, RIVN, BRK-B historical live acceptance | [Committed summary](../../../references/acceptance/agent1-v1-2026-09-27.json) | AAPL candidate positive workflow; RIVN/BRK-B negative/sector boundary cases | Broader periods and independent source reconciliation; not blanket issuer admission |
| D04 | Stadler FY2025 annual monitoring | [Watchlist](../../../watchlists/stadler-annual.json), [reference](../../../references/monitoring/SRAIL.SW-2025-12-31.json) | Current ratio, interest coverage and net-leverage proxy under analyst policies | Supervised repeated-observation trial, exact period retention and later-period reference policy |
| D05 | ASML/NVIDIA issuer-dated event plans and provider prices | [ASML plan](../../../fixtures/agent3_closure/asml-as-source-plan.json), [NVIDIA plan](../../../fixtures/agent3_closure/nvda-source-plan.json) | Descriptive study candidates; existing plans are validation-only | Price/action/benchmark review, retained source inventory, expanded boundary cases |
| D06 | Yahoo search headline records for ASML/NVIDIA | [Populated acceptance](../../agent3-live-news-recovery.md); raw outputs local/ignored | Bounded headline/lexical workflow | Data permissions; labelled relevance/duplicate/freshness benchmark and thresholds |
| D07 | Monitoring, event, news and P&L fixtures | `fixtures/covenants.json`, `events.json`, `news.json`, `pnl.json` | Deterministic boundary tests | Never relabel fixture behaviour as live financial acceptance |
| D08 | Agent 4 synthetic close and independent control ledger | [June request](../../../fixtures/agent4/close-june.json), [control ledger](../../../fixtures/agent4/closure/control-ledger.json) | Exact accounting, versions, failure and restore tests | Preserve distinction from confidential company pilot |
| D09 | Authorised company budget/actuals | User confirmed unavailable on 10 October 2026 | Required for Agent 4 production designation | Data owner permission, mapping, period coverage, secure handling and controller acceptance |

This list selects practical starting cases from existing work. Final released
issuer/period coverage remains a Batch 4 decision. News search availability is not
archive completeness. Existing selected source checks are not general source guarantees.

## Source rights and external services

Yfinance/Yahoo prices, statements and news are currently integration dependencies.
Existing acceptance does not establish permitted production retention or redistribution.
Record permission/terms evidence for the actual proposed use before approving each
source. If unsuitable, choose a permitted replacement and validate its adapter; do
not assume endpoint substitution is an equivalent financial dataset.

Issuer-source access and retention also need an explicit inventory. Anthropic live
calls require approved input handling and cost settings. Pinned FinBERT weights,
optional model dependencies and model licence/accuracy acceptance are deferred;
lexical diagnostic use remains labelled and subject to its own input permissions.
This document is not a legal opinion or a fresh review of external terms.

## Freshness and mutation rules

- Agent 1: separately inspect price, statement and estimate dates; missing dates
  remain review reasons. Set freshness limits per data family before acceptance.
- Agent 2: current Stadler profile uses a 550-day maximum reporting-period age and
  requires FY2025 issuer reconciliation. This existing policy is not proof of interim
  coverage or an approved general freshness SLA. New periods require reviewed references.
- Agent 3: record exchange timezone/session, return basis, query, aliases, cutoff,
  exclusions and text scope. Default news freshness is seven days; evaluate whether
  it suits the pilot before accepting it.
- Agent 4: full-year budget and complete closed YTD actuals must share explicit
  entity/date/topology contracts. Later deltas preserve winning observation lineage.

## Benchmark preparation

Freeze the candidate dataset manifest, source versions, expected calculations,
tolerances, exclusions and evaluation rules before running the final candidate.
Use independent calculations for financial oracles. Keep evaluation examples distinct
from examples used to tune rules where a measured quality claim is made. Record
false inclusions/exclusions for news and false alerts/missed conditions for monitoring.
Thresholds and sample coverage are open in D-05; do not invent pass rates after seeing results.

Confidential D09 inputs and raw model/provider records must not be committed by
default. Store permission-scoped manifests and redacted evidence references in the
release register; keep sensitive artifacts in the protected storage design.

See [preliminary source-use review](source-use-review.md) for current terms evidence
and unresolved access, retention, model-processing and sharing permissions.
