# Part 3B — native company-news reports

Implemented 31 October 2026 for registered saved **synthetic** Agent 3 news runs.
Company news now opens directly inside Keystone. It remains separate from the
past-event report: coverage and document tone answer different questions from
historical price reactions.

## What the reader sees

| Section | Purpose |
| --- | --- |
| News summary | Saved cutoff and publication-age window, input/relevant/cluster counts, and an explicit withheld published tone |
| Retained stories | Fictional headline cards with publisher, publication time, text scope, source inspection and a local headline/publisher filter |
| Coverage and exclusions | Interactive processing-stage counts, distinct empty/failed/unknown states, saved basis and original exclusions |
| Tone evidence | Explanation of document scope, with story scores, daily aggregates and scorer metadata inside an explicitly diagnostic disclosure |
| Why review is required | Readable coverage, text/language, relevance/identity and scorer limitations; original identifiers remain available |
| Saved evidence | Exact source values and JSON pointers, registered original downloads, definitions and identity/hash records |

The default example retains two invented headlines about Example Rail. Its
diagnostic scores are **0.3** and **−0.3**; the saved daily diagnostic average is
**0.0**. Published tone is **withheld**. The page does not turn that numerical zero
into a published neutral conclusion, company-specific sentiment or a trade signal.

Story details distinguish publication and retrieval timestamps. Recorded scope,
language, headline matches, cluster size/members and scorer identity remain tied
to source evidence. An unspecified text scope is labelled as such; full-article
coverage is not inferred. Long display text is explicitly marked as an excerpt,
with its full original retained in the registered bundle. Fictional recorded URLs
are displayed as unverified text, without active external story links or fetching.

The headline filter affects only the displayed cards. It does not change coverage,
relevance, clustering, scores or publication state. Lists paginate at ten cards;
shared numerical tables retain their existing 25-row pages. No retained card is
silently dropped. An unmatched filter is distinct from a run with no retained news.

## Graphs and numerical boundaries

The coverage graph shows the saved counts for input, parsed, relevant and clustered
records, with whole-record axis labels. It does not present clusters as independent reporting. Consistent zero
counts remain zero. The diagnostic story graph uses a fixed **−1 to +1** vertical
range, an explicit zero baseline, exact values and categorical representatives.
Scores are not plotted as percentages, reliability probabilities or a return path.

Both graphs use the shared SVG components, with pointer selection, keyboard
arrows/Home/End, step controls, an exact numerical table and source-return focus.
Missing or invalid story scores stay missing. Invalid/inconsistent aggregate
evidence withholds the daily diagnostic rather than recalculating a replacement.

## Adapter and source controls

News adapter **1.1.0** extends the existing schema with saved basis, story detail,
cluster-member, exclusion, daily-tone, scorer-metadata and review-reason tables.
The closed `news-study-summary-v1` template is admitted only for news 1.1.0.
The original **1.0.0** recipe remains supported. Its native reader explains missing
context and does not reconstruct a chart or retrieval state from arbitrary JSON.
A fresh presentation destination is required to obtain the additional detail.

The adapter compares recorded counts with the retained input/ingested/cluster
collections and declared cluster sizes. Failed or inconsistent coverage withholds
the coverage graph and counts. Story diagnostics require bounded, matching saved
sentiment/scorer evidence from a supported scorer. Daily diagnostics require
consistent company/day/cluster associations and saved score counts. No scoring,
aggregation, retrieval or model loading occurs during projection or delivery.

Empty saved inputs, a recorded empty response, no relevant retained records,
failed retrieval/execution and inconsistent/unknown coverage have distinct
explanations. None establishes that no company news existed. Provider/live-source
admission is unchanged: this workspace still accepts only registered synthetic
inputs. The failure/empty-response cases are controlled saved-evidence tests,
not new live-source acceptance.

Published tone remains withheld throughout this synthetic reader, including a
source whose publication label or level was changed. Diagnostic averages, story
scores and model class probabilities never upgrade evidence or financial approval.
Unknown original review reasons and nested scorer/member reasons retain their
source pointers. Source integrity establishes file consistency, not source truth.

## Prepare and preview

From the repository root, use a fresh destination:

```bash
.venv/bin/python -m keystone.workspace project \
  --workspace output/workspace-event-3a \
  --destination output/workspace-news-demo
cd web
pnpm test
pnpm run build
cd ..
.venv/bin/python -m keystone.workspace serve \
  --workspace output/workspace-news-demo --port 8783
```

Use the server command only when that port is free. Open
`http://127.0.0.1:8783/#/runs/news-example`. The reviewed local preview is generated
under `output/workspace-news-3b-final`. Generated workspaces, screenshots and local
QA receipts are ignored outputs, rather than committed financial evidence.

## Verification and open acceptance

- **114 focused backend/workspace tests passed**, including 18 new news cases:
  coverage/source parity, empty/no-relevance/failed states, duplicate membership,
  exclusions, invalid/missing/zero diagnostics, inconsistent counts, false
  publication upgrades, text/language/truncation reasons and 1.0/1.1 compatibility.
- **105 frontend tests passed**, including 30 new news/data/geometry cases:
  source/version/reference boundaries, withheld/diagnostic state, score ranges and
  units, fixed score scale, search immutability and closed template/workflow rules.
- **TypeScript and the production build passed**, with no new dependencies.
- **Full Python suite: 1,112 tests passed**, after the final adapter changes.
- **Browser:** six native sections with no primary report iframe/raster image;
  headline filtering/clear, story evidence and exact score/source inspection,
  keyboard Home/End, source-return focus and the fixed −1/+1 score axis passed.
  Older 1.0.0 news opened with two cards, no invented graphs and explicit missing
  detail. Agent 1 and event reports retain their existing native routes.
- **Responsive browser:** 390px/320px sections and selected source detail had no
  outer overflow in inspected states; wide tables scroll within their container.
  The mobile Go control focused its selected section, and the temporary viewport
  override was reset.
- **Integrity refusal/recovery:** changing a disposable news bundle removed cards,
  graphs and downloads on recheck and focused the error heading. Restoring the
  exact original bytes recovered the report. Source and reviewed workspace hashes
  remain unchanged by browsing.

The results are also recorded in the acceptance matrix.
Physical touchscreen and screen-reader user acceptance, human interpretation,
maximum-payload browser timing and broad print/export acceptance remain separate.
The earlier browser-download completion limitation remains open; automated
size/hash checks continue to pass. This batch adds no live data/model calls,
execution/approval controls, source rights, backup capability or production release.
Eligible real-source published-tone acceptance remains with future authorised
provider integration. The verified event-path work from Part 3A is unchanged.
