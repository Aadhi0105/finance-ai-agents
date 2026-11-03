# Data onboarding design pack

**Batch 3A specification; no importer is implemented by this pack.**

[Batch 3B.1](../batch3b1-data-onboarding.md) now implements the separate private
saved-input backend. [Batch 3B.2](../batch3b2-fresh-close.md) implements the
fresh-close example's validation, isolated accounting state and recovery profile.
[3C](../batch3c-browser-onboarding.md) implements the protected browser onboarding flow; broader 3D acceptance remains pending.

- [Design and per-agent contracts](../batch3a-input-contracts.md)
- [Version-1 package envelope schema](input-package.schema.json)
- [Pending backend/browser/recovery acceptance](acceptance-matrix.md)
- [Fictional close-request package](examples/synthetic-close-request.json)

The package schema validates the closed outer envelope and workflow/format
pairing. `payload` intentionally remains a JSON object: existing financial formats
require their own bounded semantic adapters, identity checks and engine validation.
Envelope validation is necessary but never sufficient for import acceptance.

The example wraps the existing [fictional June close request](../../../fixtures/agent4/close-june.json)
without changing its payload. `entity-example` and `permission-synthetic-example`
are illustrative references, not existing registered entities or permission grants.
The new-close profile is implemented in 3B.2 after saved-evidence ingestion.
Its protected import accepts this shape after the references are registered;
execution requires a separate job bound to the resulting immutable version.

The example records its period range and EUR/integer-cent units explicitly.
Publication and retrieval instants remain unknown. Its metadata does not establish
budget approval, source authenticity or rights for any other file.

## Documentation verification

From the repository root, check the design schema/example using the existing
development dependencies:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

root = Path('docs/webapp/data-onboarding')
schema = json.loads((root / 'input-package.schema.json').read_text())
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema, format_checker=FormatChecker())
example = json.loads((root / 'examples/synthetic-close-request.json').read_text())
validator.validate(example)
assert example['payload'] == json.loads(Path('fixtures/agent4/close-june.json').read_text())
print('Design schema and example agree; runtime import acceptance remains pending.')
PY
```

No runtime schemas, agent inputs, databases, report catalogues or production
acceptance statuses are changed by this pack. Use the main guide's 3B.1/3B.2 →
3C → 3D implementation order. The package goes through the protected import API;
the job API accepts its resulting dataset-version reference, not this package.

## Recorded 3A checks — 2 November 2026

- Draft 2020-12 schema is valid; the complete fictional envelope passes with
  date/time format checking. Its payload exactly matches the existing fixture.
- Seventeen malformed/unsupported envelope cases were refused, including client
  approval/command/path fields, unknown versions/formats, bad dates/timestamps,
  missing/excess sources and invalid payload shapes.
- All 24 mismatched workflow/format combinations were refused. The six permitted
  pairings were checked only at the envelope layer, without claiming payload validity.
- Nineteen local documentation links resolved; Git whitespace checks passed.

These are design-artifact checks. No application regression suite or browser
rehearsal was rerun for these documentation-only changes. All 30 implementation
acceptance rows were pending at the 3A design checkpoint. Current backend evidence
is recorded in the 3B.1 guide; the matrix continues to track final acceptance.
