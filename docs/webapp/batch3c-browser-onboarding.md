# Webapp Batch 3C — private browser onboarding

**3 November 2026.** Implements the browser flow specified in [3A](batch3a-input-contracts.md)
on the [3B.1 saved-input backend](batch3b1-data-onboarding.md) and [3B.2 fresh-close backend](batch3b2-fresh-close.md).
This is the local supervised analyst interface. Broader acceptance and explicit portable recovery are recorded in [3D](batch3d-onboarding-acceptance.md). No production, source-use or financial approval is granted.

## What the analyst can do

The same built application now selects the synthetic demonstration or private
interface from bounded public capabilities. Before private connection it displays
only the static shell and local connection controls. Company names, counts,
dataset metadata, receipts, reports and source files require current local access.

The private interface uses Keystone's green analyst-desk styling, native report
sections and interactive numerical charts. It includes:

- **Overview:** registered reports, datasets, identities and the four agent areas.
- **Data & inputs:** company/group and workflow filters, identity registration,
  dataset creation, supported-format/action selection and dataset versions.
- **Package review:** choose one JSON file, inspect declared source scope and
  units, then explicitly import the reviewed bytes. Inspection and import do not
  start a job.
- **Accepted version:** inspect the retained validation notes, effective source
  classification, period, upstream reference, backup holds and exact version.
  Technical identities and verified input downloads are available on demand.
- **Run request:** explicitly select the accepted version, review its scope and
  choose a processing deadline of 1–600 seconds. Live data and paid models stay
  disabled. Financial review is a separate requirement.
- **Runs & jobs:** paged saved jobs and individual execution records, including
  queue/worker state, single-attempt count, operation outcome, recovery holds and
  a rechecked link to the registered result.
- **Reports:** native readers for research, monitoring, events, news and close,
  with protected original/source downloads and complete reading/print copies.
- **Import history:** paged attempts and individual receipts, with acceptance,
  refusal, active validation and interrupted/prepared-delivery states kept distinct.

For example, the fictional June close package first becomes an accepted input
version. Only the separate calculation request produces the EUR 60 budget / EUR 65
actual / EUR 5 variance report. A later correction is another accepted version
and job: EUR 75 actual / EUR 15 variance. Both original and corrected reports
remain registered with their own input and accounting proof.

## Connection and private reads

The current token can be pasted into the masked field or read from the local
`access-token.key` file through a separate connection-file picker. The picker
accepts only that fixed filename within a small byte limit; it does not import
credential files into a dataset. Its contents are used only for local access.
The masked text field is uncontrolled: pasted credentials do not become HTML
value attributes or React state, and the field clears when connection begins.
That behavior was checked in the visible browser on the final interface.

The token, upload bytes, pending request keys and protected responses stay in
this tab's memory. They are not stored in local/session storage, cookies, URLs,
page attributes or logs. Clearing access aborts reads, revokes tracked temporary
download URLs and unmounts private pages. Reloading requires reconnection.
Already downloaded local files remain intentional local copies.

Every private read and write uses the same authenticated transport, including
native report reads, original verification, artifact downloads and reading-copy
rechecks. Requests refuse redirects and external destinations, omit ambient
credentials, bypass caches and enforce bounded response bodies/deadlines.
Authentication failure clears the connected application state. Epoch and page
checks reject late replies after disconnection/navigation.

The production application shell is now available at the private server root;
private metadata APIs and files still require the token. Exact local host/origin,
loopback-only serving, protected HEAD requests and restrictive content policies
continue to apply. This is a local capability, not enterprise authentication.

## Read-only inspection and unchanged source bytes

3C adds `POST /api/datasets/{dataset_id}/inspect`, available only with imports
enabled and current same-origin private access. It accepts one bounded,
uncompressed JSON package using the existing transport/parser limits.

Inspection returns a version-1 preview containing the existing preflight
descriptor and effective policy/classification, with `validation=pending_import`,
`processing=not_started` and `financial_approval=false`. It shares the reservation
identity/source-policy checks and performs **no** reservation, file retention,
semantic financial validation, accounting write, job admission or URL retrieval.
Semantic validation happens during explicit import, as before.

The server computes the existing Python canonical payload hash. This avoids
browser reserialization of large integers, floating-point tokens or Unicode.
The browser independently verifies the package byte hash and sends the original
immutable `File` bytes for both inspection and transfer. Metadata and financial
numbers are not rewritten to satisfy a browser-specific fingerprint algorithm.
Nullable source references, currencies, units and retained dates stay missing
rather than being fabricated. Source references are inert escaped text.

No browser control installs or approves source-use permissions. Missing, revoked,
expired or mismatched operator records refuse inspection/import. Permission and
accounting predecessor checks are repeated at the existing backend boundaries.

## Confirmations, retries and recovery holds

Each import keeps one request key, frozen descriptor and original byte source.
A lost reservation reply retries that same identity. A lost transfer reply first
reads the saved receipt; an already accepted transfer is not uploaded again.
Active validation and prepared-delivery holds do not silently become new imports.
An unresolved write blocks a new conflicting request in this tab.

Jobs likewise keep their exact dataset version, contract hash, deadline and
original key until confirmed or definitively refused. A synchronous preparation
lock prevents two rapid clicks from dispatching two admissions while the version
is being rechecked. An expired-token refusal during a retry does not erase the
identity of an earlier unconfirmed write. Reconnection to a different workspace
cannot reuse pending writes from the original workspace.

Company/dataset creation has no server idempotency contract. The UI therefore
serializes creation and flags an unconfirmed creation: refresh and inspect the
existing entries before explicitly acknowledging that hold. It never retries an
uncertain creation automatically.

Import and job identities survive navigation within the connected tab. Browser
reload intentionally loses in-memory recovery keys: reconnect and inspect saved
history rather than blindly starting another operation. Operator recovery of
prepared imports and committed closes remains in the documented local CLI;
there are no browser financial-approval, queue reset or calculation-retry controls.

## Readers and classification

Private adapter version `2.0.0` is admitted only with a private input origin.
Synthetic legacy adapter contracts remain supported. The browser binds report
identity, source artifacts, supported recipes and effective classification to the
registered run, and retains all existing figure/evidence/review checks.

`synthetic`, `provider`, `issuer`, `internal`, `mixed` and `unknown` remain distinct
across report lists, reader headers, charts, evidence panels and reading copies.
Fresh closes use their combined accounting lineage classification. A current
synthetic delta cannot relabel inherited internal data. Classification labels
are provenance categories, not assertions of source authenticity.

Original HTML is downloaded after authenticated byte/hash verification; it is
not embedded as an active report. Charts use retained numerical data, selection
controls, source references and exact tables. Missing/withheld values and
conditional forecast restrictions remain unchanged.

## Operating the built application

From the repository root, build the existing frontend and serve an explicitly
prepared private root. Replace the sample root with the intended local workspace:

```bash
PATH=/path/to/node-24/bin:$PATH pnpm --dir web run build
.venv/bin/python -m keystone.workspace serve \
  --workspace /absolute/path/to/private-workspace \
  --port 8765 --enable-imports --enable-job-admission --enable-worker
```

Open the printed loopback address and connect with the token in that workspace's
private control folder. Omit the enable flags for reading-only operation;
omitting `--enable-worker` keeps admitted requests queued with an explicit notice.
Follow 3B.1/3B.2 for workspace preparation and operator source records.

During this implementation a separate fictional preview was prepared under
`output/onboarding-ui-3c-preview/`. Its six JSON packages are in `packages/`:
research, monitoring, events, news, June close and June correction. Their
operator permission records are explicitly fictional test attestations, not
rights for any actual company/provider data.

The live development preview uses port **8840**, a loopback API on **8841** and
an exact front-origin session. `KEYSTONE_DEV_API` can configure a loopback-only
Vite target; it preserves the original host and origin instead of rewriting the
backend's access checks. Normal built serving needs no Node process.

## Recorded verification

| Check | Evidence |
| --- | --- |
| Full Python regression | **1,376 passed** in 478.00 seconds |
| Inspection/static-shell checks | **13 passed**, included above; no retention on inspection, exact hashes, shared reservation regression, current access/origin, revocation, size/media and disabled imports |
| Frontend regression | **269 passed**, including 35 new private-boundary, format and retry checks |
| TypeScript and production build | Passed on the final interface, including access-input and layout adjustments |
| Pre-merge onboarding/inspection regression | **56 passed** in 75.35 seconds after making the shell fixture independent of a local frontend build; Python-only CI does not require `web/dist` |
| Visible browser workflow | Six accepted inputs, six jobs, six native reports: all five workflow types plus a separate close correction; one claimed attempt each |
| Financial example | Original close EUR 60 / EUR 65 / EUR 5; corrected close EUR 60 / EUR 75 / EUR 15; interactive bridge selection shows the retained step amount |
| Protected output | Original HTML download and complete reading copy checked after authenticated revalidation |
| Clear/reload | Private names and dataset content disappear on disconnect; reload requires reconnection |
| Responsive layout | 319 CSS-pixel dataset/overview screens and 1,280 CSS-pixel analyst desk checked; no page-level horizontal overflow; temporary viewport override reset |
| Existing boundaries | No live/provider retrieval or paid model calls; outputs retain financial-review holds |

The final browser pass also corrected nullable source-reference handling, an
inspection/reservation refactor field error, rapid-submit preparation and retry
identity retention across expired access. These cases have regression coverage.
The final visual adjustment aligns parallel workflow cards and lets mobile
connection controls wrap within the screen.

Ignored local evidence, including the six run identities and screenshots, stays
under the preview output directory. Existing engine fixtures and the earlier
3B.1/3B.2 rehearsals were read as references and preserved. No Git publication is
part of this implementation request.

This passes the bounded 3C implementation checks. [3D](batch3d-onboarding-acceptance.md) records the subsequent browser failure/volume/portable-restore acceptance. Human interpretation, real
company FP&A acceptance, unresolved source licences, independent backup and
clean-machine disaster recovery remain open.
