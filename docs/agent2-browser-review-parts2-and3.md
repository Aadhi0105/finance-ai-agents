# Agent 2 browser review — Parts 2 and 3

Reviewed 3 October 2026. This completes the review begun in
[Part 1](agent2-monitoring-review-part1.md). This is a review with findings,
not an implementation of the missing browser workflows.

## Scope and result

Part 2 covers correction approval, rejection, effective state, preserved original
reports, and failed/successful triage recovery. Part 3 covers the existing showcase
and review evidence at desktop and narrow widths, long names, empty states,
scenario selection, links and illustrative-data disclosure.

The sampled correction/recovery behavior passed. Browser acceptance for actual
Agent 2 operations remains incomplete: the product exposes CLI text, JSON and
saved state, while the showcase illustrates scenarios. The temporary HTML evidence
wrapper is not a production report or approval interface.

No production state, real-company approval, external provider or paid model call
was used. All mutations were in isolated synthetic databases. No application code
was changed by this review.

## Part 2 — correction and recovery checks

The existing recovery regression suite passed: **18 tests** in
`tests/test_agent2_recovery.py` using `pytest -q -o addopts=''`.

A separate local exercise ran actual fixture cycles and CLI commands against two
isolated databases, with a deliberately long synthetic company name. The history
started with values 1, 4 and 5 against a maximum threshold of 3. A subsequent
candidate proposed correcting the second observation from 4 to 2.

| Check | Observed result |
| --- | --- |
| Pending correction | Review output identifies the item, candidate date/value, previous value and review ID. |
| Approval | Effective history becomes 1, 2, 5; current classification changes from WIDENING to NEW_BREACH. |
| Rejection | Effective history stays 1, 4, 5 and remains WIDENING; an exact repeated candidate is identified as rejected. |
| Attribution | Decision records contain the action, reviewer and reason. This is local attribution, not authenticated identity. |
| Original evidence | Original saved run records remain unchanged after either decision. |
| Cycle advancement | Approval/rejection and retries do not advance the next cycle. |
| Failed triage | An injected scripted-model failure produces a failed result with a retained audit artifact. |
| Successful retry | A scripted retry succeeds with a distinct audit artifact and explicitly identifies saved cycle 3 as original evidence, not current state. |
| Empty pending queue | CLI output is exactly `[]`. |

The existing tests also cover stale/conflicting decisions, required attribution,
transaction rollback and frozen retry context. These are regression checks, not
proof of a browser approval workflow or a fresh live-model run.

### Presentation findings

1. **High: no browser correction or recovery workflow.** Users cannot inspect a
   saved pending correction, compare observations, review the consequence, or
   navigate decision/retry history through the existing showcase. The corresponding
   CLI capabilities exist. A future UI should make the review ID, observation date,
   old/new values, threshold direction, reviewer/reason and outcome explicit.
2. **Medium: effective state and original reports need an explanation together.**
   Approval intentionally changes effective history while preserving original
   reports. The sampled current-state line shows value, threshold, classification
   and cycle but does not provide an adjacent observation date or decision link.
   A report should distinguish original-as-issued from current-effective state and
   link the decision that explains the difference.
3. **Medium: decision output is too dense for a routine reader.** Full before/after
   diagnostic JSON preserves evidence but repeats substantial detail. Present a
   short comparison and outcome first, with raw evidence available separately.
4. **Medium: retry attempts need a readable timeline.** Separate failed/completed
   artifacts preserve history, but there is no browser timeline connecting them to
   their saved cycle. Preserve the existing original-evidence warning and show
   attempt status, time and audit link without suggesting a new monitoring cycle.
5. **Low: the empty queue has no explanatory state.** `[]` is valid machine output
   but does not tell a browser reader that there are no pending reviews. Provide
   an explicit empty-state message without changing the JSON contract.

## Part 3 — browser layout and usability

Inspection used the Codex in-app browser against a localhost server restricted to
known review/showcase files. Requested viewport overrides of 1280 and 390 produced
measured CSS viewport widths of **984 and 300 pixels** respectively; the results
below use those measured widths. Overrides were reset after inspection.

| Surface/check | Result and limitation |
| --- | --- |
| Existing Agent 2 showcase, desktop | Document scroll width equals viewport width (984); no horizontal page overflow in the inspected scenario. |
| Existing showcase, narrow | Scroll width equals 300; cards and scenario heading fit the sampled layout. |
| Scenario selection | Both breach and quiet scenarios could be selected; the quiet panel displayed the Interest Coverage heading. |
| Long scenario title | Quiet scenario heading stayed within the narrow panel; measured selector width was about 252 pixels. |
| Recovery evidence wrapper | Scroll width equals viewport width at both 300 and 984; long synthetic company names wrap. This validates only the wrapper CSS. |
| Tables | No actual Agent 2 browser data table exists in the reviewed workflow; responsive table acceptance remains untested. |
| Empty/retry states | Visible in the wrapper as raw command output/JSON, not designed product states. |
| Scope link | The visible link targets `about-this-showcase.md`, which exists locally. Browser navigation returned `ERR_BLOCKED_BY_CLIENT`; destination rendering is not verified. |
| Disclosure | The showcase labels its illustrative scope, but the local phrase “One spine, verified” can imply verification of placeholder results. |

No horizontal overflow does not establish usability. The wrapper is a long series
of raw payloads, with escaped Unicode and repeated diagnostics, rather than a
scannable decision history. Screenshots and DOM inspection support only the
sampled in-app-browser layouts. This was not a cross-browser, screen-reader,
keyboard-accessibility or exhaustive breakpoint audit.

### Layout and wording changes recommended

- Provide a real saved-run report before treating the showcase as operational UI.
- Use readable company/metric names, observation dates, units and direction-aware
  thresholds; keep raw identifiers available in evidence details.
- Place a clear illustrative-data label next to the Agent 2 demo results and revise
  “One spine, verified” so it cannot imply that those placeholders are live output.
- Provide a browser-readable scope destination and recheck navigation; the current
  client block does not by itself prove a repository defect.
- Test responsive tables, decision timelines and empty/error states once those
  actual components exist. Retain the existing narrow-layout containment.

## Consolidated order of work across all three reviews

1. Implement a read-only saved-run browser report with prominent routine, held,
   unavailable and error states, correct periods and direction-aware thresholds.
2. Add an original/effective comparison and decision/retry history with evidence
   links. Any interactive approval UI needs explicit decision context and outcome;
   it should use the existing validated recovery operations.
3. Correct the showcase's cycle-number inconsistency identified in Part 1 and its
   local verification wording; improve empty states and evidence presentation.
4. Repeat desktop/narrow acceptance on the actual implemented reports, including
   long names, tables, links, empty queues, rejected corrections and failed retries.

Parts 1–3 are complete as reviews. The presentation gaps remain open; passing the
recovery checks does not mean the browser workflow is complete.

## Local evidence

Ignored directory: `output/agent2-parts23-review/`.

- `exercise.py`: reproducible synthetic exercise and assertions.
- `cli-outputs.json`: captured commands, exit codes and output.
- `approve.duckdb`, `reject.duckdb`: isolated review databases.
- Pending/after-state JSON, `rejected-repeat.json`, `failed-triage.json`,
  `recovered-triage.json`, and `audits/`: retained outcome evidence.
- `reports.html`: clearly labelled review-only wrapper of unchanged command output.
- `showcase-desktop.png`, `showcase-narrow.png`, `recovery-desktop.png`,
  `recovery-narrow.png`: local browser captures.

These ignored artifacts are local evidence, not files included in the documentation
commit. No push or merge was performed as part of this review.
