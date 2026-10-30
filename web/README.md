# Keystone report workspace frontend

React/TypeScript browser interface for the local, read-only FastAPI workspace.
It displays saved synthetic results from the four existing agents. It has no
execution, upload, correction or approval controls.

See the [complete setup and acceptance guide](../docs/webapp/batch1-report-workspace.md).

Requires Node.js 24 and pnpm 11.25.0. From this directory:

```bash
pnpm install --frozen-lockfile
pnpm run build
```

The build includes the TypeScript check and writes ignored files under `dist/`.
Python serves that build through `python -m keystone.workspace serve` from the
repository root. No Node process is needed while serving the built workspace.

For frontend development, start the Python workspace server on port 8765 and
run `pnpm dev` here. Vite binds to `127.0.0.1` and proxies `/api` to that backend.
The pnpm lock is committed; dependency and source files are separate from the
earlier `keystone-showcase/` prototype.
