"""Append-only analyst dispositions over the unchanged 5A review scope.

The journal is a separate write protocol. Snapshot v1 remains read-only; no
disposition grants financial approval, changes evidence or executes an agent.
"""
from collections import Counter
from typing import Literal
import uuid

from pydantic import Field, field_validator

from ..catalog import Catalog
from ..job_contract import now
from ..onboarding import contracts as c
from ..report_views.delivery import load_view
from ..report_views.values import canonical, digest
from .contracts import (Binding, Decision, Disposition, Hash, Identifier,
                        ReviewError, ReviewRecord, SnapshotId, TargetKind, reduce_decisions)
from .projection import project_review

MAX_DECISION_BYTES = 16_384
MAX_RUN_DECISIONS = 1000
MAX_WORKSPACE_DECISIONS = 2000
MAX_JOURNAL_BYTES = 4_000_000
PAGE_SIZE = 25


class DecisionRequest(ReviewRecord):
    schema_version: Literal[1]
    snapshot_id: SnapshotId
    target_id: Identifier
    target_sha256: Hash
    expected_sequence: int = Field(ge=0, strict=True)
    disposition: Disposition
    reviewer_label: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1600)
    note_ids: list[str] = Field(max_length=10)
    correction_ids: list[str] = Field(max_length=5)

    @field_validator('reviewer_label', 'reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('A decision needs explanation and attribution.')
        value.encode('utf-8')
        return value

    @field_validator('note_ids', 'correction_ids')
    @classmethod
    def references(cls, value, info):
        import re
        prefix = 'note' if info.field_name == 'note_ids' else 'correction'
        if len(set(value)) != len(value) or any(re.fullmatch(prefix + r'-[a-f0-9]{32}', v) is None for v in value):
            raise ValueError('Invalid or repeated decision reference.')
        return value


class DecisionRecord(ReviewRecord):
    schema_version: Literal[1]
    kind: Literal['keystone.review-decision-record']
    id: str = Field(pattern=r'^decision-[a-f0-9]{32}$')
    ordinal: int = Field(ge=1, strict=True)
    binding: Binding
    request: DecisionRequest
    decision: Decision
    target_title: str = Field(min_length=1, max_length=240)
    target_kind: TargetKind
    request_key_sha256: Hash
    request_sha256: Hash
    financial_approval: Literal[False]


class DecisionReceipt(ReviewRecord):
    schema_version: Literal[1]
    kind: Literal['keystone.review-decision-receipt']
    id: str = Field(pattern=r'^decision-key-[a-f0-9]{64}$')
    decision_id: str = Field(pattern=r'^decision-[a-f0-9]{32}$')
    request_sha256: Hash


def fingerprint(run_id, request):
    return digest(dict(run_id=run_id, request=request))


def transition(state, disposition):
    if (state == 'not_recorded' or disposition == state
            or disposition == 'reopened' and state == 'pending'):
        raise c.InputError('review_decision_transition', 409)
    return 'pending' if disposition == 'reopened' else disposition


class DecisionsStore:
    def __init__(self, inputs):
        self.inputs = inputs

    def records(self, con):
        rows = con.execute("SELECT kind,id FROM objects WHERE kind IN ('review_decision','review_decision_receipt') ORDER BY sequence").fetchall()
        if len(rows) > 2 * MAX_WORKSPACE_DECISIONS:
            raise c.InputError('review_decisions_unavailable', 503)
        records, receipts, run_counts, scope_counts = [], {}, Counter(), Counter()
        keys, subjects, states = set(), {}, {}
        try:
            for kind, ident in rows:
                raw = self.inputs._object(con, kind, ident)
                if kind == 'review_decision_receipt':
                    proof = DecisionReceipt.model_validate(raw)
                    if proof.id != ident:
                        raise ValueError('Receipt identity changed.')
                    receipts[ident] = proof
                    continue
                record = DecisionRecord.model_validate(raw)
                q, event, binding = record.request, record.decision, record.binding
                run_counts[binding.run_id] += 1
                scope = (binding.run_id, q.snapshot_id)
                scope_counts[scope] += 1
                subject = (*scope, q.target_id)
                metadata = (q.target_sha256, record.target_title, record.target_kind)
                if (record.id != ident or event.id != record.id
                        or binding.workspace_id != self.inputs.descriptor['id'] or not binding.version_id
                        or not binding.dataset_id or not binding.contract_sha256 or not binding.request_sha256
                        or record.ordinal != run_counts[binding.run_id] or record.ordinal > MAX_RUN_DECISIONS
                        or q.expected_sequence != record.ordinal - 1 or event.sequence != scope_counts[scope]
                        or any(getattr(event, key) != getattr(q, key) for key in
                               ('snapshot_id', 'target_id', 'target_sha256', 'disposition', 'reviewer_label', 'reason'))
                        or record.request_sha256 != fingerprint(binding.run_id, q.model_dump())
                        or record.request_key_sha256 in keys
                        or subject in subjects and subjects[subject] != metadata
                        or len(canonical(raw)) > MAX_DECISION_BYTES):
                    raise ValueError('Decision binding/ordering changed.')
                states[subject] = transition(states.get(subject, 'pending'), event.disposition)
                subjects[subject] = metadata
                keys.add(record.request_key_sha256); records.append(record)
            if len(records) != len(receipts):
                raise ValueError('Incomplete decision transaction.')
            for record in records:
                proof = receipts.get('decision-key-' + record.request_key_sha256)
                if proof is None or (proof.decision_id, proof.request_sha256) != (record.id, record.request_sha256):
                    raise ValueError('Decision receipt changed.')
            return records, receipts
        except (ValueError, KeyError, TypeError, c.InputError) as exc:
            raise c.InputError('review_decisions_unavailable', 503) from exc

    @staticmethod
    def subject(snapshot, request):
        target = next((t for t in snapshot['targets'] if t['id'] == request.target_id), None)
        if (request.snapshot_id != snapshot['snapshot_id'] or target is None
                or target['availability'] != 'available' or target['scope_sha256'] != request.target_sha256):
            raise c.InputError('review_scope_changed', 409)
        return target

    def check_scope(self, record, snapshot):
        if record.binding.model_dump() != snapshot['binding']:
            raise c.InputError('review_decisions_unavailable', 503)
        if record.request.snapshot_id == snapshot['snapshot_id']:
            try:
                target = self.subject(snapshot, record.request)
                if (record.target_title, record.target_kind) != (target['title'], target['kind']):
                    raise ValueError('Decision subject changed.')
            except (ValueError, c.InputError) as exc:
                raise c.InputError('review_decisions_unavailable', 503) from exc

    def links(self, records, snapshot, context, con):
        note_ids = {ident for r in records for ident in r.request.note_ids}
        correction_ids = {ident for r in records for ident in r.request.correction_ids}
        notes, corrections = {}, {}
        if note_ids:
            from .notes import NotesStore
            store = NotesStore(self.inputs)
            values, _ = store.records(con)
            notes = {n.id: n for n in values}
            for ident in note_ids:
                note = notes.get(ident)
                if note is None:
                    raise c.InputError('review_decision_reference', 409)
                store.check_scope(note, snapshot)
        if correction_ids:
            from .corrections import CorrectionsStore
            store = CorrectionsStore(self.inputs)
            values, _ = store.records(con)
            corrections = {v.id: v for v in values}
            for ident in correction_ids:
                record = corrections.get(ident)
                if record is None:
                    raise c.InputError('review_decision_reference', 409)
                store.check_record(record, context)
        for record in records:
            request = record.request
            for item in [*(notes[i] for i in request.note_ids), *(corrections[i] for i in request.correction_ids)]:
                if (item.binding.model_dump() != snapshot['binding']
                        or item.request.snapshot_id != request.snapshot_id
                        or item.request.target_id != request.target_id
                        or item.request.target_sha256 != request.target_sha256):
                    raise c.InputError('review_decision_reference', 409)

    @staticmethod
    def progress(snapshot, records):
        try:
            return reduce_decisions(snapshot, [r.decision for r in records if r.request.snapshot_id == snapshot['snapshot_id']])
        except ReviewError as exc:
            raise c.InputError('review_decisions_unavailable', 503) from exc

    def append(self, context, run_id, value, key):
        try:
            request = DecisionRequest.model_validate(value)
            kh = c.request_key(key)
        except (ValueError, TypeError) as exc:
            raise c.InputError('review_decision_invalid', 422) from exc
        with self.inputs.write() as con:
            snapshot = context(run_id)['snapshot']
            if snapshot['binding']['workspace_id'] != self.inputs.descriptor['id'] or not snapshot['binding']['version_id']:
                raise c.InputError('review_scope_changed', 409)
            all_records, receipts = self.records(con)
            records = [r for r in all_records if r.binding.run_id == run_id]
            for record in records:
                self.check_scope(record, snapshot)
            fp = fingerprint(run_id, request.model_dump())
            proof = receipts.get('decision-key-' + kh)
            if proof:
                if proof.request_sha256 != fp:
                    raise c.InputError('review_decision_conflict', 409)
                old = next(r for r in records if r.id == proof.decision_id)
                self.links([old], snapshot, context, con)
                return old.model_dump(), True
            target = self.subject(snapshot, request)
            if request.expected_sequence != len(records):
                raise c.InputError('review_decision_stale', 409)
            progress = self.progress(snapshot, records)
            transition(progress['targets'][request.target_id], request.disposition)
            if len(records) >= MAX_RUN_DECISIONS or len(all_records) >= MAX_WORKSPACE_DECISIONS:
                raise c.InputError('review_decision_capacity', 409)
            ident = 'decision-' + uuid.uuid4().hex
            event = Decision(schema_version=1, kind='keystone.review-decision', id=ident,
                sequence=progress['decision_count']+1, snapshot_id=request.snapshot_id, target_id=request.target_id,
                target_sha256=request.target_sha256, disposition=request.disposition,
                reviewer_label=request.reviewer_label, identity_assurance='local_operator_unverified',
                reason=request.reason, recorded_at=now(), financial_approval=False)
            record = DecisionRecord(schema_version=1, kind='keystone.review-decision-record', id=ident,
                ordinal=len(records)+1, binding=snapshot['binding'], request=request, decision=event,
                target_title=target['title'], target_kind=target['kind'], request_key_sha256=kh,
                request_sha256=fp, financial_approval=False)
            self.links([record], snapshot, context, con)
            data = record.model_dump(); size = len(canonical(data))
            if size > MAX_DECISION_BYTES or self.inputs.path.stat().st_size + size*2 + 8192 > 64_000_000:
                raise c.InputError('review_decision_capacity', 409)
            receipt = DecisionReceipt(schema_version=1, kind='keystone.review-decision-receipt',
                id='decision-key-'+kh, decision_id=ident, request_sha256=fp).model_dump()
            self.inputs._put(con, 'review_decision', ident, data)
            self.inputs._put(con, 'review_decision_receipt', receipt['id'], receipt)
        return data, False

    def journal(self, snapshot, context, *, enabled=False, before=None, revision=None):
        with self.inputs.connect() as con:
            all_records, _ = self.records(con)
            records = [r for r in all_records if r.binding.run_id == snapshot['binding']['run_id']]
            for record in records:
                self.check_scope(record, snapshot)
            self.links(records, snapshot, context, con)
        return journal(snapshot, records, enabled=enabled, before=before, revision=revision)


def journal(snapshot, records=(), *, enabled=False, before=None, revision=None):
    count = len(records)
    if revision is not None and revision != count:
        raise c.InputError('review_decision_stale', 409)
    if before is None:
        ordinal = count + 1
    else:
        cursor = next((r for r in records if r.id == before), None)
        if cursor is None or revision is None:
            raise c.InputError('review_decision_invalid', 422)
        ordinal = cursor.ordinal
    current = [r for r in records if r.request.snapshot_id == snapshot['snapshot_id']]
    latest = {}
    for record in current:
        latest[record.request.target_id] = dict(decision=record.decision.model_dump(), ordinal=record.ordinal,
            target_title=record.target_title, target_kind=record.target_kind,
            note_ids=record.request.note_ids, correction_ids=record.request.correction_ids)
    page = [r for r in reversed(records) if r.ordinal < ordinal][:PAGE_SIZE+1]
    result = dict(schema_version=1, kind='keystone.review-journal', protocol_version='dispositions/1.0.0',
        snapshot_id=snapshot['snapshot_id'], binding=snapshot['binding'], decisions_enabled=enabled,
        last_sequence=count, current_count=len(current), earlier_scope_count=count-len(current),
        progress=DecisionsStore.progress(snapshot, records), latest_events=[latest[k] for k in sorted(latest)],
        records=[r.model_dump() for r in page[:PAGE_SIZE]], financial_approval=False,
        page=dict(before=before, before_ordinal=ordinal, next_cursor=page[PAGE_SIZE-1].id if len(page)>PAGE_SIZE else None,
                  limit=PAGE_SIZE, total=count))
    if len(canonical(result)) > MAX_JOURNAL_BYTES:
        raise c.InputError('review_decisions_unavailable', 503)
    return result


def validate_decisions(inputs):
    store = DecisionsStore(inputs)
    with inputs.connect() as con:
        records, _ = store.records(con)
    if not records:
        return
    catalog = Catalog(inputs.root/'reports'); manifest = catalog.load()
    runs = {r.id: r for r in manifest.runs}; scopes = {}
    def context(ident):
        if ident not in runs:
            raise c.InputError('review_decisions_unavailable', 503)
        if ident not in scopes:
            scopes[ident] = project_review(manifest, runs[ident], load_view(catalog, runs[ident]))
        return scopes[ident]
    for run_id in {r.binding.run_id for r in records}:
        store.journal(context(run_id)['snapshot'], context)
