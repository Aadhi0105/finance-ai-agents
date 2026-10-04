"""One prior/current boundary shared by variance and persistence analysis."""
from datetime import date
from copy import deepcopy
from agent4.contracts import cents


def assemble_history(node, current_cents, close_date=None):
    cents(current_cents, 'current variance')
    points = node.get('observation_history')
    frequency = node.get('history_frequency')
    if frequency not in (None, 'monthly', 'quarterly', 'annual'):
        raise ValueError('history_frequency must be monthly, quarterly or annual')
    gaps = []
    if points is not None:
        if not close_date:
            raise ValueError('dated history requires close_date')
        close = date.fromisoformat(close_date)
        stamps = [date.fromisoformat(p['period']) for p in points]
        if any(s >= close for s in stamps) or any(a >= b for a, b in zip(stamps, stamps[1:])):
            raise ValueError('history must be ordered, unique and strictly before close')
        prior = [cents(p['variance_cents'], 'prior variance') for p in points]
        if frequency:
            step = {'monthly': 1, 'quarterly': 3, 'annual': 12}[frequency]
            sequence = stamps + [close]
            for a, b in zip(sequence, sequence[1:]):
                if (b.year-a.year)*12+b.month-a.month != step:
                    gaps.append({'after': a.isoformat(), 'before': b.isoformat()})
        basis = 'dated prior observations'
    else:
        prior = node.get('history', [])
        if not isinstance(prior, list):
            raise ValueError('history must be a list')
        prior = [cents(v, 'prior variance') for v in prior]
        basis = 'legacy undated prior observations; cadence unverified'
    return {'prior_cents': prior, 'current_cents': current_cents,
            'current_period': close_date, 'prior_observations': deepcopy(points),
            'basis': basis, 'frequency': frequency, 'gaps': gaps,
            'cadence_verified': points is not None and frequency is not None and not gaps}
