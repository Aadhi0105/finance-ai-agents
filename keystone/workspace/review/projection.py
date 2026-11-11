"""Build review subjects from a verified native report without editing evidence."""
from ..catalog import run_identity
from ..report_views.values import canonical, digest
from .contracts import MAX_REVIEW_BYTES, POLICY_VERSION, ReviewError, Snapshot, Target, reduce_decisions


def project_review(manifest, run, view):
    reg = run.native_view
    by_id = {a.id: a for a in run.artifacts}
    origin = getattr(run, 'input_origin', None)
    job = origin or getattr(run, 'job_origin', None)
    workspace = getattr(manifest, 'workspace_id', None) or 'synthetic-' + digest(
        manifest.model_dump(exclude={'runs'}))
    binding = dict(workspace_id=workspace, run_id=run.id, run_sha256=digest(run_identity(run)),
                   report_view_sha256=by_id[reg.artifact_id].sha256,
                   artifact_hashes={a.id: a.sha256 for a in run.artifacts},
                   dataset_id=origin.dataset_id if origin else None,
                   version_id=origin.version_id if origin else None,
                   contract_sha256=origin.contract_sha256 if origin else None,
                   request_sha256=job.request_sha256 if job else None)
    targets = []

    def section_evidence(section):
        refs = []
        for field, collection in (('metric_refs', 'metrics'), ('finding_refs', 'findings'),
                                  ('chart_refs', 'charts'), ('table_refs', 'tables')):
            for item in view[collection]:
                if item['id'] in section[field]:
                    refs.extend(item.get('content', item).get('evidence_refs', []))
        return refs

    def add(ident, kind, title, detail, *, sections=(), evidence=(), issues=(), available=True):
        value = dict(id=ident, kind=kind, title=title, detail=detail,
                     availability='available' if available else 'not_recorded',
                     section_refs=list(sections), evidence_refs=sorted(set(evidence)), issue_refs=list(issues))
        targets.append(Target(**value, scope_sha256=digest(value)))

    evidence = [e['id'] for e in view['evidence']]
    add('source-inputs', 'source_inputs', 'Source inputs',
        'Inspect the retained input and its source basis. Acceptance for processing does not establish financial accuracy or source authenticity.',
        evidence=evidence)
    add('financial-mappings', 'financial_mappings', 'Figure mappings',
        'Inspect the saved field links and transformations used by report figures. These are not PDF extraction mappings.',
        evidence=evidence, available=bool(evidence))
    assumption_ids = {m['id'] for m in view['metrics'] if m['id'].startswith(('assumption-', 'weight-', 'dcf-weight-', 'dcf-growth-'))
                      or 'threshold' in m['id']}
    method_sections = {'valuation', 'method', 'event-context', 'event-review', 'news-context',
                       'close-forecast-context', 'forecast', 'monitor-context'}
    sections = [s for s in view['sections'] if s['availability'] != 'not_applicable'
                and (s['id'] in method_sections or assumption_ids.intersection(s['metric_refs']))]
    add('calculation-assumptions', 'calculation_assumptions', 'Assumptions and method',
        'Inspect retained assumptions, policy thresholds and method limits. Unrecorded choices cannot be confirmed here.',
        sections=[s['id'] for s in sections],
        evidence=[ref for s in sections for ref in section_evidence(s)], available=bool(sections))
    for section in view['sections']:
        add('section-' + section['id'], 'report_section', section['title'],
            'Review this saved section with its availability and linked restrictions. Acknowledgement cannot release withheld figures.',
            sections=[section['id']], evidence=section_evidence(section), issues=section['review_refs'])
    for issue in view['review_items']:
        add('issue-' + issue['id'], 'review_issue', issue['title'], issue['explanation'],
            sections=issue['section_refs'], evidence=issue['evidence_refs'], issues=[issue['id']])
    value = dict(schema_version=1, kind='keystone.review-snapshot', policy_version=POLICY_VERSION,
                 binding=binding, input_acceptance='accepted_for_processing' if origin else 'retained_evidence',
                 execution=run.execution_status, evidence_gate=view['state']['evidence_gate'],
                 financial_approval=False, authenticated_reviewer=False, decisions_enabled=False,
                 targets=[t.model_dump() for t in targets])
    snapshot = Snapshot(**value, snapshot_id='review-' + digest(value))
    result = dict(snapshot=snapshot.model_dump(), progress=reduce_decisions(snapshot))
    if len(canonical(result)) > MAX_REVIEW_BYTES:
        raise ReviewError('review_unavailable', 503)
    return result
