# Webapp Batch 4D — supplied-input workflow acceptance

**4 November 2026 · Bounded synthetic engineering acceptance.**
Follows [4B](batch4b-local-research.md) and [4C](batch4c-other-workflows.md).

## Bounded engineering scope

Exercise all four newly enabled calculation paths using fictional inputs. Preserve
existing workspaces. The live demonstration uses a new private workspace under
`output/fresh-workflows-4d-preview/` on loopback port 8862.

| Case | Input / fault | Required outcome |
| --- | --- | --- |
| FW-01 | Ten annual research periods | All ten years survive import, calculation, native projection and exact tables; current revenue EUR 1bn, margin 12%, FCFF EUR 80m; financial review remains required |
| FW-02 | 20 policies × 100 observations | All 2,000 points retained, including ten missing latest points; assessed 10, active breaches 10, missing 10; no borrowed latest values |
| FW-03 | 20 events + 20 controls | All 40 windows retained; 20 usable events/issuers and historical mean CAR 6%; inference/scenarios still held |
| FW-04 | 100 articles, 5,000-character bodies, 100 positive + 100 negative words | All 100 distinct documents retained/assessed; exact word-count arithmetic; no truncation or model retrieval |
| FW-05 | One beyond each structural count bound | Reject during supervised semantic import validation; no accepted version or job. Inspection reports validation pending and proves only transfer identity/source-use scope |
| FW-06 | Write, flush, rename or input-index commit failure in each new format | Earlier input/evidence unchanged; no partially accepted version; complete prepared imports recover once without calculation |
| FW-07 | Result write, native registration, proof write, pre-promotion flush or promotion failure in each format | No public partial result; attempt stays one; incomplete proof cannot be delivered; complete committed result may recover delivery only |
| FW-08 | Catalogue delivery write/flush/rename failure | Earlier reports unchanged; complete proof retained; repeated recovery delivers exactly once without calculation/rendering |
| FW-09 | Full pending-result reservations across mixed workflows | Refuse next job without deleting evidence; same-key retry still finds original |
| FW-10 | Permission revoked after completed calculation | Block private result/input delivery; preserve stored evidence and original attempt |
| FW-11 | Mixed completed results + queued work, local snapshot/restore | Preserve artifact hashes/lineage, rotate token, hold queues, release explicitly after recheck; original untouched |
| FW-12 | Visible max-volume native readers | Exact-table paging and keyboard chart selection work; complete reading copy retains rows/holds; desktop and narrow layout fit |
| FW-13 | Regressions and compatibility | Full Python/interface checks and frontend build pass; old families remain supported; no production approval inferred |

The [39-row research design matrix](fresh-analysis/acceptance-matrix.md) remains
the detailed design checklist. This batch records the engineering checks below;
it does not relabel that entire frozen matrix as unconditionally passed.

## What the larger workload found and changed

The first real supervised 20-policy × 100-point calculation exceeded the existing
2,000,000-byte analytical-result limit: repeated context and statistical method
prose made the result about **3.18 MB**. A valid accepted history therefore failed
before delivery. The limit correctly prevented an oversized result.

Monitoring now retains each diagnostic's method/caveat/producer metadata once in
`details.diagnostic_methods`. Per-observation diagnostics reference that registry
under `details.diagnostic_encoding=interned-method-metadata/1`. Policy context
remains in the exact supplied input, linked by each item's `input_pointer`.
Duplicated scalar diagnostic summaries are represented by their existing nested
diagnostic values. The engine calculations, exact threshold decisions, source
values, dates, missing points and 2 MB bound are unchanged. A regression expands
every saved diagnostic back to its shared-engine value and checks equality.

The demonstrated monitoring result is now **1,681,713 bytes**, including every
usable cycle's diagnostics and all **2,000** chart observations. Its 8 registered
artifacts total 2,537,803 bytes; both staged and delivered copies fit the existing
16 MB reservation. Earlier saved reports keep their original details layout and
remain readable; the native adapter does not depend on the compact detail shape.

## Observed maximum-count demonstration

These are the configured count limits, with some maximum-size fields, rather than
every combination of maximum strings, decimals, dates and Unicode widths. They
are one local-machine measurement, not a throughput or availability guarantee.
Durations below are the supervisor's recorded child duration, excluding import,
browser interaction and final public-catalogue delivery.

| Workflow | Package bytes | Calculated result bytes | All 8 artifact bytes | Child seconds |
| --- | ---: | ---: | ---: | ---: |
| Research: 10 annual periods | 24,965 | 35,956 | 124,046 | 0.759 |
| Monitoring: 20 × 100 points | 129,681 | 1,681,713 | 2,537,803 | 3.195 |
| Events: 20 events + 20 controls | 346,294 | 160,860 | 565,431 | 1.577 |
| News: 100 articles with 5,000-character bodies; 100 + 100 words | 531,590 | 1,797,441 | 2,479,648 | 0.900 |

All four requests were explicitly confirmed through the browser after protected
imports. All completed with one claimed attempt, zero reserved model requests or
output tokens, no live-data permission and financial approval false. The news
case assesses 100 distinct bodies; every document has one positive token and no
negative token, with score checked independently against its total token count.
The 20-issuer event sample still withholds inference and forward scenarios.

## Fault and recovery evidence

The [105-case acceptance file](../../tests/test_workspace_fresh_workflow_acceptance.py)
adds the following checks to the earlier 4B/4C cases:

- Actual protected import, supervised child calculation, native projection and
  artifact verification at each demonstrated count limit.
- Eight one-over-limit refusals during supervised import validation; no accepted
  version or analytical job. Inspection explicitly reports validation pending.
- Sixteen input write/flush/rename/index-commit failures across the four formats.
  Prior accepted versions remain exact; complete prepared imports recover once.
- Twenty result-write/native-registration/proof-write/flush/promotion failures at
  the real renderer boundaries. These are in-process fault injections under the
  same private gate, not physical power-loss experiments. No partial public result
  or second claimed calculation attempt is exposed.
- Sixteen catalogue delivery faults after real supervised calculations. Earlier
  reports remain exact; repeated recovery delivers the saved proof once without
  executing or rendering again. Corrupted proof refuses recovery until the
  preserved original bytes are restored in the test.
- Real supervisor deadlines using a controlled sleeping test child for all four
  profiles. Timeout keeps outcome uncertainty and one attempt; no report appears.
- Mixed pending reservations stop the next admission, while same-key retries find
  the original jobs. No automatic evidence deletion makes space.
- Post-calculation permission revocation blocks private report delivery while
  preserving stored evidence. A mixed four-result/four-queue snapshot restores
  exact input/report bytes with a new token and holds every queue until explicit
  recheck/release. Original inputs and reports remain unchanged.
- Thirty malformed/contradictory research input cases plus lossless monitoring
  diagnostic representation. Existing financial arithmetic and source-gate tests
  continue to supply the broader coverage.

The input-fault cases deliberately preserve unindexed, complete prepared folders
after a failed final index commit. This is retained recovery evidence, not an
accepted partial version. A write failure without complete proof cannot recover.
Inspection checks transfer identity and source-use scope; semantic acceptance
remains a separate supervised validation step. The first test harness expected
inspection to perform that later step and was corrected to exercise the actual
boundary. It also now uses the fixture-owned service lifespan and the renderer's
normal private gate; no production guard was relaxed to make a test pass.

## Visible browser and private download checks

**27 checks passed** on the actual four browser-requested results. These include
all 20 monitoring charts, keyboard selection of the hundredth observation, the
four exact-table pages, a missing last point, twenty event issuers with 6% CAR and
held inference, all four news pages with 100 unique headlines, fixed news score
scale, complete news/research reading-copy coverage, visible FCFF/conditional
valuation and all four reports at **1,280 and 320 CSS pixels** without page-level
horizontal overflow. Reload clears private report content; reconnect returns to
the original result without submitting a job. Temporary viewport overrides were
reset. Screenshots and the individual observations are retained in ignored output.

The protected loopback verifier downloaded **all 32 registered artifacts**, checked
their exact byte counts and hashes against the saved catalogue, and confirmed the
private `no-store` response boundary. This proves the HTTP evidence path. It does
not claim physical print-device completion or browser download-folder placement.

## Reopen or reproduce locally

The preview is **http://127.0.0.1:8862/**, using only
`output/fresh-workflows-4d-preview/workspace`. Its current local access token is in
that workspace's `control/access-token.key`; do not add it to Git or a URL.

After stopping the existing session, reopen it with:

```bash
.venv/bin/python -m keystone.workspace serve \
  --workspace output/fresh-workflows-4d-preview/workspace \
  --port 8862 --enable-imports --enable-job-admission --enable-worker
```

Preserve lock files and existing input/report folders. For a fresh reproduction,
prepare a different empty private workspace under `output/` and start its server.
The [preparation helper](../../scripts/prepare_fresh_workflow_acceptance_preview.py)
imports the [deterministic volume cases](../../scripts/fresh_workflow_acceptance_cases.py)
through the protected API and starts no financial job. The operator must then
confirm each calculation. These helpers install fictional permission records;
they are not real-source authorisation.

The [read-only verifier](../../scripts/verify_fresh_workflow_acceptance_preview.py)
checks the four completed fictional reports through that server. Run the complete
Python suite without concurrent demonstration imports or jobs: the checkout-wide
gate intentionally refuses overlapping mutators. An exploratory timeout check
overlapped preparation and was refused at that gate; its isolated rerun passed.

## Final regression and retained evidence

| Check | Result |
| --- | --- |
| Complete Python regression suite | **1,612 passed**, no failures/errors/skips, **686.063 seconds**; includes all **105** new cross-workflow cases |
| Strengthened boundary subset | **8 passed** after ensuring the over-limit record has a unique identity/date and otherwise valid source coverage; duplicated records cannot conceal a missing count guard |
| Frontend suite | **324 passed** |
| TypeScript / production frontend build | Passed |
| Visible browser acceptance | **27 passed**; viewport reset |
| Protected HTTP evidence | **32 downloads** matched exact bytes/hashes; exactly four original completed demo jobs |
| Documentation / change hygiene | Local links, Python syntax, whitespace and candidate credential-pattern checks passed; generated output/state/access tokens excluded |

The [tracked aggregate record](../../references/acceptance/workspace-fresh-workflows-2026-11-04.json)
retains measured bytes/durations, input/request/job/result lineage, producer source
hashes and the 32 artifact hashes. Detailed test XML, browser case observations,
HTTP checks and screenshots remain under the ignored
`output/fresh-workflows-4d-preview/` directory. All FW-01–FW-13 rows above passed
within the stated bounded engineering scope. The broader design and release
dependencies below keep their own status.

## Separate dependencies

Synthetic checks cannot approve real-company financial interpretation, source-use
rights, customer/enterprise deployment, independent backup, encryption/key
recovery, clean-machine recovery or authorised Agent 4 business inputs. External
backup remains deferred. Physical touch, screen-reader and actual print-device
acceptance require separate evidence.

## Coverage limits retained

These checks do not exhaust the Cartesian product of every field/volume/fault,
emulate hardware failure, or establish operating-system/filesystem durability
after sudden device power loss. Missing-handler installations, every extreme
near-overflow financial parameter combination, every first-listing race and
physical accessibility/browser compatibility variants are not newly certified
by this batch. The frozen research matrix remains a useful detailed hardening
backlog, with existing regression evidence where present. This bounded workload
and fault acceptance does not turn those broader conditions into all-pass claims.
