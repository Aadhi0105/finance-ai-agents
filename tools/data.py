"""
Data tools — the fetcher family (spec §3.1).

SKELETON scope: one fetcher, `get_financials`.

Source strategy (matches the offline/live switch used everywhere in this repo):
- If AGENT_DATA_SOURCE=fixture (default), read from fixtures/<TICKER>.json.
  This is what lets the loop be proven with no network — and it doubles as the
  deterministic test path even once yfinance is live.
- If AGENT_DATA_SOURCE=yfinance, pull live via yfinance on your Mac.

Either way the tool returns the SAME shape, so nothing downstream cares which
source produced it. yfinance is imported lazily so this module imports fine in
an environment where the package isn't installed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _source() -> str:
    return os.environ.get("AGENT_DATA_SOURCE", "fixture").lower()


def get_financials(tool_input: dict, state=None) -> dict:
    ticker = tool_input["ticker"].upper()
    if _source() == "yfinance":
        return _from_yfinance(ticker)
    return _from_fixture(ticker)


def _from_fixture(ticker: str) -> dict:
    path = _FIXTURE_DIR / f"{ticker}.json"
    if not path.exists():
        return {"error": f"no fixture for {ticker}", "ticker": ticker}
    with open(path) as f:
        raw = json.load(f)
    return {"ticker": ticker, "source": "fixture", "financials": raw["financials"]}


def _from_yfinance(ticker: str) -> dict:
    # Lazy import: only needed on the live path (your Mac), never in the sandbox.
    import yfinance as yf

    tk = yf.Ticker(ticker)
    fin = tk.financials  # DataFrame: rows are line items, columns are periods
    if fin is None or fin.empty:
        return {"error": f"yfinance returned no financials for {ticker}", "ticker": ticker}

    # Most recent period is the first column. Map yfinance labels to our schema.
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
    # Prior period for a simple YoY growth input, if available.
    if len(fin.columns) > 1:
        prev = fin.columns[1]
        try:
            financials["revenue_prior"] = float(fin.loc["Total Revenue", prev])
        except Exception:
            financials["revenue_prior"] = None

    return {"ticker": ticker, "source": "yfinance", "financials": financials}
