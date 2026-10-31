# Keystone report workspace frontend

React/TypeScript browser interface for the local, read-only FastAPI workspace.
It displays saved synthetic results from the four existing agents. It has no
execution, upload, correction or approval controls.

Agent 1 uses native summary, financial analysis, valuation, peer and dated market
sections through the registered report-view API. Consensus and broker research
have separate availability. Agent 3 historical events and company news also use
the native reader; Agents 2/4 retain the original saved-report reader.
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
