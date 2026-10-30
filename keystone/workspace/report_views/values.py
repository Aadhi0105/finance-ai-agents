"""Small source-reading and exact presentation helpers; no execution or I/O."""
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def decimal_text(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite() or abs(number.adjusted()) > 60:
            return None
        result = format(number, 'f')
        return result if len(result) <= 80 else None
    except (InvalidOperation, ValueError):
        return None


def minor_to_major(value):
    """Exact integer cents conversion, independent of Decimal context precision."""
    if type(value) is not int:
        return None
    amount = abs(value)
    text = ('-' if value < 0 else '') + f'{amount // 100}.{amount % 100:02d}'
    return decimal_text(text.rstrip('0').rstrip('.'))


def token(value):
    return str(value).replace('~', '~0').replace('/', '~1')


def resolve(value, pointer):
    if not pointer:
        return value
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        raise ValueError('Invalid source pointer')
    for part in pointer[1:].split('/'):
        if re.search(r'~(?![01])', part):
            raise ValueError('Invalid source pointer')
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', part):
                raise ValueError('Invalid source array index')
            value = value[int(part)]
        else:
            value = value[part]
    return value


def get(value, pointer, default=None):
    try:
        return resolve(value, pointer)
    except (KeyError, IndexError, TypeError, ValueError):
        return default


def currency(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Z]{3}', value) else None


def history_ok(rows):
    """Reject an invalid series rather than deleting points and joining the gap."""
    if not isinstance(rows, list) or not rows or len(rows) > 2000:
        return False
    previous = None
    for row in rows:
        try:
            current = date.fromisoformat(row['date'])
            close = decimal_text(row['close'])
            if (type(row['close']) not in (int, float) or close is None or Decimal(close) <= 0
                    or (previous and current <= previous)):
                return False
            previous = current
        except (KeyError, TypeError, ValueError):
            return False
    return True
