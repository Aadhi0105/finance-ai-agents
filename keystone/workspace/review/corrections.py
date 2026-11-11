"""Version-linked input corrections, never in-place financial overrides.

Replacement packages use normal intake, validation and payload-scoped permission
records. This ledger only records the analyst's relationship between two saved
versions. Job admission and accounting corrections retain their existing rules.
"""
from copy import deepcopy
from typing import Literal
import uuid

from pydantic import Field, field_validator

from ..catalog import Catalog, read_json
from ..job_contract import now
from ..onboarding import contracts as c
from ..report_views.delivery import load_view
from ..report_views.values import canonical, digest
from .contracts import Binding, Hash, Identifier, ReviewRecord, SnapshotId, TargetKind
from .projection import project_review

MAX_CORRECTIONS = 200
MAX_CORRECTION_BYTES = 16_384
MAX_CHANGES = 200


class VersionPin(ReviewRecord):
    dataset_id: Identifier
    version_id: Identifier
    contract_sha256: Hash
    payload_sha256: Hash


class CorrectionRequest(ReviewRecord):
    schema_version: Literal[1]
    snapshot_id: SnapshotId
    target_id: Identifier
    target_sha256: Hash
    replacement: VersionPin
    change_sha256: Hash
    reviewer_label: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator('reviewer_label', 'reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('A correction needs a reason and local attribution.')
        value.encode('utf-8')
        return value


class Correction(ReviewRecord):
    schema_version: Literal[1]
    kind: Literal['keystone.review-correction']
    id: str = Field(pattern=r'^correction-[a-f0-9]{32}$')
    sequence: int = Field(ge=1, strict=True)
    recorded_at: str = Field(min_length=1, max_length=80)
    binding: Binding
    request: CorrectionRequest
    target_title: str = Field(min_length=1, max_length=240)
    target_kind: TargetKind
    change_count: int = Field(ge=1, le=MAX_CHANGES, strict=True)
    request_key_sha256: Hash
    request_sha256: Hash
    identity_assurance: Literal['local_operator_unverified']
    financial_approval: Literal[False]

    @field_validator('recorded_at')
    @classmethod
    def valid_time(cls, value):
        c.instant(value)
        return value


class CorrectionReceipt(ReviewRecord):
    schema_version: Literal[1]
    kind: Literal['keystone.review-correction-receipt']
    id: str = Field(pattern=r'^correction-key-[a-f0-9]{64}$')
    correction_id: str = Field(pattern=r'^correction-[a-f0-9]{32}$')
    request_sha256: Hash


def pin(version):
    return VersionPin(dataset_id=version['dataset_id'], version_id=version['id'],
                      contract_sha256=version['contract_sha256'],
                      payload_sha256=version['contract']['payload_sha256']).model_dump()


def fingerprint(run_id, request):
    return digest(dict(run_id=run_id, request=request))


def changes(before, after):
    """Bounded JSON-pointer diff, including absent versus explicit null.

    Full values stay in immutable packages. Long scalar values in the browser
    preview are labelled truncated, with a hash of the complete scalar.
    """
    missing = object()
    result = []

    def cell(value):
        if value is missing:
            return dict(present=False, text='', truncated=False, sha256=None)
        text = canonical(value).decode()
        return dict(present=True, text=text[:500], truncated=len(text) > 500, sha256=digest(value))

    def walk(a, b, path):
        if a is not missing and b is not missing and canonical(a) == canonical(b):
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                walk(a.get(key, missing), b.get(key, missing), path + '/' + key.replace('~', '~0').replace('/', '~1'))
        elif isinstance(a, list) and isinstance(b, list):
            for index in range(max(len(a), len(b))):
                walk(a[index] if index < len(a) else missing, b[index] if index < len(b) else missing, path + '/' + str(index))
        else:
            if len(path) > 2048:
                raise c.InputError('review_correction_diff_limit', 409)
            result.append(dict(path=path, before=cell(a), after=cell(b)))
            if len(result) > MAX_CHANGES:
                raise c.InputError('review_correction_diff_limit', 409)
    walk(before, after, '')
    if not result:
        raise c.InputError('review_correction_unchanged', 409)
    return result


def comparable(package):
    value = deepcopy(package)
    # The required lineage pointer itself is not a financial/source correction.
    value['dataset'].pop('supersedes_version_id', None)
    return value


class CorrectionsStore:
    def __init__(self, inputs):
        self.inputs = inputs

    def records(self, con):
        rows = con.execute("SELECT kind,id FROM objects WHERE kind IN ('review_correction','review_correction_receipt') ORDER BY sequence").fetchall()
        if len(rows) > 2 * MAX_CORRECTIONS:
            raise c.InputError('review_corrections_unavailable', 503)
        records, receipts, keys, parents = [], {}, set(), set()
        try:
            for kind, ident in rows:
                raw = self.inputs._object(con, kind, ident)
                if kind == 'review_correction_receipt':
                    proof = CorrectionReceipt.model_validate(raw)
                    if proof.id != ident:
                        raise ValueError('Receipt identity mismatch.')
                    receipts[ident] = proof
                    continue
                record = Correction.model_validate(raw)
                parent = record.binding.version_id
                if (record.id != ident or record.sequence != len(records) + 1
                        or record.binding.workspace_id != self.inputs.descriptor['id']
                        or not parent or not record.binding.dataset_id or not record.binding.contract_sha256
                        or parent == record.request.replacement.version_id
                        or record.binding.dataset_id != record.request.replacement.dataset_id
                        or parent in parents or record.request_key_sha256 in keys
                        or record.request_sha256 != fingerprint(record.binding.run_id, record.request.model_dump())
                        or len(canonical(raw)) > MAX_CORRECTION_BYTES):
                    raise ValueError('Correction binding mismatch.')
                parents.add(parent); keys.add(record.request_key_sha256); records.append(record)
            if len(records) != len(receipts):
                raise ValueError('Incomplete correction transaction.')
            for record in records:
                proof = receipts.get('correction-key-' + record.request_key_sha256)
                if proof is None or (proof.correction_id, proof.request_sha256) != (record.id, record.request_sha256):
                    raise ValueError('Correction receipt mismatch.')
            return records, receipts
        except (ValueError, KeyError, TypeError) as exc:
            raise c.InputError('review_corrections_unavailable', 503) from exc

    def source(self, snapshot):
        binding = snapshot['binding']
        if (binding['workspace_id'] != self.inputs.descriptor['id'] or not binding['version_id']):
            raise c.InputError('review_correction_unsupported', 409)
        version = self.inputs.version(binding['version_id'])
        if version['dataset_id'] != binding['dataset_id'] or version['contract_sha256'] != binding['contract_sha256']:
            raise c.InputError('review_corrections_unavailable', 503)
        return version

    def candidate(self, snapshot, version_id):
        old = self.source(snapshot)
        new = self.inputs.version(version_id, processing=True)
        meta = new['contract']['metadata']
        if (new['id'] == old['id'] or new['dataset_id'] != old['dataset_id']
                or meta['dataset']['supersedes_version_id'] != old['id']
                or meta['payload_format'] != old['contract']['metadata']['payload_format']):
            raise c.InputError('review_correction_invalid', 409)
        before, after = (read_json(self.inputs.read('inputs/' + v['id'] + '/package.json')) for v in (old, new))
        delta = changes(comparable(before), comparable(after))
        return dict(replacement=pin(new), changes=delta, change_count=len(delta), change_sha256=digest(delta))

    def check_record(self, record, context):
        snapshot = context(record.binding.run_id)['snapshot']
        if record.binding.model_dump() != snapshot['binding']:
            raise c.InputError('review_corrections_unavailable', 503)
        if record.request.snapshot_id == snapshot['snapshot_id']:
            target = self.target(snapshot, record.request)
            if (record.target_title, record.target_kind) != (target['title'], target['kind']):
                raise c.InputError('review_corrections_unavailable', 503)
        delta = self.candidate(snapshot, record.request.replacement.version_id)
        if (record.request.replacement.model_dump() != delta['replacement']
                or record.request.change_sha256 != delta['change_sha256'] or record.change_count != delta['change_count']):
            raise c.InputError('review_corrections_unavailable', 503)

    @staticmethod
    def target(snapshot, request):
        target = next((t for t in snapshot['targets'] if t['id'] == request.target_id), None)
        if (snapshot['snapshot_id'] != request.snapshot_id or target is None
                or target['scope_sha256'] != request.target_sha256 or target['availability'] != 'available'):
            raise c.InputError('review_scope_changed', 409)
        return target

    def append(self, context, run_id, value, key):
        try:
            request = CorrectionRequest.model_validate(value)
            kh = c.request_key(key)
        except (ValueError, TypeError) as exc:
            raise c.InputError('review_correction_invalid', 422) from exc
        # Same transaction/gate as revocations. Never mint source permission here.
        with self.inputs.write() as con:
            snapshot = context(run_id)['snapshot']
            source = self.source(snapshot)
            records, receipts = self.records(con)
            fp = fingerprint(run_id, request.model_dump())
            receipt = receipts.get('correction-key-' + kh)
            if receipt:
                if receipt.request_sha256 != fp:
                    raise c.InputError('review_correction_conflict', 409)
                old = next(r for r in records if r.id == receipt.correction_id)
                self.check_record(old, context)
                return old.model_dump(), True
            target = self.target(snapshot, request)
            delta = self.candidate(snapshot, request.replacement.version_id)
            if request.replacement.model_dump() != delta['replacement'] or request.change_sha256 != delta['change_sha256']:
                raise c.InputError('review_correction_invalid', 409)
            if any(r.binding.version_id == source['id'] for r in records):
                raise c.InputError('review_correction_already_linked', 409)
            if len(records) >= MAX_CORRECTIONS:
                raise c.InputError('review_correction_capacity', 409)
            record = Correction(schema_version=1, kind='keystone.review-correction', id='correction-' + uuid.uuid4().hex,
                sequence=len(records)+1, recorded_at=now(), binding=snapshot['binding'], request=request,
                target_title=target['title'], target_kind=target['kind'], change_count=delta['change_count'],
                request_key_sha256=kh, request_sha256=fp, identity_assurance='local_operator_unverified', financial_approval=False).model_dump()
            size = len(canonical(record))
            if size > MAX_CORRECTION_BYTES or self.inputs.path.stat().st_size + size * 2 + 8192 > 64_000_000:
                raise c.InputError('review_correction_capacity', 409)
            receipt = CorrectionReceipt(schema_version=1, kind='keystone.review-correction-receipt',
                id='correction-key-' + kh, correction_id=record['id'], request_sha256=fp).model_dump()
            self.inputs._put(con, 'review_correction', record['id'], record)
            self.inputs._put(con, 'review_correction_receipt', receipt['id'], receipt)
        return record, False

    def lineage(self, snapshot, context, manifest, *, enabled=False, replacement_version_id=None):
        source = self.source(snapshot)
        with self.inputs.connect() as con:
            records, _ = self.records(con)
            versions = [self.inputs._object(con, 'version', row[0]) for row in
                        con.execute("SELECT id FROM objects WHERE kind='version' ORDER BY sequence DESC")]
        relevant = [r for r in records if source['id'] in (r.binding.version_id, r.request.replacement.version_id)]
        incoming, outgoing = [], []
        for record in relevant:
            self.check_record(record, context)
            def reports(version_id):
                values = []
                for run in manifest.runs:
                    if run.input_origin.version_id == version_id:
                        context(run.id)  # Current permission, file and job-lineage checks.
                        values.append(dict(id=run.id, title=run.title, execution=run.execution_status))
                return values
            item = dict(record=record.model_dump(), affected_reports=reports(record.binding.version_id),
                        replacement_reports=reports(record.request.replacement.version_id))
            (outgoing if record.binding.version_id == source['id'] else incoming).append(item)
        candidates = []
        if not outgoing:
            for version in versions:
                if version['dataset_id'] != source['dataset_id'] or version['contract']['metadata']['dataset']['supersedes_version_id'] != source['id']:
                    continue
                try:
                    current = self.inputs.version(version['id'], processing=True)
                except c.InputError as exc:
                    if exc.code in {'input_policy_refused', 'input_invalid'}:
                        continue
                    raise
                validation = current['contract']['validation']
                candidates.append(dict(pin=pin(current), created_at=current['created_at'], period=validation.get('period', validation.get('period_end'))))
        selected = self.candidate(snapshot, replacement_version_id) if replacement_version_id else None
        result = dict(schema_version=1, kind='keystone.review-corrections', snapshot_id=snapshot['snapshot_id'],
            workspace_id=snapshot['binding']['workspace_id'], run_id=snapshot['binding']['run_id'],
            corrections_enabled=enabled, source=pin(source), incoming=incoming, outgoing=outgoing,
            candidates=candidates, comparison=selected, financial_approval=False)
        if len(canonical(result)) > 2_000_000:
            raise c.InputError('review_corrections_unavailable', 503)
        return result


def validate_corrections(inputs):
    store = CorrectionsStore(inputs)
    with inputs.connect() as con:
        records, _ = store.records(con)
    if not records:
        return
    catalog = Catalog(inputs.root / 'reports')
    manifest = catalog.load(); runs = {r.id: r for r in manifest.runs}; snapshots = {}
    def context(ident):
        if ident not in runs:
            raise c.InputError('review_corrections_unavailable', 503)
        if ident not in snapshots:
            snapshots[ident] = project_review(manifest, runs[ident], load_view(catalog, runs[ident]))
        return snapshots[ident]
    for record in records:
        store.check_record(record, context)
