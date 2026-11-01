# Part 4C — cross-agent report acceptance

Implemented and checked **1 November 2026** for registered, saved synthetic
evidence. This completes the bounded implementation and browser rehearsal across
the five report families. It does not complete human interpretation, physical
accessibility or actual print/PDF acceptance, and grants no financial approval.
Part 4B is included in the same pending change set.

## What changed

Agent 1 now has the same complete reading/print-copy option as monitoring, events,
news and close. Its copy distinguishes Keystone's conditional model valuation,
provider consensus and identifiable broker research. In the example, consensus
is unavailable and broker reports/ratings were not collected.

All copies now retain saved observations and definitions, section scope,
section-specific review requirements, source date fields and the full reference
index alongside the complete numerical tables. Preparation time does not become
an observation date. This is the complete native presentation; an excerpt in a
saved source remains an excerpt, with its registered original separately available.

The static plots in the copy share geometry and series styles with the interactive
reader. Research scenarios and peer comparisons use separate dots, with no fitted
path or implied probability interval. Multiple lines have named legends and
distinct patterns/marks; missing observations still break lines. Percentage axes
identify their display unit. First and last labels align inside the chart, in both
interactive and copied plots. Exact source precision remains in the tables.

No adapter recipe, financial calculation, evidence gate, source record or approval
decision is changed by Part 4C. Opening and downloading remain read-only.

## Repeatable controlled workspace

`scripts/prepare_native_report_acceptance.py` combines explicitly supplied,
registered synthetic workspaces into a fresh private destination. It verifies
source bytes, copies original evidence unchanged and prepares current native views.
Repeated run IDs require identical original evidence **and** inventory metadata.
It refuses conflicting IDs, an existing destination, a child of any input, symlink
destinations and inventories over the catalogue bound. It does not scan arbitrary
output directories, acquire data or call a model.

The earlier guides describe preparing the three inputs. From the repository:

```bash
.venv/bin/python scripts/prepare_native_report_acceptance.py \
  --workspace output/workspace-agent3-3c-acceptance \
  --workspace output/workspace-monitoring-4a-verified \
  --workspace output/workspace-close-4b-release \
  --destination output/workspace-native-4c

.venv/bin/python -m keystone.workspace serve \
  --workspace output/workspace-native-4c --port 8791
```

Choose another fresh destination if that directory exists. Generated workspaces,
receipts and screenshots remain ignored local QA output, not committed company data.
The rehearsal combined **32 unique runs** and checked **201 source files**, with
the original source workspaces preserved. This is a presentation test workspace,
not an independent backup or a production deployment.

## Browser evidence

Checks used the in-app browser against the local production build. Results are
bounded to this browser, these saved cases and the inspected layouts.

| Check | Observed result |
| --- | --- |
| Five baseline report families | One visible main heading, no primary-report iframe, explicit financial approval “Not approved” |
| All 32 primary reports and complete copies | Expected measure, finding, table-row, chart-row, source and evidence-reference counts retained; no outer page overflow at the desktop viewport |
| Controlled event/news cases | Repeated and ten-event samples, empty/irrelevant feeds, failed retrieval, unavailable scorer, mixed exclusions, pagination and larger payloads remain readable without promoting held results |
| Controlled monitoring cases | Baseline, pending/approved/replaced correction, quiet/no-new-data, absent history and paginated cases retain their separate scopes |
| Controlled close cases | Original/corrected, loss, zero, cost-root, held forecast, populated uncertainty, closed year and larger account hierarchy remain distinct |
| Larger copies | 2,000 event chart rows; 600 news representatives with all 3,611 saved table rows; close with 305 measures and all 1,545 saved table rows retained |
| 390px and 320px | All five baseline primary/copy layouts fit without outer overflow; plot/table scroll regions stay contained; viewport override reset |
| Keyboard | Mobile section selector + Go focuses the chosen section; Home/End selects exact first/last observations; source details open and Return to reading restores the invoking source button in all five families |
| Copy entry/return | Heading receives focus; returning restores the copy button and clears copy mode; controlled cases retain their report identity |
| Structural accessibility checks | No duplicate element IDs or unresolved labelled/described-by targets in the inspected controlled primary reports and narrow baseline reports |
| Research plot visual review | All three price/moving-average lines have distinct patterns and named legend entries; all inspected date labels fit inside the plot |
| Actual original HTML downloads | Five browser download completions; saved bytes and SHA-256 match their registered originals. Research HTML contains embedded chart images; the other four checked originals have no image dependencies |
| Changed-source refusal | In a separate disposable workspace, one source-byte change per report family blocks the copy, removes stale figures/downloads and focuses “Saved evidence needs attention”; exact restoration recovers each report |
| Source preservation | Combined and original QA evidence checked for unchanged bytes after browsing; disposable evidence restored exactly |

The complete-copy counts are checked against the registered views, not against an
assumed minimum number of visible rows. Interactive filters/pagination do not limit
the copy. Source file consistency still does not establish financial source truth.

Local evidence includes `output/native-4c-expected.json`,
`output/native-4c-browser-receipt.json`, `output/native-4c-download-receipt.json`,
`output/native-4c-source-hashes.json` and `output/native-4c-research-copy.png`.
Run identities and hashes change when fixture inputs are prepared again.

## Automated verification

- Full Python suite: **1,172 passed**.
- Interface tests: **189 passed**.
- TypeScript check and production build passed; no dependencies added.
- New combination-helper tests cover real offline fixture integration, read-only
  delivery across all five families, network isolation, collisions and unsafe destinations.
- New copy/plot tests cover supported current/prior recipes, complete content,
  discrete scenario/peer plots, multi-series legends, missing gaps, genuine zero,
  withheld values, escaping, edge labels and refusal of financial approval changes.

## Remaining acceptance

Use the [reader trial](reader-trial.md) without looking at its separate
[reviewer answer guide](reader-trial-answer-guide.md) first. Record actual answers
and confusing wording; no reviewer has been marked as having passed it.

Physical touch and a screen-reader session remain pending. Browser keyboard and
DOM checks are useful evidence but do not establish conformance on those devices.
Actual PDF pagination, value/restriction reconciliation in the resulting PDF and
physical printing remain pending. The copy and print stylesheet are implemented;
this session did not submit a print job or validate a generated PDF. An HTML
download match does not establish print/PDF correctness or cross-browser support.

The verified event-relative path and authorised real-source published news tone
remain separately scoped analytical capabilities. Live execution through the web
interface is Webapp Batch 2. Licensing, independent backups, clean-machine recovery,
authenticated approvals and deployment retain their existing release dependencies.
