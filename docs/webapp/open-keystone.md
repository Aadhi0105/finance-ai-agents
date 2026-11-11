# Open Keystone

Open the **finance-ai-agents repository folder** in VS Code, rather than an
individual file or its parent Job Applications folder. Press **Cmd+Shift+P**,
choose **Tasks: Run Task**, then **Open Keystone**. The local task is in
[tasks.json](../../.vscode/tasks.json), following the official
[VS Code task format](https://code.visualstudio.com/docs/debugtest/tasks).

The task uses the repository's existing `.venv/bin/python` and
[launcher](../../scripts/open_keystone.py). It works without `node` or `pnpm`
being on the VS Code terminal's PATH. No extension or global shell alias is needed.
This first launcher supports the existing macOS local pilot; Windows is not supported.

## First launch on this Mac

The initial private settings select the existing Adidas workspace on port 8864.
If the original manually started server is still running there, stop **that
terminal** with Ctrl+C once, then run the task. The launcher will not terminate an
unmanaged process or delete lock files. No new copy of Adidas data is created.

After a successful build, the browser opens at the configured loopback address.
Connect with the workspace's current `control/access-token.key` file if prompted.
The token is read only into memory for readiness checks; it is never printed,
stored in launcher settings, passed on a command line or included in the URL.

Keep the task terminal running. Ctrl+C in that terminal stops its server, or use
VS Code's **Tasks: Terminate Task**. It shuts down only the child it started and
waits for normal cleanup. Existing workspaces, queues, reports and lock files are
preserved. Use **Open Keystone** again to start a fresh session.

A second invocation can rebuild/reopen a matching launcher-owned session. If
local source files have changed since that server started, it requests a stop and
restart. An old backend is not silently presented as the updated application.
The VS Code task allows two instances so the second invocation can perform that
check and exit; it does not start a second worker for the same workspace.

## What “updated” means

Each successful start validates Node 24 and the pnpm version in `web/package.json`,
then runs the existing TypeScript check and website production build. It builds
in a temporary directory first, publishes assets before the new index, and keeps
older hashed assets available for already-open tabs. A failed build stops startup
and leaves the existing website index intact; it never opens an old-build fallback.

The code is the code currently on this Mac, including saved uncommitted changes.
The launcher does not pull GitHub changes, install dependencies, refresh market
data, parse PDFs, submit new analysis, approve reports or enable paid/live execution.
Save edits before launching; files changed during a build cause a clear refusal.
The enabled worker can continue previously accepted eligible queued jobs. Restored
queues retain their existing holds; the launcher does not release them.

## Local configuration

Machine-specific paths live in ignored `state/launcher/settings.json`. For a new
installation, create it after preparing an existing private workspace:

```json
{
  "schema_version": 1,
  "workspace": "output/my-workspace/workspace",
  "port": 8765,
  "node": "/absolute/path/to/node",
  "pnpm_js": "/absolute/path/to/pnpm/bin/pnpm.mjs"
}
```

Paths may be absolute or relative to the repository. Select existing executables
and the existing pnpm JavaScript entry point. Install the locked frontend
dependencies using the [normal setup guide](batch1-report-workspace.md) first.
The launcher never downloads build tools automatically.

This Mac's configuration points to the already installed Node/pnpm files in
Codex's local runtime cache. VS Code launches those files directly; Codex does not
have to be running. Cache removal or a runtime relocation requires updating the
two paths, or selecting a separately installed Node 24/pnpm 11.25.0 toolchain.
Do not commit these machine paths or workspace credentials.

The same launcher can be started from the repository terminal:

```bash
.venv/bin/python scripts/open_keystone.py
```

For an isolated existing preview workspace, overrides do not change saved settings:

```bash
.venv/bin/python scripts/open_keystone.py \
  --workspace output/open-keystone-preview/workspace --port 8866 --no-browser
```

The preview directory must already be a prepared private workspace. It is not
created or populated automatically. `--no-browser` is for checks or a separately
opened preview; normal task execution opens the system default browser.

## Failure messages

- **Port already in use:** stop the original server in its terminal. The launcher
  does not guess which process to kill or select a different workspace/port.
- **Local code has changed:** stop the earlier launcher task, then run it again.
- **Build tools/settings unavailable:** update the local paths or complete setup;
  no old website is opened as a successful rebuild.
- **Another build is running:** let it finish, then rerun the task.
- **Server stops or readiness times out:** inspect the server output above the
  message. Workspace binding, imports/jobs/worker readiness and offline limits
  must match before the browser opens. Preserve existing evidence and lock files.

Launching does not weaken the private connection or change source-use/release
approval. The private worker remains offline and bounded; actual analysis still
requires an explicit request inside Keystone.

## Analyst review notes — Batch 5B

Open Keystone now also enables protected review-note recording and checks that
capability before reopening a session. An older server must be stopped and
restarted; it is not presented as the updated review workspace. Launching still
records no note or financial decision automatically.

Open a report, choose **Review priorities / requirements**, then **Open review
workspace**. Notes remain bound to the exact report and item. They are saved in
the private workspace ledger and included in its consistent snapshots. The
[review-workspace guide](batch5b-review-workspace.md) explains retries and scope.

A manually started private server enables note writes explicitly with
`--enable-review-notes`. Omitting it preserves note reads while refusing new
notes. Note recording does not require enabling imports, jobs or a worker.
Existing source-use checks, local-token access and financial restrictions apply.

## Input corrections — Batch 5C

Open Keystone also enables `--enable-review-corrections` and verifies that
capability when reusing a server. In the report's review workspace, use
**A new version. A clear reason.** to inspect the source version, import a
successor, compare its changes and record the correction. The original report
then links to the replacement input; processing still needs an explicit request.
Reports generated from that replacement link back to the original evidence.

A manual private server without this flag can read retained correction history
but cannot record new links. This is independent of note, import and job flags.
The [5C guide](batch5c-corrections-lineage.md) describes supported packages,
source permissions, retry recovery and the distinction from accounting decisions.

## Local verification — 9 November 2026

Twenty launcher tests passed, covering settings, process ownership, build failures,
retained website assets, source changes, readiness restrictions and browser failure.
Actual Node 24.22.1/pnpm 11.25.0 builds and private startup passed with a minimal
terminal PATH containing neither Node nor pnpm. Reopening reused the same preview
server; SIGTERM and terminal Ctrl+C both closed only the owned preview. The original
Adidas server remained running. Browser connection to the empty engineering preview
was verified; no financial request or input import was submitted. The default-browser
dispatch is exercised in the unit checks, while visible preview verification used
the in-app browser. Full platform regression and production release are separate.
