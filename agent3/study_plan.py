"""Explicit human-reviewed inputs. A plan is an attestation, not automatic verification."""
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from tools.event_contracts import ticker


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp must be an ISO string with a timezone')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError('timestamp must include a timezone')
    return dt


def review(value, *, source=False):
    if not isinstance(value, dict):
        raise ValueError('review evidence must be an object')
    for k in ['reviewed_by', 'rationale', 'reviewed_at']:
        if not isinstance(value.get(k), str) or not value[k].strip():
            raise ValueError(f'review requires {k}')
    timestamp(value['reviewed_at'])
    if source:
        if not isinstance(value.get('source_url'),str):
            raise ValueError('source_url must be a string')
        u = urlparse(value['source_url'])
        if u.scheme not in ('https', 'http') or not u.netloc:
            raise ValueError('review requires an issuer/source URL')
    return value


def validate_plan(plan, tickers, event_type):
    if plan is None:
        return None
    if not isinstance(plan, dict) or plan.get('schema_version') != 1:
        raise ValueError('study plan requires schema_version=1')
    if plan.get('event_class') != 'earnings':
        raise ValueError('only earnings events are supported')
    companies = plan.get('companies')
    if not isinstance(companies, dict) or set(companies) != set(tickers):
        raise ValueError('plan companies must exactly match the requested target and peers, in uppercase')
    ids = []
    if type(plan.get('schema_version')) is not int:
        raise ValueError('schema_version must be an integer')
    for tk, c in companies.items():
        ticker(tk)
        if not isinstance(c, dict) or not isinstance(c.get('issuer_id'), str) or not c['issuer_id'].strip():
            raise ValueError('company requires a nonempty issuer_id')
        ids.append(c['issuer_id'].strip().casefold())
        if not isinstance(c.get('benchmark'), str) or not c['benchmark'].strip():
            raise ValueError('company requires an explicit benchmark')
        ZoneInfo(c['timezone'])
        review(c.get('benchmark_review'), source=True)
        if c.get('stock_return_basis') not in ('total_return', 'price_return') or c.get('benchmark_return_basis') != c['stock_return_basis']:
            raise ValueError('stock and benchmark return bases must be explicit and compatible')
        reviewed = c.get('reviewed_events', [])
        controls = c.get('reviewed_controls', [])
        if not isinstance(controls, list) or len(controls) > 100:
            raise ValueError('reviewed_controls must be a bounded list')
        if not isinstance(reviewed, list) or len(reviewed) > 100:
            raise ValueError('reviewed_events must be a bounded list')
        for e in reviewed + controls:
            review(e, source=True)
            timestamp(e.get('release_timestamp'))
            if timestamp(e['release_timestamp']) > datetime.now().astimezone():
                raise ValueError('reviewed historical events/controls must already have occurred')
            if e.get('session') not in ('before_open', 'during_session', 'after_close'):
                raise ValueError('confirmed event requires a release session')
    if len(set(ids)) != len(ids):
        raise ValueError('multiple listings of the same issuer cannot be counted as different peers')
    review(plan.get('comparability_review'), source=True)
    review(plan.get('sampling_review'))
    family = plan.get('hypotheses')
    if not isinstance(family, list) or not family or len(family) > 1000 or not all(isinstance(x, str) and x.strip() for x in family) or len(set(family)) != len(family):
        raise ValueError('plan requires unique planned hypothesis IDs (at most 1000)')
    if event_type not in family:
        raise ValueError('event_type must identify a predeclared hypothesis in the plan')
    # JSON object used as immutable-by-convention input; caller saves it with the result.
    return plan
