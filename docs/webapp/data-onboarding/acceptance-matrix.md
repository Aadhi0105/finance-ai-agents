# Batch 3 — data onboarding acceptance matrix

**2 November 2026.** [3B.1](../batch3b1-data-onboarding.md) implements and tests the
private saved-input backend. This matrix tracks final cross-part acceptance:
pending includes the remaining 3B.2/3C/3D work, not an assertion that no backend is
implemented. The [3B.2 guide](../batch3b2-fresh-close.md) records the fresh-close
backend and recovery evidence. [3C](../batch3c-browser-onboarding.md) records the bounded
browser checks for all five workflows and the fresh-close correction; final cross-part
acceptance remains 3D work. Passing a
documentation example or existing engine test alone does not pass an import
boundary. [Normative design](../batch3a-input-contracts.md) ·
[Envelope schema](input-package.schema.json).

| ID | Requirement | Evidence required before enabling it | Owner / final acceptance |
| --- | --- | --- | --- |
| IN-01 | Existing synthetic readers/jobs keep their contracts | Existing v1/v2 catalogues and v1 job requests remain supported; unknown versions refused; original jobs/reports unchanged | 3B.1 / pending |
| IN-02 | Private reads are protected | Before connection, no company names, counts, metadata, receipts or report bytes; missing/wrong/expired tokens and cross-origin access refused on every private route, including HEAD/downloads | 3B.1 + 3C / pending |
| IN-03 | Import is separately enabled | Read-only startup accepts no new mutation; imports do not enable worker/live/model capabilities; worker disabled permits no implied processing success | 3B.1 / pending |
| IN-04 | Policy precedes payload retention | Missing/denied/expired/mismatched local-retention or local-processing scope refuses transfer; references resolve to operator records, never client-provided approval flags | 3B.1 / pending |
| IN-05 | Classification is derived and preserved | A real-looking payload declaring fixture/synthetic cannot bypass origin review; provider/issuer/confidential/mixed/unknown labels propagate consistently through API, native reader, charts and downloads | 3B.1 + 3C / pending |
| IN-06 | Transport and parser are bounded | Enforce stream size without trusting Content-Length; reject compression, invalid UTF-8, duplicate keys, non-finite values, excessive nesting/value/row/text counts and slow transfers | 3B.1 / pending |
| IN-07 | Uploads cannot select code or paths | Reject archives, HTML, database/spreadsheet/executable formats, symlinks/special sources and arbitrary commands/paths; never fetch a supplied URL or execute source text | 3B.1 / pending |
| IN-08 | Safe preflight/transfer matching | Expected length/hash, entity, format, dataset and source declarations agree; changed metadata/body under a saved request identity conflicts | 3B.1 / pending |
| IN-09 | Durable duplicate handling | Lost acknowledgement plus resend returns one import identity; identical effective content with a new key resolves to one dataset version; no cross-workspace existence disclosure | 3B.1 + 3C / pending |
| IN-10 | Immutable versions and lineage | Changing an input yields a distinct version; supersession cannot rewrite original bytes/jobs/reports or silently change an already selected version | 3B.1 / pending |
| IN-11 | Entity/listing boundaries hold | Reject envelope/payload mismatch and unsupported share-class/currency/period substitutions; equal names do not merge companies; raw payload upstream IDs cannot collide with local IDs | 3B.1 / pending |
| IN-12 | Research saved-source adapter | Positive sidecar import/rebuild with tool evidence and dated chart parity; malformed schema, mismatched identity/mode, missing data and unsupported claims preserve refusal/holds; zero network/model use | 3B.1 / pending |
| IN-13 | Monitoring snapshot adapter | Selected cycle/effective state/correction evidence remain distinct; cycle IDs resolve; no state advance, imported approval or synthetic history; empty snapshot retained with no selected-cycle action | 3B.1 / pending |
| IN-14 | Event bundle adapter | Exact hashes/retained-input and attempt identities; deterministic replay matches; incomplete evidence held; wrong family/date/window/return basis rejected or explicitly held under existing rules; no invented release verification | 3B.1 / pending |
| IN-15 | News bundle adapter | Cutoff/text/cluster/score coverage retained; failed or missing scores not neutral; replay mismatch cannot publish; no fresh retrieval or inference | 3B.1 / pending |
| IN-16 | Saved-close adapter | Request digest, run ID, hierarchy, lineage and report agreement checked; no accounting writes; approval assertions remain unverified | 3B.1 / pending |
| IN-17 | New close request | Full-year budget and effective YTD leaf coverage, integer cents, IDs/signs/EUR/cadence; independent expected totals, bridge and forecast holds; package matches the engine request, not a saved report | 3B.2 backend tested; browser/final acceptance pending |
| IN-18 | Close source/state isolation | Exact predecessor state bound for deltas; reject future actuals, duplicate line/period, stale close/version, wrong entity/currency/cadence and conflicting supersession; unrelated workspaces unchanged | 3B.2 backend tested; browser/final acceptance pending |
| IN-19 | Committed close is not executed twice | Interrupt before/after accounting commit and before/after report delivery; recovery finds the committed identity, verifies saved proof and delivers once without recalculation | 3B.2 backend tested, including abrupt child exits and orphaned supervisor receipt; final acceptance pending |
| IN-20 | No incomplete input becomes visible | Interrupt receiving, validation, file promotion and ledger commit; no partial version supplies a job or download; explicit recovery validates complete proof and refuses changed/missing files | 3B.1 / pending |
| IN-21 | Capacity/disk failures preserve evidence | Reserved/failed/derived bytes count; dataset/version/report/job caps are enforced; disk full, fsync/rename/commit failure leave existing inputs/reports intact; no automatic deletion | 3B.1 / pending |
| IN-22 | Pin and recheck execution source | Job v2 binds exact dataset version/receipt, policy revision and profile; changed input/permission/state before claim or delivery blocks use; v1 saved-run meaning unchanged | 3B.1 + 3B.2 / pending |
| IN-23 | Safe presentation and errors | Source text is inert; scripts/HTML/credential-like text cannot execute or leak through errors/logs; no raw paths/records echoed; downloads require token and checked bytes | 3B.1 + 3C / pending |
| IN-24 | Clear and reload invalidate private state | Access clears on reload/explicit clear/refusal; late responses cannot restore private content or navigate away; reconnect before request recovery; no token in URL/storage/logs/screenshots | 3C / pending |
| IN-25 | Input selection is explicit | Upload alone creates no job; exact dataset/version and named action shown; empty/held/unsupported inputs have no enabled action; version changes create a new explicit selection | 3C / pending |
| IN-26 | Complete family acceptance | Five imported saved families and a new close progress through actual protected HTTP, worker, native reader and exact source downloads; reports preserve financial holds/classification; originals unchanged | 3D / pending |
| IN-27 | Onboarding backup inventory is complete | Quiesced local capture covers descriptors, ledgers, accepted bytes/receipts, applicable policy evidence, reports/jobs and close state; staging coverage declared; secrets/tokens excluded; unresolved backup rights visible | 3B + 3D / pending |
| IN-28 | Restore preserves identity and holds | Fresh private destination, all hashes/links and permissions checked, new token, no automatic queued execution, original/effective records intact; missing/corrupt/unlisted members refused | 3D / pending |
| IN-29 | Broader regression and resource evidence | Existing Python/interface checks and production build pass; bounded concurrent import/list/worker tests, deterministic ledger read snapshots and volume/deadline measurements support chosen limits | 3D / pending |
| IN-30 | Release claims stay bounded | Engineering cases separated from real-source rights, human review, company FP&A acceptance, independent backup and clean-machine recovery; no gate advanced merely by upload/render success | All parts / pending |

## Test data and acceptance discipline

Use new isolated synthetic workspaces and explicitly scoped test policy records.
Negative fixtures can declare provider/issuer/confidential categories to test
refusal and label propagation; those fixtures are still synthetic test evidence,
not proof of rights or acceptance for an actual provider or company.

Before any real saved input is used, obtain applicable source-use evidence and
record the exact intended local use. Do not reuse earlier Yahoo downloads merely
because their files are available. No paid calls, model weights, external uploads,
notifications or provider requests are needed for the engineering cases above.

Record expected outcomes before the run, exact package/contract fingerprints,
workspace/attempt/dataset/job/report identities, code/validator versions and original
artifact fingerprints. Test fault controls remain outside production API routes.
Do not equate a passing JSON envelope with semantic validity, a matching hash with
authenticity, or a local restore with protection against loss of the device.
