"""
Track A — LIVE assembly (Agent 3). Fetches real earnings dates + prices from
yfinance and assembles them into event windows for run_event_study.

Kept SEPARATE from track_a.py's pure assembly so the network/fetch code is
isolated from the proven, deterministic slicing math (which this module reuses
via assemble_event). Same discipline as everywhere: I/O at the edge, pure
computation in the core.

Design decisions locked with the user:
  - PEERS: the model proposes the comparable set from a single ticker, the set is
    PINNED into the run record (reproducible after the fact), and a --peers
    override forces a set. The validation gate (assembly step) is the backstop
    against loose sets.
  - EARNINGS-DATE THINNESS: drop-and-report per peer (missing dates / too little
    history), and refuse only if the surviving N falls below the floor.
  - WINDOWS: fixed [-1,+1] event window, [-250,-30] estimation window (from
    track_a); events lacking enough history are skipped-and-reported, never
    handled by shrinking the window.

Because Yahoo is unreachable from the build container, the fetch is written to a
narrow, well-tested seam (_fetch_prices, _fetch_earnings_dates) and the assembly
logic around it is unit-tested offline against yfinance-shaped synthetic data.
The user runs the live fetch on their machine.
"""

from __future__ import annotations

import os

from agent3.track_a import assemble_event, EST_LEN, EST_GAP, EVT_PRE, EVT_POST

_N_FLOOR = 5   # matches the scenario engine's floor: below this, refuse


# Home index per exchange suffix (reused idea from Agent 1's home_index).
_INDEX_BY_SUFFIX = {
    ".PA": "^FCHI", ".DE": "^GDAXI", ".AS": "^AEX", ".MI": "^FTSEMIB.MI",
    ".SW": "^SSMI", ".L": "^FTSE", ".MC": "^IBEX", ".BR": "^BFX",
    ".ST": "^OMX", ".HE": "^OMXH25", ".OL": "^OSEAX", ".T": "^N225",
}
_DEFAULT_INDEX = "^GSPC"   # US / ADR default


def home_index(ticker: str) -> str:
    for suf, idx in _INDEX_BY_SUFFIX.items():
        if ticker.endswith(suf):
            return idx
    return _DEFAULT_INDEX


# --- the narrow fetch seam (the only network-touching functions) ----------

def _fetch_prices(ticker: str, period: str = "6y") -> list[tuple]:
    """Return [(date, close), ...] ascending. Network seam — mocked in tests."""
    import yfinance as yf
    import warnings
    warnings.filterwarnings("ignore")
    h = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    if h is None or len(h) == 0:
        return []
    return [(idx.date(), float(row["Close"])) for idx, row in h.iterrows()]


def _fetch_earnings_dates(ticker: str, limit: int = 24) -> list:
    """Return a list of past earnings dates (datetime.date), newest first.
    Network seam — mocked in tests."""
    import yfinance as yf
    import pandas as pd
    import warnings
    warnings.filterwarnings("ignore")
    ed = yf.Ticker(ticker).get_earnings_dates(limit=limit)
    if ed is None or len(ed) == 0:
        return []
    now = pd.Timestamp.now(tz=ed.index.tz)
    past = ed[ed.index < now]
    return [ts.date() for ts in past.index]


# --- pure assembly around the seam (fully testable offline) ----------------

def _to_date(x):
    """Normalise anything date-like (date, datetime, pandas Timestamp, tz-aware or
    naive) to a plain datetime.date. This is the fix for exchange-suffix names
    (e.g. .PA) whose yfinance timestamps arrive tz-aware and otherwise raise
    'Cannot compare Timestamp with datetime.date', silently dropping every event."""
    import datetime as _dt
    if isinstance(x, _dt.date) and not isinstance(x, _dt.datetime):
        return x                       # already a plain date
    if hasattr(x, "date"):             # pandas Timestamp / datetime -> calendar date
        try:
            return x.date()
        except Exception:
            pass
    return x


def _align_index(dates: list, target, tol_days: int = 4) -> int | None:
    """Index of the trading day on/just before `target`. If `target` falls before
    the series or between gaps, snap to the NEAREST trading day within `tol_days`
    (a public holiday or a tz-shifted timestamp shouldn't discard an event). Dates
    are normalised so tz-aware vs naive never silently fails."""
    if not dates:
        return None
    target = _to_date(target)
    ds = [_to_date(d) for d in dates]

    lo, hi, ans = 0, len(ds) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if ds[mid] <= target:
            ans = mid
            lo = mid + 1
        else:
            hi = mid - 1

    if ans is not None:
        # §3: honour tol_days. The nearest trading day at/before the target must be
        # within tolerance — otherwise a long gap (missing data around the event)
        # would silently anchor the event to a far-away stale observation.
        gap = (target - ds[ans]).days
        if gap <= tol_days:
            return ans
        # too far before; if the NEXT trading day is within tolerance, snap forward
        if ans + 1 < len(ds) and (ds[ans + 1] - target).days <= tol_days:
            return ans + 1
        return None
    # target is before the whole series: snap forward if the first date is within tol
    first_gap = (ds[0] - target).days
    if 0 <= first_gap <= tol_days:
        return 0
    return None


def assemble_peer_events(ticker: str, stock_px: list[tuple], mkt_px: list[tuple],
                         earnings_dates: list, max_events: int = 12) -> tuple[list, list, dict]:
    """
    Turn one peer's raw (date, close) series + earnings dates into event dicts,
    PLUS deterministic placebo (pseudo-event) dicts. Returns (events, placebos,
    report). Pure, no network — unit-tested offline.

    §2 fix: stock and market are intersected onto a COMMON trading calendar first,
    so a single event index refers to the SAME date in both series. Previously the
    stock index was used to slice both arrays, silently misaligning returns by a
    day whenever the two calendars differed.
    """
    report = {"ticker": ticker, "earnings_dates": len(earnings_dates),
              "assembled": 0, "skipped_short_history": 0, "skipped_align": 0,
              "placebos": 0}
    if not stock_px or not mkt_px or not earnings_dates:
        report["reason"] = "missing prices or earnings dates"
        return [], [], report

    # --- §2: build a date-aligned panel on the intersection of trading dates ---
    mkt_by_date = {_to_date(d): c for d, c in mkt_px}
    dates, s_close, m_close = [], [], []
    for d, c in stock_px:
        dd = _to_date(d)
        if dd in mkt_by_date:
            dates.append(dd)
            s_close.append(c)
            m_close.append(mkt_by_date[dd])
    if len(dates) < EST_LEN + EST_GAP + 5:
        report["reason"] = "insufficient overlapping stock/market history"
        report["price_span"] = (f"{dates[0]}..{dates[-1]} ({len(dates)} common bars)"
                                if dates else "no overlap")
        return [], [], report

    report["price_span"] = f"{dates[0]}..{dates[-1]} ({len(dates)} common bars)"
    ed_norm = sorted({_to_date(e) for e in earnings_dates}, reverse=True)
    if ed_norm:
        report["earnings_span"] = f"{ed_norm[-1]}..{ed_norm[0]}"

    # STALE-DATA GUARD: some names return earnings dates that predate their price
    # history entirely (observed on certain Euronext .PA tickers). Report an
    # explicit labeled exclusion rather than an opaque skipped_align.
    px_start = dates[0]
    if ed_norm and ed_norm[0] < px_start:
        report["excluded"] = True
        report["reason"] = (f"stale earnings data: all {len(ed_norm)} dates "
                            f"({ed_norm[-1]}..{ed_norm[0]}) predate price history "
                            f"(from {px_start}) — source unusable for this name")
        return [], [], report

    need_before = EST_GAP + EST_LEN

    def _try_build(event_date):
        """Build one event dict at event_date on the common calendar, or None."""
        i = _align_index(dates, event_date)
        if i is None:
            return None, "align"
        if i - need_before < 1 or i + EVT_POST >= len(s_close):
            return None, "short_history"
        ev = assemble_event(ticker, str(event_date), s_close, m_close, i)
        return (ev, None) if ev is not None else (None, "short_history")

    events = []
    used_idx = []
    for ed in ed_norm[:max_events]:
        ev, why = _try_build(ed)
        if ev is None:
            report["skipped_align" if why == "align" else "skipped_short_history"] += 1
            continue
        events.append(ev)
        used_idx.append(_align_index(dates, ed))
        report["assembled"] += 1

    # --- §12: deterministic PLACEBO pseudo-events ---
    # For each real event, pick a pseudo-event date >= 30 days from ANY real
    # earnings date (and with enough history), by stepping back through the
    # calendar. Same estimator runs on these; a clean study finds nothing here.
    placebos = _build_placebos(ticker, dates, s_close, m_close, ed_norm,
                               need_before, len(events))
    report["placebos"] = len(placebos)
    return events, placebos, report


def _build_placebos(ticker, dates, s_close, m_close, ed_norm, need_before, want):
    """Deterministic pseudo-events: dates far from any real earnings date, with
    enough history, sampled evenly across the usable window."""
    import datetime as _dt
    ed_set = list(ed_norm)

    def _far_from_earnings(d):
        return all(abs((d - e).days) >= 30 for e in ed_set)

    lo = need_before + 1
    hi = len(dates) - EVT_POST - 1
    if hi <= lo or want == 0:
        return []
    placebos = []
    # step evenly through the usable index range, keep dates far from earnings
    step = max(1, (hi - lo) // (want + 1))
    i = lo
    while i <= hi and len(placebos) < want:
        d = dates[i]
        if _far_from_earnings(d):
            ev = assemble_event(ticker, f"{d}~placebo", s_close, m_close, i)
            if ev is not None:
                placebos.append(ev)
        i += step
    return placebos


def load_live_event_set(ticker: str, peers: list[str], event_type: str) -> dict:
    """
    Assemble a cross-ticker live event set from a PINNED peer list. `peers` is the
    model-proposed-and-pinned set (or a --peers override); this function does not
    choose peers — it consumes the pinned decision.

    Drop-and-report per peer; refuse only if surviving N < floor.
    """
    all_peers = [ticker] + [p for p in peers if p != ticker]
    events, placebo_events, reports = [], [], []

    for pk in all_peers:
        try:
            px = _fetch_prices(pk)
            idx_px = _fetch_prices(home_index(pk))
            eds = _fetch_earnings_dates(pk)
        except Exception as e:
            reports.append({"ticker": pk, "error": f"{type(e).__name__}: {e}"})
            continue
        evs, placebos, rep = assemble_peer_events(pk, px, idx_px, eds)
        reports.append(rep)
        events.extend(evs)
        placebo_events.extend(placebos)

    n = len(events)
    excluded = [r["ticker"] for r in reports if r.get("excluded")]
    errored = [r["ticker"] for r in reports if r.get("error")]
    contributing = [r["ticker"] for r in reports if r.get("assembled", 0) > 0]
    result = {
        "event_type": event_type, "source": "yfinance",
        "pinned_peers": all_peers,          # reproducibility: the exact set used
        "contributing_peers": contributing, # names that actually supplied events
        "excluded_peers": excluded,         # names dropped for stale/unusable data
        "errored_peers": errored,
        "events": events, "placebo_events": placebo_events,
        "n_events": n, "per_peer_report": reports,
    }
    if n < _N_FLOOR:
        result["verdict"] = "REFUSED"
        result["reason"] = (f"only {n} usable events across the pinned peer set "
                            f"(floor {_N_FLOOR}); too thin for a credible study")
    else:
        result["verdict"] = "OK"
    return result
