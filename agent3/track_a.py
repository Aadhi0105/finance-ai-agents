"""
Track A — structured-event assembly (Agent 3, local, fixture-first).

The pure event-study tool (tools/event_study.run_event_study, on the MCP server)
consumes clean return windows. SOMETHING has to build those from raw prices; this
is that something, and it is deliberately LOCAL — it fetches and slices, it does
not compute the study. Keeping I/O out of the served tool is what makes the tool
provably identical local-vs-MCP (the same reason Agent 1's analytical tools never
fetched their own data).

For each (ticker, event_date) it:
  1. takes the ticker's and its market index's price series,
  2. converts prices to simple returns,
  3. locates the event date in the index,
  4. slices the estimation window [-est_len-gap, -gap) and the event window
     [-pre, +post] around it,
  5. returns the dict shape run_event_study expects.

Fixture-first: offline it reads bars from a fixture; live (later) will pull from
yfinance. Track A is the RIGOR track — events are scheduled and precisely dated,
so the "when did it happen" question that wrecks event studies is answered
exactly. Cross-ticker, same-event-type sets are assembled here to give CAAR its N.
"""

from __future__ import annotations

import json
import os

_FIXTURE = os.path.join("fixtures", "events.json")

# Window conventions (spec §Agent 3 deep-dive 2).
EST_LEN = 250        # estimation window length (trading days)
EST_GAP = 30         # gap between estimation window and the event (no leakage)
EVT_PRE, EVT_POST = 1, 1   # event window [-1, +1]


def _returns(prices: list[float]) -> list[float]:
    return [prices[i] / prices[i - 1] - 1.0 for i in range(1, len(prices))]


def _slice_event(stock_px: list[float], mkt_px: list[float], event_idx: int,
                 est_len=EST_LEN, est_gap=EST_GAP, pre=EVT_PRE, post=EVT_POST):
    """Slice estimation + event window returns around a price-series index.
    Returns (est_stock, est_market, evt_stock, evt_market) or None if the series
    can't cover the requested windows."""
    # Estimation window ENDS est_gap days before the event; event window brackets it.
    est_start = event_idx - est_gap - est_len
    est_end = event_idx - est_gap                # exclusive
    evt_start = event_idx - pre
    evt_end = event_idx + post + 1               # exclusive
    if est_start < 1 or evt_end > len(stock_px):
        return None  # not enough history/future around the event

    def rets(px, a, b):
        # returns need one extra leading price to compute the first return
        return _returns(px[a - 1:b])

    return (rets(stock_px, est_start, est_end),
            rets(mkt_px, est_start, est_end),
            rets(stock_px, evt_start, evt_end),
            rets(mkt_px, evt_start, evt_end))


def assemble_event(ticker: str, event_date: str,
                   stock_px: list[float], mkt_px: list[float],
                   event_idx: int) -> dict | None:
    """Build one event dict for run_event_study from aligned price series."""
    sliced = _slice_event(stock_px, mkt_px, event_idx)
    if sliced is None:
        return None
    est_s, est_m, evt_s, evt_m = sliced
    return {"ticker": ticker, "event_date": event_date,
            "est_stock": est_s, "est_market": est_m,
            "evt_stock": evt_s, "evt_market": evt_m}


def load_event_set(event_type: str, source: str | None = None) -> dict:
    """
    Assemble a cross-ticker, same-event-type set (and its placebo) ready for
    run_event_study. Offline reads fixtures/events.json; live (later) pulls prices
    via yfinance. Returns {event_type, events, placebo_events, tickers, n_requested}.
    """
    src = source or os.environ.get("AGENT_DATA_SOURCE", "fixture")
    if src == "yfinance":
        return _load_live(event_type)   # implemented in a later checkpoint
    return _load_fixture(event_type)


def _load_fixture(event_type: str) -> dict:
    with open(_FIXTURE) as f:
        fx = json.load(f)
    grp = fx["event_types"].get(event_type)
    if grp is None:
        return {"event_type": event_type, "events": [], "placebo_events": [],
                "error": f"no fixture for event_type '{event_type}'"}

    events, placebos, tickers = [], [], []
    for item in grp["members"]:
        tk = item["ticker"]
        tickers.append(tk)
        ev = assemble_event(tk, item["event_date"], item["stock_px"],
                            item["market_px"], item["event_idx"])
        if ev is not None:
            events.append(ev)
        # placebo: same series, a non-event index well away from the real event
        if "placebo_idx" in item:
            pe = assemble_event(tk, f"{item['event_date']}~placebo",
                                item["stock_px"], item["market_px"], item["placebo_idx"])
            if pe is not None:
                placebos.append(pe)

    return {"event_type": event_type, "source": "fixture",
            "events": events, "placebo_events": placebos,
            "tickers": tickers, "n_requested": len(grp["members"])}


def _load_live(event_type: str) -> dict:
    # Wired in a later checkpoint: yfinance prices + earnings dates per ticker.
    return {"event_type": event_type, "source": "yfinance",
            "events": [], "placebo_events": [],
            "error": "live Track-A assembly not yet wired (fixture-first)"}
