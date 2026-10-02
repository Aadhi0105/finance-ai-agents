# Agent 3 Batch 3 — current-news evidence and tone controls

This batch addresses news findings F10/F11/F12/F15/F16/F17/F18. Track B remains
separate from Track A: no news score enters event-study calculations. Outputs are
current retrieved **document-level tone**, not entity-specific sentiment, causal
claims or return forecasts.

## Relevance and provenance

Fetching a ticker no longer assigns that ticker to every returned article.
Provider entity tags, query ticker, ID, publication timestamp field, retrieval
instant, publisher, article URL, headline and summary are retained separately.
Both nested and flat provider schemas are supported. Malformed records survive
shaping as explicit exclusions instead of silently disappearing. `displayTime`
is not substituted for a missing publication time.

The bounded relevance rule requires a headline match to an explicit company alias,
a full exchange ticker, or a cashtag. Bare short ticker strings such as `CAT` are
not inferred from ordinary words. Body-only mentions and provider tags alone do
not qualify. Aliases are user-supplied, recorded with the run and matched at word
boundaries; they are not automatically verified identities. This conservative
rule can miss legitimate stories and does not establish that a company is the
sole subject. Multi-entity evidence is flagged, and all scores are labelled
**document-level**, including apparently single-company headlines.

## Timestamp and clustering contracts

Timestamps must be timezone-aware ISO values, normalized to UTC. Original
publication and retrieval times remain distinct. Publication after the as-of
cutoff, publication after retrieval, retrieval after the cutoff, invalid dates
and records older than the selected window are excluded. The default freshness
window is seven days (configurable 1–30). Day buckets are UTC. This is not a
historical point-in-time archive: fetching today's edited article does not prove
what text existed at its stated publication time.

Clustering sorts by normalized publication time and evidence ID. Within 24 hours,
including across UTC midnight, equivalent normalized headline/body/entity text
shares a cluster. Tokens preserve word order, negation, numbers and currency/sign
markers; case, whitespace and nonessential punctuation do not create extra
stories. No broad Jaccard threshold merges semantically opposite headlines.
Reworded stories can remain separate: this is deliberately conservative heuristic
clustering, not proven story independence. Counts are labelled accordingly.

Canonical URLs remove tracking parameters and fragments while retaining semantic
query parameters. IDs/URLs with changed text retain separate stories and get a
review flag; corrections are not overwritten. Every cluster retains its members,
source identities and stable evidence/cluster hashes. Distinct source count is
separate from raw record coverage. Duplicate entity tags cannot multiply counts.

## Scorers and review

The live default is `lm`, explicitly disclosed as a **repository-curated lexical
tone subset**, not the verified official full Loughran–McDonald dictionary. Runtime
evidence includes vocabulary sizes, mode/version/content hash and matched tokens.
A configured `LM_DICTIONARY_CSV` is loaded once per scorer; errors refuse setup
without fallback. Membership flags greater than zero are included; negative year
flags are removed entries. The official dictionary explains those conventions:
[Loughran–McDonald resource](https://sraf.nd.edu/loughranmcdonald-master-dictionary/).
Configured files are identified by filename/hash; their official provenance is
not automatically verified.

Lexical scores are `(positive_hits - negative_hits) / tone_hits`. Zero tone hits
mean unavailable, not neutral. Lexical tone does not handle context/negation and
is held as diagnostic evidence. No invented confidence score is calculated.

`finbert` and `divergence` require optional `transformers` and `torch` plus an
explicit `AGENT_FINBERT_REVISION` containing a 40-character model commit hash.
Both model and tokenizer use that revision. Runtime records dependency versions,
class probabilities, token counts/limit and truncation. The supported model is
English with positive, negative and neutral classes:
[ProsusAI model card](https://huggingface.co/ProsusAI/finbert).
Missing dependencies, invalid probability labels/vectors and scorer exceptions
never fall back to the stub. Unsupported or unknown article-language metadata
requires review; there is no automatic language-detection or translation guarantee.
Truncation and a top-two class margin below 0.1 require review. Model probabilities
and class margins are diagnostics, not calibrated reliability estimates.

Divergence defaults to FinBERT plus the lexicon, never a hidden stub. Both component
records and all review reasons survive aggregation. Disagreement cannot increase
confidence. Aggregate confidence is null; raw fixture/custom-scorer confidence can remain
in the evidence record after range validation. No calibration claim is made.

`stub` requires explicit fixture/demo CLI mode. It needs fixture scores, never
hash-derived pseudo-sentiment. Unknown scorer names fail configuration. Scores must
be finite numbers in [-1,1], excluding booleans; supplied confidence values must
be finite and in [0,1]. Invalid output is retained as an unavailable scored item.

## Publication and saved runs

The final record includes ingested and scored stories, cluster lineage, exclusions,
source references, actual scorer identities and aggregate review reasons. A held
signal has `level=null`; any computable mean is retained only as
`diagnostic_level`. A failure in one scorer does not silently drop that story.
Exclusions, missing evidence, demo mode and any review flags hold the overall
publication. An empty feed is held and does not mean neutral sentiment. Clean
real-model output may be labelled `DESCRIPTIVE`, never an investment finding.

The CLI renders the exact final scored set without a second scoring pass. Each
started run writes `output/agent3-news/<id>/run.json` through the shared atomic
attempt mechanism. It retains input, fetch, scoring and result stages, uses a
180-second worker deadline (30–3600 configurable), and suppresses raw provider
exception text. Known environment credentials are redacted. State/replay approvals
and historical-input replay remain Batch 4; these files are editable local records.

Exit codes: 0 = descriptive completed; 2 = invalid configuration; 3 = held;
4 = provider/scorer unavailable or deadline/interruption; 5 = worker failure.
Unavailable/error outcomes also suppress publication of any retained result.
Configuration errors before an attempt can be created cannot leave an attempt file.

## Commands

```bash
# Current news, explicit headline aliases, local lexical diagnostics:
python -m agent3.run_news SRAIL.SW --alias 'Stadler Rail' --alias Stadler --scorer lm
python -m agent3.run_news ASML.AS --alias ASML --scorer lm

# Offline demonstration (always held), reproducible fixture cutoff:
python -m agent3.run_news ASML.AS --alias ASML --scorer stub --demo --fixture fixtures/news.json --as-of 2026-01-28T23:59:00Z

# Optional real model: install dependencies and set an actual approved immutable
# model commit in AGENT_FINBERT_REVISION before running:
python -m agent3.run_news ASML.AS --alias ASML --scorer finbert
```

The repository `.env` is loaded without overriding exported variables. The output
root is repository-anchored; explicit fixture/output paths are caller-relative.
Use `--max-age-days`, `--timeout` and `--output-dir` to choose bounded run settings.
The as-of cutoff defaults to after retrieval; an explicit historical fixture run
requires `--as-of`. A past cutoff does not turn live data into an archival dataset.

## Verification

Regression tests cover provider shaping, false relevance, timestamp cutoffs and
UTC days, negation/corrections, duplicate entity counts, permutation-stable clusters,
scorer validation and failure containment, final disagreement propagation,
lexicon failure/hash/membership rules, FinBERT vectors/truncation, and the real
CLI worker writing a demo evidence record.

Real FinBERT weights were not executed: optional dependencies are absent in this
workspace. Controlled pipeline tests validate the contract, not model accuracy.
No calibrated confidence or general sentiment-quality acceptance is claimed.


Live checks on 2 October 2026 used `lm` with no paid model call. The provider
returned empty lists for Stadler Rail (`SRAIL.SW`, attempt
`bdc61feda1e94db9be7acfaba138b669`) and ASML (`ASML.AS`, attempt
`8c9253828b364451bbe432cd8622a139`). Both saved held outcomes (exit 3), no signal
and no fabricated neutral value. The provider library can mask upstream absence
or response problems as an empty list; these checks do not establish that no
news exists. Evidence is in ignored `output/agent3-batch3-live/`.

The documented fixture command also ran through the actual bounded worker:
attempt `658b178f4273499a845506c43ee4a4fd` in
`output/agent3-batch3-demo/` retained nine input records, four scored clusters,
five exclusions and held synthetic results. A populated live feed and real
FinBERT inference remain unverified; offline contract tests do not replace them.


Final validation: **686 tests passed in 76.51 seconds on Python 3.11.9**, including
47 new Batch 3 regressions. Saved-level publication checks recompute the aggregate
from the referenced scored stories and reject altered levels, invalid numbers,
count mismatches and retained scorer review flags. Documentation links and
`git diff --check` passed.
