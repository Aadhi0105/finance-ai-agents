# Part 3C — Agent 3 report validation and polish

Implemented 31 October 2026. This batch checks the native event/news readers from
Parts 3A/3B against controlled saved-data cases, improves pagination and supplies
a complete reading/print copy. It does not complete human interpretation, physical
accessibility or real-source production acceptance.

## Changes made

**Complete reading copy.** Agent 3 reports have a “Reading & print copy” control.
The application rereads and validates the registered evidence before opening it,
and again before requesting printing. A failed read removes both interactive and
reading-copy figures and focuses the error state. No original record is rewritten.

The copy contains all saved measures, chart observations, tables, review notes,
definitions, evidence references and file hashes. Screen pagination, hidden series
and headline filters do not remove content from it. Missing and withheld values
retain their states and canonical nulls; diagnostic values remain labelled.
Static SVG graphs accompany complete exact tables. The reading copy retains the
saved presentation's explicit text excerpts; full original text remains in the
registered bundle. Untrusted text and recorded addresses are rendered as text.

The interactive report remains mounted while the copy is open, preserving its
selection, filters and page. Returning restores focus to the opening control.
Narrow layouts contain wide graphs and tables in labelled, focusable scroll areas.
Print styles hide application navigation and controls, repeat table headers and
use landscape A4 formatting. This uses the browser's print workflow; no PDF
generation service or new export endpoint was introduced.

**Pagination and wording.** News pages announce the matched and displayed ranges.
Next/Previous focuses and scrolls to the new retained-headline page. The filter
still changes only presentation. Known text-scope codes read “Headline only” or
“Headline and provider summary”; the original fields remain in the saved source.

**Early news failures.** A run can stop before producing any analytical result.
News adapter **1.2.0** now represents failed/unavailable/refused attempts without
inventing a valid empty feed, zero coverage or neutral tone. Counts remain
unavailable, the coverage graph is withheld and the saved terminal reason remains
traceable. Completed/held attempts without a result are refused. The new closed
`news-retrieval-summary-v1` template is admitted only for news 1.2.0 and cannot
mask a completed state or populated analytical figures. Existing 1.0.0/1.1.0
recipes are unchanged; ordinary 1.2.0 results reuse the 1.1.0 context mapping.

## Repeatable controlled cases

From the repository root:

```bash
.venv/bin/python scripts/prepare_agent3_report_qa.py \
  --workspace output/workspace-news-3b-final \
  --destination output/workspace-agent3-qa-new \
  --large
.venv/bin/python -m keystone.workspace serve \
  --workspace output/workspace-agent3-qa-new --port 8785
```

Choose a new destination and a free port. The helper accepts explicitly registered
synthetic evidence, copies the original files unchanged, and creates labelled
controlled variants. It writes a new catalogue only after successful registration
of all cases. New bundles have their own attempt identities and hashes. QA
description HTML makes no verified-replay or independent market-evidence claim.
The news cases use the offline funnel with its fixture scorer; no source/model
acquisition occurs. Large event cases repeat synthetic observations for UI stress,
not additional independent issuers or an investment study.

The reviewed workspace is `output/workspace-agent3-3c-acceptance`, served at
`http://127.0.0.1:8785/`. It contains the five baseline workflows and:

| Run ID | Browser acceptance case |
| --- | --- |
| `events-repeated` | Eight cases, seven issuers, a missing CAR, withheld mean and no invented event path |
| `events-ten` | Ten-issuer count and saved diagnostic p-value available, while other review restrictions and false financial approval remain |
| `news-empty` | Empty saved input with genuine zero counts; no claim that no company news existed |
| `news-irrelevant` | Input records exist, no headline relevance retained, original exclusions available |
| `news-failed` | Attempt stops before any result; unavailable coverage, zero plotted graphs and withheld tone |
| `news-mixed` | Duplicate membership, stale exclusion, language/headline-only limits and escaped markup-like text |
| `news-unscored` | Scorer failure with retained text but no usable tone graph or neutral substitute |
| `news-pages` | Forty representatives, page/focus navigation, filter preservation and a complete unfiltered reading copy |
| `events-large` | 2,000 repeated synthetic event cases, all plot observations and both complete 2,000-row case tables retained |
| `news-large` | 600 representatives, paginated interactive cards and complete 600-row story/score tables |

An initial large fixture with repeated source addresses exceeded the retained
review-row/cell limits and was refused before publishing a catalogue. The final
large feed uses distinct fictional addresses. Bounds were not weakened and
details were not silently dropped to make the fixture fit.

## Verification

- **1,118 Python tests passed**, including six additional early-failure and prior
  adapter compatibility cases; 120 focused backend/workspace tests passed.
- **115 frontend tests passed**, including ten complete-copy and incomplete-state
  cases. They cover all rows/references, older views, null versus zero, untrusted
  strings, closed version/template scope and refusal of contradictory states.
- **TypeScript and production build passed**, with no new dependencies. Explicit
  TypeScript import extensions let the new presentation helper use the existing
  Node test runner with the no-emit build.
- **Browser:** controlled cases above; keyboard Home/End and exact source values;
  pagination focus, forty-row copy despite a one-card filter, and return with the
  filter retained. Markup-like titles/body text produced no injected image/script.
- **Large-report observations:** one local Chrome run opened the 2,000-case report
  in about 1.0s and its full copy in 1.3s; the 600-story report in 0.75s and its
  full copy in 1.34s. These include browser/tool/HTTP overhead and are illustrative
  observations, not a performance guarantee or a test of every allowed payload.
- **390px/320px layouts:** primary and reading-copy states stayed within the outer
  viewport. Wide tables/graphs scrolled within their containers. Temporary
  viewport overrides were reset.
- **Pre-print integrity refusal:** changed bundle bytes in a disposable copy
  blocked printing before the dialog and removed stale copy/graph content.
  Byte-for-byte restoration recovered the report. Source and acceptance workspace
  hashes remained unchanged during browser reads.

**Print acceptance limit:** requesting print paused DOM automation while the
browser print workflow was active. The automated preview tab was closed without
submitting a print job, and a fresh report tab resumed normally. The complete
copy's content and print stylesheet are implemented; actual PDF pagination,
saved-PDF reconciliation and physical printing are not claimed as verified.

Human interpretation, physical touchscreen/screen-reader sessions, full
print/PDF acceptance and browser saved-download completion remain open. The
earlier Downloads-page security block was not bypassed or retried. Authorised
real-source news tone, verified event-path projection, Agents 2/4 native readers,
independent backup and production-release decisions remain separate work.
