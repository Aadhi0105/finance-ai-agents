"""Shared exact Student-t inference. Decisions use unrounded probabilities."""
from __future__ import annotations

import math
import statistics
from scipy import stats


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def t_critical(dof: int, confidence: float = 0.95) -> float:
    if type(dof) is not int or dof <= 0:
        raise ValueError('degrees of freedom must be a positive integer')
    if not _finite(confidence) or not 0 < confidence < 1:
        raise ValueError('confidence must be between zero and one')
    return float(stats.t.ppf((1 + confidence) / 2, dof))


def one_sample_t(values: list[float], mu0: float = 0.0) -> dict:
    if not isinstance(values, list) or not all(_finite(v) for v in values) or not _finite(mu0):
        raise ValueError('observations and null mean must be finite numbers, excluding booleans')
    n = len(values)
    base = {'n': n, 'mean': statistics.mean(values) if n else None,
            't_stat': None, 'p_value': None, 'significant': None,
            'inference_status': 'insufficient_observations', 'computed_by': 'one_sample_t (scipy Student-t)'}
    if n < 2:
        return {**base, 'reason': 'need at least 2 observations'}
    se = statistics.stdev(values) / math.sqrt(n)
    base.update(se=se, dof=n - 1, t_crit_95=t_critical(n - 1))
    if se == 0:
        return {**base, 'inference_status': 'degenerate_zero_dispersion'}
    t = (base['mean'] - mu0) / se
    p = float(2 * stats.t.sf(abs(t), n - 1))
    if not all(math.isfinite(v) for v in (base['mean'], se, t, p)):
        return {**base, 'mean': None, 'se': None, 'inference_status': 'numerical_failure'}
    return {**base, 't_stat': t, 'p_value': p, 'significant': p < .05, 'inference_status': 'available'}


def mean_ci(values: list[float], level: str = '95') -> dict:
    try:
        confidence = float(level) / 100
    except (TypeError, ValueError):
        raise ValueError('level must be a percentage between zero and 100') from None
    if isinstance(level, bool) or not math.isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError('level must be a percentage between zero and 100')
    r = one_sample_t(values)
    if r['inference_status'] != 'available':
        return {**r, 'ci': None, 'confidence_level': confidence}
    half = t_critical(len(values) - 1, confidence) * r['se']
    interval = [r['mean'] - half, r['mean'] + half]
    if not all(_finite(v) for v in interval):
        return {**r, 'ci': None, 'inference_status': 'numerical_failure', 'confidence_level': confidence}
    return {**r, 'ci': interval, 'confidence_level': confidence}
