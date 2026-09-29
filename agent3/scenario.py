"""Historical CAR summaries. No claim of forward predictive calibration."""
from __future__ import annotations
import random
import statistics
from tools.event_contracts import finite


def _percentile(values, q):
    i = q * (len(values)-1)
    lo = int(i)
    return values[lo] if lo+1 == len(values) else values[lo]*(1-(i-lo))+values[lo+1]*(i-lo)


def scenario_from_event_study(event_study, seed=12345, n_boot=10000):
    base = {'event_type':event_study.get('event_type','unspecified'), 'distribution':None,
            'confidence':'unavailable', 'computed_by':'scenario_engine (python)'}
    if type(seed) is not int or type(n_boot) is not int or not 200 <= n_boot <= 100000:
        return {**base, 'verdict':'REFUSED', 'reason':'seed must be integer; n_boot must be an integer in [200,100000]'}
    per = event_study.get('per_event')
    if not isinstance(per,list) or any(not isinstance(e,dict) or not finite(e.get('car')) for e in per):
        return {**base, 'verdict':'REFUSED', 'reason':'invalid per-event CAR evidence'}
    cars = [e['car'] for e in per]; n = len(cars)
    if type(event_study.get('n_events')) is not int or event_study['n_events'] != n or n < 5:
        return {**base, 'verdict':'REFUSED', 'reason':'insufficient or inconsistent event counts', 'n_events':n}
    significant = event_study.get('caar_significant')
    if significant is not None and type(significant) is not bool:
        return {**base, 'verdict':'REFUSED', 'reason':'invalid significance type'}
    available = event_study.get('inference_status') == 'available' and type(significant) is bool
    outcomes = sorted(cars)
    dist = {'mean_car':statistics.mean(cars), 'median_car':_percentile(outcomes,.5),
            'p10':_percentile(outcomes,.1), 'p25':_percentile(outcomes,.25),
            'p75':_percentile(outcomes,.75), 'p90':_percentile(outcomes,.9),
            'prob_positive':sum(c>0 for c in cars)/n, 'mean_ci95':None}
    if available:
        rng = random.Random(seed)
        means = sorted(statistics.mean(rng.choices(cars,k=n)) for _ in range(n_boot))
        dist['mean_ci95'] = [_percentile(means,.025), _percentile(means,.975)]
    verdict = ('HISTORICAL' if significant else 'NULL') if available else 'UNDETERMINED'
    return {**base, 'verdict':verdict, 'n_events':n, 'underlying_significant':significant,
            'distribution':dist, 'confidence':'descriptive_only',
            'headline':('Historical sample only; no forward scenario is published. '
                        + ('The mean is not statistically distinguishable from zero.' if available and not significant
                           else 'Inference is unresolved.' if not available else 'The eligible historical mean differs from zero.')),
            'method':'empirical CAR quantiles; iid mean bootstrap only for eligible independent events',
            'bootstrap':{'seed':seed,'replicates':n_boot if available else 0},
            'caveats':['Event-weighted history is not a next-event forecast.',
                       'No mean interval is supplied for unresolved dependence.']}
