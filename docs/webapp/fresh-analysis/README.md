# Fresh-analysis contract pack — 4A.2

**Design artifacts only · 3 November 2026.**
The [engineering specification](../batch4a2-fresh-analysis-contracts.md) defines
the new local Agent 1 workflow after [4A.1](../batch4a1-fresh-analysis-scope.md).
[4B](../batch4b-local-research.md) now implements the corresponding bounded
runtime workflow. At the 4A.2 checkpoint the importer refused these new versions;
the document schemas and examples below remain design artifacts rather than
accepted runtime versions or real financial results.

- [Full prospective package schema](financial-kit.schema.json): envelope 2,
  `agent1.financial-kit/1`; closed identity, sources, annual periods and quote.
- [Prospective request schema](analysis-request.schema.json): request 3,
  version-pinned source, complete plan and bound valuation acknowledgement.
- [Prospective validation receipt](validation-receipt.schema.json): receipt 3,
  accepted input readiness with analytical execution explicitly not started.
- [Prospective analytical result schema](local-result.schema.json): result 1,
  lineage, typed values/series, derivation pointers, section holds and review gate.
- [Mandatory financial semantics](financial-semantics.md): signs, dates, missing
  values, applicability, shared-math reuse and unsupported groups.
- [Execution/recovery specification](execution-and-recovery.md): exact binding,
  new immutable record/receipt versions, fixed profile, atomic proof, limits,
  private reads, delivery-only recovery and local backup inventory.
- [39-row acceptance matrix](acceptance-matrix.md): fixed runtime expectations,
  **all pending**; design checks below grant no runtime acceptance.

## Fictional examples

| File | Purpose |
| --- | --- |
| [Complete kit](examples/complete-kit.json) | Northstar's three annual periods and separate dated quote; no provider retrieval |
| [Valuation request](examples/valuation-request.json) | Complete one-year DCF plan and calculated source/plan acknowledgement hashes |
| [Summary-only request](examples/summary-only-request.json) | Same version, valuation/review explicitly null |
| [Expected valuation result](examples/expected-valuation-result.json) | Expected fictional evidence shape and independent benchmark values; not an actual engine output |
| [Missing-cash kit](examples/missing-cash-kit.json) | Same current summary, explicitly missing current cash |
| [Missing-cash request](examples/missing-cash-request.json) | Distinct fictional version and newly bound acknowledgement; confirms the held requested valuation |
| [Expected missing-cash result](examples/expected-missing-cash-result.json) | Summary remains useful, DCF/EV multiple held; no cash-zero substitution |

Entity, dataset, workspace and permission IDs are illustrative and are not
registered resources. Classification is synthetic. Input/plan/request digests
are calculated from the supplied examples; policy, producer, receipt and contract
digests are explicitly fictional placeholders. **No permission grant, live case,
accepted version, actual calculation receipt or real job is represented.**
Source locators describe fictional tables, not inspected issuer filings.

The examples cover the fixed supported output set: current revenue/operating/
net income, three margins, YoY, revenue CAGR, dated annual P/E and EV/operating-
income, FCFF/scenario equity and per-share values, weighted value/gap, revenue
and net-margin history. Available figures link to named derivations and input
pointers. Unknown/held fields stay null. Engine templates/series/registration
must be implemented and checked separately; these files are not native-view
responses or drop-in production fixtures.

## Repeatable documentation verification

From the repository root with existing development dependencies:

```bash
.venv/bin/python docs/webapp/fresh-analysis/check_design.py
```

The checker uses only local design files, `jsonschema`, Python's standard library
and Decimal. It writes no workspace, database or report and imports no engine,
provider or agent. No network requests or schema fetching occur. It checks:

- Draft 2020-12 schema validity, closed shapes, date-format checks and all seven
  examples; request/result plan definitions agree.
- Selected malformed variants including unsupported versions/fields, unavailable
  value contradictions, malformed observations, false review and capability flags.
- Sample source references, periods, plan/request/source/review digests and
  input-to-result derivation/metric/series references.
- Independent one-year end-of-year DCF, net-debt/per-share/weight/gap, ratios and
  CAGR arithmetic for the fictional benchmark; explicit missing-cash holds.

This checker is a **sample consistency check**, not the future semantic validator.
For example, arbitrary kit period, permission, sign or rate violations can pass
JSON Schema and still require runtime rejection. A genuine implementation needs
the full semantics, counterexamples, faults and measured acceptance matrix.

## Recorded verification — 3 November 2026

The four schemas and all seven examples passed. **45 malformed structural
variants were refused**. Sample source/derivation/series references, generated
plan/request/review hashes, independent Decimal valuation/ratio/CAGR arithmetic
and the missing-cash holds matched. Four counterexamples deliberately show where
schema validity still needs semantic rejection. All 39 runtime rows remain
pending. No production
Python/frontend regression or new browser execution run is required for these
documentation/schema/example changes. The frozen 4A.1 prototype remains separate
and does not gain new capabilities. No production source or runtime schema is
changed by this pack.
