"""Live daily earnings assembly. Provider dates are unverified evidence.

Confirmed dates may be supplied in a sourced, human-reviewed study plan. No
provider date is silently promoted to issuer-confirmed status. Windows contain
250 estimation returns [-280,-31] and three event returns [-1,+1].
"""
from __future__ import annotations
from bisect import bisect_left
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from agent3.track_a import assemble_event
from agent3.study_plan import validate_plan, timestamp
from tools.event_contracts import EST_LEN, EST_GAP, EVT_POST, finite, ticker as normalize

_INDEX_BY_SUFFIX = {
    '.PA': ('^FCHI', 'Europe/Paris'), '.DE': ('^GDAXI', 'Europe/Berlin'),
    '.AS': ('^AEX', 'Europe/Amsterdam'), '.MI': ('^FTSEMIB.MI', 'Europe/Rome'),
    '.SW': ('^SSMI', 'Europe/Zurich'), '.L': ('^FTSE', 'Europe/London'),
    '.MC': ('^IBEX', 'Europe/Madrid'), '.BR': ('^BFX', 'Europe/Brussels'),
    '.ST': ('^OMX', 'Europe/Stockholm'), '.HE': ('^OMXH25', 'Europe/Helsinki'),
    '.OL': ('^OSEAX', 'Europe/Oslo'), '.T': ('^N225', 'Asia/Tokyo'),
}


def listing(ticker):
    tk = normalize(ticker)
    for suffix, value in _INDEX_BY_SUFFIX.items():
        if tk.endswith(suffix):
            return value
    if '.' not in tk:
        return '^GSPC', 'America/New_York'
    raise ValueError('unsupported listing: supply an explicit benchmark and timezone in a study plan')


def home_index(ticker):
    return listing(ticker)[0]


def _fetch_prices(ticker, period='6y', *, return_basis='total_return'):
    import yfinance as yf
    h = yf.Ticker(ticker).history(period=period, auto_adjust=return_basis == 'total_return')
    if h is None or h.empty:
        return []
    local_today = datetime.now(h.index.tz or timezone.utc).date()
    # Exclude the current day's potentially unfinished daily candle.
    return [(idx.date(), float(row['Close'])) for idx, row in h.iterrows() if idx.date() < local_today]


def _fetch_earnings_dates(ticker, limit=24):
    """Keep timezone and original provider timestamp. Confirm nothing here."""
    import yfinance as yf
    ed = yf.Ticker(ticker).get_earnings_dates(limit=limit)
    if ed is None or ed.empty:
        return []
    now = datetime.now(timezone.utc)
    records = []
    for ts in ed.index:
        # Naive timestamps remain unusable rather than acquiring a guessed timezone.
        try:
            dt = timestamp(ts.isoformat())
        except ValueError:
            continue
        if dt < now:
            records.append({'release_timestamp': dt.isoformat(), 'session': 'unknown',
                            'date_status': 'unverified', 'source': 'yfinance.earnings_dates',
                            'retrieved_at': now.isoformat()})
    return records


def _to_date(x):
    return x.date() if isinstance(x, datetime) else x


def _align_index(dates, target, tol_days=4):
    """First observed session on/after date. Never move a release backward."""
    target = _to_date(target)
    i = bisect_left(dates, target)
    if i < len(dates) and 0 <= (dates[i] - target).days <= tol_days:
        return i
    return None


def _prices(rows, name):
    if not isinstance(rows, list):
        raise ValueError(f'{name}: expected a price list')
    out = []
    for d, px in rows:
        d = _to_date(d)
        if type(d) is not date or not finite(px) or px <= 0:
            raise ValueError(f'{name}: invalid date or nonpositive/nonfinite price')
        out.append((d, px))
    if [d for d, _ in out] != sorted({d for d, _ in out}):
        raise ValueError(f'{name}: price dates must be unique and ascending')
    return out


def _event_record(value, tz):
    if isinstance(value, dict):
        dt = timestamp(value.get('release_timestamp'))
        return {**value, 'release_date': dt.astimezone(ZoneInfo(tz)).date(),
                'provider_timestamp': value.get('provider_timestamp', dt.isoformat() if value.get('date_status') != 'reviewed' else None)}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError('naive earnings timestamps are not accepted')
        return _event_record({'release_timestamp': value.isoformat(), 'session': 'unknown'}, tz)
    if type(value) is date:  # offline seam; no source/session attestation
        return {'release_date': value, 'session': 'unknown', 'date_status': 'unverified'}
    raise ValueError('invalid earnings record')


def assemble_peer_events(ticker, stock_px, mkt_px, earnings_dates, max_events=12,
                         *, exchange_timezone=None, benchmark=None, company=None, plan=None):
    tk = normalize(ticker)
    if type(max_events) is not int or not 1 <= max_events <= 100:
        raise ValueError('max_events must be an integer between 1 and 100')
    default_benchmark, default_tz = listing(tk) if exchange_timezone is None or benchmark is None else (benchmark, exchange_timezone)
    tz, bench = exchange_timezone or default_tz, benchmark or default_benchmark
    company = company or {}
    stock, market = _prices(stock_px, 'stock'), _prices(mkt_px, 'benchmark')
    report = {'ticker': tk, 'earnings_dates': len(earnings_dates), 'assembled': 0,
              'skipped_short_history': 0, 'skipped_align': 0, 'placebos': 0, 'rejected_events': [],
              'benchmark': bench, 'timezone': tz}
    if not stock or not market or not earnings_dates:
        return [], [], {**report, 'excluded': True, 'reason': 'missing prices or earnings dates'}
    m = dict(market); stock_days = {d for d, _ in stock}
    dates = [d for d, _ in stock if d in m]
    if len(dates) < EST_LEN + EST_GAP + 5:
        return [], [], {**report, 'excluded': True, 'reason': 'insufficient overlapping history'}
    s = dict(stock); s_close, m_close = [s[d] for d in dates], [m[d] for d in dates]
    report['price_span'] = f'{dates[0]}..{dates[-1]} ({len(dates)} common bars)'
    records = []
    for value in earnings_dates:
        try:
            records.append(_event_record(value, tz))
        except (ValueError, TypeError) as exc:
            report['rejected_events'].append({'reason': str(exc)})
    records.sort(key=lambda e: e['release_date'], reverse=True)
    if records and records[0]['release_date'] < dates[0]:
        return [], [], {**report, 'excluded': True, 'reason': 'all earnings dates predate price history'}
    if records:
        report['earnings_span'] = f"{records[-1]['release_date']}..{records[0]['release_date']}"
    # Detect asymmetric missing bars, plus unexpected multi-weekday gaps. Holidays
    # can trigger a flag; a flag is conservative uncertainty, not fabricated returns.
    def build(record, *, control=False):
        rd = record['release_date']
        target = rd + timedelta(days=1) if record.get('session') == 'after_close' else rd
        i = _align_index(dates, target)
        if i is None:
            raise ValueError('align')
        if i - 280 < 1 or i + 1 >= len(dates):
            raise ValueError('short_history')
        a, b = i - 280, i - 30
        ev = assemble_event(tk, str(rd) + ('~placebo' if control else ''), s_close, m_close, i)
        sample_dates = dates[a-1:b] + dates[i-2:i+2]
        lo, hi = sample_dates[0], sample_dates[-1]
        missing = any(lo <= d <= hi and d not in stock_days for d in m) or any(lo <= d <= hi and d not in m for d in stock_days)
        gaps = any(sum((x + timedelta(days=j)).weekday() < 5 for j in range(1, (y-x).days)) > 0
                   for group in (dates[a-1:b], dates[i-2:i+2]) for x, y in zip(group, group[1:]))
        flags = ['calendar_gap_or_missing_bar'] if missing or gaps else []
        reviewed = record.get('date_status') == 'reviewed' and record.get('session') != 'unknown'
        evidence = {'date': {k: record[k] for k in ('reviewed_by','reviewed_at','rationale','source_url') if k in record},
                    'benchmark': company.get('benchmark_review', {}),
                    'design': plan.get('sampling_review', {}) if plan else {}}
        ev.update(issuer_id=company.get('issuer_id', tk), anchor_date=str(dates[i]),
                  window_dates=[str(d) for d in dates[i-1:i+2]], est_dates=[str(d) for d in dates[a:b]],
                  release_timestamp=record.get('release_timestamp'), provider_timestamp=record.get('provider_timestamp'),
                  source=record.get('source', 'reviewed_study_plan' if reviewed else 'provider'),
                  retrieved_at=record.get('retrieved_at'), exchange_timezone=tz, session=record.get('session','unknown'),
                  date_status='reviewed' if reviewed else 'unverified', benchmark=bench,
                  stock_return_basis=company.get('stock_return_basis','total_return'),
                  benchmark_return_basis=company.get('benchmark_return_basis','unverified'),
                  benchmark_status='reviewed' if company else 'unverified',
                  design_status='reviewed' if plan else 'unverified', review_evidence=evidence,
                  quality_flags=flags, window_spec={'estimation':[-280,-31], 'event':[-1,1]})
        return ev, i
    events, used = [], set()
    for record in records:
        if len(events) >= max_events:
            break
        try:
            ev, i = build(record)
            if any(abs(i - old) <= 2 for old in used):
                raise ValueError('duplicate or overlapping event anchor')
            used.add(i); events.append(ev)
        except ValueError as exc:
            reason = str(exc)
            if reason in ('align','short_history'):
                report['skipped_align' if reason == 'align' else 'skipped_short_history'] += 1
            report['rejected_events'].append({'release_date': str(record['release_date']), 'reason': reason})
    placebos = []
    controls = company.get('reviewed_controls', [])
    if controls:
        for value in controls:
            try:
                rec = _event_record({**value, 'date_status':'reviewed'}, tz)
                if any(abs((rec['release_date']-e['release_date']).days)<30 for e in records):
                    raise ValueError('reviewed control is within 30 calendar days of a supplied earnings date')
                pe, _ = build(rec, control=True)
                placebos.append(pe)
            except (ValueError,TypeError) as exc:
                report['rejected_events'].append({'control':True, 'reason':str(exc)})
    else:
        step = max(3, (len(dates)-283)//(len(events)+1))
        for i in range(281, len(dates)-1, step):
            if len(placebos) >= len(events): break
            if any(abs((dates[i] - e['release_date']).days) < 30 for e in records): continue
            pe, _ = build({'release_date': dates[i], 'session':'unknown'}, control=True)
            # Generated controls do not establish that no other event occurred.
            placebos.append(pe)
    report.update(assembled=len(events), placebos=len(placebos),
                  selection_policy=f'latest {max_events} usable, nonoverlapping events',
                  not_selected=max(0,len(records)-len(events)-sum('release_date' in r for r in report['rejected_events'])))
    if not events: report.update(excluded=True, reason='no usable event windows')
    return events, placebos, report


def load_live_event_set(ticker, peers, event_type, *, study_plan=None):
    tk = normalize(ticker)
    if not isinstance(peers, list) or len(peers) > 20:
        raise ValueError('peers must be a list of at most 20 tickers')
    all_peers = list(dict.fromkeys([tk] + [normalize(p) for p in peers]))
    plan = validate_plan(study_plan, all_peers, event_type)
    events, placebos, reports = [], [], []
    for pk in all_peers:
        try:
            c = plan['companies'][pk] if plan else {}
            bench, tz = (c['benchmark'], c['timezone']) if c else listing(pk)
            px = _fetch_prices(pk, return_basis=c.get('stock_return_basis','total_return'))
            ix = _fetch_prices(bench, return_basis=c.get('benchmark_return_basis','price_return'))
            if c.get('reviewed_events'):
                eds = [{**e, 'date_status':'reviewed'} for e in c['reviewed_events']]
            else:
                eds = _fetch_earnings_dates(pk)
            ev, pe, rep = assemble_peer_events(pk, px, ix, eds, exchange_timezone=tz,
                                               benchmark=bench, company=c, plan=plan)
            events.extend(ev); placebos.extend(pe); reports.append(rep)
        except Exception as exc:
            reports.append({'ticker':pk, 'excluded':True, 'error':f'{type(exc).__name__}: {exc}'})
    contributing = [r['ticker'] for r in reports if r.get('assembled',0)]
    result = {'event_type':event_type, 'event_class':'earnings', 'source':'yfinance',
              'target':tk, 'target_contributed':tk in contributing, 'pinned_peers':all_peers,
              'contributing_peers':contributing, 'excluded_peers':[r['ticker'] for r in reports if r.get('excluded')],
              'per_peer_report':reports, 'events':events, 'placebo_events':placebos,
              'study_plan':plan, 'comparability_status':'human_reviewed' if plan else 'unverified',
              'retrieved_at':datetime.now(timezone.utc).isoformat(), 'n_events':len(events),
              'verdict':'OK' if len(events) >= 5 else 'REFUSED'}
    if result['verdict'] == 'REFUSED': result['reason'] = 'fewer than five usable historical events'
    return result
