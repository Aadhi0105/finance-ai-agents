# Batch 1 browser QA

Date: 30 October 2026. Local FastAPI server, built React frontend, and the
ChatGPT in-app browser. The preview used `output/workspace-batch1-preview/`
(five synthetic runs, twenty artifacts). No live provider calls, paid models,
external uploads or approval actions were exercised.

## Checks completed

| Area | Observed result |
| --- | --- |
| Overview | Five saved reports, four agents and five review-required results displayed |
| Search | Company search narrowed the list; an unmatched query showed a clear empty state; clear filters restored results |
| Status filter | Held state showed the two held Agent 3 runs |
| Workflow navigation | Research, monitoring, events/news and close showed their registered runs |
| Research report | Original review draft loaded; five chart images completed with nonzero natural widths |
| Monitoring report | Saved cycle observations, breaches and correction-workflow boundaries loaded |
| Historical events | Saved HTML displayed matched replay and held descriptive diagnostics |
| News | Invented headlines, matched replay, withheld tone and publication hold remained visible |
| Financial close | Summary and original report agreed: EUR 60.00 budget, EUR 65.00 actual, EUR +5.00 variance |
| JSON inspection | Saved sealed-news evidence and close/lineage JSON displayed in the evidence panel |
| Download | Registered sealed-news JSON downloaded successfully and matched its registered SHA-256 hash; navigation remained in the workspace |
| Evidence library | Twenty registered artifacts across five report cards |
| History and missing run | Run history loaded; an unregistered run showed “Saved run not found” |
| Route reload | Reloading a detail URL retained the selected run |
| Keyboard tabs | ArrowRight and End selected the expected report-detail tabs |
| Skip link | Focus moved to main content without changing the selected route |
| Information dialog | Focus entered the dialog, Tab stayed inside, Escape closed it, and focus returned to its trigger |
| Short desktop window | Sidebar information control remained reachable by scrolling |
| Narrow overview | At measured 390 × 844 CSS pixels, document width was 390; the 720px table scrolled inside its 356px container |
| Narrow details | Close metrics, evidence controls and JSON preview fit the 390px page without outer horizontal scrolling |
| Small overview | At measured 320px width, document width remained 320 |
| Mobile information dialog | Content and close control remained within the viewport; longer content can scroll inside the dialog |
| Console | No captured JavaScript error messages at final overview check |

## Fixes made during review

- Kept the skip link separate from hash-based application routing.
- Restored dialog focus to the opening control and trapped keyboard focus inside
  the dialog while open.
- Allowed a short desktop sidebar to scroll so its bottom controls stay reachable.
- Returned page scroll to the top when navigating between workspace views.
- Positioned the table container so hidden accessibility text could not escape
  its horizontal scrolling boundary and widen the mobile page.
- Labelled inventory consistency as “Matched on load” to describe the saved
  browser snapshot accurately.
- Constrained the information dialog's height on small screens and strengthened
  execution/review text contrast.

## Evidence and limits

Local screenshots and the interaction checklist are generated under
`output/workspace-batch1-qa/`. They remain gitignored along with the synthetic
workspace. Repeat the setup in the [workspace guide](batch1-report-workspace.md)
to create a fresh preview on another checkout.

These checks establish bounded local rendering and interaction evidence. They
are not a full accessibility audit, cross-browser certification, mobile-device
acceptance, authenticated approval test, or analyst interpretation sign-off.
Existing report layouts remain separately owned by their agent renderers; some
wide report tables intentionally scroll horizontally within their report.

The server started for the initial layout review was stopped during teardown.
The user subsequently requested the working app after opening the source HTML in
a file preview; the local preview was restarted. Use the guide's `serve` command
whenever the local server is not running. The application URL requires the server;
opening `web/index.html` directly does not build TypeScript or start the backend.

## Pre-merge audit fixes and recheck

The original layout pass did not exercise the close report's internal download
and history links. A subsequent code audit found that the registered filenames
differed from those links, that both report sandbox settings blocked downloads,
and that the ordinary developer requirements omitted FastAPI.

All three were corrected before commit:

- The preparer preserves `close-june.html` and `close-june.json`, leaving the
  original HTML bytes intact. A regression check resolves every local report
  link/image reference against that run's explicit inventory.
- The iframe and response sandbox both allow downloads while continuing to block
  scripts and forms. The corrected close report's own download control succeeded
  inside the iframe and in a standalone report tab. Both saved JSON downloads
  matched the registered content hash. The original close-history link also
  returned to the saved report successfully.
- A new virtual environment installed only `requirements-dev.txt`, passed
  `pip check`, and passed all **1,032** tests, including **35** workspace checks.
  The frontend also passed a frozen-lockfile installation, type check and build.

This recheck used the newly generated `output/workspace-batch1-fixed/` workspace.
Earlier preview directories were preserved; they are not silently migrated.
