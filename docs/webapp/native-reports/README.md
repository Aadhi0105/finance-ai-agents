# Native reports — specification and implementation

Prepared: **30 October 2026**. Part 1 defines the report structure and data contract.
**Part 2A implements the native data layer and read-only API for registered
synthetic evidence.** [Part 2B.1](part2b1-reader.md) adds the native Agent 1 summary
and key-figure reader. [Part 2B.2](part2b2-research.md) implements Agent 1 supporting
sections and saved-data tables. [Part 2C](part2c-charts.md) implements interactive
Agent 1 plots with exact point/source inspection and keyboard controls.
See [Part 2A implementation and commands](part2a-data-layer.md).

## The intended experience

An analyst opens a saved run and reads its report directly inside Keystone:
what was examined, the main observations, supporting charts, limitations, and
evidence. Graphs respond to pointer, keyboard and touch interaction. Original
saved evidence and export files remain accessible.

Agent 1 now opens in the native reader with its summary, key figures, supporting
analysis, review notes and evidence controls. Consensus and broker research have
separate availability. The other agents retain the existing saved-HTML reader.

## Read this pack

| Document | What to review |
| --- | --- |
| [Report specification](report-specification.md) | Reading order, content boundaries, chart behaviour, visual principles and scope |
| [Page outlines](page-outlines.md) | Five annotated report layouts, including detailed Agent 1 and Agent 3 examples |
| [Data contract](report-data-contract.md) | What Python supplies, how the browser reads it, source mapping and error behaviour |
| [Acceptance matrix](acceptance-matrix.md) | How later implementation will demonstrate correctness and usability |
| [JSON Schema](report-view.schema.json) | Machine-readable structural definition of the proposed format |
| [Agent 1 example](examples/agent1-research.json) | Financial history, valuation restrictions and unavailable consensus |
| [Agent 2 example](examples/agent2-monitoring.json) | A saved monitoring exception with its original threshold and observation date |
| [Agent 3 event example](examples/agent3-events.json) | Historical diagnostic returns with publication restrictions |
| [Agent 3 news example](examples/agent3-news.json) | Retained headlines and a withheld published tone result |
| [Agent 4 example](examples/agent4-close.json) | Exact budget/actual amounts and an unavailable forecast interval |

The examples use saved **synthetic** evidence. They are design examples, not
registered runtime report views or verified company facts. Their artifact hashes
identify local snapshots; those generated source artifacts are not added to Git.
New preparation creates different run identities and hashes. Schema validity does
not establish source truth, publication eligibility or implementation readiness.
Each example contains selected sections to illustrate contract rules; the page
outlines define the complete coverage required for a finished native report.

## Recommended decisions

These are explicit design recommendations, not user approval or financial sign-off.

| Decision | Recommendation | Reason |
| --- | --- | --- |
| Primary report | Native sections inside the existing Keystone shell | One readable application, with consistent navigation and styling |
| First data scope | Existing registered synthetic saved runs | Develop the experience without new provider access or model calls |
| Reading order | Summary → supporting analysis → review requirements → evidence | Readers can identify the finding and its limitations before examining diagnostics |
| Narrative | Python-rendered, source-linked explanations of supported facts | Useful prose can be added without publishing unsupported model claims |
| Analyst content | Separate Keystone assessment, external consensus and external research | Readers can identify who produced each statement and what is actually available |
| Charts | Shared interactive components using backend-supplied numerical series | Hover/focus labels and numerical tables agree with the saved evidence |
| Missing or withheld results | Explicit states with reasons and null values | Missing does not become zero; a held tone result does not become neutral |
| Original evidence | Preserve immutable artifacts and offer downloads | Native presentation remains traceable to the saved run |
| Assumption editing | Later controlled analysis work | Changing a discount rate or peer universe produces a new analytical result |
| Agent 3 navigation | Separate “Past event reactions” and “Company news” reports | The two workflows answer different questions and require different explanations |

## Work sequence after this specification

1. Part 2A: shared native data adapters, registration and API — implemented.
2. Part 2B.1: shared native reader and Agent 1 summary/key figures — implemented.
3. Part 2B.2: Agent 1 supporting sections and browser layout review — implemented;
   human interpretation acceptance remains open.
4. Part 2C: Agent 1 interactive charts over saved series and exact tables —
   implemented; physical-device/accessibility and human acceptance remain open.
5. Part 3: native Agent 3 event and news reports.
6. Part 4: apply shared components to Agents 2 and 4, then complete cross-agent
   browser, accessibility, interpretation and export acceptance.
7. Webapp Batch 2: controlled execution, using the same report contract for newly
   completed runs.

External broker research, free-form investment theses, real-data permissions,
authenticated approvals and production deployment remain separately scoped work.
The independent-backup deferral remains unchanged.

## Part 1 verification

Part 1 verification checks the five example documents against the proposed JSON
Schema, checks their internal identifiers and source references, and compares
referenced values with the local synthetic snapshots. Those checks concern this
design pack. The acceptance matrix now records Part 2A's backend checks separately
from the browser and reader acceptance still required.
