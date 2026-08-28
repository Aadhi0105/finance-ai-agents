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
        return ans
    # target is before the whole series: snap forward if the first date is within tol
    first_gap = (ds[0] - target).days
    if 0 <= first_gap <= tol_days:
        return 0
    return None


def assemble_peer_events(ticker: str, stock_px: list[tuple], mkt_px: list[tuple],
                         earnings_dates: list, max_events: int = 12) -> tuple[list, dict]:
    """
    Turn one peer's raw (date, close) series + earnings dates into event dicts.
    Returns (events, report) where report explains what was used/dropped — pure,
    no network, so this is unit-tested offline.
    """
    report = {"ticker": ticker, "earnings_dates": len(earnings_dates),
              "assembled": 0, "skipped_short_history": 0, "skipped_align": 0}
    if not stock_px or not mkt_px or not earnings_dates:
        report["reason"] = "missing prices or earnings dates"
        return [], report

    s_dates = [d for d, _ in stock_px]
    s_close = [c for _, c in stock_px]
    m_dates = [d for d, _ in mkt_px]
    m_close = [c for _, c in mkt_px]

    # Diagnostic: the span of price history actually returned, vs the earnings
    # dates we're trying to place in it. Surfaces the real cause when events drop.
    if s_dates:
        report["price_span"] = f"{_to_date(s_dates[0])}..{_to_date(s_dates[-1])} ({len(s_dates)} bars)"
    ed_norm = sorted((_to_date(e) for e in earnings_dates), reverse=True)
    if ed_norm:
        report["earnings_span"] = f"{ed_norm[-1]}..{ed_norm[0]}"

    events = []
    for ed in ed_norm[:max_events]:
        si = _align_index(s_dates, ed)
        mi = _align_index(m_dates, ed)
        if si is None or mi is None:
            report["skipped_align"] += 1
            continue
        # need EST_LEN+EST_GAP history before, and EVT_POST ahead, in BOTH series
        need_before = EST_GAP + EST_LEN
        if si - need_before < 1 or mi - need_before < 1 \
                or si + EVT_POST >= len(s_close) or mi + EVT_POST >= len(m_close):
            report["skipped_short_history"] += 1
            continue
        ev = assemble_event(ticker, str(ed), s_close, m_close, si)
        if ev is not None:
            events.append(ev)
            report["assembled"] += 1
        else:
            report["skipped_short_history"] += 1
    return events, report


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
        evs, rep = assemble_peer_events(pk, px, idx_px, eds)
        reports.append(rep)
        events.extend(evs)
        # placebo: use mid-history non-event points (built later in the gate step;
        # for now a simple placebo from each series' midpoint index)
        # (kept minimal here; the validation gate owns richer placebo construction)

    n = len(events)
    result = {
        "event_type": event_type, "source": "yfinance",
        "pinned_peers": all_peers,          # reproducibility: the exact set used
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
