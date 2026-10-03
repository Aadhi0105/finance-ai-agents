# Agent 3 — live-news retrieval recovery and populated-feed acceptance

## What changed

The previous `Ticker.news` path returned HTTP 404 and its SDK normalized the
missing stream into an empty list. Track B now uses the documented
[yfinance Search interface](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Search.html).
This is a different endpoint of the same provider, not an independent news source.

A checked curl session observes the search HTTP response before SDK shaping. Failed
HTTP statuses, request failures, missing/invalid `news` envelopes and oversized
responses are unavailable, never successful empty searches. A valid successful
`news: []` is explicitly recorded as empty. No fallback sentiment or provider is
invented. Safe failure records retain reason/status/error class without provider
error bodies or exception text. All paths remain subject to the bounded worker.
Unknown transport status (including an SDK cache hit that skips the checked session)
is not certified as success; normal CLIs use a new worker per attempt.

The adapter requests 20 results, rejects over 100 records and rejects search
responses over 5 MB before SDK parsing. This is bounded search coverage, not a
complete company-news archive. Requirements now identify the tested yfinance 1.7.0
API and its curl runtime minimum; optional FinBERT dependencies remain optional.

`--news-query` explicitly controls retrieval without changing the target ticker or
establishing article relevance. `ASML.AS` returned a valid empty search; `ASML`
returned populated results. We use the latter query and retain `ASML.AS` as the
analysis target. There is no automatic ADR substitution or alias inference.

The successful provider records, query, HTTP status, retrieval time, normalized
items and text scope are retained in the sealed bundle. The search results in this
acceptance run contain headlines, not article bodies or language metadata. We do
not fabricate either. Headline-only evidence is explicitly held and labelled in
the CLI and export. Provider summaries, if present, are identified separately.

A populated run exposed another bug: valid index tags such as `^GSPC` caused whole
articles to be rejected by the equity-ticker validator. News ingestion now accepts
bounded index tags as provider metadata, preserves them, and keeps them separate
from the requested analysis universe. Headline alias/cashtag evidence is still
required. Malformed tags receive an explicit `invalid_entity_tags` exclusion.

Saved HTML now lists retained headline evidence with escaped text, normalized
source links, timestamps, text scope and review reasons. Links are references to
provider-returned sources, not certification of publisher authenticity or access.

## Live acceptance — 2026-10-03

| Check | ASML.AS, query ASML | NVDA, query NVDA |
|---|---:|---:|
| Successful provider records | 20 | 20 |
| Ingested | 20 | 20 |
| Relevant headline records | 12 | 4 |
| Excluded for no headline entity evidence | 8 | 16 |
| Text clusters | 12 | 4 |
| UTC entity-days | 4 | 1 |
| No lexical tone evidence (null score) | 4 | 2 |
| Offline replay | Matched | Matched |
| HTML report and evidence links | Exported, held | Exported, held |

Both actual bounded CLIs returned exit 3, meaning **held**, not a retrieval failure.
The acceptance checker reconstructs normalized items from retained provider records,
accounts for every ingestion/relevance/cluster decision, checks lexical arithmetic,
verifies the publication hold and compares the complete offline replay result.
It does not rerun the provider or scorer and does not measure sentiment accuracy.

No exact duplicate clusters were observed in these two live samples. Duplicate,
correction, stale/future timestamp and language controls remain covered by the
existing controlled regressions; live exposure to all those cases is not claimed.

## Qualitative review of actual retained headlines

The positive/negative lexical matches were inspected as **word evidence**:

- ASML's rebound headline matched `rebound`; the geopolitical-risk headline matched
  `risk`. These are consistent lexical matches, not validated company outlooks.
- Comparison questions containing `better` receive positive lexical counts without
  resolving which company is favoured. This is a demonstrated context limitation.
- Some surge/slip headlines have no matching dictionary word and correctly retain
  null scores rather than synthetic neutrality.
- NVIDIA's inheritance-tax headline is relevant by name but is not necessarily
  operating-company news. Headline relevance does not establish topic suitability.
- Missing language metadata and multi-company coverage stay visible as review
  reasons. English-looking text was not automatically relabelled as verified English.

All signals stay held for headline-only evidence, unknown language, lexical/context
limitations, the disclosed unverified dictionary subset and other applicable flags.
No investment signal, entity-specific sentiment or return forecast is approved.
Real FinBERT was not installed or tested in this batch.

Two sample article-page checks through the web reader failed (one HTTP 429, one
inaccessible). Provider-returned link normalization and HTML escaping passed;
full-article accessibility, publication facts and full-body sentiment were not
independently verified. No article text was fabricated to fill that gap.

## Reproduce

```bash
python -m agent3.run_news ASML.AS --news-query ASML --alias ASML --scorer lm \
  --output-dir output/news-asml --db output/news-asml.duckdb --timeout 120
python -m agent3.run_news NVDA --alias NVIDIA --scorer lm \
  --output-dir output/news-nvda --db output/news-nvda.duckdb --timeout 120
python -m scripts.check_agent3_news_acceptance <saved-bundle.json> \
  --output <new-acceptance.json> --html <new-report.html>
pytest -q
```

`--news-query` is live-only, nonempty and at most 200 characters. An omitted query
uses the exact ticker. Explicit `--alias` remains the separate headline-relevance
policy. Successful empty retrieval is held (3); unavailable retrieval exits 4.
Reproduction uses current search results, which may differ or be unavailable.

## Evidence and verification

Full local suite: **763 passed in 84.79 seconds**, Python 3.11.9, including
27 new regressions. The new tests also passed separately with a fixed provider clock;
package dependency checks and repository whitespace checks passed.

Local evidence is ignored under `output/agent3-news-recovery/`:

- Final ASML: `asml-accepted/0ca21cb717214b6c979526bf4e30deb7/`
- Final NVIDIA: `nvda-accepted/b49cd747a06244f08320e5ce6ca01697/`
- `asml-final-acceptance.json`, `nvda-final-acceptance.json`
- `asml-final-report.html`, `nvda-final-report.html`

Earlier probe/intermediate attempts are retained separately. Do not confuse their
counts with final acceptance; the index-tag correction intentionally changes those
older analytical results. Restore original code to replay an older result exactly.
Final live bundles retain hashes for their actual working source versions.

New regressions cover HTTP errors, malformed envelopes, empty success, bounded
responses, safe failure archival, explicit queries, relevance separation,
headline/language holds, populated replay/export, HTML escaping, index metadata and
acceptance-evidence tampering. Existing duplicate/correction and failure/recovery
regressions remain in the full suite.

Remaining scope: optional real FinBERT inference and a reviewed, labelled sentiment
benchmark; richer article text/language evidence and stronger relevance policies
would require their own validation. These populated samples establish bounded
retrieval and processing, not universal coverage or sentiment accuracy.
