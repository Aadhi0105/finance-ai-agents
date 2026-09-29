"""Shared local/MCP event input contract; fixed daily market-model design."""
from datetime import date
import math
import re
import json
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EST_LEN, EST_GAP, EVT_PRE, EVT_POST = 250, 30, 1, 1
MAX_EVENTS = 1000


def finite(v):
    try:
        return type(v) in (int, float) and math.isfinite(v)
    except OverflowError:
        return False


def ticker(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9.^=-]{0,31}', value.strip().upper()):
        raise ValueError('invalid ticker')
    return value.strip().upper()


def iso_date(value):
    if not isinstance(value, str):
        raise ValueError('date must be an ISO date string')
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError('date must use YYYY-MM-DD')
    return parsed


def validate_event(event):
    if not isinstance(event, dict):
        raise ValueError('event must be an object')
    try:
        json.dumps(event, allow_nan=False)
    except (ValueError, TypeError, OverflowError):
        raise ValueError('event must contain JSON-safe finite values') from None
    e = dict(event)
    e['ticker'] = ticker(e.get('ticker'))
    if 'issuer_id' in e and (not isinstance(e['issuer_id'],str) or not e['issuer_id'].strip()):
        raise ValueError('issuer_id must be a nonempty string')
    # Legacy fixture control labels remain readable but do not establish dated evidence.
    raw_date = e.get('event_date')
    iso_date(raw_date.removesuffix('~placebo') if isinstance(raw_date, str) else raw_date)
    for k, size in [('est_stock', EST_LEN), ('est_market', EST_LEN), ('evt_stock', 3), ('evt_market', 3)]:
        vals = e.get(k)
        if not isinstance(vals, list) or len(vals) != size:
            raise ValueError(f'{k} must contain exactly {size} returns')
        if not all(finite(v) and -1 < v <= 100 for v in vals):
            raise ValueError(f'{k} requires finite simple returns in (-1, 100], excluding booleans')
    for k, size in [('est_dates', EST_LEN), ('window_dates', 3)]:
        if k in e:
            ds = e[k]
            if not isinstance(ds, list) or len(ds) != size:
                raise ValueError(f'{k} has wrong length')
            parsed = [iso_date(d) for d in ds]
            if parsed != sorted(set(parsed)):
                raise ValueError(f'{k} must be strictly increasing')
    if 'est_dates' in e and 'window_dates' in e:
        if e['est_dates'][-1] >= e['window_dates'][0]:
            raise ValueError('estimation/event windows overlap')
    if 'anchor_date' in e:
        iso_date(e['anchor_date'])
        if e.get('window_dates') and e['anchor_date'] != e['window_dates'][1]:
            raise ValueError('anchor does not match event window')
    return e


def review_complete(value, *, source=False):
    if not isinstance(value, dict):
        return False
    if not all(isinstance(value.get(k), str) and value[k].strip() for k in ('reviewed_by','reviewed_at','rationale')):
        return False
    try:
        dt = datetime.fromisoformat(value['reviewed_at'].replace('Z','+00:00'))
        if dt.tzinfo is None: return False
    except ValueError:
        return False
    if source:
        if not isinstance(value.get('source_url'),str): return False
        u = urlparse(value['source_url'])
        if u.scheme not in ('http','https') or not u.netloc: return False
    return True


def release_provenance_complete(event):
    try:
        dt = datetime.fromisoformat(event['release_timestamp'].replace('Z','+00:00'))
        if dt.tzinfo is None or event.get('session') not in ('before_open','during_session','after_close'):
            return False
        local = dt.astimezone(ZoneInfo(event['exchange_timezone'])).date()
        release = iso_date(event['event_date'].removesuffix('~placebo'))
        anchor = iso_date(event['anchor_date'])
        if local != release or not 0 <= (anchor-release).days <= 4:
            return False
        return event['session'] != 'after_close' or anchor > release
    except (KeyError, TypeError, ValueError, AttributeError, ZoneInfoNotFoundError):
        return False
