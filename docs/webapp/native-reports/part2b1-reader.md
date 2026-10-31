# Part 2B.1 — native research reader

Implemented 30 October 2026; handoff checked 31 October 2026. Agent 1's **saved summary and key figures now render directly
inside Keystone**. The primary Agent 1 reader has no report iframe or raw HTML
injection. Agents 2–4 retain their existing saved-report reader.

## Delivered scope

Shared report elements provide an editorial header, separate execution/evidence/
approval/file-consistency states, review notice, section navigation, metric cards
and labelled sections. They follow the existing forest-green shell, restrained
gold accents and neutral report surfaces.

The Agent 1 page reads Part 2A's registered report-view endpoint. It displays the
backend's supported summary and up to three available main observations, followed
by revenue, operating margin, reported free cash flow and prior-year revenue
growth when those saved metrics exist. Diagnostic valuation is not promoted into
the summary. Each figure retains its unit and own financial period.

Compact labels such as `EUR 32.67bn` have an explicit exact-value/source control.
The source panel shows `EUR 32,667,300,000.00`, its canonical value and unit, the
saved artifact and JSON Pointer. Returning restores focus to the same source
control. Decimal-string formatting avoids conversion through a JavaScript Number,
including for large exact monetary amounts. Percentage scaling and compact-label
rounding are display operations; no financial calculation is introduced.

Review notes remain expandable, with affected source sections and every saved
check reference. Source records and original HTML are optional verified downloads.
Technical identities/hashes stay behind an evidence disclosure. No raw model
prose, confidence-as-investment-certainty or approval control is added.

## Read and failure behaviour

Requests use the saved run ID, no-store reads and cancellation on navigation.
The reader validates the fields it uses, supported version/templates, cross
references, and agreement with the selected inventory's source IDs, names and
hashes. Python remains responsible for the full schema and source/financial
projection checks. The browser's smaller boundary is not a second financial engine.

| State | Reader behaviour |
| --- | --- |
| Loading | Explicit busy state; no previous report presented as freshly checked |
| Valid native view | Native summary, four eligible key-figure slots, review and evidence |
| Missing main figures/observations | Explicit unavailable/empty wording; no zero substitution |
| Legacy run without native registration | Clear unavailable state; offer original HTML only after a fresh successful registered HEAD check |
| Unsupported version/template | Unsupported state; no guessed conversion or partial figures |
| Changed/invalid evidence | Block figures and download controls; move focus to the error heading |
| Removed run | Saved-run-not-found state |
| Connection failure | Safe local-server explanation and retry/reload controls |

Downloads are read through the registered same-origin file URL, then checked for
the loaded inventory's exact byte length and SHA-256 before the browser receives
the file. A failed evidence read invalidates the displayed report. A later retry
must successfully revalidate it; no cached analytical view is silently substituted.
“Matched when loaded” identifies a snapshot, not continuous monitoring or source
authentication. Rechecking makes no new provider/model request.

## Run locally

Use a fresh destination to prepare new offline examples, or project an existing
registered synthetic workspace with Part 2A's `project` command:

```bash
.venv/bin/python -m keystone.workspace prepare --native \
  --destination output/workspace-native-reader
cd web
pnpm test
pnpm run build
cd ..
.venv/bin/python -m keystone.workspace serve \
  --workspace output/workspace-native-reader --port 8776
```

Open `http://127.0.0.1:8776/#/runs/research-example`. Existing catalogue v1 examples
do not gain native data automatically. See [Part 2A](part2a-data-layer.md) for
projection commands and the supported source scope.

## Verification

- **25 frontend tests passed:** version/source/reference refusal, empty/withheld and
  diagnostic boundaries, exact decimal/percentage formatting, safe errors,
  cancellation, original verification, confined URLs and download integrity.
- **71 workspace/backend tests passed:** existing report/download protections and
  the native projection/data API regressions.
- **TypeScript check and production frontend build passed.** CI now includes the
  frontend boundary tests; a remote CI run is not claimed for this uncommitted work.
- **Browser checks:** actual native research with zero iframes, keyboard section
  jumps, exact source inspection and focus return, verified model download, legacy
  fallback, unsupported version, removed run, altered-evidence refusal and recovery.
  The tested preview copy was restored byte-for-byte after the negative probes.
- **Responsive checks:** 320px and 390px layouts preserve content without outer
  horizontal overflow, including the selected source panel. Desktop section
  navigation and the four-card layout were also inspected.

The frontend fixture is a reduced synthetic reader-boundary capture. It is not a
complete backend report, independent source evidence or a publishable workspace.
Browser checks use the complete registered local workspace. Neither check grants
financial approval or completes analyst interpretation acceptance.

## Remaining work

**[Part 2B.2](part2b2-research.md) is implemented:** performance detail, valuation
assumptions, peers, market context, consensus, external-research availability and
richer evidence presentation now render natively. Its separate record describes
versioned saved-data detail, numerical tables and browser checks. Human
interpretation acceptance remains open.

**Part 2C** supplies interactive graphs and hover/focus/touch inspection over the
saved series and numerical tables. Native Agent 3 pages, other-agent native readers, full print/export
acceptance and cross-agent browser/reader acceptance remain later work. No live
data access, browser execution, financial approvals, backup or deployment change
is included.
