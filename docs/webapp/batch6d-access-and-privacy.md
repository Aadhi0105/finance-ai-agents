# Webapp Batch 6D — access and privacy controls

**14 November 2026 · Single-operator local pilot.**
[Batch 6 roadmap](batch6-operational-readiness.md) · [Open Keystone](open-keystone.md)

Access & privacy helps an operator answer three questions: does this tab still
have valid local access, do the workspace's file checks pass, and which uses of
the retained sources remain held? It also provides a deliberately small diagnostic
download for inspection before requesting help.

For example, a fictional company dataset can permit local calculation and local
backup while denying transfer to a model or external sharing. The page shows
those distinct recorded rights. An expired or revoked record holds local use of
the corresponding saved version. A successful installation or calculation never
changes these source-use records.

This batch strengthens the existing trusted-account boundary. It does not add
enterprise authentication, team roles, authenticated financial approval or a
production release decision.

## Use the page

Connect to the selected private workspace, then choose **Access & privacy**.
**Recheck access & privacy** performs a fresh protected read. The timestamp
includes seconds. A previous observation is explicitly labelled while a recheck
is pending; a failed observation removes it. There is no automatic polling.

The page is also available through **Open Operations only**, using the same local
key. This navigation mode is a convenience view, not a restricted backend role.
It still represents the same operator authority. Source-use observations can be
unavailable when the input ledger or supporting records cannot be read.

The page contains:

- A current session-key check and a button to clear this tab's access.
- A bounded workspace file-mode/ownership/link check.
- Current local source-use counts, held versions, and the five distinct recorded
  rights: retention, processing, backup, model transfer and sharing.
- The limits of private downloads, named-analyst identity and local protection.
- An explicit **Download redacted check** action and safe session-ending steps.

The browser client applies a closed response parser, exact workspace binding,
bounded responses, disconnect/abort handling and session-epoch checks. Late
responses cannot restore a disconnected view or produce a diagnostic download.
No key, private response or diagnostic is persisted in browser storage.

## Local access boundary

The supported server remains on `127.0.0.1`. Protected reads, downloads and enabled
writes use the existing same-authority Host, Origin, Fetch Metadata and bearer
header checks. Credentials are not accepted from a URL or a cookie. Public
`/api/execution` exposes fixed capability information, not workspace names,
records, source text or access keys. This change adds `privacy_supported` to the
private capability observations.

The local key is randomly generated on server startup and atomically written to
the private control folder. In addition to comparing the presented bearer key,
each protected request now rechecks:

1. The retained control-directory identity, ownership and private mode bits, and
   the absence of linked path ancestors.
2. The key's original device/inode identity, regular-file type, single-link
   count, owner, private mode bits and expected byte length.
3. The exact current key bytes, using a bounded, no-follow, non-blocking read and
   a constant-time comparison, followed by file/directory identity checks.

A missing, replaced, linked, broadened or changed key invalidates that running
session's in-memory key. Restoring the file's previous contents or permissions
does not revive the invalidated session. No key is printed or rewritten by a
request, and no in-place browser rotation endpoint is added.

These are checks at request time. They cannot establish that a key was never
copied or temporarily exposed between observations. An already authorised request
or admitted job is not retroactively cancelled by a later failed access check.

### Finish or replace a session

**Clear this tab's access** removes its connection and loaded access-dependent
views, aborts outstanding reads and revokes its temporary download URLs. Pending
write identities remain subject to the existing uncertain-outcome handling; this
is not deletion of accepted work or cancellation of an admitted job.

Clearing a tab does not stop the server, invalidate other connected tabs or stop
the worker. Stop the owning Open Keystone terminal when finished. For a suspected
exposed key:

1. Stop the owning server/launcher and follow any existing in-flight-work recovery
   instructions. Preserve the workspace and its saved request identities.
2. Inspect local permissions and the trusted account. Do not delete leases or
   weaken checks to make a connection succeed.
3. Restart through the supported launcher. It writes a new key; the preceding
   key must fail and each tab must reconnect using the new file.

There is no automatic idle expiry in this local pilot. Possession of the key
allows the enabled operator actions; it is not proof of a named person's identity.
Use this only under the declared trusted local account. Named users, separate
roles, strong authentication, central revocation and approval integrity belong
to the later team-application scope.

## File and source-use observation

The file observation reuses Batch 6B's full-workspace inventory. It checks private
POSIX mode bits, ownership, member types, link counts and expected areas without
opening credential contents as part of the inventory. Authentication separately
opens the current key to verify it. Linked or unreadable members remain held;
unexpected members receive attention. The scan is bounded at 60,000 members.

The root's retained identity and descriptor are checked before and after the
scan. This is not a recursive permission repair. It does not verify macOS ACLs,
other account policies, FileVault, external-drive encryption, malware resistance,
every ancestor's access policy, or all files elsewhere on the Mac.

Source-use observations verify ledger hashes, content-scoped permission records,
evidence hashes, entity bindings, expiry and revocation. Version contract/policy
checks reuse the existing local-action policy semantics. They do not read the
financial payloads or validate financial conclusions. Observations are bounded
at 1,000 permission records, 200 versions and 50 MB of permission/contract file
reads. They fail closed to unavailable counts when a bound or integrity check
prevents completion.

The summary distinguishes:

- **Held records:** revoked/expired records, or records whose local retention or
  local processing is not allowed.
- **Held versions:** saved version contracts whose current source-use check
  refuses or no longer matches the pinned policy.
- **Recorded rights:** allowed, denied and pending counts for each separate use,
  including held records. Current holds override the historically recorded
  allowed values. Backup restrictions also produce attention.

Unknown counts remain unknown. Zero appears only after a successful check. These
cross-store observations are not a globally atomic snapshot; recheck a transient
failure and use the stopped evidence audit for retained-reference validation.

The records remain local operator declarations backed by retained evidence. They
do not authenticate a provider's licence or demonstrate legal permission. Nothing
in 6D sends a provider enquiry, updates a rights register, authorises Yahoo usage
or enables a live financial feed/model. The existing unresolved provider rights
and source-review dependencies remain in force.

## Private delivery and redacted diagnostics

Private API responses retain `no-store`, `nosniff`, `no-referrer`, same-origin
resource policy and the existing content-security policies. A restrictive
Permissions-Policy disables camera, microphone and geolocation. The supported
server already suppresses HTTP access logs, so request URLs are not copied into
ordinary access logs. Unexpected private request failures now return a fixed
503 error envelope with these headers rather than raw exception details.

Original report and input downloads remain authenticated private copies. Their
figures, source text, operator notes and other contents are **not** transformed
into safe public documents. A local download does not grant redistribution rights
or prove that the operating system's Downloads directory is privately protected.
The server cannot prevent someone from copying a file after it is downloaded.

The separate diagnostic is constructed from this fixed allowlist:

| Field | Content |
| --- | --- |
| `schema_version`, `kind` | Fixed diagnostic contract identity |
| `observed_at` | Time of this observation |
| `state`, `source_use` | Checked, attention or unavailable |
| `controls` | Fixed control states and explicit disabled/unsupported features |

It contains no workspace ID/name, permission IDs, entity/provider/reviewer names,
record counts, financial values, source text, notes, key, path, raw error or log.
The client independently rejects unknown fields and inconsistent claims before
requesting a download. Both server and client bound the response at 16 KB.

`GET/HEAD /api/privacy` returns the protected full observation;
`GET/HEAD /api/privacy/diagnostic` returns the smaller protected attachment.
Query parameters and mutations are refused. Closed checked-in JSON schemas cover
both responses. Neither route changes permissions, installs source records,
repairs storage, submits jobs or contacts an external service.

The browser downloads `keystone-access-check.json` only after the operator clicks.
It stays local; there is no upload, telemetry or support-message action. Review
its timestamp and control states before sharing it. Redaction is defined by this
allowlist, not by a promise to sanitise arbitrary logs or reports.

## Acceptance and remaining scope

Local acceptance covers protected observation and delivery, current key-file
checks, latched invalidation, restart rotation, closed response contracts,
permission holds, source-read bounds, safe unexpected errors and the redacted
download. Existing evidence and private settings are preserved.

Recorded validation on 14 November 2026:

- 27 new backend privacy cases passed. The related regression run passed all
  385 cases, including jobs, ordinary/private API reads, operations, lifecycle,
  installation, launcher, onboarding and analyst-review workflows.
- All 571 frontend tests passed, including 37 new privacy/parser/download cases.
  TypeScript checking and the production build passed.
- The visible isolated browser workspace retained its saved fictional report,
  analyst note and decision. Access & privacy showed two local permission
  records and one saved version with no current source-use holds; model transfer
  and sharing remained denied in those records.
- The actual redacted download passed the closed backend diagnostic contract and
  allowlist checks. Keyboard recheck updated the observation; the observed
  576 px viewport had no horizontal page overflow or alert.
- Saved evidence hashes were compared before/after browser observation. Local
  screenshots, logs and rehearsal evidence remain under ignored
  `output/privacy-6d-preview/`, outside Git.

This acceptance is for the supported local pilot. Independent encrypted backup,
key recovery and clean-machine disaster recovery remain pending. The next 6E
part covers recovery/support. Batch 7 and the six document-intake parts retain
their agreed sequence; the broader backend programme follows all six intake
parts. Repository cleanup and local consolidation remain a separately verified
later milestone.
