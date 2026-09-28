# Agent 2 v1 acceptance and operating boundary

Agent 2 is an analyst-reviewed monitoring prototype over a bundled, dated covenant
watchlist. Its deterministic cycle detects changes, retains evidence and recovery
state, and optionally uses an audited model to investigate and order surfaced
items. Python controls published recommendations. Acceptance covers this scope;
it does not certify a production credit-surveillance service.

## Acceptance evidence

Final verification on 28 September 2026: **490 regression tests passed** on
Python 3.11.9, including eleven new acceptance/formatting/anomaly cases.

| Check | Observed result |
| --- | --- |
| Complete fixture sequence | Twelve cycles completed on each transport; cycles 11–12 explicitly had no new observations |
| Local / MCP parity | Complete cycle results, reports and catch-up results matched exactly |
| Expected events | Gamma recovered in cycle 5; Delta breached in 7; coverage anomaly and breach in 9; leverage breach and coverage recovery in 10 |
| Controls | Beta stayed quiet; leverage warnings appeared before breach; baseline alerts were suppressed |
| Offline triage | Nine surfaced cycles per transport produced audited, validated commentary |
| Recovery | Saved-cycle replay, catch-up gap, persisted cycle evidence and sequence advancement verified |
| Real model | `claude-sonnet-4-5-20250929` completed cycle 9 with two model turns and four successful tool calls: two inspections and two rechecks |
| Publication | Active breach first, observation verification retained, early warning surfaced, no unrestricted model prose published |
| CLI replay and state | Replay made no new triage call; saved cycles 1–9 matched offline evidence and the next cycle remained 10 |

Local evidence is retained under
`output/agent2-acceptance/df06c3352cf345bea965e93816937d21/`:
`summary.json`, transport-specific `cycles.json` and triage audits, CLI outputs,
`live-model.json`, and separate databases. These outputs are ignored by Git;
the tests and repeatable acceptance runner are versioned. One successful live
run establishes observed compatibility with that model, not universal reliability.

The first sandboxed attempt recorded APIConnectionError without losing cycle 9.
A subsequent network-enabled attempt completed its model calls but was withheld
because the model wrapped JSON in a Markdown code fence. The parser now accepts
one whole-response JSON fence, while still rejecting surrounding prose, additional
blocks and duplicate keys. Original model text remains unchanged in the audit.
The successful run was performed after that fix.

Acceptance also uncovered a significant-anomaly recommendation edge case:
nonisolated anomalies accompanying a breach or corroborated warning now retain
an explicit observation-verification instruction. Escalation is never removed.

## Repeat the check

From the repository with dependencies installed:

```bash
python -m scripts.check_agent2_acceptance
python -m scripts.check_agent2_acceptance --live
```

The second command makes paid Anthropic calls and loads the repository `.env`.
To use an existing credential file elsewhere, add `--env-file '/path/to/.env'`.
Existing environment variables take precedence. Keys are never printed or copied
into evidence. Both commands create unique output directories and isolated
monitoring databases; they do not reset an existing monitoring database.

The runner exits nonzero on a failed check and saves its failed stage and error
type. Raw provider exception messages are not exposed. `--live` requests one
fixture cycle's model triage, with up to the shared loop's twelve model turns;
it does not switch the observation provider. Subprocesses have bounded timeouts.
No live test runs automatically in CI.

## Operator review

1. Check coverage before interpreting alerts: baseline, skipped observations,
   review holds and no-new-observation cycles do not establish compliance.
2. Read the persisted current state as well as the exception report. Baseline and
   unchanged breaches can be suppressed from exception output. A quiet cycle
   does not erase an existing breach.
3. Review the underlying value, threshold, date, direction and covenant definition.
   The current ratios and simulated January 2026 dates are illustrative fixture
   data, not verified issuer observations or actual current monitoring dates.
4. Treat anomaly, drift and crossing probability as diagnostics of one scalar
   series. Crossing probability is a Brownian approximation, not a calibrated
   probability of default; irregular observation spacing can make it unavailable.
5. Escalate active breaches for analyst review and verify anomalous observations.
   Inspect `model.json` execution and publication status separately: a completed
   model loop can still have withheld commentary.
6. If triage fails, the committed cycle remains valid. CLI exit 2 reports triage
   failure or withholding. Replaying the cycle retrieves its evidence without
   rerunning the model; automatic triage retry is not implemented. Preserve the
   failed audit for diagnosis rather than resetting monitoring state.
7. Corrected observations and changed definitions enter a persistent review hold.
   An approved new definition can start a new item ID. In-place correction approval
   and historical backfill are not supported.

## Boundaries and deferred extensions

- No live issuer/fundamental ingestion, business-specific covenant extraction,
  independent-source reconciliation, automated notifications or external actions.
- Local DuckDB and cooperating-process locks; no distributed scheduling guarantees.
  The optional loop is deterministic only, logs tick failures and keeps running;
  its exit alone is not a health certificate. Review the ledger and failure output.
- Audits are local atomic files, not a tamper-proof archive or a cross-file/database
  transaction. A killed model process can leave a running/pending audit.
- Legacy databases are migrated without reconstructing missing historical evidence.
- There is no guaranteed all-company coverage, autonomous credit decision-making,
  or production service-level guarantee.

These are explicit operating limits, not claims that additional integrations have
been completed. See the [calculation](agent2-calculation-alerts.md),
[state recovery](agent2-state-recovery.md) and
[publication](agent2-triage-publication.md) notes for the component contracts.
