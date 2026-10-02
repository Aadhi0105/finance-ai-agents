# Agent 3 Batch 2 — reliable live execution and peer selection

> Follow-up: [Batch 3](agent3-batch3.md) implements Track B evidence and publication controls. The remaining news limitations below describe the Batch 2 milestone.

This batch addresses the review/live-execution portion of the Agent 3 audit
(F03/F04/F06/F20/F22 and configuration in F24). It retains Batch 1's strict
historical inference policy. It does not certify Track B or forward forecasts.

## Peer selection

The live proposer now calls the shared `AnthropicModel.respond` interface.
Without `--peers`, the live CLI requests a model proposal and needs
`ANTHROPIC_API_KEY`. Missing/blank credentials produce **unavailable**, with no
fixture fallback. Library callers must explicitly select `live_propose=True` or
supply peers for live assembly. Offline `propose_peers(..., live=False)` remains
an illustrative stub only.

Model JSON requires a sector, bounded ticker list, overall rationale, and one
assessment per accepted peer with a rationale and public HTTP(S) source leads.
Tickers normalize to uppercase; the target and duplicates are removed; at most
20 proposed entries are allowed. The prompt requests 5–10 peers, but a smaller
nonempty valid proposal is usable for descriptive assembly. Empty model proposals
are refused. An explicit empty `--peers` means target-only analysis, bypassing
the model; it cannot satisfy the ten-independent-issuer inference requirement.

Only a complete JSON object or an exact enclosing Markdown JSON fence is parsed.
Refusal prose, truncated replies, duplicate JSON keys, nonfinite constants, invalid
lists and mismatched assessment sets are refused. There is one model request with
SDK retries disabled and a 45-second request timeout. No automatic second model
attempt is made after a refusal.

**Model source leads are not verified evidence.** The accepted set and assessments
remain `unverified`; they do not approve economic comparability or a study plan.
Before pooling model-selected peers, live assembly compares the provider's equity
listing symbol/website against the proposed issuer source domains. A mismatch or
missing identity evidence excludes the peer and retains both sides for review.
This is a conservative consistency screen, not authoritative identity verification;
it can exclude legitimate peers with different corporate/IR domains. It never
establishes economic comparability. Explicit user-selected peers follow the
existing reviewed-universe policy. Unsupported listings or unavailable provider
data remain visible exclusions.
Proposal checkpoints preserve model ID, prompt, messages, response, stop reason,
usage, request ID and accepted/refused decision. Raw SDK/provider error messages
are withheld; error classes and safe reason codes remain available.

## Live commands

Run from the repository with its runtime dependencies installed:

```bash
# Uses a live model to propose peers, then live market data:
python -m agent3.run_live ASML.AS semicap_earnings

# Skips model proposal; no model key is required:
python -m agent3.run_live ASML.AS semicap_earnings --peers ASM.AS BESI.AS

# Explicit human review inputs, still checked against the exact universe:
python -m agent3.run_live ASML.AS semicap_earnings --peers ASM.AS BESI.AS --study-plan reviewed-plan.json

# Optional isolated state/output paths and whole-run timeout:
python -m agent3.run_live ASML.AS semicap_earnings --peers ASM.AS BESI.AS --db output/asml/catalyst.duckdb --output-dir output/asml/runs --timeout 240

# Retry one recorded attempt; provide the path printed by that run:
python -m agent3.run_live --retry-from output/asml/runs/RUN_ID/run.json
```

The CLI loads `.env` from the repository root, without overriding exported
variables. `AGENT_MODEL` selects the proposal model; the attempt records its ID.
`AGENT_STATS_VIA_MCP=1` explicitly selects MCP; `0` selects local calculation.
Other values are refused. The legacy `AGENT3_LIVE_PROPOSE` accepts only `0`/`1`;
`0` requires explicit peers unless `--live-propose` is supplied. Combining
`--live-propose` and `--peers` is refused.

Default output and database paths are anchored to the repository, independent
of the working directory. Explicit relative paths resolve from the caller's
working directory. Bare database filenames are supported.

## Outcomes, deadlines and diagnostics

| Exit | Terminal status | Meaning |
|---|---|---|
| 0 | `completed` | Eligible historical result; never a forward forecast |
| 2 | `refused` | Invalid inputs/configuration, invalid model proposal, or insufficient usable events |
| 3 | `held` | Historical diagnostics exist but review/inference requirements are unresolved |
| 4 | `unavailable` | Missing credentials, model/service unavailable, all-peer provider failure, MCP error, interruption or whole-run timeout |
| 5 | `failed` | Unexpected execution, worker or persistence failure |

Argument-parser usage errors also exit 2. Configuration errors encountered before
an output attempt can be created print a refusal without a record; an unwritable
output directory cannot be checkpointed. These failures do not print tracebacks.

Each started attempt has a unique `output/agent3-runs/<id>/run.json`, atomically
updated through configuration, peer selection, assembly, calculation, validation,
result and persistence stages. Per-peer progress and exclusions survive subsequent
failures. Known configured credentials are redacted from saved text, and worker
stdout/stderr are not exposed as diagnostics. Review the safe reason, error class,
stage history, proposal audit and per-peer reports in that file.

The CLI starts a separate worker with a **300-second default whole-run deadline**
(configurable 30–3600 seconds). On timeout/interruption it kills the worker process
group and marks the attempt unavailable. The CLI-owned MCP server has a parent
watchdog because the SDK can start it in a separate session; it exits when its
worker disappears. This
process-group cleanup is supported on macOS/Linux. Direct library calls do not get
the CLI deadline. Individual provider exceptions are isolated; a hung provider can
exhaust the whole attempt deadline. No automatic provider-pass or model retries
are added. The underlying data provider may perform its own internal requests,
all bounded by the CLI worker deadline.

Outcome persistence opens only after calculation. The database is closed even
when writing fails. A write failure returns failed and retains held diagnostics;
it cannot present a completed result. A timeout around a committed database write
can leave a summary row even when the attempt is unavailable; immutable conflict
and reconciliation semantics remain Batch 4.

## Retry and review boundaries

`--retry-from` creates a new attempt and preserves the old file. It reuses the
saved target, event label, transport, model ID, study plan and accepted peer set.
If peer selection never succeeded, retry explicitly makes another model attempt.
The original peer proposal/audit is retained when accepted peers are reused.
Ticker, peers, event type and study plan cannot be changed through retry flags;
start a new request for those changes. A new database, output directory or deadline
may be selected. Loaded retry JSON is revalidated and size-limited.

A retry fetches fresh provider data and recomputes the study. It is **not a replay
of the original market snapshot**, not an approval, and not an automatic promotion
of model-generated peer/source claims. Saved files are editable local evidence,
not authenticated or tamper-proof approval records. Full raw-input replay bundles
and state reconciliation remain Batch 4.

Both brief and scan rendering fail closed for unknown or stale publication states.
They recheck retained study evidence instead of trusting a saved PASS label; held
or failed runs do not publish a distribution, and scan significance is unavailable
while held. Historical quantiles are descriptive; no causal or predictive
calibration claim is added. Batch 1's sourced study-plan and dependence constraints
continue to apply.

## Verification

Regression coverage exercises the real shared adapter and SDK conversion with a
mock HTTP transport, strict proposal/refusal schemas, missing credentials, exact
JSON fences, explicit empty overrides, MCP failure, unknown saved states,
provider failure accounting, persistence failure, subprocess deadlines, foreign
working directories and retry preservation.

### Live verification — 30 September 2026

Using the existing local model credentials and an isolated output/database:

- The first ASML proposal was preserved as a refusal because the model emitted
  a JSON fence. Exact fenced-object support was added and regression-tested;
  refusal text around a fence remains rejected.
- An explicit retry called the real model through the shared adapter, accepted
  an audited unverified peer set, and completed live assembly/persistence with
  60 events across five contributing firms. ASML was excluded at window assembly.
  Review/dependence gates held publication, exit 3.
- Inspection caught a model identity error: the rationale/source leads named
  Tokyo Electron, but ticker `TEL` resolved to **TE Connectivity plc**, website
  `te.com`, rather than the proposed `tel.com`. The new consistency screen
  excludes that peer; it does not silently replace the ticker.
- A subsequent retry reused the accepted proposal without a new model request.
  Fresh live assembly returned 48 events across four firms, excluded ASML and
  TEL, and remained held (exit 3). ASML's assembly failure was not repaired or
  reclassified as valid evidence. Structured price-input reason codes were added
  and independently regression-tested after this run.
- Both completed study attempts retained `NULL` significance and
  `HOLD_FOR_REVIEW` in the isolated database. The original refused and held
  attempt files remained intact, linked through retry lineage.

Local evidence is in ignored `output/agent3-batch2-live/`: proposal attempt
`b34c4681e4b0434fbb154ad605ac8f31`, live study
`b4da4599210c422e91d8e320a9563e0c`, and identity-checked retry
`b55cd2ab9b1e4bc09171213082b7c727`. No investment finding, provider-wide
correctness, economic comparability approval or forward calibration was established.


Final local suite: **639 passed in 75.60 seconds on Python 3.11.9**, including
53 new Batch 2 regressions. The final run includes the real guarded MCP transport
and a detached-process test proving that its heartbeat stops after parent loss.
Documentation links and `git diff --check` passed. No real FinBERT test was run;
news correctness remains Batch 3.
