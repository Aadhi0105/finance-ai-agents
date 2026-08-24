"""
Analytical tools — the computation family (spec §3.1). THE DIFFERENTIATING SET.

Governing principle: the LLM never does the math. Every number this repo reports
comes out of a deterministic Python function here. The model decides WHICH tool
to call and READS the result; it never computes.

Tools in this checkpoint:
  compute_ratios      margins + growth, plus P/E and EV/EBIT when prices exist
  run_dcf             scenario-weighted DCF  -> PROBABILITY (L)
  peer_outlier_check  is a multiple an outlier vs peers?  -> STATISTICS (S)

Every assumption a tool makes (DCF discount rate, FCF proxy, peer list, ...) is
returned in its output so a reviewer can audit exactly what drove each number.
"""

from __future__ import annotations

import statistics
from tools import data


# --- compute_ratios -------------------------------------------------------

def compute_ratios(tool_input: dict, state=None) -> dict:
    ticker = tool_input["ticker"].upper()

    fetched = state.results.get("get_financials") if state is not None else None
    if not fetched or "financials" not in fetched:
        return {"error": "compute_ratios needs get_financials to run first", "ticker": ticker}
    f = fetched["financials"]

    revenue = f.get("revenue")
    gross_profit = f.get("gross_profit")
    operating_income = f.get("operating_income")
    net_income = f.get("net_income")
    revenue_prior = f.get("revenue_prior")

    def _ratio(numer, denom):
        if numer is None or denom in (None, 0):
            return None
        return round(numer / denom, 4)

    ratios = {
        "gross_margin": _ratio(gross_profit, revenue),
        "operating_margin": _ratio(operating_income, revenue),
        "net_margin": _ratio(net_income, revenue),
        "revenue_growth_yoy": (
            _ratio(revenue - revenue_prior, revenue_prior)
            if (revenue is not None and revenue_prior not in (None, 0)) else None
        ),
    }

    # Valuation multiples require prices. If get_prices ran, add P/E and EV/EBIT.
    # SKELETON simplification (logged): EV is approximated by market cap
    # (net-debt bridge is a later data-layer improvement).
    prices = state.results.get("get_prices") if state is not None else None
    assumptions = {}
    if prices and prices.get("market_cap"):
        mcap = prices["market_cap"]
        ratios["pe"] = _ratio(mcap, net_income)
        ratios["ev_ebit"] = _ratio(mcap, operating_income)
        assumptions["ev_approx"] = "EV approximated by market cap (net debt ignored, skeleton)"
    else:
        assumptions["multiples"] = "P/E and EV/EBIT skipped: get_prices not in memory"

    return {
        "ticker": ticker,
        "ratios": ratios,
        "assumptions": assumptions,
        "computed_by": "compute_ratios (python)",
    }


# --- run_dcf --------------------------------------------------------------

_DCF_DEFAULTS = {
    "horizon_years": 5,
    "discount_rate": 0.10,       # WACC proxy
    "terminal_growth": 0.025,
    "base_growth": 0.08,
    # scenario growth deltas applied to base_growth, and their probability weights
    "bear_delta": -0.04, "base_delta": 0.0, "bull_delta": 0.04,
    "weights": {"bear": 0.25, "base": 0.50, "bull": 0.25},
    "fcf_proxy": "net_income",   # SKELETON: FCF proxied by net income
}


def _one_dcf(fcf0, growth, r, tg, n):
    """Deterministic single-scenario DCF -> enterprise value proxy."""
    pv = 0.0
    fcf_t = fcf0
    for t in range(1, n + 1):
        fcf_t = fcf0 * (1 + growth) ** t
        pv += fcf_t / (1 + r) ** t
    # Gordon-growth terminal value on the final projected FCF.
    tv = fcf_t * (1 + tg) / (r - tg)
    pv_tv = tv / (1 + r) ** n
    return pv + pv_tv


def run_dcf(tool_input: dict, state=None) -> dict:
    ticker = tool_input["ticker"].upper()

    fin = state.results.get("get_financials") if state is not None else None
    prices = state.results.get("get_prices") if state is not None else None
    if not fin or "financials" not in fin:
        return {"error": "run_dcf needs get_financials first", "ticker": ticker}

    net_income = fin["financials"].get("net_income")
    if not net_income:
        return {"error": "run_dcf: no net_income to proxy FCF from", "ticker": ticker}

    # Merge caller overrides onto defaults; everything used is logged below.
    a = dict(_DCF_DEFAULTS)
    for k in ("horizon_years", "discount_rate", "terminal_growth", "base_growth"):
        if k in tool_input and tool_input[k] is not None:
            a[k] = tool_input[k]

    r, tg, n, g = a["discount_rate"], a["terminal_growth"], a["horizon_years"], a["base_growth"]
    fcf0 = net_income  # proxy, per assumptions

    ev = {
        "bear": _one_dcf(fcf0, g + a["bear_delta"], r, tg, n),
        "base": _one_dcf(fcf0, g + a["base_delta"], r, tg, n),
        "bull": _one_dcf(fcf0, g + a["bull_delta"], r, tg, n),
    }

    shares = prices.get("shares_outstanding") if prices else None
    current_price = prices.get("current_price") if prices else None

    # EV -> per share. SKELETON: equity value approximated by EV (net debt ignored).
    per_share = {k: (v / shares if shares else None) for k, v in ev.items()}
    w = a["weights"]
    weighted_ev = sum(ev[k] * w[k] for k in ev)
    weighted_ps = weighted_ev / shares if shares else None

    upside = None
    if weighted_ps and current_price:
        upside = round(weighted_ps / current_price - 1, 4)

    return {
        "ticker": ticker,
        "enterprise_value": {k: round(v, 0) for k, v in ev.items()},
        "value_per_share": {k: (round(v, 2) if v else None) for k, v in per_share.items()},
        "probability_weighted_per_share": round(weighted_ps, 2) if weighted_ps else None,
        "current_price": current_price,
        "implied_upside": upside,
        "assumptions": {
            "fcf_base": fcf0, "fcf_proxy": a["fcf_proxy"],
            "base_growth": g, "scenario_deltas": {"bear": a["bear_delta"], "base": a["base_delta"], "bull": a["bull_delta"]},
            "weights": w, "discount_rate": r, "terminal_growth": tg, "horizon_years": n,
            "simplifications": "equity value approximated by EV (net debt bridge omitted, skeleton)",
        },
        "computed_by": "run_dcf (python)",
    }


# --- peer_outlier_check ---------------------------------------------------

def _pe_for(ticker: str) -> float | None:
    """Fetch a peer's market cap and net income via the data layer, return P/E."""
    fin = data.get_financials({"ticker": ticker})
    prices = data.get_prices({"ticker": ticker})
    ni = fin.get("financials", {}).get("net_income") if "financials" in fin else None
    mcap = prices.get("market_cap") if "error" not in prices else None
    if ni and mcap:
        return mcap / ni
    return None


def peer_outlier_check(tool_input: dict, state=None) -> dict:
    """
    Is the target's multiple an outlier vs an EXPLICIT peer set?

    Peer SELECTION is an analyst judgment, not something this tool pretends to
    solve — peers are passed in. The tool fetches each peer's P/E, then reports
    where the target sits in that distribution (z-score + IQR flag).
    """
    ticker = tool_input["ticker"].upper()
    peers = [p.upper() for p in tool_input.get("peers", [])]
    metric = tool_input.get("metric", "pe")
    if metric != "pe":
        return {"error": f"peer_outlier_check: only 'pe' supported in this checkpoint", "ticker": ticker}
    if len(peers) < 2:
        return {"error": "peer_outlier_check needs at least 2 peers", "ticker": ticker}

    # Target P/E from working memory (already fetched).
    prices = state.results.get("get_prices") if state is not None else None
    fin = state.results.get("get_financials") if state is not None else None
    target_ni = fin["financials"].get("net_income") if fin and "financials" in fin else None
    target_mcap = prices.get("market_cap") if prices else None
    if not (target_ni and target_mcap):
        return {"error": "peer_outlier_check needs get_financials + get_prices for the target first", "ticker": ticker}
    target_pe = target_mcap / target_ni

    peer_pes = {}
    for p in peers:
        pe = _pe_for(p)
        if pe is not None:
            peer_pes[p] = round(pe, 2)

    values = list(peer_pes.values())
    if len(values) < 2:
        return {"error": "could not compute P/E for enough peers", "ticker": ticker, "peer_pes": peer_pes}

    mean = statistics.mean(values)
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    z = (target_pe - mean) / stdev if stdev else None

    # IQR flag (crude at small n — flagged in output).
    iqr_flag = None
    if len(values) >= 4:
        q1, _, q3 = statistics.quantiles(values, n=4)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        iqr_flag = not (lo <= target_pe <= hi)

    is_outlier = bool(z is not None and abs(z) > 2) or bool(iqr_flag)

    return {
        "ticker": ticker,
        "metric": "pe",
        "target_pe": round(target_pe, 2),
        "peer_pes": peer_pes,
        "peer_mean": round(mean, 2),
        "peer_stdev": round(stdev, 2),
        "z_score": round(z, 2) if z is not None else None,
        "is_outlier": is_outlier,
        "caveat": "peer selection is an analyst input; IQR flag unreliable below 4 peers",
        "computed_by": "peer_outlier_check (python)",
    }
