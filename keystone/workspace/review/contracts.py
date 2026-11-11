"""Review contracts and pure decision reduction. No storage or approval side effects.

Batch 5A exposes snapshots only. Later writers must load a freshly authorised
snapshot, assign sequence/time, append decisions durably, and use this reducer.
An acknowledgement never changes source checks or approves a financial result.
"""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from ..catalog import Record
from ..report_views.values import digest

Hash = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
Identifier = Annotated[str, Field(pattern=r'^[a-z0-9][a-z0-9_-]{0,99}$')]
SnapshotId = Annotated[str, Field(pattern=r'^review-[a-f0-9]{64}$')]
TargetKind = Literal['source_inputs', 'financial_mappings', 'calculation_assumptions',
                     'report_section', 'review_issue']
Disposition = Literal['acknowledged', 'changes_requested', 'reopened']
POLICY_VERSION = 'review/1.0.0'
MAX_REVIEW_BYTES = 2_000_000


class ReviewError(ValueError):
    def __init__(self, code='review_unavailable', status=409):
        self.code, self.status = code, status
        super().__init__(code)

    def envelope(self):
        return {'error': {'code': self.code, 'message':
            'The review could not be matched to the current saved evidence. Recheck the report; no approval was granted.'}}


class ReviewRecord(Record):
    # Pydantic's literal equality otherwise accepts True as 1 and 0 as False,
    # unlike the published JSON schemas. Keep wire types exact at this boundary.
    @field_validator('schema_version', mode='before', check_fields=False)
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError('Review schema version must be an integer.')
        return value

    @field_validator('financial_approval', 'authenticated_reviewer', 'decisions_enabled',
                     mode='before', check_fields=False)
    @classmethod
    def boolean_flags(cls, value):
        if type(value) is not bool:
            raise ValueError('Review flags must be booleans.')
        return value


class Binding(ReviewRecord):
    workspace_id: Identifier
    run_id: Identifier
    run_sha256: Hash
    report_view_sha256: Hash
    artifact_hashes: dict[Identifier, Hash] = Field(min_length=1, max_length=40)
    dataset_id: Identifier | None
    version_id: Identifier | None
    contract_sha256: Hash | None
    request_sha256: Hash | None


class Target(ReviewRecord):
    id: Identifier
    kind: TargetKind
    title: str = Field(min_length=1, max_length=240)
    detail: str = Field(min_length=1, max_length=1600)
    availability: Literal['available', 'not_recorded']
    section_refs: list[Identifier] = Field(max_length=20)
    evidence_refs: list[Identifier] = Field(max_length=5000)
    issue_refs: list[Identifier] = Field(max_length=200)
    scope_sha256: Hash

    @model_validator(mode='after')
    def scope_matches(self):
        if self.scope_sha256 != digest(self.model_dump(exclude={'scope_sha256'})):
            raise ValueError('Review target scope changed.')
        for refs in (self.section_refs, self.evidence_refs, self.issue_refs):
            if len(set(refs)) != len(refs):
                raise ValueError('Duplicate review reference.')
        return self


class Snapshot(ReviewRecord):
    schema_version: Literal[1]
    kind: Literal['keystone.review-snapshot']
    policy_version: Literal['review/1.0.0']
    snapshot_id: SnapshotId
    binding: Binding
    input_acceptance: Literal['accepted_for_processing', 'retained_evidence']
    execution: Literal['completed', 'held', 'refused', 'unavailable', 'failed']
    evidence_gate: Literal['held_for_review', 'passed_evidence_checks', 'unavailable']
    financial_approval: Literal[False]
    authenticated_reviewer: Literal[False]
    decisions_enabled: Literal[False]
    targets: list[Target] = Field(min_length=1, max_length=223)

    @model_validator(mode='after')
    def binding_matches(self):
        if len({t.id for t in self.targets}) != len(self.targets):
            raise ValueError('Duplicate review target.')
        inputs = (self.binding.dataset_id, self.binding.version_id, self.binding.contract_sha256)
        if (self.input_acceptance == 'accepted_for_processing'
                and (not all(inputs) or self.binding.request_sha256 is None)
                or self.input_acceptance == 'retained_evidence' and any(x is not None for x in inputs)):
            raise ValueError('Input acceptance disagrees with its version binding.')
        expected = 'review-' + digest(self.model_dump(exclude={'snapshot_id'}))
        if self.snapshot_id != expected:
            raise ValueError('Review snapshot binding changed.')
        return self


class Decision(ReviewRecord):
    schema_version: Literal[1]
    kind: Literal['keystone.review-decision']
    id: str = Field(pattern=r'^decision-[a-f0-9]{32}$')
    sequence: int = Field(ge=1)
    snapshot_id: SnapshotId
    target_id: Identifier
    target_sha256: Hash
    disposition: Disposition
    reviewer_label: str = Field(min_length=1, max_length=120)
    identity_assurance: Literal['local_operator_unverified']
    reason: str = Field(min_length=1, max_length=1600)
    recorded_at: str = Field(min_length=1, max_length=80)
    financial_approval: Literal[False]

    @field_validator('reviewer_label', 'reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Review explanation and attribution must not be blank.')
        return value

    @field_validator('recorded_at')
    @classmethod
    def aware_time(cls, value):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('A review time needs a timezone.')
        return value


def reduce_decisions(snapshot, decisions=()):
    """Reduce one ordered, snapshot-scoped history; refuse stale/unknown subjects.

    All targets start pending. Acknowledging one does not acknowledge another.
    Reopening restores pending status. No state grants financial approval or
    removes publication restrictions. This is not a persistence implementation.
    """
    try:
        snapshot = Snapshot.model_validate(snapshot.model_dump() if isinstance(snapshot, Snapshot) else snapshot)
        if len(decisions) > 2000:
            raise ValueError('Review history exceeds bounds.')
        targets = {t.id: t for t in snapshot.targets}
        states = {t.id: 'pending' if t.availability == 'available' else 'not_recorded'
                  for t in snapshot.targets}
        seen = set()
        for sequence, raw in enumerate(decisions, 1):
            decision = Decision.model_validate(raw.model_dump() if isinstance(raw, Decision) else raw)
            target = targets.get(decision.target_id)
            if (decision.sequence != sequence or decision.id in seen
                    or decision.snapshot_id != snapshot.snapshot_id or target is None
                    or target.availability != 'available'
                    or target.scope_sha256 != decision.target_sha256):
                raise ValueError('Stale, duplicate or invalid review decision.')
            seen.add(decision.id)
            states[target.id] = 'pending' if decision.disposition == 'reopened' else decision.disposition
        available = [state for state in states.values() if state != 'not_recorded']
        overall = ('not_started' if not decisions else
                   'changes_requested' if 'changes_requested' in available else
                   'reviewed_with_limitations' if available and all(s == 'acknowledged' for s in available) else
                   'in_review')
        return dict(analyst_review=overall, targets=states, decision_count=len(decisions),
                    financial_approval=False, evidence_gate=snapshot.evidence_gate)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ReviewError('review_binding_mismatch') from exc
