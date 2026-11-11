"""Private append-only notes in the existing transactional input ledger.

Notes are analyst-authored observations, questions or follow-up work. They never
become review decisions, source corrections, execution commands or approvals.
"""
from collections import Counter
import uuid
from typing import Literal

from pydantic import Field, field_validator

from ..catalog import Catalog
from ..job_contract import now
from ..report_views.delivery import load_view
from ..report_views.values import canonical, digest
from ..onboarding import contracts as c
from .contracts import Binding, Hash, Identifier, ReviewRecord, SnapshotId, TargetKind
from .projection import project_review

MAX_NOTE_BYTES = 16_384
MAX_RUN_NOTES = 100
MAX_WORKSPACE_NOTES = 1000


class NoteRequest(ReviewRecord):
    schema_version: Literal[1]
    snapshot_id: SnapshotId
    target_id: Identifier
    target_sha256: Hash
    reviewer_label: str = Field(min_length=1, max_length=120)
    note_type: Literal['observation', 'question', 'follow_up']
    text: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[Identifier] = Field(max_length=10)

    @field_validator('reviewer_label', 'text')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('A note needs text and attribution.')
        value.encode('utf-8')
        return value

    @field_validator('evidence_refs')
    @classmethod
    def unique_refs(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('Repeated evidence reference.')
        return value


class Note(ReviewRecord):
    schema_version: Literal[1]
    kind: Literal['keystone.review-note']
    id: str = Field(pattern=r'^note-[a-f0-9]{32}$')
    sequence: int = Field(ge=1)
    recorded_at: str = Field(min_length=1, max_length=80)
    binding: Binding
    request: NoteRequest
    target_title: str = Field(min_length=1, max_length=240)
    target_kind: TargetKind
    request_key_sha256: Hash
    request_sha256: Hash
    identity_assurance: Literal['local_operator_unverified']
    financial_approval: Literal[False]

    @field_validator('recorded_at')
    @classmethod
    def valid_time(cls, value):
        c.instant(value)
        return value


class NoteReceipt(ReviewRecord):
    schema_version: Literal[1]
    kind: Literal['keystone.review-note-receipt']
    id: str = Field(pattern=r'^review-key-[a-f0-9]{64}$')
    note_id: str = Field(pattern=r'^note-[a-f0-9]{32}$')
    request_sha256: Hash


def request_fingerprint(run_id, request):
    return digest(dict(run_id=run_id, request=request))


def validate_subject(snapshot, request):
    target = next((t for t in snapshot['targets'] if t['id'] == request.target_id), None)
    if (request.snapshot_id != snapshot['snapshot_id'] or target is None
            or request.target_sha256 != target['scope_sha256']
            or target['availability'] != 'available'
            or not set(request.evidence_refs) <= set(target['evidence_refs'])):
        raise c.InputError('review_scope_changed', 409)
    return target


class NotesStore:
    def __init__(self, inputs):
        self.inputs = inputs

    def records(self, con):
        """Validate paired note/receipt objects, workspace identity and sequence."""
        rows = con.execute("SELECT kind,id FROM objects WHERE kind IN ('review_note','review_note_receipt') ORDER BY sequence").fetchall()
        if len(rows) > 2 * MAX_WORKSPACE_NOTES:
            raise c.InputError('review_notes_unavailable', 503)
        notes, receipts, counts, keys = [], {}, Counter(), set()
        try:
            for kind, ident in rows:
                raw = self.inputs._object(con, kind, ident)
                if kind == 'review_note_receipt':
                    receipt = NoteReceipt.model_validate(raw)
                    if receipt.id != ident:
                        raise ValueError('Receipt identity mismatch.')
                    receipts[ident] = receipt
                    continue
                note = Note.model_validate(raw)
                run_id = note.binding.run_id
                counts[run_id] += 1
                if (note.id != ident or note.binding.workspace_id != self.inputs.descriptor['id']
                        or note.sequence != counts[run_id] or counts[run_id] > MAX_RUN_NOTES
                        or note.request_key_sha256 in keys
                        or note.request_sha256 != request_fingerprint(run_id, note.request.model_dump())
                        or len(canonical(raw)) > MAX_NOTE_BYTES):
                    raise ValueError('Note binding mismatch.')
                keys.add(note.request_key_sha256)
                notes.append(note)
            if len(notes) != len(receipts):
                raise ValueError('Incomplete note transaction.')
            for note in notes:
                receipt = receipts.get('review-key-' + note.request_key_sha256)
                if receipt is None or (receipt.note_id, receipt.request_sha256) != (note.id, note.request_sha256):
                    raise ValueError('Note receipt mismatch.')
            return notes, receipts
        except (ValueError, KeyError, TypeError) as exc:
            raise c.InputError('review_notes_unavailable', 503) from exc

    @staticmethod
    def check_scope(note, snapshot):
        if note.binding.model_dump() != snapshot['binding']:
            raise c.InputError('review_notes_unavailable', 503)
        if note.request.snapshot_id == snapshot['snapshot_id']:
            try:
                target = validate_subject(snapshot, note.request)
            except c.InputError as exc:
                raise c.InputError('review_notes_unavailable', 503) from exc
            if (note.target_title, note.target_kind) != (target['title'], target['kind']):
                raise c.InputError('review_notes_unavailable', 503)

    def notebook(self, snapshot, *, enabled=False):
        with self.inputs.connect() as con:
            all_notes, _ = self.records(con)
        notes = [n for n in all_notes if n.binding.run_id == snapshot['binding']['run_id']]
        for note in notes:
            self.check_scope(note, snapshot)
        current = [n.model_dump() for n in notes if n.request.snapshot_id == snapshot['snapshot_id']]
        earlier = [n.model_dump() for n in notes if n.request.snapshot_id != snapshot['snapshot_id']]
        return notebook(snapshot, current, earlier, enabled=enabled)

    def append(self, context, value, key):
        try:
            request = NoteRequest.model_validate(value)
            kh = c.request_key(key)
        except (ValueError, TypeError) as exc:
            raise c.InputError('review_note_invalid', 422) from exc
        # The source check runs under the same input-ledger write transaction as
        # permission revocation. Browser hashes alone never authorise a note.
        with self.inputs.write() as con:
            snapshot = context()['snapshot']
            if snapshot['binding']['workspace_id'] != self.inputs.descriptor['id']:
                raise c.InputError('review_scope_changed', 409)
            notes, receipts = self.records(con)
            run_id = snapshot['binding']['run_id']
            fp = request_fingerprint(run_id, request.model_dump())
            proof = receipts.get('review-key-' + kh)
            if proof is not None:
                if proof.request_sha256 != fp:
                    raise c.InputError('review_note_conflict', 409)
                old = next(n for n in notes if n.id == proof.note_id)
                self.check_scope(old, snapshot)
                return old.model_dump(), True
            target = validate_subject(snapshot, request)
            count = sum(n.binding.run_id == run_id for n in notes)
            if len(notes) >= MAX_WORKSPACE_NOTES or count >= MAX_RUN_NOTES:
                raise c.InputError('review_note_capacity', 409)
            record = Note(schema_version=1, kind='keystone.review-note', id='note-' + uuid.uuid4().hex,
                          sequence=count + 1, recorded_at=now(), binding=snapshot['binding'], request=request,
                          target_title=target['title'], target_kind=target['kind'], request_key_sha256=kh,
                          request_sha256=fp, identity_assurance='local_operator_unverified', financial_approval=False).model_dump()
            size = len(canonical(record))
            if size > MAX_NOTE_BYTES or self.inputs.path.stat().st_size + size * 2 + 8192 > 64_000_000:
                raise c.InputError('review_note_capacity', 409)
            receipt = NoteReceipt(schema_version=1, kind='keystone.review-note-receipt', id='review-key-' + kh,
                                  note_id=record['id'], request_sha256=fp).model_dump()
            self.inputs._put(con, 'review_note', record['id'], record)
            self.inputs._put(con, 'review_note_receipt', receipt['id'], receipt)
        return record, False


def notebook(snapshot, notes=(), earlier=(), *, enabled=False):
    return dict(schema_version=1, kind='keystone.review-notebook', snapshot_id=snapshot['snapshot_id'],
                workspace_id=snapshot['binding']['workspace_id'], run_id=snapshot['binding']['run_id'],
                notes_enabled=enabled, notes=list(notes), earlier_scope_notes=list(earlier),
                analyst_review='in_review' if notes else 'not_started', decision_count=0, financial_approval=False)


def validate_notes(inputs):
    """Included in snapshot/restore validation; no new files or DB migration."""
    store = NotesStore(inputs)
    with inputs.connect() as con:
        notes, _ = store.records(con)
    if not notes:
        return
    catalog = Catalog(inputs.root / 'reports')
    manifest = catalog.load()
    runs = {r.id: r for r in manifest.runs}
    snapshots = {}
    for note in notes:
        ident = note.binding.run_id
        if ident not in runs:
            raise c.InputError('review_notes_unavailable', 503)
        if ident not in snapshots:
            snapshots[ident] = project_review(manifest, runs[ident], load_view(catalog, runs[ident]))['snapshot']
        store.check_scope(note, snapshots[ident])
