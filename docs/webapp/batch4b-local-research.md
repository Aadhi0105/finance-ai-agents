# Webapp Batch 4B — calculate new local company research

**3 November 2026 · Bounded local implementation.**
[Product scope](batch4a1-fresh-analysis-scope.md) ·
[Engineering design](batch4a2-fresh-analysis-contracts.md) ·
[Financial semantics](fresh-analysis/financial-semantics.md).

## What now works

The private webapp can calculate a **new Agent 1 analysis from supplied structured
financial observations**. This is a distinct action from rebuilding a saved
`model.json`. The first supported input is one listed nonfinancial operating
company, consolidated annual statements, one ordinary-share basis and EUR/base
units. It performs no filing extraction, provider retrieval or language-model
inference. The old CLI and saved-report paths retain their original contracts.

The analyst can import an authorised local financial kit, inspect its accepted
version, choose a financial-summary request or explicitly reviewed scenario DCF,
confirm the exact version and scope, follow one durable job, and open its native
report. Importing never starts the analysis. Results always require financial
review; the interface does not grant financial approval.

The numerical report contains current figures, eligible margins and revenue
growth, supplied annual history/CAGR, dated quote comparisons and optional
conditional valuation. Interactive SVG charts use retained numerical observations,
with keyboard/touch selection and exact tables. The report is part of the app;
it is not embedded HTML. A separately verified original HTML export remains.

Raw peer sets, price/benchmark history, consensus, broker documents and arbitrary
prose are outside this new input format. Their report sections retain explicit
unavailability. Existing saved research still displays its retained supported
content. No buy/hold/sell recommendation is manufactured.

## Supported contracts and execution

| Boundary | Implemented identity |
| --- | --- |
| Package / preflight | Envelope and descriptor version 2; `agent1.financial-kit/1` |
| Payload | `keystone.financial-kit`, version 1 |
| Input validation | Receipt version 3; validator `financial-kit/1.0.0`; `analytical_execution=not_started` |
| Request / admission | Request version 3; immutable job version 4; `calculate-local-research/1` |
| Execution receipt | **Version 3**, existing states plus analytical commit fingerprint; old receipt 1 and close receipt 2 unchanged |
| Calculated source | `keystone.local-research-result`, version 1; source schema `agent1.local-analysis/1` |
| Native projection | `agent1-local-report/1.0.0`; existing report-view version 1 and private catalogue 3 |

Runtime schemas live in
[the research contract directory](../../keystone/workspace/onboarding/research/).
They have runtime identifiers, separate from the prospective document schemas.
Shape validation is followed by semantic, source-policy, identity, date, sign,
minimum-data and financial-method checks. New code reads the older record
families; unknown versions remain refused. No enum-only activation or in-place
rewriting of old saved models is used.

The first accepted kit atomically pins its declared listing/company scope across
datasets. This checks consistency with the registered company's ticker and later
versions, not independent exchange verification. Operator permission records
must cover the exact payload, every source and the intended local use before
retention/processing. Recheck permissions and immutable input hashes at admission,
claim, registration and private delivery. Source authenticity remains unverified.

Requests bind the exact dataset version/contract and complete plan. Valuation
acknowledgement hashes the selected source reference and canonical UTF-8 plan;
input/parameter changes reset review. It is an acknowledgement, not authenticated
analyst sign-off. Same-key retries preserve the original request; a changed plan
under that key conflicts. Lost responses do not trigger a new-key retry.

The local profile permits **zero provider/model requests and zero model output
tokens**, with a maximum 120-second operation. The shared internal offline
executor accepts those effective zero limits only while paid/live flags are
false; existing non-local operation limits are preserved. The child strips
credentials and denies network connection entry points. It uses a fixed plan
over supplied values, without fixture or acquisition fallback.

Local packages are capped at 1,000,000 bytes, requests at 8,192 bytes and calculated
evidence at 2,000,000 bytes. A new local job reserves 16,000,000 bytes within the
existing retained evidence ceiling, accounting for staged and delivered copies.
Existing lower capacity limits also apply. Capacity refusal preserves existing
inputs, jobs and reports; there is no automatic deletion or truncation.

## Financial behaviour

- Current revenue plus operating or attributable net income establishes the
  minimum useful summary. Zero remains an observation; missingness remains null.
- Comparable annual periods support YoY; CAGR requires at least three latest
  consecutive positive revenue observations. Supplied dates/values remain in
  history; gaps are not interpolated.
- Quote currency/share/date basis is explicit. The exact Decimal 5% cap/price/
  share reconciliation boundary is checked. Quotes older than seven calendar
  days withhold dependent comparisons and per-share values.
- Shared source-free ratio and FCFF/DCF functions calculate from normalized
  local inputs. The existing full provider-research publication gate is not
  repurposed to claim a complete research run for this narrower workflow.
- DCF needs every parameter explicitly, valid scenario weights, a selected tax
  basis, observed working capital, positive FCFF and an eligible complete equity
  bridge. There is no default tax rate or missing-working-capital substitution.
- Missing cash/debt/claims holds valuation while retaining the financial summary.
  Nonpositive FCFF makes this growth model inapplicable. Negative equity remains
  diagnostic and affected per-share/weighted targets are withheld.
- Scenario weights are assumptions. A model-value gap versus a dated quote is
  conditional arithmetic, not a forecast return or broker price target.

## Saved evidence and recovery

Each private run registers calculated `payload.json`, `financial-kit.json`,
`analysis-request.json`, `input-contract.json`, `report_REVIEW.html`, retained
native series/view, and `analysis-commit.json`. The report's evidence page exposes
verified downloads. Its source pointers, section restrictions and producer/plan/
input lineage remain inspectable. Viewing writes nothing and performs no new math.

The complete result is prepared privately, checked, flushed and atomically
promoted. Its analytical proof inventories artifacts without a circular self/
catalogue hash. Partial staging never becomes a visible result. A promoted
complete proof can support explicit **delivery-only** recovery, including an
interruption before the supervisor recorded completion. Recovery does not call
the calculator or renderer and does not make a second attempt.

This is the reason for execution receipt **3**, a refinement of 4A.2's original
schema-1 reuse proposal: its `analysis_commit_sha256` can prove saved analytical
completion while the original operation remains `outcome_unknown`. It preserves
that uncertainty rather than falsely changing the operation to completed. The
registered report/job still requires review. Old execution receipts are unchanged.

Quiesced private snapshots include the new versions, listing pins, requests,
proofs, attempt inputs and reports through the existing inventory. Restore uses
a new folder/token, retains immutable identities, holds never-started queued
jobs, and requires explicit current-code/source rechecks before release. The
new-format restore/release test confirms one attempt after release. This remains
local restore evidence; independent backup and clean-machine recovery are pending.

## Browser demonstration

The isolated demonstration is at **http://127.0.0.1:8858/**, using
`output/fresh-analysis-4b-preview/workspace`. It contains one fictional company,
one dataset, two accepted input versions and two browser-requested reports:

| Case | Recorded result |
| --- | --- |
| Complete kit | Revenue EUR 1bn, operating margin 12%, revenue growth 11.11%; independent one-year DCF scenario values EUR 96/100/104 per share, weighted EUR 100; review-required |
| Missing cash | Same usable summary; valuation and EV multiple held, no cash-zero substitution; review-required |

Both jobs have one claimed attempt and zero paid usage. Source dates/classification
remain separate from processing time. Screenshots and browser checks are under
`output/fresh-analysis-4b-preview/`; generated evidence, tokens and private state
are ignored by Git. The tracked native-reader fixture contains fictional data
only and no access token.

To reopen the retained demonstration from the repository root after stopping its
existing server:

```bash
.venv/bin/python -m keystone.workspace serve \
  --workspace output/fresh-analysis-4b-preview/workspace \
  --port 8858 --enable-imports --enable-job-admission --enable-worker
```

Connect with the current local `control/access-token.key` file. Reusing the
running window avoids the existing-session lock. Do not delete lock files.

For a **new** fictional demonstration, first prepare a fresh private workspace,
serve it, then run the operator-only
[preparation helper](../../scripts/prepare_local_research_preview.py) with its
`--workspace` and `--port`. It registers scoped fictional permission evidence and
imports through actual protected loopback HTTP, with proxy forwarding disabled.
It starts no jobs. It must not be used to claim permission for real inputs.

## Verification and remaining scope

The focused [local research tests](../../tests/test_workspace_local_research.py)
cover independent arithmetic, signs/zero/missingness, tax, quote age and exact
5% boundary, growth fade, no acquisition, request/review binding, byte reservations,
actual worker/native delivery, interrupted completion, delivery-only recovery,
source revocation and snapshot/restore/release. The frontend has a separately
captured fictional recipe/job fixture and refusal tests for wrong source family,
recipe, approval and missing evidence.

Recorded verification: **1,454 Python tests passed** (547.94 seconds), including
42 local-research cases; **282 frontend tests passed**, TypeScript checks and
production build passed. **Eight visible browser checks passed**, including
exact-value keyboard selection, parameter-review reset, held valuation, native
SVG/no embed, and bounded 1,280/320 CSS-pixel layouts. All 16 registered artifacts
across the two actual browser-requested reports were re-read and hash-verified.
See the [machine-readable evidence](../../references/acceptance/workspace-local-research-2026-11-03.json). The design matrix remains the broader 4D checklist; it is
not automatically marked all-pass by schema/example or a two-case browser run.
In particular, broad maximum-volume/disk-fault combinations for the new profile,
real-company human interpretation, source-use authorisation and independent
recovery retain separate acceptance requirements. No production release gate
is advanced by this implementation.

Next product work is **4C**, separately scoped new monitoring, event and news
processing. The existing source-rights review and deferred external-drive decision
remain unchanged.
