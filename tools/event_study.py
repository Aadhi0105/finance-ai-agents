"""Market-model historical study with conservative, explicit inference eligibility.

Repeated issuers or overlapping event windows are descriptive only. This bounded
version does not estimate clustered standard errors from a small peer universe.
"""
from __future__ import annotations
from collections import Counter
import math
import statistics
from scipy import stats
from tools.event_contracts import validate_event, finite, MAX_EVENTS, review_complete, release_provenance_complete
from tools.significance import one_sample_t


def _ols_market_model(stock_rets, mkt_rets):
    mbar, sbar = statistics.mean(mkt_rets), statistics.mean(stock_rets)
    s_mm = sum((r - mbar) ** 2 for r in mkt_rets)
    if s_mm <= 1e-16:
        raise ValueError('market-model slope is unidentifiable: insufficient market variance')
    beta = sum((m - mbar) * (s - sbar) for m, s in zip(mkt_rets, stock_rets)) / s_mm
    return sbar - beta * mbar, beta


def _car_for_event(event):
    e = validate_event(event)
    alpha, beta = _ols_market_model(e['est_stock'], e['est_market'])
    ars = [s - alpha - beta * m for s, m in zip(e['evt_stock'], e['evt_market'])]
    car = sum(ars)
    if not all(finite(v) for v in [alpha, beta, car, *ars]):
        raise ValueError('nonfinite market-model output')
    return {k: v for k, v in {**e, 'alpha': alpha, 'beta': beta,
            'abnormal_returns': ars, 'car': car}.items()
            if k not in ('est_stock', 'est_market', 'evt_stock', 'evt_market')}


def _sign_test(cars):
    pos, neg = sum(c > 0 for c in cars), sum(c < 0 for c in cars)
    n = pos + neg
    p = float(stats.binomtest(pos, n, .5).pvalue) if n else None
    return {'n_nonzero': n, 'positive': pos, 'negative': neg,
            'p_value': p, 'significant': p < .05 if p is not None else None}


def _collect(events):
    accepted, rejected, identities, windows = [], [], set(), {}
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        return [], [{'index': None, 'reason': f'events must be a list of at most {MAX_EVENTS} records'}]
    for i, event in enumerate(events):
        try:
            e = validate_event(event)
            issuer = e.get('issuer_id') or e['ticker']
            if not isinstance(issuer, str) or not issuer.strip():
                raise ValueError('invalid issuer identity')
            issuer = issuer.strip().upper()
            e['issuer_id'] = issuer
            anchor = e.get('anchor_date', e['event_date'])
            identity = (issuer, anchor)
            if identity in identities:
                raise ValueError('duplicate issuer/event anchor')
            # Same issuer's overlapping measurement windows cannot be independent events.
            ds = set(e.get('window_dates', []))
            if ds & windows.get(issuer, set()):
                raise ValueError('overlapping event windows for issuer')
            c = _car_for_event(e)
            identities.add(identity)
            windows.setdefault(issuer, set()).update(ds)
            accepted.append(c)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            rejected.append({'index': i, 'reason': str(exc)})
    return accepted, rejected


def _summarize(events, event_type):
    per, rejected = _collect(events)
    n = len(per)
    counts = Counter(e.get('issuer_id', e['ticker']) for e in per)
    reasons = []
    if rejected: reasons.append('rejected_input_records')
    if n < 10: reasons.append('fewer_than_10_independent_events')
    if any(c > 1 for c in counts.values()): reasons.append('repeated_issuer_dependence')
    all_dates = [d for e in per for d in e.get('window_dates', [])]
    if len(set(all_dates)) != len(all_dates): reasons.append('overlapping_cross_issuer_windows')
    if any(not e.get('window_dates') or not e.get('est_dates') for e in per):
        reasons.append('missing_window_dates')
    if any(e.get('date_status') != 'reviewed' for e in per): reasons.append('unverified_event_dates')
    if any(not release_provenance_complete(e) for e in per): reasons.append('missing_or_inconsistent_release_provenance')
    if any(e.get('benchmark_status') != 'reviewed' for e in per): reasons.append('unverified_benchmark_basis')
    if any(e.get('quality_flags') for e in per): reasons.append('price_calendar_quality_flags')
    if any(e.get('design_status') != 'reviewed' for e in per): reasons.append('unreviewed_sampling_assumptions')
    for e in per:
        evidence = e.get('review_evidence') or {}
        if not isinstance(evidence,dict) or not all(review_complete(evidence.get(k), source=k != 'design') for k in ('date','benchmark','design')):
            reasons.append('missing_review_evidence')
            break
    cars = [e['car'] for e in per]
    ttest = one_sample_t(cars)
    if ttest['inference_status'] != 'available': reasons.append(ttest['inference_status'])
    eligible = not reasons
    return {'event_type': event_type, 'n_events': n, 'n_issuers': len(counts),
            'events_by_issuer': dict(counts), 'weighting': 'equal weight per accepted event',
            'caar': statistics.mean(cars) if cars else None,
            'caar_significant': ttest['significant'] if eligible else None,
            't_stat': ttest['t_stat'] if eligible else None,
            'p_value': ttest['p_value'] if eligible else None,
            'inference_status': 'available' if eligible else 'unavailable',
            'inference_reasons': reasons, 'rejected_events': rejected, 'per_event': per,
            'sign_test': _sign_test(cars) if eligible else {'significant': None, 'p_value': None, 'reason': 'same independence restrictions as t-test'},
            'power_note': 'Sample size alone does not establish statistical power.',
            'method': 'OLS market model; historical equal-event CAR mean; independent-event Student-t only when eligible',
            'computed_by': 'run_event_study (python)'}


def run_event_study(events: list[dict], event_type: str = 'unspecified',
                    placebo_events: list[dict] | None = None) -> dict:
    if not isinstance(event_type,str) or not event_type.strip() or len(event_type)>200:
        result = _summarize([], 'invalid_event_type')
        result['rejected_events'] = [{'index':None,'reason':'event_type must be a nonempty string of at most 200 characters'}]
        return result
    result = _summarize(events, event_type)
    placebo = _summarize([] if placebo_events is None else placebo_events, event_type)
    actual_days = {(e['issuer_id'],d) for e in result['per_event'] for d in e.get('window_dates', [])}
    control_days = {(e['issuer_id'],d) for e in placebo['per_event'] for d in e.get('window_dates', [])}
    if actual_days & control_days:
        placebo.update(inference_status='unavailable', caar_significant=None, p_value=None, t_stat=None,
                       sign_test={'significant':None,'p_value':None})
        placebo['inference_reasons'].append('control_overlaps_real_event')
    sig = placebo['caar_significant']
    placebo['interpretation'] = ('UNAVAILABLE — control inference unresolved' if sig is None else
        'REVIEW — control mean differs from zero' if sig else
        'No statistically detectable control mean; this does not prove absence of an effect')
    result['placebo'] = placebo
    return result
