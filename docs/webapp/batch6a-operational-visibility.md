# Webapp Batch 6A — operational visibility

**12 November 2026 · Private, supervised local operation.**
[Batch 6 roadmap](batch6-operational-readiness.md) · [Open Keystone](open-keystone.md)

The Operations page helps a local operator answer: Is the worker available?
What happened to a request? Why is work waiting? Which records cannot be checked?
Is an application storage limit approaching?

For example, a fictional research request can remain queued because the server
was started without its worker. Operations shows the original request, its
not-started state and the worker explanation. Enabling the supported worker lets
that same request proceed; creating another job would only add another request.
A delivered report is then counted as ready for financial review, not approved.

## Using the page

Connect to the private workspace and choose **Operations** in the navigation.
**Recheck operations** performs a fresh read. Optional automatic refresh runs
every 15 seconds while the page is visible, without overlapping its own checks.
It is off by default. Times include seconds; observations older than one minute
are labelled for rechecking. During a refresh, the previous observation stays
explicitly labelled; a failed request removes it instead of displaying cached
health as current.

The page provides:

- Separate checks for job records, input records, registered reports, the owned
  worker process and local storage.
- Full retained-job counts with active, recorded failed/changed, ready-for-review
  and recovery-inspection groups. Filters and ten-item pages provide individual
  references, execution stages, saved dates, elapsed time and the selected limit.
- Current workspace capacities, measured storage/reservations and free space on
  the workspace's disk volume.
- Import outcomes and links to existing job/receipt screens in the normal view.
- Plain-language next steps, with details of the observation's limits available
  separately. There are no repair, deletion, restart or financial-action buttons.

Checking status never submits, claims, cancels, retries or recovers work. It
does not retrieve provider data or run a model. Historical failed jobs remain
visible without permanently declaring the current application broken. Uncertain
outcomes and recovery holds still receive explicit inspection guidance.

## Operations-only access

If normal connection fails because reports cannot be loaded, select **Open
Operations only** on the connection screen, then choose the current access file
or enter the local token again. The verified token is still required. This view
does not load the analyst report inventory, entities, datasets or source figures.
It shows only operator observations and exact references; ordinary analysis,
report and input controls are absent.

Disconnect and connect normally to return to the analyst workspace. Confirmed
financial/review records are unaffected. A temporary failure of an ordinary
workspace refresh also retains the verified workspace identity, allowing both
operating diagnostics and a later successful recheck.

This is a restricted interface view, **not a new backend role or an enterprise
permission boundary**. The local token still represents the existing operator
authority. Server startup must have succeeded first. If an inventory or control
database prevents startup, inspect the terminal and use the documented operator
procedures; this page cannot diagnose a server that is not running.

## What is checked

| Area | Observation | Practical limit |
| --- | --- | --- |
| Jobs | Immutable admissions, execution records, restoration holds and latest saved events, on one read transaction | No invented heartbeat, completion percentage or prediction of completion time |
| Inputs | SQLite consistency, import descriptors/receipts and retained-object counts | Not a full integrity audit of every input, permission and review object |
| Reports | Registered inventory/file checks and each report's current source-version permission/binding | Does not establish financial accuracy or authenticate an issuer |
| Worker | Whether the server-owned process is running at observation time | A running process does not prove that a particular calculation is progressing |
| Storage | Private database sizes, bounded input/staging/report/control trees and reservations; volume free space | Not total device usage, retention validation or proof of backup protection |

The response is an observation across separate stores, not a consistent backup
or a globally atomic view of work in flight. A worker may change state between
component checks. Recheck a transient hold before interpreting it as persistent.

Unreadable components remain unavailable while other components can still be
shown. A corrupt individual job or import is counted as unreadable, rather than
quietly removed from the total. Pending-space estimates remain unavailable when
the records needed to calculate reservations cannot be read. Zero is displayed
only for a known zero count. Source-held reports retain their count and opaque
references without returning their figures or source content.

The overall labels are **Checks available**, **Attention needed** and **Some
checks unavailable**. Financial approval, live-provider enablement, paid-model
enablement and production-release approval all remain false in this contract.
No operational state grants financial approval or changes a source restriction.

## Capacity observations

Advisories start at 80% of a current application limit. Existing admission rules
still decide whether a particular request is eligible; these numbers are not
permission to process more work.

| Capacity | Current limit |
| --- | ---: |
| Active jobs / retained jobs | 20 / 1,000 |
| Unfinished imports / retained import attempts | 5 / 1,000 |
| Datasets / accepted input versions | 100 / 200 |
| Workspace review notes / correction links / review decisions | 1,000 / 200 / 2,000 |
| Input database / job database | 64 MB each |
| Inputs, staging and import reservations | 200 MB |
| Fresh-analysis evidence and active reservations | 100 MB |

Input reservations use the existing admission allowance of three times package
size plus 65,536 bytes for each unfinished attempt, including interrupted and
delivery-held imports. Fresh research and supplied monitoring/event/news jobs
reserve 16 MB each while active, against their existing combined report/control
evidence allowance. The next admission also needs its own reservation. Thus work
can be limited by evidence space while the queue still has unused job slots.

The fresh-analysis byte/reservation/file constants are shared with admission;
this change does not increase its limits or change eligibility. Other financial
and per-report limits remain enforced by their existing writers. Accounting
storage, permissions and every other file on the device are not claimed to be
covered by a single total on this page.

Free disk space is separate. Advice begins below 5% of the workspace volume or
100 MB. This is a planning warning, not a write probe, disk repair or a new
admission policy. Storage walks inspect only fixed private roots, refuse links
and non-private entries, and stop after 60,000 members per scan group. A failed
or exceeded scan leaves its measurements unavailable.

## Contract and protection

`GET` / `HEAD /api/operations` exists only in private workspaces. The existing
local-token, host, origin, no-store and same-origin boundaries apply. Queries and
write methods are refused. No additional enable flag is required for this read.
Open Keystone checks that the running server advertises operational support.

The strict [version-1 schema](../../keystone/workspace/operations.schema.json)
defines `keystone.operations`. At most 1,000 jobs, 1,000 imports and 100 registered
reports are considered; aggregate counts cover the full bounded ledgers, rather
than only the first UI page. Responses are limited to 1.5 MB. Unknown or malformed
responses are refused by the browser, with checks for the bound workspace,
count totals, stages, capacity states, component states and approval boundaries.

The endpoint returns allowlisted codes, statuses, opaque IDs, dates and counts.
It returns no absolute paths, tokens, financial packages, notes, source names,
raw exceptions or agent logs. The browser keeps the token and responses in tab
memory; it adds no persistent credential or diagnostic cache.

## Acceptance and remaining boundaries

Automated coverage includes empty and queued work, owned-process availability,
running stages, interruption, historical failure, all five saved report families,
permission withdrawal, corrupt records/ledgers/inventories, capacity reservations,
low space, bounded/link-refusing scans, request protection and read-only evidence
preservation. Restored queued work must remain held; observation must not release
or execute it. Concurrent receipt updates must not become invented zero counts.

Frontend checks cover real fictional backend observations, malformed or promoted
approval fields, false healthy summaries, inconsistent counts, wrong authority,
oversized replies, expired access, late responses, diagnostics-only connection
and ordinary refresh recovery.

The isolated browser rehearsal covers queued-worker guidance, the same job's
completed delivery, a reversible fictional report-inventory outage, normal-access
refusal, operations-only diagnosis, restoration of the exact original inventory,
and normal reconnection. Generated outputs, local keys and screenshots remain
ignored under `output/operations-6a-preview`.

This completes the local visibility scope of 6A. Storage lifecycle and retention
are 6B; repeatable installation/updates are 6C; the wider access/privacy review is
6D; recovery/support rehearsals are 6E. Large-corpus performance, analyst
interpretation and the scoped release decision retain their later acceptance
work. Independent backup, encryption/key recovery and clean-machine recovery
remain deferred dependencies. No new hosted telemetry service is introduced.

### Recorded validation

- **216 distinct related backend cases passed:** the 215-case operations,
  workspace, job-admission, onboarding, private-recovery and launcher run, plus
  the fresh-close accounting read check. These include 30 operations-specific
  cases. The complete repository suite was not rerun for this local batch.
- **All 470 frontend tests passed**, including 35 new operating-contract and
  connection cases. TypeScript checks and the production build passed.
- The browser showed the original fictional job waiting with its worker disabled,
  then delivered through that same request after enabling the worker. It retained
  financial-review-required status and reserved zero model requests/output tokens.
- During an isolated report-inventory fault, normal connection refused access
  while Operations-only access showed the unavailable report count and readable
  independent components. Reversing the fault restored the exact inventory.
- All **25 original input/report/operation/database files** stayed byte-identical
  after the read-only checks and fault reversal; only one job existed throughout.
- Optional automatic refresh advanced the visible observation time. Keyboard
  refresh, normal reload/reconnection and the final 576-pixel side-panel layout
  were checked, with no horizontal page overflow.

Ignored evidence includes `regression-tests.log`, `accounting-read-test.log`,
`web-tests.log`, `build.log`, `browser-check.json`, `integrity-check.json`,
`operations-overview.jpg` and `operations-outage.jpg`.
