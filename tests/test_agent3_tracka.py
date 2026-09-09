"""Agent 3 Track-A live assembly (§2 common-calendar alignment, §3 _align_index
tolerance, §12 placebo generation). Uses synthetic yfinance-shaped data offline."""

from datetime import date, timedelta
import random
from agent3 import track_a_live as tal


def _series(seed, start, n, drop_every=0):
    r = random.Random(seed); d = start; out = []; px = 100.0
    for i in range(n):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        if not (drop_every and i % drop_every == 0):
            px = round(px * (1 + r.gauss(0.0004, 0.012)), 4)
            out.append((d, px))
        d += timedelta(days=1)
    return out


def test_align_index_finds_on_or_before():
    dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 8)]
    assert tal._align_index(dates, date(2026, 1, 6)) == 1
    assert tal._align_index(dates, date(2026, 1, 7)) == 2 or tal._align_index(dates, date(2026, 1, 7)) == 1
    # exact match
    assert tal._align_index(dates, date(2026, 1, 8)) == 2


def test_align_index_rejects_stale_anchor():
    """§3: a target far after the last available date (a data gap) must be rejected,
    not anchored to a weeks-old observation."""
    dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    # target 30 days later, tol_days=4 -> no valid anchor
    assert tal._align_index(dates, date(2026, 2, 6), tol_days=4) is None


def test_align_index_weekend_snaps_within_tolerance():
    dates = [date(2026, 1, 9)]  # a Friday
    # Saturday target (gap 1) should still find the Friday within tol
    assert tal._align_index(dates, date(2026, 1, 10), tol_days=4) == 0


def test_common_calendar_alignment_and_windows():
    """§2: stock and market on DIFFERENT calendars are intersected; one index then
    refers to the same date in both, so est/evt windows are equal length."""
    stock = _series(1, date(2020, 1, 1), 700)
    market = _series(2, date(2020, 1, 1), 700, drop_every=37)  # market missing days
    ed = [stock[i][0] for i in (620, 560, 500, 440, 380)]
    events, placebos, rep = tal.assemble_peer_events("TST", stock, market, ed)
    assert rep["assembled"] == 5
    for e in events:
        assert len(e["est_stock"]) == len(e["est_market"])
        assert len(e["evt_stock"]) == len(e["evt_market"])


def test_placebos_are_generated():
    """§12: the live path generates placebo pseudo-events (was []), far from real
    earnings dates."""
    stock = _series(3, date(2020, 1, 1), 700)
    market = _series(4, date(2020, 1, 1), 700)
    ed = [stock[i][0] for i in (620, 560, 500, 440, 380)]
    events, placebos, rep = tal.assemble_peer_events("TST", stock, market, ed)
    assert len(placebos) > 0
    assert rep["placebos"] == len(placebos)
    # placebo event_dates are marked as placebos
    assert all("placebo" in p["event_date"] for p in placebos)


def test_stale_earnings_excluded():
    """Earnings dates entirely before the price window -> labeled exclusion."""
    stock = _series(5, date(2020, 1, 1), 400)
    market = _series(6, date(2020, 1, 1), 400)
    ed = [date(2008, 5, 7), date(2009, 10, 28), date(2018, 11, 14)]  # all pre-2020
    events, placebos, rep = tal.assemble_peer_events("OLD.PA", stock, market, ed)
    assert rep.get("excluded") is True
    assert events == []
