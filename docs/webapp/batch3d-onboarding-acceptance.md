# Webapp Batch 3D — onboarding acceptance and local recovery

**3 November 2026.** Completes the bounded local engineering acceptance of
[3A](batch3a-input-contracts.md), [3B.1](batch3b1-data-onboarding.md),
[3B.2](batch3b2-fresh-close.md) and [3C](batch3c-browser-onboarding.md).
The [matrix](data-onboarding/acceptance-matrix.md) separates engineering evidence
from production, source-use and financial approval. Final verification results
are recorded below; no external backup or paid/live call is part of this work.

## What changed

The new `restore-private` operator command restores an explicit private snapshot
into a **fresh directory** and verifies the retained input/permission ledger,
job admissions and events, registered reports, prepared results and company
accounting proofs. It checks that every declared snapshot source belongs to the
original workspace inventory. The original folder need not exist.

Verification and transformation take place inside the unpublished restore
directory under exclusive maintenance. Only after all checks and durable writes
does the existing restoration mechanism publish the destination. An incomplete,
corrupt, unlisted, mismatched or permission-refused snapshot is not published;
the snapshot and original workspace are preserved. Empty fixed application
directories are reconstructed without copying arbitrary source paths.

The copied job ledger's mutable directory binding is changed explicitly. A
`control/restore-history.json` entry records the snapshot/manifest identity,
previous/new roots, preserved workspace identity, held queued requests and
interrupted attempts. Its fingerprint is bound in the copied ledger. Restore
receipts inventory new derived recovery files as well as transformed originals.
Subsequent private snapshots retain this recovery history.

Saved input files, immutable job admissions, operation receipts, registered
reports and accounting proofs are not rewritten. Financial results are never
recalculated during restore. Original paths in operation receipts remain
provenance only and are never followed to read the old folder.

## Queued, interrupted and delivered work

- **Previously queued:** remains queued with zero claimed attempts and an
  explicit restoration hold. Even an enabled worker skips it. The browser shows
  **Restored queue · held for review**, its exact selected version and why it
  cannot run. Holds still consume pending capacity.
- **Previously running:** becomes `outcome_unknown` with its original single
  attempt retained. There is no automatic retry or conversion to success.
- **Completed/review-required:** the registered report, prepared output and
  execution proof must agree before restoration is accepted.
- **Interrupted delivery after a committed close:** remains held. The operator's
  existing delivery recovery can register the verified saved result once, without
  invoking financial calculation again. A partly registered report may keep
  workspace/report reads held until that recovery is completed.

`release-restored-job` rechecks one never-started queued request, current input
and permission evidence and, for a fresh close, its exact accounting predecessor.
It refuses attempted operations, stale predecessors and conflicting working
directories. The reason and review time are retained in mutable control metadata.
It releases that request for a later enabled worker; the command itself does not
dispatch work. This is a local operator acknowledgement, not authenticated
financial approval. No browser release/requeue/reset endpoint is introduced.

Generic `keystone restore` keeps its earlier scope and does **not** silently
adopt a private job ledger at another path. Use the explicit private command for
a restartable private workspace. Never edit a binding or remove its lock files
to bypass a refusal.

## Operator procedure

Run from the repository root with the project environment installed. Replace the
example paths with the intended private root and the exact returned snapshot.
Stop that workspace's server before capturing its snapshot.

```bash
.venv/bin/python -m keystone.workspace snapshot-private \
  --workspace state/workspaces/analyst-demo \
  --destination output/private-local-snapshots

.venv/bin/python -m keystone.workspace restore-private \
  output/private-local-snapshots/RETURNED_SNAPSHOT_ID \
  --destination state/workspaces/analyst-restored

.venv/bin/python -m keystone.workspace serve \
  --workspace state/workspaces/analyst-restored --port 8765
```

Default serving is for inspection: imports, new jobs and the worker are disabled.
The terminal prints the web address and current token-file path. Choose that
`access-token.key` through the browser connection picker. On a Mac, **Command +
Shift + G** in the picker accepts its full path even when `.codex` is hidden.
Reconnection is required after reload/restart. Tokens are excluded from snapshots
and generated afresh by server startup.

After inspecting a held request, stop any worker and explicitly release only its
saved job identity:

```bash
.venv/bin/python -m keystone.workspace release-restored-job \
  --workspace state/workspaces/analyst-restored \
  --job-id job-REPLACE_WITH_EXACT_SAVED_ID \
  --reason 'Reviewed the exact restored input and current source scope'
```

The placeholder above is not a valid job ID. Retain the full actual `job-…` ID
shown on its saved job page. Restart with `--enable-job-admission --enable-worker`
only when ready to process released/new requests. Add `--enable-imports` separately
if new intake is intended. Other restored queue holds remain in force.

`job_control_busy` now explains that another session or recovery task owns local
control. Use its existing window or stop it cleanly before restarting. The shared
maintenance gate also deliberately excludes storage recovery from active
financial mutation in the checkout.

## Additional acceptance fixes

The saved research adapters do not establish exchange/share-class mappings, so
non-null `listing.exchange` and `listing.share_class` are refused in preflight,
before payload retention. Keep them null for these supported adapters. A declared
quote currency requires a matching retained quote currency; an unknown saved
currency cannot be replaced by an asserted label. No ticker, share class,
exchange, currency or period conversion is performed by onboarding.

The browser connection page now includes expandable file-location/restart help. Refused/expired access clears private records and retains a useful connection message; late refusals from an older connection cannot clear a newer successful one.
Held restored requests have their own explanation rather than the message for a
possibly committed close. Older private job responses without the optional
restoration-hold field remain supported; malformed or contradictory fields are
refused by the client.

## Repeatable engineering checks

```bash
.venv/bin/python -m pytest tests/test_workspace_private_recovery.py \
  tests/test_workspace_onboarding_acceptance.py -q

.venv/bin/python -m keystone.workspace prepare --native \
  --destination output/onboarding-3d-source-NEW

.venv/bin/python tests/workspace_onboarding_acceptance.py \
  --source output/onboarding-3d-source-NEW \
  --destination output/onboarding-3d-acceptance-NEW --port 8852
```

Each preparation/rehearsal needs a new destination and an available loopback port.
The test runner uses fictional operator attestations and existing synthetic engine
outputs. Its local-only fault setup is outside production API routes. Do not run
financial/storage verification processes concurrently in one checkout; the shared
maintenance/mutator lease intentionally refuses competing operations.

The HTTP rehearsal covers five saved families, a fresh close and its correction;
read-only package inspection; explicit import/run separation; duplicate request
identity; real supervised offline execution; protected native/source downloads;
source/report hashes; a 60-dataset history spanning 25/25/10 API pages; token
rotation; queued holds; an interrupted attempt; a single reviewed release; and
reopening all reports after relocating with the original workspace unavailable.

The independent arithmetic remains EUR 60 budget / EUR 65 actual / EUR 5 variance;
after correction it is EUR 60 / EUR 75 / EUR 15. There are exactly two accounting
runs, including the original. A released saved monitoring request adds a report
without changing accounting state. All results retain financial-review holds.

Storage fault cases cover input writes, durable directory sync, promotion and
SQLite commit; restore faults cover copy, preparation, receipt and publication.
Prior accepted evidence remains readable and prepared imports require explicit
recovery. Other cases cover malformed/resealed snapshots, current permissions,
stale close predecessors, repeated relocation, empty directories, post-commit
delivery interruption, concurrent intake/read/admission, 100-identity/dataset
limits, 60 import receipts and bounded parser content.

## Verification record

The matrix's evidence keys resolve to these checks:

| Key | Source |
| --- | --- |
| I | [Private onboarding tests](../../tests/test_workspace_onboarding.py) |
| F | [Fresh-close tests](../../tests/test_workspace_fresh_close.py) |
| C | [Browser-client tests](../../web/tests/onboarding.test.mjs) and [protected inspection/shell tests](../../tests/test_workspace_onboarding_browser.py) |
| R | [Private recovery tests](../../tests/test_workspace_private_recovery.py) |
| A | [Fault, stream, concurrency and volume tests](../../tests/test_workspace_onboarding_acceptance.py) |
| E | [Actual HTTP acceptance runner](../../tests/workspace_onboarding_acceptance.py) |
| B | Visible in-app-browser review; ignored local evidence described below |
| W | Full regression, including native readers, workspace jobs/workers, execution acceptance and production storage tests |

The [sanitized engineering record](../../references/acceptance/workspace-onboarding-2026-11-03.json) identifies the candidate by its base commit and changed source/test fingerprints. It is not a release approval.

| Check | Result |
| --- | --- |
| Full Python regression | **1,408 passed**, exit 0; all 1,408 progress markers passed and the run reached 100% (repository `addopts=-q` plus CLI `-q` suppress the usual count summary) |
| Final fault/stream/concurrency/volume suite | **16 passed** in 30.92 seconds; four late stream/identity cases are additional to the full run, the other twelve overlap |
| Unique current Python cases validated | **1,412**, confirmed by collection; counts above must not be added in full |
| Frontend regression | **273 passed**, including restored-hold compatibility/refusal feedback/stale-connection cases |
| TypeScript and production build | Passed after the last connection-feedback fix |
| Final actual HTTP/worker/restore rehearsal | Seven accepted versions, eight registered reports, two accounting runs; exact download hashes; 54 original source files preserved |
| Restored requests | Unreleased queued work: zero attempts; separately reviewed monitoring request: one attempt; interrupted request: one prior attempt, outcome unknown |
| Bounded volume | 60 datasets/identities, API pages 25/25/10; maximum measured dataset-page response 0.002 seconds on this Mac; not a production latency guarantee |
| Visible readers | Research, monitoring, events, news, saved close, calculated close and correction all reopened with synthetic labels, no iframes and no financial approval |
| Visible interactions | Restored research chart selected its final saved observation; corrected bridge selected EUR 75 actual; protected original HTML download matched its saved SHA-256 |
| Access and layout | Disconnect removes private names/report content; wrong access exposes no records; 1,280 and 320 CSS-pixel held-job layouts have no horizontal overflow; temporary viewport override reset |
| Calls | Zero provider requests and zero reserved model requests; financial/production approval remains false |

The first HTTP attempt used an incorrect test expectation (`201` instead of the existing `200` for entity/dataset creation); it stopped after the seven workflows. Its output remains separately preserved. The corrected rehearsal and final-code repeat both passed; no successful acceptance is claimed for that initial attempt.

Generated private receipts, packages, tokens and screenshots remain ignored under `output/onboarding-acceptance-3d-verified/` (visible browser review) and `output/onboarding-acceptance-3d-final/` (final-code HTTP rehearsal). Source fixtures are isolated under `output/onboarding-acceptance-3d-source/`. Test logs are local `/tmp/keystone-3d-*.log` files. No actual provider or company data was introduced.

## Remaining boundaries

This work accepts a bounded, single-analyst, offline local workflow using
fictional test inputs. It does not establish rights for real provider/issuer/
company data, authorised real-company FP&A acceptance, human interpretation or
financial sign-off, enterprise identity/roles, internet exposure, independent
encrypted backup, key recovery or clean-machine disaster recovery. The external
drive remains deferred by the user. A successful local restore does not prove
survival of device loss or meet the production disaster-recovery release gate.
