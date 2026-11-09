# Webapp Batch 4C — other supplied-input workflows

**4 November 2026 · Bounded local implementation.**
[Product sequence](batch4a1-fresh-analysis-scope.md) ·
[Company analysis implemented in 4B](batch4b-local-research.md).

Keystone now has three additional **new calculation** actions in Data & inputs.
These are separate from importing and replaying saved monitoring/news/event
reports. Select an accepted immutable version, review its supplied parameters,
confirm one request, follow its durable job and open a native report. Importing
an input starts no job. Every result remains held for financial review.

## What each new action answers

| Action | Question | First supported scope |
| --- | --- | --- |
| Evaluate supplied observations | Which supplied policy observations cross their thresholds, and what changed within this history? | One company; up to 20 analyst policies, each with 1–100 dated observations; fractions, multiples, scores or EUR/base-unit amounts |
| Analyse supplied events | What historical abnormal returns can these event windows support? | One explicit ticker group; up to 20 event windows and 20 controls; 250 estimation returns and three event returns per window |
| Analyse supplied news text | Which supplied stories mention the company, repeat the same text, or contain the chosen tone words? | One company/ticker; up to 100 English text records, explicit aliases and an authorised supplied word list; a fixed cutoff and 1–30 day age window |

For example, the fictional leverage history `2 → 3.5 → 3.5` against a policy
requiring the value to stay **below 3** establishes a baseline, identifies a new
breach, then records a known stable breach. A quiet latest change does not erase
the active breach. A separate missing latest observation remains unavailable;
the earlier observation is not silently presented as current.

The event sample deliberately constructs stock returns as
`0.0005 + 1.2 × market return + abnormal return`. Its three abnormal returns are
1%, 2% and 3%, so the historical cumulative abnormal return is 6%. This is a
diagnostic example. It says nothing about the next earnings release.

The news sample supplies five article records. One is stale, one does not mention
the company, two contain matching text and cluster together, and the remaining
relevant story contains no matching tone words. Two matching positive tokens in
six word tokens produce the diagnostic score `2 / 6`; no matching tone words
produce **unavailable tone**, rather than zero.

## Scope boundaries

Monitoring in this slice is a **self-contained supplied-history assessment**.
It does not mutate Agent 2's persistent CLI monitoring database, infer a
predecessor from previous web jobs, schedule further cycles or approve a
correction. A changed history is another immutable input and request. Persistent
cross-job monitoring continuity/correction admission is a separate extension.
Thresholds are analyst policies; contractual covenant verification is excluded.

Historical event calculations reuse the existing market-model and validation
tools. Raw windows cannot assert reviewed date, benchmark, design or
comparability status. Those fields are deliberately not accepted. Their
unverified state keeps inference and scenarios held regardless of sample count.
Rejected estimation windows retain their reasons and are shown in coverage.
This workflow accepts supplied return windows; it does not collect prices,
resolve issuer releases or assemble windows from arbitrary price files.

News processing reuses ingestion, headline relevance, text clustering and
aggregation. Scoring uses the exact supplied positive/negative token lists:
`(positive tokens − negative tokens) / all English word tokens`. It does not
handle negation or context and is always diagnostic. It is not FinBERT or the
Loughran–McDonald dictionary. There are no downloaded models, provider calls,
LLM summaries, fabricated broker recommendations or return forecasts. Word-list
rights are reviewed alongside article-text rights. Empty coverage is a truthful
held result with no invented score or chart point.

## Contracts and input preparation

| Boundary | New identity |
| --- | --- |
| Package / preflight | Envelope **3**; supported only for these three new workflows |
| Monitoring payload | `agent2.observations/1` / `keystone.monitoring-observations` |
| Event payload | `agent3.event-windows/1` / `keystone.event-windows` |
| News payload | `agent3.news-text/1` / `keystone.news-text` |
| Input validation | Receipt **4**, validator `local-workflows/1.0.0`, `analytical_execution=not_started` |
| Processing request / immutable job | Request **4** / job **5**; exact accepted source and fixed versioned method |
| Execution receipt | Existing analytical receipt **3**, including atomic completion fingerprint |
| Calculated result | `keystone.local-workflow-result`, version **1** |
| Native adapters | `local-monitoring-report`, `local-events-report`, `local-news-report`, each **1.0.0** |

The [runtime contracts](../../keystone/workspace/onboarding/local_workflows/contracts.py)
and adjacent JSON schemas define closed fields and bounds. The envelope schema
is a metadata boundary; payload-model and semantic checks are still required.
The [three fictional packages](../../fixtures/local_workflows/) show the format.
Their illustrative entity/permission IDs must be replaced with the actual
registered workspace records. JSON examples do not grant source rights.

Each used source ID resolves to declared owner, role, reference, units and dated
coverage. The local operator must install payload-scoped source-use evidence
before retention or processing. Observation/publication/retrieval dates remain
separate from upload and execution time. The new workflows perform no FX,
security-basis or undocumented unit conversions. Monitoring policy boundaries
use exact Decimal comparisons; shared statistical diagnostics use floating-point
calculations and retain their limits.

Only supported structured JSON is accepted. Arbitrary HTML/PDF/spreadsheet/DB
parsing, paths, executable commands, remote-source fetching, and free-form method
selection are not accepted through these formats. Each package is limited to
**1 MB**, each fixed request to the existing **4 KB** bound, calculated evidence
to **2 MB**, and reserved result staging/delivery to **16 MB** within the existing
100 MB retained-evidence admission ceiling. Inputs and results are never
automatically deleted or truncated to make capacity available.

## Execution, presentation and recovery

The profiles `calculate-local-monitoring`, `calculate-local-events` and
`calculate-local-news` use **zero provider/model requests, zero model output
tokens and at most 120 seconds**. Their child strips credentials and denies
network entry points. A browser cannot provide a command, path or executable
profile. It confirms a closed method and exact accepted source reference.

Admission, claim, result promotion and private delivery recheck source permission
and immutable hashes. Claim and promotion also check the pinned producer,
including shared monitoring engines, runtime schemas and the dependency-lock
identity. Same-key retries preserve the original request. Changing a timeout or
source under that key conflicts; a lost response is not permission to create a
new-key retry. One claimed attempt remains the maximum.

Each new report retains the calculated result, supplied input, processing
request, input contract, original HTML export, native view/series and analytical
completion proof. The native reader has an overview, interactive observations,
coverage/exclusions where relevant, method limits, grouped review notes and
verified evidence downloads. Policy values and thresholds appear side by side.
Event/word-tone charts are diagnostic discrete points; monitoring history
preserves missing gaps. Hover, keyboard selection and exact numerical tables use
the retained values. There is no primary report iframe or image-based chart.

All artifacts are checked/flushed before atomic promotion. Complete saved proof
supports explicit **delivery-only** recovery without recalculating or rendering
again. Incomplete or changed proof is not a rerun instruction. An orphaned
operation's uncertainty stays visible even when its separately proved result is
recovered. The request/job/result formats preserve the older record families.

Private snapshots include these inputs, requests, proofs and reports. A restore
keeps their identities, generates a new access token and holds never-started
queued work until explicit operator recheck/release. This is local recovery
evidence; it does not establish independent backup or clean-machine recovery.

## Local demonstration

The user-facing preview is **http://127.0.0.1:8860/** with the isolated fictional
workspace `output/other-workflows-4c-final/workspace`. The earlier exploratory
`output/other-workflows-4c-preview/` evidence is preserved separately. Existing
4B and user input/report workspaces are unchanged.

To reopen after stopping the existing server:

```bash
.venv/bin/python -m keystone.workspace serve \
  --workspace output/other-workflows-4c-final/workspace \
  --port 8860 --enable-imports --enable-job-admission --enable-worker
```

Connect with that workspace's current `control/access-token.key`. Preserve lock
files; return to the running session instead of launching another on the same
workspace. The operator-only [preparation helper](../../scripts/prepare_local_workflows_preview.py)
can populate a **fresh empty** demonstration via the protected loopback API.
It installs fictional test permissions, disables proxy forwarding and starts no
financial jobs. It must never be used as real-source authorisation.

## Acceptance boundary

The [focused tests](../../tests/test_workspace_local_workflows.py) cover known
arithmetic, baseline/new/stable breach states, decimal boundaries, missing data,
degenerate event fits, news exclusions/clustering/no-match/empty coverage, strict
input refusal, no-acquisition paths, idempotency, permission revocation,
one-attempt native delivery, orphaned completion recovery, capacity refusal and
snapshot/restore/release for all three new formats.

Recorded verification:

| Check | Observed result |
| --- | --- |
| Complete Python suite | **1,507 passed** in 581.82 seconds, including 53 new local-workflow cases |
| Interface suite | **324 passed**, including 42 new local-workflow checks |
| TypeScript and production frontend build | Passed |
| Visible browser checks | **17 passed**: explicit confirmation, exact monitoring counts/missing state, keyboard selection, independent event arithmetic with held inference, news coverage, complete reading copy, fixed score scale, pointer labels and all three reports at 1,280/320 CSS-pixel widths |
| Actual browser-requested report evidence | All **24 registered artifacts** matched; all three operations used zero model requests/output tokens |
| Documentation and change hygiene | Local document links and whitespace checks passed; generated output/state and access tokens are excluded from the candidate changes |

The first broad test run overlapped the demonstration import and correctly
refused three command-line checks at the checkout-wide admission gate. Their
isolated recheck passed; the final full suite above passed without overlapping
demonstration writes. No locking guard was bypassed. Browser review also caught
and corrected an exact-count presentation mismatch before the final fixtures
and checks were captured.

See the [tracked acceptance record](../../references/acceptance/workspace-local-workflows-2026-11-04.json).
Ignored screenshots, per-case browser results and artifact checks are under
`output/other-workflows-4c-final/`. These are controlled engineering checks on
fictional inputs; they are not human financial interpretation or real-source
validation. Physical touch/screen-reader, real print/download completion and
general browser compatibility are not claimed by this review.

The subsequent **[4D acceptance](batch4d-workflow-acceptance.md)** records larger
count-bound inputs and cross-workflow storage-fault, capacity and recovery checks.
Real-source permissions and human financial interpretation remain separate
release dependencies. Continuous monitoring, approved correction intake, independently
reviewed event inference and advanced language-model scoring remain separately
scoped extensions. No production release approval is granted by this batch.
