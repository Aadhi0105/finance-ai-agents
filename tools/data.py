"""
Data tools — the fetcher family (spec §3.1).

Two fetchers now: `get_financials` and `get_prices`.

Source strategy (unchanged switch):
- AGENT_DATA_SOURCE=fixture (default): read fixtures/<TICKER>.json. Each fixture
  holds BOTH a "financials" block and a "prices" block, so one file feeds both
  tools. This is what keeps the loop provable offline.
- AGENT_DATA_SOURCE=yfinance: pull live on your Mac.

Both tools return the same shape regardless of source, so nothing downstream
cares which produced it. yfinance is imported lazily.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _source() -> str:
    return os.environ.get("AGENT_DATA_SOURCE", "fixture").lower()


def _load_fixture(ticker: str):
    path = _FIXTURE_DIR / f"{ticker}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


# --- get_financials -------------------------------------------------------

def get_financials(tool_input: dict, state=None) -> dict:
    ticker = tool_input["ticker"].upper()
    if _source() == "yfinance":
        return _financials_yfinance(ticker)
    fx = _load_fixture(ticker)
    if fx is None or "financials" not in fx:
        return {"error": f"no financials fixture for {ticker}", "ticker": ticker}
    return {"ticker": ticker, "source": "fixture", "financials": fx["financials"]}


def _financials_yfinance(ticker: str) -> dict:
    import yfinance as yf
    tk = yf.Ticker(ticker)
    fin = tk.financials
    if fin is None or fin.empty:
        return {"error": f"yfinance returned no financials for {ticker}", "ticker": ticker}
    latest = fin.columns[0]

    def _get(label):
        try:
            return float(fin.loc[label, latest])
        except Exception:
            return None

    financials = {
        "period": str(latest.date()) if hasattr(latest, "date") else str(latest),
        "revenue": _get("Total Revenue"),
        "gross_profit": _get("Gross Profit"),
        "operating_income": _get("Operating Income"),
        "net_income": _get("Net Income"),
    }
    if len(fin.columns) > 1:
        prev = fin.columns[1]
        try:
            financials["revenue_prior"] = float(fin.loc["Total Revenue", prev])
        except Exception:
            financials["revenue_prior"] = None

    # --- DCF v2 inputs: free cash flow (cash-flow statement) + net-debt items ---
    # yfinance row labels drift across versions/filers, so each lookup tries a
    # few known labels and returns None if absent (DCF v2 then falls back and logs it).
    def _row(df, *labels):
        if df is None or getattr(df, "empty", True):
            return None
        col = df.columns[0]
        for lab in labels:
            try:
                v = df.loc[lab, col]
                if v is not None:
                    return float(v)
            except Exception:
                continue
        return None

    try:
        cf = tk.cashflow
    except Exception:
        cf = None
    try:
        bs = tk.balance_sheet
    except Exception:
        bs = None

    fcf = _row(cf, "Free Cash Flow")
    if fcf is None:  # derive from OCF - capex if the explicit FCF row is missing
        ocf = _row(cf, "Operating Cash Flow", "Total Cash From Operating Activities")
        capex = _row(cf, "Capital Expenditure", "Capital Expenditures")
        if ocf is not None and capex is not None:
            fcf = ocf + capex  # capex is reported negative, so add

    financials["free_cash_flow"] = fcf
    financials["total_debt"] = _row(bs, "Total Debt")
    financials["cash_and_equivalents"] = _row(
        bs, "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Cash Equivalents And Short Term Investments",
    )
    return {"ticker": ticker, "source": "yfinance", "financials": financials}


# --- get_prices -----------------------------------------------------------

def get_prices(tool_input: dict, state=None) -> dict:
    """
    Return the scalars downstream tools need: current price, market cap, shares
    outstanding. The full price *series* for charts is a later-checkpoint concern
    — this tool returns scalars so the trace stays readable.
    """
    ticker = tool_input["ticker"].upper()
    if _source() == "yfinance":
        return _prices_yfinance(ticker)
    fx = _load_fixture(ticker)
    if fx is None or "prices" not in fx:
        return {"error": f"no prices fixture for {ticker}", "ticker": ticker}
    p = fx["prices"]
    return {
        "ticker": ticker,
        "source": "fixture",
        "current_price": p.get("current_price"),
        "market_cap": p.get("market_cap"),
        "shares_outstanding": p.get("shares_outstanding"),
    }


def _prices_yfinance(ticker: str) -> dict:
    import yfinance as yf
    tk = yf.Ticker(ticker)
    fi = tk.fast_info

    def _fi(*keys):
        # fast_info key names vary across yfinance versions; try a few.
        for k in keys:
            try:
                v = fi[k]
                if v:
                    return float(v)
            except Exception:
                pass
        return None

    current_price = _fi("last_price", "lastPrice")
    market_cap = _fi("market_cap", "marketCap")
    shares = _fi("shares", "sharesOutstanding")

    if shares is None:
        try:
            so = tk.info.get("sharesOutstanding")
            shares = float(so) if so else None
        except Exception:
            shares = None

    return {
        "ticker": ticker,
        "source": "yfinance",
        "current_price": current_price,
        "market_cap": market_cap,
        "shares_outstanding": shares,
    }

# --- get_price_history ----------------------------------------------------
#
# Chart data, NOT an analysis tool. The agent loop never calls this — the model
# reasons over financials/prices/ratios/DCF/peers, none of which need a price
# series. History is fetched by the composer at report time (see composer.py)
# and written into model.json, so the report is rebuildable from the sidecar.
#
# Live: real daily history via yfinance. Offline: a DETERMINISTIC synthetic
# series (seeded, ending at the fixture's current_price) so the chart pipeline
# is provable with no network. Both return the same schema.

def get_price_history(ticker: str, period: str = "1y") -> dict:
    ticker = ticker.upper()
    if _source() == "yfinance":
        return _history_yfinance(ticker, period)
    return _history_synthetic(ticker)


def _history_yfinance(ticker: str, period: str) -> dict:
    import yfinance as yf
    tk = yf.Ticker(ticker)
    hist = tk.history(period=period, auto_adjust=True)
    if hist is None or hist.empty:
        return {"ticker": ticker, "source": "yfinance", "history": [], "error": "no history"}
    rows = []
    for idx, row in hist.iterrows():
        d = idx.date().isoformat() if hasattr(idx, "date") else str(idx)
        rows.append({
            "date": d,
            "close": round(float(row["Close"]), 4),
            "volume": int(row["Volume"]) if row.get("Volume") == row.get("Volume") else None,
        })
    return {"ticker": ticker, "source": "yfinance", "period": period, "history": rows}


def _history_synthetic(ticker: str) -> dict:
    """Deterministic synthetic daily series for offline runs. Clearly labelled;
    ends at the fixture's current_price so charts look plausible."""
    import random
    from datetime import date, timedelta

    fx = _load_fixture(ticker)
    end_price = (fx or {}).get("prices", {}).get("current_price") or 100.0
    n = 252  # ~1 trading year

    rng = random.Random(hash(ticker) & 0xFFFFFFFF)
    # Build a gentle random walk, then scale so the final point == end_price.
    steps = [1.0]
    for _ in range(n - 1):
        steps.append(steps[-1] * (1 + rng.gauss(0.0005, 0.015)))
    scale = end_price / steps[-1]
    closes = [round(s * scale, 4) for s in steps]

    # Business-day dates ending at a fixed reference date.
    ref = date(2025, 12, 31)
    dates, d = [], ref
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d -= timedelta(days=1)
    dates = list(reversed(dates))

    rows = [{"date": dates[i], "close": closes[i],
             "volume": int(rng.uniform(1_000_000, 5_000_000))} for i in range(n)]
    return {"ticker": ticker, "source": "fixture-synthetic", "period": "1y", "history": rows}
