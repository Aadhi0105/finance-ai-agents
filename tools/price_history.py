"""Chart-only policy: retain missing rows; trim an invalid trailing suffix only.

No interpolation or bridging an internal gap. A usable historical window is
not evidence of today's price. All excluded dates remain in the saved payload.
"""
from copy import deepcopy
from datetime import date
from tools.financial_contract import number


def prepare_history(payload):
    result = deepcopy(payload)
    rows = []
    previous = None
    for row in payload.get('history', []):
        current = date.fromisoformat(row['date'])
        if previous is not None and current <= previous:
            raise ValueError('history dates must be unique and increasing')
        previous = current
        rows.append({**row, 'close': number(row.get('close')),
                     'volume': number(row.get('volume'))})
    result['raw_history'] = rows
    result['history_policy'] = 'trim_invalid_trailing_observations_only'
    valid = lambda row: row['close'] is not None and row['close'] > 0
    end = len(rows)
    while end and not valid(rows[end - 1]):
        end -= 1
    result['excluded_observations'] = [dict(row, reason='missing or nonpositive trailing close')
                                       for row in rows[end:]]
    if end < 2 or not all(valid(row) for row in rows[:end]):
        result['history'] = []
        result['error'] = 'insufficient history or invalid interior observation; no gaps bridged'
        return result
    result['history'] = rows[:end]
    result['effective_end_date'] = rows[end - 1]['date']
    if end != len(rows):
        dates = ', '.join(row['date'] for row in rows[end:])
        result.setdefault('warnings', []).append(
            'Chart history ends on ' + rows[end - 1]['date'] +
            '; excluded invalid trailing observations: ' + dates +
            '. No prices were interpolated; latest quote is separate.')
    return result
