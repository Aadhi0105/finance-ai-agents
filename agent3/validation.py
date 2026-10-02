"""Fail-closed research eligibility; confidence is not a probability of truth."""
import math
import statistics
from tools.event_contracts import finite


def assess(study, *, contributing_peers=None, n_event_types_tested=1,
           study_plan=None, comparability_status='unverified', assembly_issues=None):
    checks=[]
    def add(name, status, detail): checks.append({'check':name,'status':status,'detail':detail})
    if isinstance(study_plan, dict) and study_plan.get('validation_only') is not False and 'validation_only' in study_plan:
        add('validation_only', 'fail', 'Source-check/acceptance plan is not a human-approved research design')
    n=study.get('n_events'); per=study.get('per_event')
    valid = (type(n) is int and isinstance(per,list) and n == len(per) and n >= 10
             and finite(study.get('caar')) and study.get('inference_status') == 'available'
             and type(study.get('caar_significant')) is bool and finite(study.get('p_value'))
             and 0 <= study['p_value'] <= 1 and not study.get('rejected_events'))
    add('inference', 'pass' if valid else 'fail', 'Eligible independent-event inference' if valid else
        'Unavailable or invalid inference: ' + ', '.join(study.get('inference_reasons',[]) or ['missing/invalid study evidence']))
    if valid:
        cars=[e.get('car') if isinstance(e,dict) else None for e in per]
        valid=all(finite(c) for c in cars)
        if valid:
            valid=(math.isclose(statistics.mean(cars), study['caar'], rel_tol=1e-12, abs_tol=1e-12)
                   and study['caar_significant'] == (study['p_value'] < .05))
        if not valid: add('consistency','fail','Study totals or inference decision do not match its evidence')
    peers=study.get('n_issuers',0)
    enough=type(peers) is int and peers >= 10
    if contributing_peers is not None and contributing_peers != peers: enough=False
    add('thin_data','pass' if enough else 'fail',f'{n} events; {peers} distinct issuers; minimum 10 independent issuers for this bounded method')
    add('comparability','pass' if comparability_status=='human_reviewed' else 'fail',
        'Human-reviewed universe and return bases' if comparability_status=='human_reviewed' else 'Peer economic comparability has not been reviewed')
    if assembly_issues: add('assembly','fail','Requested evidence was excluded or could not be assembled; review the accounting')
    family = study_plan.get('hypotheses') if isinstance(study_plan,dict) else None
    known = (isinstance(family,list) and bool(family) and len(family) <= 1000
             and all(isinstance(x,str) and x.strip() for x in family)
             and len(set(family)) == len(family) and study.get('event_type') in family)
    if type(n_event_types_tested) is not int or n_event_types_tested < 1:
        known=False
    if known and n_event_types_tested > len(family): known=False
    count=len(family) if known else None
    p=study.get('p_value')
    adjusted=min(1.,p*count) if known and finite(p) else None
    add('multiple_testing','pass' if known else 'fail',
        f'Predeclared family size={count}; adjusted p={adjusted}' if known else 'No valid predeclared hypothesis family; exploratory result')
    if valid and study['caar_significant'] and (adjusted is None or adjusted >= .05):
        add('adjusted_significance','fail','Does not survive the declared family adjustment')
    placebo=study.get('placebo') or {}
    ps=placebo.get('caar_significant')
    if ps is True:
        add('placebo','fail','Control mean differs from zero; review design')
    elif ps is False and placebo.get('inference_status') == 'available':
        add('placebo','pass','No detectable control mean; absence of effect is not established')
    else:
        add('placebo','fail','Control inference is missing, invalid or unresolved')
    hold=any(c['status']!='pass' for c in checks)
    return {'checks':checks,'verdict':'HOLD_FOR_REVIEW' if hold else 'PASS',
            'confidence':None,'confidence_note':'Eligibility checks, not calibrated confidence',
            'n_warn':0,'n_fail':sum(c['status']=='fail' for c in checks),
            'adjusted_p_value':adjusted,'family_size':count,'computed_by':'agent3.validation.assess (python)'}
