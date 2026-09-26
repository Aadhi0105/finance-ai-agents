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
from datetime import datetime, timezone
from tools.financial_contract import number, annual_pair

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _stable_seed(text: str) -> int:
    """A seed that is reproducible ACROSS PROCESSES. Python's built-in str hash()
    is randomized per interpreter (PYTHONHASHSEED), so seeding an RNG with it makes
    'deterministic' offline runs differ between invocations — which quietly breaks
    the auditability claim. A sha256 digest is stable everywhere."""
    import hashlib
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


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
    return {"ticker": ticker, "source": "fixture", "financials": fx["financials"],
            "retrieved_at": None, "provenance": "committed illustrative fixture; not live data"}


def _retrieved():
    return datetime.now(timezone.utc).isoformat()


def _date(col):
    return str(col.date()) if hasattr(col, "date") else str(col)


def _row(df, period, *labels):
    """Read ONLY the requested period, skipping missing/non-finite aliases."""
    if df is None or getattr(df, "empty", True):
        return None
    cols = [c for c in df.columns if _date(c) == period]
    if len(cols) != 1:
        return None
    for label in labels:
        try:
            value = number(df.loc[label, cols[0]])
            if value is not None:
                return value
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _info(tk):
    try:
        return tk.info or {}
    except Exception:
        return {}


def _financials_yfinance(ticker: str) -> dict:
    import yfinance as yf
    tk = yf.Ticker(ticker)
    fin = tk.financials
    if fin is None or fin.empty:
        return {"error": f"yfinance returned no financials for {ticker}", "ticker": ticker}
    period = max(_date(c) for c in fin.columns)
    warnings = []
    statements = {"income": fin}
    for name, attr in (("cash_flow", "cashflow"), ("balance_sheet", "balance_sheet")):
        try:
            statements[name] = getattr(tk, attr)
        except Exception:
            statements[name] = None
    periods = {}
    for name, frame in statements.items():
        periods[name] = period if frame is not None and period in [_date(c) for c in frame.columns] else None
        if periods[name] is None:
            warnings.append(f"{name} unavailable for {period}; no other period substituted")
    cf, bs = statements["cash_flow"], statements["balance_sheet"]
    fields = {
        "revenue": (fin, ("Total Revenue",)), "gross_profit": (fin, ("Gross Profit",)),
        "operating_income": (fin, ("Operating Income",)), "net_income": (fin, ("Net Income",)),
        "ebit": (fin, ("EBIT", "Operating Income")),
        "tax_provision": (fin, ("Tax Provision", "Income Tax Expense")),
        "pretax_income": (fin, ("Pretax Income", "Income Before Tax")),
        "depreciation_amortization": (cf, ("Depreciation And Amortization", "Depreciation Amortization Depletion", "Depreciation Depletion And Amortization")),
        "capex": (cf, ("Capital Expenditure", "Capital Expenditures")),
        "free_cash_flow": (cf, ("Free Cash Flow",)),
        "total_debt": (bs, ("Total Debt",)),
        "cash_and_equivalents": (bs, ("Cash And Cash Equivalents",)),
    }
    financials = {key: _row(frame, period, *labels) for key, (frame, labels) in fields.items()}
    if _row(fin, period, "EBIT") is None and financials["ebit"] is not None:
        warnings.append("EBIT unavailable; operating income used as explicitly labelled proxy")
    if financials["depreciation_amortization"] is None:
        financials["depreciation_amortization"] = _row(fin, period, "Reconciled Depreciation")
    raw_capex = financials["capex"]
    financials["capex"] = abs(raw_capex) if raw_capex is not None else None
    if financials["free_cash_flow"] is None:
        ocf = _row(cf, period, "Operating Cash Flow", "Total Cash From Operating Activities")
        if ocf is not None and raw_capex is not None:
            financials["free_cash_flow"] = ocf - abs(raw_capex)
    # Yahoo's cash-flow row is a signed contribution to operating cash flow.
    # Contract uses the opposite sign: investment/absorption in working capital.
    raw_wc = _row(cf, period, "Change In Working Capital")
    financials["change_in_working_capital"] = -raw_wc if raw_wc is not None else None
    previous = sorted((d for d in (_date(c) for c in fin.columns) if annual_pair(period, d)), reverse=True)
    financials["revenue_prior"] = _row(fin, previous[0], "Total Revenue") if previous else None
    financials.update({
        "period": period, "prior_period": previous[0] if previous else None,
        "ebit_basis": "reported EBIT" if _row(fin, period, "EBIT") is not None else "operating income proxy",
        "period_type": "annual", "statement_periods": periods,
        "currency": _info(tk).get("financialCurrency"), "monetary_unit": "base",
        "working_capital_convention": "balance_change", "capex_convention": "outflow_magnitude",
        "working_capital_basis": "provider operating-assets/liabilities aggregate; may include non-current items",
        "period_basis": "provider annual period labels; may differ from issuer fiscal closing date",
    })
    return {"ticker": ticker, "source": "yfinance", "retrieved_at": _retrieved(),
            "financials": financials, "warnings": warnings,
            "normalization": {"working_capital": {"raw": raw_wc, "raw_convention": "cash_flow_contribution",
                               "operation": "negate", "normalized": financials["change_in_working_capital"]},
                              "capex": {"raw": raw_capex, "operation": "absolute_outflow"}}}


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
        "currency": p.get("currency"), "monetary_unit": p.get("monetary_unit"),
        "as_of": p.get("as_of"), "retrieved_at": None,
        "provenance": "committed illustrative fixture; not live data",
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
                if number(v) is not None:
                    return number(v)
            except Exception:
                pass
        return None

    current_price = _fi("last_price", "lastPrice")
    market_cap = _fi("market_cap", "marketCap")
    shares = _fi("shares", "sharesOutstanding")

    info = _info(tk)
    if shares is None:
        shares = number(info.get("sharesOutstanding"))

    return {
        "ticker": ticker,
        "source": "yfinance",
        "current_price": current_price,
        "market_cap": market_cap,
        "shares_outstanding": shares,
        "currency": info.get("currency"), "monetary_unit": "base",
        "as_of": None, "provider_quote_time": info.get("regularMarketTime"),
        "timestamp_note": "fast_info price timestamp unavailable; provider_quote_time belongs to info snapshot", "retrieved_at": _retrieved(),
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
            "close": round(number(row["Close"]), 4) if number(row["Close"]) is not None else None,
            "volume": int(number(row.get("Volume"))) if number(row.get("Volume")) is not None else None,
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

    rng = random.Random(_stable_seed(ticker))
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

# --- home index mapping (for the price-vs-index chart) --------------------
# Maps an exchange suffix to its benchmark index ticker. Used only by the
# composer for the price-vs-index chart; not an analysis input.

_HOME_INDEX = {
    ".AS": "^AEX",     # Amsterdam
    ".DE": "^GDAXI",   # Frankfurt / Xetra (DAX)
    ".PA": "^FCHI",    # Paris (CAC 40)
    ".L":  "^FTSE",    # London (FTSE 100)
    ".SW": "^SSMI",    # Switzerland (SMI)
    ".MC": "^IBEX",    # Madrid (IBEX 35)
    ".BR": "^BFX",     # Brussels (BEL 20)
    ".MI": "FTSEMIB.MI",  # Milan (FTSE MIB)
}


def home_index_ticker(ticker: str) -> str | None:
    """Return the benchmark index ticker for a listing, or None if unmapped.
    US tickers (no dot suffix) default to the S&P 500."""
    t = ticker.upper()
    for suffix, index in _HOME_INDEX.items():
        if t.endswith(suffix):
            return index
    if "." not in t:            # US-listed
        return "^GSPC"          # S&P 500
    return None                 # unmapped exchange -> chart skipped gracefully

# --- get_consensus --------------------------------------------------------
#
# THE branch point (spec §3.1). Consensus/analyst estimates are the one
# genuinely hard input — mostly paywalled — so this tool is DESIGNED to often
# return available=False. It does NOT silently fall back: it reports the null
# honestly, and the *model* must decide to call get_historical_trend instead.
# That decision is where the loop stops being a pipeline.

def _consensus_result(ticker, source, estimates, **metadata):
    cleaned = {}
    for key in ("price_target", "revenue_estimate_avg", "eps_estimate_avg"):
        values = {str(k): number(v) for k, v in (estimates.get(key) or {}).items()}
        values = {k: v for k, v in values.items() if v is not None}
        if key == "price_target":
            values = {k: v for k, v in values.items() if k in ("low", "high", "mean", "median") and v > 0}
        else:
            values = {k: v for k, v in values.items() if k in ("0q", "+1q", "0y", "+1y")}
            if key == "revenue_estimate_avg":
                values = {k: v for k, v in values.items() if v > 0}
        if values:
            cleaned[key] = values
    return {"ticker": ticker, "source": source, "available": bool(cleaned),
            "consensus": cleaned, "monetary_unit": "base",
            "reason": None if cleaned else "no usable analyst estimates",
            **metadata}


def get_consensus(tool_input: dict, state=None) -> dict:
    ticker = tool_input["ticker"].upper()
    if _source() == "yfinance":
        return _consensus_yfinance(ticker)
    fx = _load_fixture(ticker) or {}
    return _consensus_result(ticker, "fixture", fx.get("consensus", {}), retrieved_at=None,
                             as_of=None, coverage={}, warnings=["illustrative fixture"],
                             reporting_currency=fx.get("financials", {}).get("currency"),
                             quote_currency=fx.get("prices", {}).get("currency"))


def _consensus_yfinance(ticker: str) -> dict:
    import yfinance as yf
    tk = yf.Ticker(ticker)
    out, coverage, warnings = {}, {}, []
    try:
        out["price_target"] = tk.analyst_price_targets or {}
    except Exception as exc:
        warnings.append(f"price targets unavailable ({type(exc).__name__})")
    for attr, key in (("revenue_estimate", "revenue_estimate_avg"),
                      ("earnings_estimate", "eps_estimate_avg")):
        try:
            df = getattr(tk, attr)
            if df is not None and not df.empty and "avg" in df.columns:
                out[key], coverage[key] = {}, {}
                for idx in df.index:
                    count = number(df.loc[idx, "numberOfAnalysts"]) if "numberOfAnalysts" in df.columns else None
                    coverage[key][str(idx)] = count
                    if count is None or count > 0:
                        out[key][str(idx)] = number(df.loc[idx, "avg"])
        except Exception as exc:
            warnings.append(f"{key} unavailable ({type(exc).__name__})")
    info = _info(tk)
    coverage["price_target"] = number(info.get("numberOfAnalystOpinions"))
    if coverage["price_target"] is None:
        coverage["price_target"] = number(out.get("price_target", {}).get("numberOfAnalysts"))
    if coverage["price_target"] is not None and coverage["price_target"] <= 0:
        out.pop("price_target", None)
    return _consensus_result(ticker, "yfinance", out, retrieved_at=_retrieved(), as_of=None,
                            reporting_currency=info.get("financialCurrency"),
                            quote_currency=info.get("currency"), coverage=coverage,
                            warnings=warnings + ["provider estimate publication dates unavailable; retrieval time is not estimate date"])


# --- annual historical trend ---------------------------------------------

def get_historical_trend(tool_input: dict, state=None) -> dict:
    ticker = tool_input["ticker"].upper()
    if _source() == "yfinance":
        return _trend_yfinance(ticker)
    fx = _load_fixture(ticker) or {}
    if "trend" not in fx:
        return {"ticker": ticker, "source": "fixture", "error": "no trend fixture"}
    result = _summarise_trend(ticker, "fixture", fx["trend"]["revenue_by_year"],
                              fx["trend"]["net_income_by_year"])
    result.update({"currency": fx.get("financials", {}).get("currency"),
                   "monetary_unit": "base", "retrieved_at": None,
                   "provenance": "committed illustrative annual fixture; not live data"})
    return result


def _trend_yfinance(ticker: str) -> dict:
    import yfinance as yf
    tk = yf.Ticker(ticker)
    fin = tk.financials
    if fin is None or fin.empty:
        return {"ticker": ticker, "source": "yfinance", "error": "no financials for trend"}
    rev, ni, periods, excluded = {}, {}, {}, []
    # Start at the latest period; exclude stubs and preserve exact source dates.
    previous = None
    for col in sorted(fin.columns, key=_date, reverse=True):
        period = _date(col)
        if previous and not annual_pair(previous, period):
            excluded.append({"period": period, "reason": "not a comparable consecutive annual period"})
            continue
        year = period[:4]
        if year in periods:
            excluded.append({"period": period, "reason": "duplicate fiscal year"})
            continue
        periods[year] = period
        rev[year] = _row(fin, period, "Total Revenue")
        ni[year] = _row(fin, period, "Net Income")
        previous = period
    out = _summarise_trend(ticker, "yfinance", rev, ni)
    out.update({"periods": periods, "excluded_periods": excluded, "retrieved_at": _retrieved(),
                "currency": _info(tk).get("financialCurrency"), "monetary_unit": "base"})
    return out


def _summarise_trend(ticker: str, source: str, rev: dict, ni: dict) -> dict:
    rev = {str(y): number(v) for y, v in rev.items() if str(y).isdigit() and len(str(y)) == 4}
    ni = {str(y): number(v) for y, v in ni.items()}
    years = sorted(rev)
    net_margin_by_year = {y: number(round(ni[y] / rev[y], 4)) for y in years
                          if ni.get(y) is not None and rev[y] is not None and rev[y] > 0}
    cagr = None
    # Use only the latest contiguous usable annual sequence. Yahoo often adds
    # an all-NaN oldest column; it must not discard four valid recent years.
    cagr_years = []
    for y in reversed(years):
        if rev[y] is None or rev[y] <= 0:
            break
        if cagr_years and int(cagr_years[-1]) - int(y) != 1:
            break
        cagr_years.append(y)
    cagr_years.reverse()
    comparable = len(cagr_years) >= 2
    if comparable:
        try:
            cagr = number((rev[cagr_years[-1]] / rev[cagr_years[0]]) ** (1 / (len(cagr_years) - 1)) - 1)
        except OverflowError:
            cagr = None
        comparable = cagr is not None
    return {
        "ticker": ticker, "source": source, "available": comparable,
        "revenue_by_year": {y: rev[y] for y in years},
        "net_margin_by_year": net_margin_by_year, "revenue_cagr": round(cagr, 4) if cagr is not None else None,
        "cagr_years": cagr_years if comparable else [],
        "basis": "company_own_history" if comparable else "insufficient_comparable_history",
        "reason": None if comparable else "need at least two consecutive annual periods with positive finite revenues",
        "computed_by": "get_historical_trend (python)",
    }
