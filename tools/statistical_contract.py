"""Finite input/output boundary shared by the statistical tools."""
import inspect
import json
from functools import wraps
from tools.financial_contract import finite


def validated_statistics(function):
    signature = inspect.signature(function)

    @wraps(function)
    def checked(*args, **kwargs):
        try:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            p = bound.arguments
            values = p['values']
            if not isinstance(values, (list, tuple)) or not all(finite(v) for v in values):
                raise ValueError('values must be a sequence of finite numbers, not booleans')
            minimum = 3 if function.__name__ == 'drift_check' else 2
            if type(p['min_obs']) is not int or p['min_obs'] < minimum:
                raise ValueError(f'min_obs must be an integer of at least {minimum}')
            if 'times' in p:
                times = p['times']
                if (not isinstance(times, (list, tuple)) or len(times) != len(values)
                        or not all(finite(t) for t in times)
                        or any(b <= a for a, b in zip(times, times[1:]))):
                    raise ValueError('times must match values and be finite and strictly increasing')
            if 'threshold' in p:
                optional = function.__name__ == 'drift_check'
                if not (optional and p['threshold'] is None and p['direction'] is None):
                    if not finite(p['threshold']) or p['direction'] not in ('below', 'above'):
                        raise ValueError('finite threshold and direction below/above required together')
            if 'z_flag' in p and (not finite(p['z_flag']) or p['z_flag'] <= 0):
                raise ValueError('z_flag must be finite and positive')
            if 'horizon' in p:
                if type(p['horizon']) is not int or p['horizon'] <= 0:
                    raise ValueError('horizon must be a positive integer')
                if not finite(p['tail_at']) or not 0 < p['tail_at'] <= 1:
                    raise ValueError('tail_at must be in (0, 1]')
            result = function(*args, **kwargs)
            json.dumps(result, allow_nan=False)
            return result
        except (ValueError, TypeError, ArithmeticError) as exc:
            return {'error': str(exc), 'inference_status': 'unavailable',
                    'computed_by': function.__name__ + ' (python)'}
    return checked
