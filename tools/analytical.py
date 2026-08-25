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

# --- run_dcf (v2) ---------------------------------------------------------
#
# What changed from v1 (and why): v1 was a single-stage, 5-year DCF on
# net-income-as-FCF with equity value approximated by EV. On a durable
# compounder that shape prints an implausibly low value and reads as broken.
# v2 fixes the three things that made it naive:
#   1. FCF base = real free cash flow (from get_financials); net income only
#      as a logged fallback when FCF is unavailable.
#   2. Two-stage: growth fades LINEARLY from a high starting rate to the
#      terminal rate across a 10-year explicit horizon, then Gordon terminal
#      value — not flat growth then a cliff.
#   3. Net-debt bridge: equity value = EV - net debt (net debt = total debt -
#      cash). Net-cash companies get a value ABOVE EV.
# The point is a defensible METHOD, not a number tuned to match the price.

_DCF_DEFAULTS = {
    "horizon_years": 10,          # explicit high-growth/fade phase
    "discount_rate": 0.09,        # WACC proxy
    "terminal_growth": 0.025,
    "high_growth": 0.12,          # year-1 growth; fades to terminal_growth by year N
    # scenario shifts applied to the high_growth starting rate, + probability weights
    "bear_delta": -0.04, "base_delta": 0.0, "bull_delta": 0.04,
    "weights": {"bear": 0.25, "base": 0.50, "bull": 0.25},
}


def _two_stage_ev(fcf0, high_g, term_g, r, n):
    """
    Deterministic two-stage DCF -> enterprise value.
    Growth in year t fades linearly from high_g (year 1) to term_g (year n).
    Terminal value is Gordon growth at term_g on the final-year FCF.
    """
    pv = 0.0
    fcf_t = fcf0
    for t in range(1, n + 1):
        # linear fade: year 1 -> high_g, year n -> term_g
        g_t = high_g + (term_g - high_g) * (t - 1) / (n - 1) if n > 1 else term_g
        fcf_t = fcf_t * (1 + g_t)
        pv += fcf_t / (1 + r) ** t
    tv = fcf_t * (1 + term_g) / (r - term_g)
    pv_tv = tv / (1 + r) ** n
    return pv + pv_tv


def run_dcf(tool_input: dict, state=None) -> dict:
    ticker = tool_input["ticker"].upper()

    fin = state.results.get("get_financials") if state is not None else None
    prices = state.results.get("get_prices") if state is not None else None
    if not fin or "financials" not in fin:
        return {"error": "run_dcf needs get_financials first", "ticker": ticker}
    f = fin["financials"]

    # FCF base: real free cash flow, with net income as a logged fallback.
    fcf0 = f.get("free_cash_flow")
    fcf_source = "free_cash_flow (cash-flow statement)"
    if not fcf0:
        fcf0 = f.get("net_income")
        fcf_source = "net_income (fallback — no FCF available)"
    if not fcf0:
        return {"error": "run_dcf: no FCF or net income to base the DCF on", "ticker": ticker}

    # Merge caller overrides onto defaults. Accept high_growth or legacy base_growth.
    a = dict(_DCF_DEFAULTS)
    if tool_input.get("base_growth") is not None and tool_input.get("high_growth") is None:
        a["high_growth"] = tool_input["base_growth"]
    for k in ("horizon_years", "discount_rate", "terminal_growth", "high_growth"):
        if tool_input.get(k) is not None:
            a[k] = tool_input[k]

    r, tg, n, hg = a["discount_rate"], a["terminal_growth"], a["horizon_years"], a["high_growth"]

    ev = {
        "bear": _two_stage_ev(fcf0, hg + a["bear_delta"], tg, r, n),
        "base": _two_stage_ev(fcf0, hg + a["base_delta"], tg, r, n),
        "bull": _two_stage_ev(fcf0, hg + a["bull_delta"], tg, r, n),
    }

    # Net-debt bridge: equity value = EV - net debt (negative net debt = net cash).
    total_debt = f.get("total_debt") or 0.0
    cash = f.get("cash_and_equivalents") or 0.0
    net_debt = total_debt - cash
    bridge_known = ("total_debt" in f and f.get("total_debt") is not None) or \
                   ("cash_and_equivalents" in f and f.get("cash_and_equivalents") is not None)
    equity = {k: v - net_debt for k, v in ev.items()}

    shares = prices.get("shares_outstanding") if prices else None
    current_price = prices.get("current_price") if prices else None
    per_share = {k: (v / shares if shares else None) for k, v in equity.items()}

    w = a["weights"]
    weighted_equity = sum(equity[k] * w[k] for k in equity)
    weighted_ps = weighted_equity / shares if shares else None
    upside = round(weighted_ps / current_price - 1, 4) if (weighted_ps and current_price) else None

    return {
        "ticker": ticker,
        "enterprise_value": {k: round(v, 0) for k, v in ev.items()},
        "equity_value": {k: round(v, 0) for k, v in equity.items()},
        "value_per_share": {k: (round(v, 2) if v else None) for k, v in per_share.items()},
        "probability_weighted_per_share": round(weighted_ps, 2) if weighted_ps else None,
        "current_price": current_price,
        "implied_upside": upside,
        "assumptions": {
            "fcf_base": fcf0, "fcf_source": fcf_source,
            "model": "two-stage: linear growth fade over horizon, then Gordon terminal",
            "high_growth": hg, "terminal_growth": tg, "horizon_years": n, "discount_rate": r,
            "scenario_deltas": {"bear": a["bear_delta"], "base": a["base_delta"], "bull": a["bull_delta"]},
            "weights": w,
            "net_debt": net_debt if bridge_known else None,
            "net_debt_note": ("equity = EV - net debt" if bridge_known
                              else "net-debt items unavailable; equity approximated by EV"),
        },
        "computed_by": "run_dcf v2 (python)",
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

    values = list(peer_pes.values())
    if len(values) < 2:
        return {"error": "could not compute P/E for enough peers", "ticker": ticker, "peer_pes": peer_pes}

    # --- PRIMARY: robust stats (median + MAD) --------------------------------
    # Median and MAD ignore a single extreme peer, so the verdict doesn't hinge
    # on one inflated multiple (e.g. a peer at trough earnings). This is the
    # headline outlier call.
    median = statistics.median(values)
    abs_devs = [abs(v - median) for v in values]
    mad = statistics.median(abs_devs)
    # Iglewicz-Hoaglin modified z-score; 0.6745 makes it comparable to a normal z.
    if mad > 0:
        modified_z = 0.6745 * (target_pe - median) / mad
        robust_outlier = abs(modified_z) > 3.5   # standard modified-z threshold
    else:
        modified_z = None                        # MAD=0: peers too clustered to judge
        robust_outlier = None

    # --- SECONDARY: mean-based stats (kept for comparison) -------------------
    mean = statistics.mean(values)
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    z = (target_pe - mean) / stdev if stdev else None
    mean_outlier = bool(z is not None and abs(z) > 2)

    # --- Divergence: do robust and mean-based verdicts disagree? -------------
    # Divergence usually means one peer is skewing the mean — itself a useful
    # signal to inspect the peer set.
    divergence = (robust_outlier is not None) and (robust_outlier != mean_outlier)
    skew_note = None
    if mean and median and abs(mean - median) / median > 0.15:
        skew_note = (f"peer mean ({round(mean,2)}) and median ({round(median,2)}) diverge "
                     f">15% — the mean is likely skewed by an extreme peer; trust the median.")

    # Primary verdict is the robust one; fall back to mean only if MAD was zero.
    is_outlier = robust_outlier if robust_outlier is not None else mean_outlier

    return {
        "ticker": ticker,
        "metric": "pe",
        "target_pe": round(target_pe, 2),
        "peer_pes": peer_pes,
        # primary (robust)
        "peer_median": round(median, 2),
        "peer_mad": round(mad, 2),
        "modified_z": round(modified_z, 2) if modified_z is not None else None,
        "is_outlier": is_outlier,
        "verdict_basis": "median/MAD (robust)" if robust_outlier is not None else "mean/z (MAD was zero)",
        # secondary (mean-based), for comparison
        "peer_mean": round(mean, 2),
        "peer_stdev": round(stdev, 2),
        "z_score": round(z, 2) if z is not None else None,
        "mean_based_outlier": mean_outlier,
        # signals
        "verdict_divergence": divergence,
        "skew_note": skew_note,
        "caveat": "peer selection is an analyst input; robust stats still noisy below ~5 peers",
        "computed_by": "peer_outlier_check (python, median/MAD primary)",
    }
