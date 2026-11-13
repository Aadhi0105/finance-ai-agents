# Webapp Batch 6C — installation and updates

**13 November 2026 · Supervised local pilot.**
[Batch 6 roadmap](batch6-operational-readiness.md) · [Open Keystone](open-keystone.md)

This part gives an operator a repeatable way to prepare an isolated installation,
identify the code/runtime/web build being served, and rehearse an update and
recovery on copies of a saved workspace. It introduces no financial schema
migration, background updater, package signing, cloud deployment or production
approval. The broader backend programme remains scheduled after all six intake
parts; this batch supplies the installation controls needed for the local pilot.

For example, before updating a fictional research workspace, the operator retains
the previous code and Python environment and captures a verified snapshot. The
candidate is installed into a new folder. Its environment, evidence audit and web
readiness are tested on a new restored copy. The previous code is then checked
against another copy of the pre-update snapshot. A failed candidate keeps its
diagnostics and leaves both the previous installation and snapshot available.
The operator reviews the receipt before choosing any authoritative workspace.

## Supported installation boundary

The target is Apple Silicon macOS with CPython 3.11. Actual local validation uses
macOS 26.6.1 and Python 3.11.9. Node 24 and the exact pnpm version declared in
`web/package.json` (currently 11.25.0) must already be installed. Python/Node OS
installation is an operator prerequisite; the setup tool does not install system
software or make global shell changes. Linux CI remains a development
compatibility check, not an accepted installer platform. Windows is unsupported.

Git is needed to inventory a source checkout during preparation. A staged app
uses its preparation manifest for source identity and managed-launch revision;
it does not discover or inherit a parent repository. Snapshot provenance likewise
records the selected source identity, with unavailable identity left explicit.
The classic snapshot metadata now includes that source identity and uses its
commit/dirty state, preserving provenance for staged applications outside Git.

`requirements-web-macos-arm64-py311.lock` includes the original immutable agent
lock and adds the missing FastAPI and annotated-doc wheels. Starlette and Uvicorn
were already pinned through the earlier lock. Every Python distribution is pinned
with a wheel hash. Existing CLI lock bytes and historical acceptance hashes remain
unchanged. Frontend dependencies continue to use `web/pnpm-lock.yaml`.

The installer uses explicit **local offline caches**. It never falls back to a
package registry when an artifact is missing. A first-time operator must separately
obtain the reviewed Python/Node tools and populate caches. This can require network
access; it is separate from installation and has no financial-data entitlement.

## Prepare caches and a new installation

Run from the reviewed repository source. These example paths are placeholders;
choose actual existing Node/pnpm files and a local wheel-cache destination:

```bash
KEYSTONE_NODE="/absolute/path/to/node"
KEYSTONE_PNPM_JS="/absolute/path/to/pnpm.mjs"
KEYSTONE_WHEELS="/absolute/path/to/keystone-wheels"

python3.11 -m pip download --require-hashes --only-binary=:all: \
  -r requirements-web-macos-arm64-py311.lock --dest "$KEYSTONE_WHEELS"
"$KEYSTONE_NODE" "$KEYSTONE_PNPM_JS" --dir web fetch --frozen-lockfile
```

The two cache-population commands can contact package registries. Review their
configuration separately if a managed enterprise package mirror is required.
The following setup command works offline and requires a **new** destination:

```bash
python3.11 scripts/setup_keystone.py \
  --destination /absolute/path/to/installations/release-candidate \
  --wheelhouse "$KEYSTONE_WHEELS" \
  --node "$KEYSTONE_NODE" --pnpm-js "$KEYSTONE_PNPM_JS"
```

Setup performs these steps:

1. Refuse unsupported platforms, existing/linked destinations, destinations inside
   retained workspaces/environments, missing tools/caches and uncommitted source.
2. Copy only registered source files into the new `app/` folder, with hashes,
   bounds and before/after copy checks. Ignored workspaces, access keys, `.env`,
   caches and existing virtual environments are not copied. Known secret/link
   members in the selected source inventory are refused.
3. Create `app/.venv`; install hash-checked binary wheels with `--no-index` and
   `--find-links`; run `pip check`.
4. Install frontend dependencies using `--offline --frozen-lockfile --ignore-scripts`, then build
   and bind the generated files to the frontend source fingerprint.
5. Run the new installation doctor. Publish a `prepared` receipt only after the
   checks pass. No workspace is chosen and no worker/server is started.

`installation.json` records source commit, file proofs, clean/development status,
tool versions, preparation state and false release approval. `setup.log` is kept
privately beside it. Receipt updates use a flushed temporary file and atomic
replacement. Failure preserves the partial destination as `failed_preserved`;
it does not overwrite an existing installation or delete failure evidence.
Correct the prerequisites and retry with another new destination.

For implementation rehearsals only, `--development` explicitly permits saved
uncommitted source. The receipt and interface identify that source as development;
its base commit alone is not a complete source identity. Prepared applications
also refuse undeclared, altered or linked executable source. Runtime-generated
locks, environments, caches, build output and private state are outside the source
manifest. A partial/failed preparation cannot pass the managed launcher gate.

This is a source-and-runtime staging workflow, not an autonomous application
updater or a portable binary bundle. Python/Node and the selected workspace remain
separate dependencies. A matching installed version does not authenticate every
installed package byte. Wheel acquisition hashes and the source/build manifests
detect the supported integrity failures; they are not publisher signatures or a
defence against a local owner rewriting code and manifests together.
Offline flags and disabled dependency hooks are installation controls, not an OS
network boundary for trusted source/tool execution.

## Inspect what is running

In the private webapp choose **Installation & updates**, including through the
Operations-only diagnostic connection. Manual recheck is read-only. During a
refresh the previous observation is labelled; failure clears it. The page shows:

- Captured running source identity versus current source, with a restart hold
  when source changes after startup or identity is unavailable.
- Web build binding and generated-file integrity; stale/missing/altered stamps
  or assets remain explicit attention states.
- Python/platform and differences from the complete frozen runtime lock.
- Workspace schema versions: input ledger 1, job ledger 2 and catalogue 3.
  A known legacy job schema requires migration review; future/unknown formats
  and inaccessible stores are refused. Checking versions does not audit contents.
- The supervised update steps, exact source/lock fingerprints and recovery limits.

The protected `GET`/`HEAD /api/installation` contract is recorded in
`keystone/workspace/installation.schema.json`. It has a 32 KB client response
bound, fixed fields, matching workspace identity and false update/migration/
financial/release flags. It returns no filesystem paths, credentials or logs.
Query-based path selection and all mutations are refused.

The build script requires Node 24 with the pinned pnpm and writes
`web/dist/build.json` after successful compilation. The stamp records frontend
source identity, build time and output checksums. Managed builds still use a new
temporary directory and publish assets before the index, preserving older hashed
assets for open tabs and keeping the prior served index when a build fails.

From the selected application's `app/` directory:

```bash
.venv/bin/python -m keystone.installation doctor
.venv/bin/python -m keystone.installation workspace-check \
  --workspace /absolute/path/to/workspace
```

Doctor exits 0 for matching local installation checks, 3 for attention and 2 for
an unavailable check. Workspace-check opens SQLite read-only and performs no
migration or crash recovery. Legacy/unknown formats require a separately tested
migration procedure; this batch supplies none. The installer's `doctor --preparing`
option is only its pre-publication check and does not make a partial installation
eligible for managed launch.

## Rehearse an update and recovery

Retain the existing trusted source and runtime. Stop the owning server and all
writers to the selected workspace. Capture the complete, permission-checked local
snapshot using [6B's procedure](batch6b-storage-and-evidence.md). Source-use holds
must be resolved before claiming a valid capture. The unavailable independent
backup remains a release dependency; a same-device snapshot is local rehearsal
evidence, not device-loss protection.

Use the current reviewed source environment to run:

```bash
.venv/bin/python -m scripts.check_workspace_update \
  --snapshot /absolute/path/to/pre-update-snapshot \
  --candidate-source /absolute/path/to/installations/release-candidate/app \
  --candidate-python /absolute/path/to/installations/release-candidate/app/.venv/bin/python \
  --previous-source /absolute/path/to/retained-previous-source \
  --previous-python /absolute/path/to/retained-previous-runtime/bin/python \
  --output /absolute/path/to/new-update-rehearsal
```

These are trusted local code/runtime selections; the tool executes their code.
It accepts no remote code URL and provides no browser endpoint for running it.
The previous source must have a verifiable checkout or staged-install identity.

The rehearsal verifies the snapshot, restores a new `candidate-workspace`, checks
the candidate doctor and schema compatibility, initialises only that copy without
enabling a worker/admission, and runs its stopped evidence audit. A temporary
loopback server with its worker disabled checks protected installation readiness;
only that owned child is closed afterwards. Access tokens stay in headers and
memory; redirects/proxies are refused and no provider credentials are inherited.
Public offline/disabled-worker capabilities are checked before authenticated
readiness, which must match the exact selected source and restored workspace.

Even if the candidate fails, recovery restores a separate `rollback-workspace`
from the **pre-update snapshot** and audits it using the retained previous code
and runtime. It never presents the candidate's potentially changed state to older
code as an assumed downgrade. Snapshot/source identities are rechecked afterwards.

`rehearsal.json` and private candidate/previous logs are retained in the new output.
Exit 0 means the candidate, web readiness and previous-code recovery checks passed;
exit 2 preserves failure evidence. Both copies retain the existing restored queue
holds. No request is released or executed, no authoritative workspace is selected,
and no active installation pointer/settings is changed.

## Select an installation after review

After reviewing the exact rehearsal receipt and resolving any failures, open the
chosen `app/` folder in VS Code. Its copied **Open Keystone** task uses its own
`.venv`. Create that application's private `state/launcher/settings.json` using the
[launcher guide](open-keystone.md), supplying the deliberately selected existing
workspace, free local port and Node/pnpm files. No company/test workspace is
selected by the installer. Existing source installation settings are untouched.

Open Keystone checks source/runtime and schema compatibility **before starting a
worker**, builds the site, rechecks build identity, then starts/reuses only the
matching server. It also requires `installation_supported` and checked protected
installation readiness. Saved development source is supported and visibly labelled.
Direct developer API/CLI entry points remain outside this managed update workflow.

Failed preparation or rehearsal is not an activation signal. Retain the previous
code/runtime, original snapshot and failure evidence. Financial work acknowledged
after the snapshot must be reconciled explicitly before selecting any rollback
copy. Do not overwrite a workspace, delete locks or retry financial work merely
because an update failed. No backup expiry or automatic cleanup is introduced.

## Acceptance boundary

This is local engineering acceptance. Automated checks cover protected observation,
closed contracts, source/build drift, schema refusal without writes, complete-lock
coverage, safe destinations, offline commands, failed preparation and atomic
receipts, pre-worker launcher gates, snapshot isolation and previous-code recovery.
The isolated live preview and actual setup/update evidence are retained under
`output/installation-6c-preview/`, outside Git.

Independent encrypted backup, key recovery, clean-machine installation/disaster
recovery, authenticated team permissions, source rights and production release
sign-off remain separate requirements. No existing user workspace is relocated.

## Recorded local validation — 13 November 2026

- The broader related regression run passed 228 cases. Subsequent storage,
  standalone provenance and focused runs cover the final source changes; the
  latest focused run passed all 86 installation/setup/launcher cases. One new
  provenance test initially intercepted the OS `uname` call as if it were Git;
  its fixture was corrected and the test passed. Application behaviour was not
  changed to accommodate that fixture.
- All 534 frontend tests passed. The TypeScript and production build passed,
  including the source/asset build stamp and Node/pnpm checks.
- Actual isolated installations succeeded from the local pinned wheel/frontend
  caches, including disabled dependency install hooks. Development source and
  exact identities were recorded; no clean signed release is claimed.
- An actual empty-cache installation refused without registry fallback and
  retained its `failed_preserved` receipt. The preceding runtime configuration
  hash and installed-version observation remained unchanged.
- The staged candidate passed doctor, schema/evidence audit and the exact-source,
  exact-workspace web check on a restored fictional research workspace containing
  a saved report, analyst note and decision. The preceding committed 6B source
  (`3bac1d6`) and retained existing runtime successfully audited a separate
  recovery copy. This validates preceding code with its retained runtime; it does
  not claim rollback across changed dependency versions or database migrations.
- A deliberate candidate-start failure preserved the candidate copy and still
  verified previous-code recovery from another pre-update snapshot copy.
- The staged application launched through its own Open Keystone task, and a
  second invocation reused the same owned session. Only a disposable fictional
  workspace copy and that test installation's new settings were selected for
  the preview; original launcher settings and user workspaces were untouched.
- Browser inspection showed the staged identity, all four matching checks,
  keyboard refresh and no page overflow at the observed 576 px viewport. All
  41 non-runtime evidence files retained identical hashes; there was one retained
  job and zero active jobs after observation/reopening.
- Evidence/logs/source and runtime test copies remain under the ignored
  `output/installation-6c-preview/` tree. No files were sent to an independent
  backup destination. Git publication is a separate requested closure step.
