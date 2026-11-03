# Batch 3B.2 — fresh financial-close backend

2 November 2026. This extends the [3B.1 private input backend](batch3b1-data-onboarding.md)
and implements the new-close profile in the [3A design](batch3a-input-contracts.md).
[3C](batch3c-browser-onboarding.md) implements browser onboarding; wider usability, capacity and portable-restart
acceptance remain 3D. No production or financial approval is granted.

## What this adds

A private dataset can now select `agent4.close-request/1`. Its payload is an
Agent 4 close request containing the approved-budget assertion, exact-cent rows,
actuals delta, accounting tree, close date and stable version/run IDs. The server
derives the fixed `calculate-imported-close` profile. A client cannot select an
arbitrary command, database path, live source, model call or approval action.

For example, the fictional June fixture has budget sales of 10,000 cents and
costs of 4,000 cents: budget profit is EUR 60.00. Actual sales of 11,000 cents
and costs of 4,500 cents produce EUR 65.00 profit and a favourable EUR 5.00
variance. A later correction changing only June sales to 12,000 cents retains
the preceding months and June costs, yielding EUR 75.00 profit and EUR 15.00
variance. The previous close stays available as its original frozen evidence.

`agent4.close/1` continues to render a saved bundle without calculating a close.
The other four saved-input profiles retain their existing behavior. This batch
does not add fresh research, live monitoring, news retrieval or event gathering.

## Input validation and state ownership

The [complete example](data-onboarding/examples/synthetic-close-request.json) is
now a supported payload shape. Replace its placeholder entity/permission IDs
with records from the selected private workspace. It is fictional test data.

Raw close declarations must cover budget and actuals roles and explicitly state
`EUR` and `integer cents`. Optional declared period bounds must contain their
submitted rows. The request entity must exactly match the selected company.
Missing/denied/expired source-use records remain a separate refusal.

Validation shares Agent 4's source-preparation code: supported calendar periods,
integer cents, stable IDs, explicit signs, full-year budget and effective closed
YTD coverage, unique line/periods, no future actuals, immutable source versions,
latest actuals basis and valid current-period supersession. It uses a disposable
copy of the predecessor state, then rolls back. Upload does not call `rollup`,
`reforecast` or `execute_close` and creates no canonical accounting database/run.

The validation receipt is version 2 and binds an accounting-state generation,
workspace ID, entity ID and predecessor input-version lineage. Existing version
1 validation receipts keep their original serialization. The six immutable
accepted-input files and package size/time/permission limits remain unchanged.

Canonical accounting state has a fixed server-owned location:

```text
<private workspace>/accounting/<entity-id>/state.duckdb
```

The first job creates an empty private database before recording its close
intent. Workspaces and entity IDs select separate databases even when companies
have equal display names. Existing standalone Agent 4 databases are not adopted.
The state generation hashes ordered financial versions, rows, frozen runs,
heads and atomic attribution proofs. Failed-attempt and delivery logs do not
stale a financial pin. A missing database after an intent is lost state, never
an empty predecessor or proof that nothing committed.

## Admission, commit and delivery

The public job request remains version 2 with a dataset-version reference. A
fresh-close admission creates immutable job record version 3, including the
validated predecessor pin. Its execution receipt is version 2 and additionally
binds the accounting-commit proof. Existing saved-job admission/execution
schemas are unchanged.

1. Admission rechecks input identity, current permissions and predecessor state.
2. Claim rechecks them again under the financial mutator gate. Two queued jobs
   can initially pin the same predecessor; after the first commits, the second
   is refused as `source_changed` before dispatching an operation.
3. A durable company-specific close intent is saved before dispatch. An
   unresolved intent blocks further closes for that company until inspected.
4. Agent 4 commits sources, forecasts, frozen report bundle, head and job/input
   attribution in **one accounting transaction**. Attribution failure rolls all
   financial changes back. Each claimed job has at most one calculation attempt.
5. A separate immutable registry proof and report artifacts bind the raw
   request, computed bundle, predecessor, complete input lineage and job identity.
   Native report data uses the computed bundle, not the raw request.
6. Report registration and execution acknowledgement follow the accounting
   commit. Successful output is always `review_required`; upload assertions and
   process success do not establish authenticated budget approval or financial
   sign-off.

All predecessor input permissions are rechecked on admission, claim, delivery,
recovery and protected report reads. This is conservative: all contributing
close-input versions are retained in lineage, even if later deltas replace some
rows. Mixed source history is labelled `mixed`; a synthetic current delta cannot
relabel inherited internal data. HTTP report reads verify immutable registry
proofs and permissions without opening the mutable accounting database.

## Explicit recovery

Stop the server before using these operator commands. Recovery takes the
exclusive worker lease and financial gate, which also excludes a surviving
supervised child. Use the actual private workspace path and saved job ID.

```bash
.venv/bin/python -m keystone.workspace recover-job \
  --workspace "$KEYSTONE_PRIVATE/reports" \
  --jobs-dir "$KEYSTONE_PRIVATE/control" \
  --job-id job-REPLACE_WITH_SAVED_ID
```

If the accounting transaction committed, this reads and validates that frozen
run and its atomic job attribution, recovers its database journal if necessary,
and delivers/registers it once. It never invokes the close calculation or
forecasting again. Partial report files remain available for inspection rather
than being overwritten. A repeated successful recovery reuses the registered
result, including after a later legitimate close.

The original operation receipt stays byte-for-byte unchanged. A recovered job
can therefore show an original `failed_inspect_state` or `outcome_unknown`
operation beside a verified, delivered close. If the supervisor never wrote a
final receipt, the original admitted/running receipt and separate disabled
usage ledger are checked; the recovered execution retains an unknown operation
outcome. A verified accounting commit supplies the separate evidence of
financial computation, never a fabricated successful operation receipt.

If inspection proves there was **no** accounting commit and the financial state
still exactly equals the pinned predecessor, release the held intent explicitly:

```bash
.venv/bin/python -m keystone.workspace release-uncommitted-close \
  --workspace "$KEYSTONE_PRIVATE" \
  --job-id job-REPLACE_WITH_SAVED_ID
```

The old job stays failed/unknown; it is not requeued. A deliberate new request
key can admit a new job only after this resolution. A committed, missing,
corrupt, changed or ambiguous state refuses this release. Revoked/expired source
rights cannot be bypassed by recovery.

## Backup and remaining boundaries

`snapshot-private` inventories each company accounting database separately as
`kind=database, role=agent4_state`, so the existing quiescence/checkpoint logic
applies. Registry intents/proofs/resolutions, accepted inputs, permissions and
report/control evidence are included; the local access token is excluded.
An abandoned disposable validation database holds backup for operator inspection
instead of being copied as an ordinary tree member.

Local snapshot/restoration of accounting state is tested. Private queue ownership
still binds its original report directory: portable queue restart remains held
for 3D. A local copy does not provide independent-device backup, encryption/key
recovery or clean-machine disaster recovery. Real-company FP&A acceptance,
source-use permission review and analyst interpretation review remain open.

## Verification

`tests/test_workspace_fresh_close.py` covers independent arithmetic, source and
state failures, predecessor races, corrections, lineage permissions and labels,
workspace isolation, local accounting restore and explicit recovery. Fault cases
include real supervised process exit inside the accounting transaction and just
after commit, report failure, missing supervisor acknowledgement and catalogue
failure before/after replacement. Recovery tests forbid financial execution.

`tests/workspace_fresh_close_scenarios.py` is the test-only loopback rehearsal for
fresh close and correction requests through the actual server/owned worker. Its
ignored receipt records report/operation identities, zero model use and source
fixture preservation. It is engineering evidence, not financial approval.

Run it with a fresh destination; an existing destination is refused:

```bash
.venv/bin/python tests/workspace_fresh_close_scenarios.py \
  --destination output/onboarding-fresh-close-3b2 \
  --port 8801
```

The owned server and worker stop at the end. The resulting `receipt.json`,
`source-before.json` and private workspace remain available locally for inspection.

### Recorded engineering evidence — 2 November 2026

| Check | Result |
| --- | --- |
| Full Python regression | **1,362 passed** in 481.53 seconds |
| Final fresh-close suite | **42 passed** in 129.50 seconds, including the final additional job-receipt/commit mismatch refusal |
| Frontend regression | **234 passed** |
| TypeScript check and production build | Passed |
| Actual loopback HTTP server and owned worker | Two accepted inputs, two committed accounting runs, two registered native reports; one claimed attempt each |
| Independent arithmetic | June profit EUR 65.00 versus budget EUR 60.00; correction profit EUR 75.00; retained YTD and later-period delta cases pass |
| Provider/model use in rehearsal | Zero provider requests and zero reserved model requests |
| Existing evidence | Both Agent 4 fixture files preserved; the earlier 3B.1 workspace's five reports and five accepted versions remain readable |
| Local snapshot and restoration | Accounting database declared explicitly and semantic state restored exactly; relocated private queue restart remains refused pending 3D |

The full regression preceded the final additional receipt/commit consistency
guard. The complete 42-case fresh-close suite and actual HTTP rehearsal passed
on that final code. Counts overlap and should not be added together.

The successful local evidence is under
`output/onboarding-fresh-close-3b2-verified/`. The initial attempt under
`output/onboarding-fresh-close-3b2/` was stopped by the execution environment's
local-port restriction before any close; it is preserved separately. The
verified rerun used permission to bind loopback only. These ignored local files
and the preceding test logs are not committed application data or release evidence
for an actual company.
