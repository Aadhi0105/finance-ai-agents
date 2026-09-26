"""One publication decision for live runs and saved-record rebuilds."""
from validation import gate, note_grounding


def assess_record(record):
    analysis = record.get('analysis', {})
    previous = record.get('validation') or {}
    template = record.get('note_template')
    if template is None:
        template = (previous.get('note_grounding') or {}).get('original_note', record.get('note', ''))
    grounding = note_grounding.ground_note(template, analysis)
    result = gate.assess(analysis, calls=record.get('call_history', []))
    checks = result['checks'] + [{'check': 'note_grounding',
        'status': 'pass' if grounding['passed'] else 'fail',
        'detail': grounding['note'] if grounding['passed'] else str(grounding['unmatched'])}]
    if record.get('schema_version') != 2:
        checks.append({'check': 'record_schema', 'status': 'fail',
                       'detail': 'unsupported or legacy record schema; current version is 2'})
    execution = record.get('execution') or {}
    if (execution.get('configuration') or {}).get('narrative_output') == 'evidence_only_fallback':
        checks.append({'check': 'narrative_fallback', 'status': 'quality_warn',
                       'detail': 'model interpretation withheld after grounding failure; evidence-only output'})
    if execution.get('status') != 'completed' or (execution.get('outcome') or {}).get('status') != 'completed':
        checks.append({'check': 'execution_status', 'status': 'fail',
                       'detail': 'model execution not completed or completion evidence missing'})
    for name, series in (record.get('chart_data') or {}).items():
        if isinstance(series, dict):
            for warning in series.get('warnings', []):
                checks.append({'check': 'history_' + name, 'status': 'quality_warn',
                               'detail': warning})
    artifacts = record.get('artifacts') or {}
    for error in artifacts.get('errors', []):
        checks.append({'check': 'artifact_' + error['stage'], 'status': 'quality_warn',
                       'detail': error.get('error_type', 'artifact generation incomplete')})
    result = gate.aggregate_checks(checks)
    result['note_grounding'] = grounding
    return result, grounding['rendered_note']
