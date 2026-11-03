# Keystone report workspace frontend

React/TypeScript browser interface for the local FastAPI workspace. It displays
saved synthetic results from the four existing agents. The default server is
read-only. [Batch 2C](../docs/webapp/batch2c-run-interface.md) adds **Run & jobs**
over explicitly enabled protected admission and the supervised offline worker:
temporary token access, bounded saved-source requests, recorded stages, history
and result navigation. That original execution slice has no upload/correction or financial-approval controls; the later private interface adds supported JSON intake and separately versioned close corrections. Financial approval remains separate.
[Batch 2D](../docs/webapp/batch2d-execution-acceptance.md) validates failure/recovery
flows and larger histories, with guards against late navigation and stale page rows.

[Webapp Batch 3A](../docs/webapp/batch3a-input-contracts.md) is the design for data
onboarding and workspace/input versions. It defines the initial JSON contracts,
permission preflight, protected private reads, later interface flow and acceptance
criteria. [3B.1](../docs/webapp/batch3b1-data-onboarding.md) implements its private
backend and protected saved-input jobs. The frontend serves both the existing synthetic workspaces and the protected
private interface. [3C](../docs/webapp/batch3c-browser-onboarding.md) adds local
connection, company/dataset management, package review/import, immutable-version
execution and classification-aware native readers. Private records require access;
the public shell contains no company metadata.

[3B.2](../docs/webapp/batch3b2-fresh-close.md) adds the fresh-close backend with
exact-cent validation, fixed per-company accounting state and delivery-only
recovery of committed calculations. Its input selection and version pages are implemented in 3C.

Agent 1 uses native summary, financial analysis, valuation, peer and dated market
sections through the registered report-view API. Consensus and broker research
have separate availability. Agent 3 historical events/company news, Agent 2
monitoring and Agent 4 financial close also use native readers; originals remain
available as verified downloads.
See [Part 2B.1](../docs/webapp/native-reports/part2b1-reader.md) for the shared reader
and [Part 2B.2](../docs/webapp/native-reports/part2b2-research.md) for supporting
sections, research adapter compatibility and verification.
[Part 2C](../docs/webapp/native-reports/part2c-charts.md) implements eight interactive
Agent 1 plots with point/source inspection, keyboard controls and mobile layouts;
the retained numerical tables preserve exact values and missing observations.
[Part 3A](../docs/webapp/native-reports/part3a-events.md) adds the six-section
past-event report, interactive diagnostic CAR bars and readable study restrictions.
Event adapters 1.0.0/1.1.0 are supported; a verified event-relative path is not yet
projected. Evidence and financial-approval boundaries remain unchanged.
[Part 3B](../docs/webapp/native-reports/part3b-news.md) adds headline cards/search,
saved coverage, exclusions and explicitly diagnostic text-tone graphs. News
adapters 1.0.0/1.1.0 are supported; synthetic published tone stays withheld.
[Part 3C](../docs/webapp/native-reports/part3c-validation.md) adds complete Agent 3
reading/print copies, pagination focus and controlled browser acceptance cases.
News 1.2.0 also handles an early failed attempt without an analytical result;
news 1.0.0/1.1.0 retain their original recipes. PDF/physical-print acceptance and
human interpretation remain open.

[3D](../docs/webapp/batch3d-onboarding-acceptance.md) adds explicit private restoration, queued-work holds, operator release and complete-path/fault/volume acceptance. Connection help explains the local token file and hidden Mac folders.

See the [complete setup and acceptance guide](../docs/webapp/batch1-report-workspace.md).

Requires Node.js 24 and pnpm 11.25.0. From this directory:

```bash
pnpm install --frozen-lockfile
pnpm test
pnpm run build
```

The build includes the TypeScript check and writes ignored files under `dist/`.
Tests use Node 24's built-in runner and TypeScript stripping; no browser-test
package or external service is required for the read-boundary tests.
Python serves that build through `python -m keystone.workspace serve` from the
repository root. No Node process is needed while serving the built workspace.

For frontend development, start the Python workspace server on port 8765 and
run `pnpm dev` here. Vite binds to `127.0.0.1` and proxies `/api` to that backend.
The pnpm lock is committed; dependency and source files are separate from the
earlier `keystone-showcase/` prototype.
