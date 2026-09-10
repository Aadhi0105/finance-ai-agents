"""
Analytical tools — the computation family (spec §3.1). THE DIFFERENTIATING SET.

Governing principle: the LLM never does the math. Every number this repo reports
comes out of a deterministic Python function here. The model decides WHICH tool
to call and READS the result; it never computes.

Tools:
  compute_ratios      margins + growth, plus P/E and EV/EBIT when prices exist
  run_dcf             scenario-weighted DCF  -> PROBABILITY (L)
  peer_outlier_check  is a multiple an outlier vs peers?  -> STATISTICS (S)

Every assumption a tool makes is returned in its output so a reviewer can audit
exactly what drove each number.

Integrity invariants enforced here (Agent-1 hardening):
  - a dependent tool refuses if the upstream result is for a DIFFERENT ticker;
  - EV is real enterprise value (mktcap + debt - cash), never approximated by mktcap;
  - multiples with a non-positive denominator return None + a status, never a
    meaningless negative;
  - missingness (None) is distinguished from a genuine zero;
  - the DCF refuses nonsensical parameters (r <= g, out-of-range) rather than
    printing a broken number;
  - the net-debt bridge is only 'complete' when BOTH debt and cash are known.
"""

from __future__ import annotations

import statistics
from tools import data


def _upstream(state, name, ticker):
    """Fetch an upstream tool result, enforcing ticker consistency. Returns
    (payload, error_dict). One-ticker agent: a dependent tool must not compute on
    another ticker's stored data."""
    if state is None:
        return None, {"error": f"{name} unavailable: no run state"}
    res = state.results.get(name)
    if not res:
        return None, {"error": f"needs {name} to run first"}
    stored_ticker = (res.get("ticker") or "").upper()
    if stored_ticker and stored_ticker != ticker:
        return None, {"error": f"ticker mismatch: {name} holds '{stored_ticker}', "
                               f"requested '{ticker}' — refusing to mix tickers"}
    return res, None


# --- compute_ratios -------------------------------------------------------

def compute_ratios(tool_input: dict, state=None) -> dict:
    ticker = tool_input["ticker"].upper()
    if state is not None and state.ticker and ticker != state.ticker.upper():
        return {"error": f"ticker mismatch: run is for '{state.ticker}', "
                         f"compute_ratios requested '{ticker}'", "ticker": ticker}

    fetched, err = _upstream(state, "get_financials", ticker)
    if err:
        return {**err, "ticker": ticker}
    if "financials" not in fetched:
        return {"error": "get_financials returned no financials", "ticker": ticker}
    f = fetched["financials"]

    revenue = f.get("revenue")
    gross_profit = f.get("gross_profit")
    operating_income = f.get("operating_income")
    net_income = f.get("net_income")
    revenue_prior = f.get("revenue_prior")

    def _ratio(numer, denom):
        if numer is None or denom is None or denom == 0:
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

    prices, perr = _upstream(state, "get_prices", ticker)
    assumptions = {}
    multiple_status = {}
    if prices and not perr and prices.get("market_cap"):
        mcap = prices["market_cap"]

        # P/E: only meaningful with positive earnings.
        if net_income is None:
            ratios["pe"] = None
            multiple_status["pe"] = "not_computable_no_net_income"
        elif net_income <= 0:
            ratios["pe"] = None
            multiple_status["pe"] = "not_meaningful_negative_earnings"
        else:
            ratios["pe"] = round(mcap / net_income, 4)

        # EV/EBIT: REAL enterprise value = market cap + total debt - cash.
        total_debt = f.get("total_debt")
        cash = f.get("cash_and_equivalents")
        if total_debt is None or cash is None:
            ratios["ev_ebit"] = None
            multiple_status["ev_ebit"] = "not_computable_incomplete_net_debt"
            assumptions["ev"] = ("EV not computed: need both total_debt and "
                                 "cash_and_equivalents; one or both missing")
        else:
            ev = mcap + total_debt - cash
            assumptions["ev"] = ev
            assumptions["ev_formula"] = "market_cap + total_debt - cash"
            if operating_income is None:
                ratios["ev_ebit"] = None
                multiple_status["ev_ebit"] = "not_computable_no_ebit"
            elif operating_income <= 0:
                ratios["ev_ebit"] = None
                multiple_status["ev_ebit"] = "not_meaningful_negative_ebit"
            else:
                ratios["ev_ebit"] = round(ev / operating_income, 4)
    else:
        assumptions["multiples"] = "P/E and EV/EBIT skipped: get_prices not in memory"

    return {
        "ticker": ticker,
        "ratios": ratios,
        "multiple_status": multiple_status,
        "assumptions": assumptions,
        "computed_by": "compute_ratios (python)",
    }


# --- run_dcf (v2) ---------------------------------------------------------

_DCF_DEFAULTS = {
    "horizon_years": 10,
    "discount_rate": 0.09,
    "terminal_growth": 0.025,
    "high_growth": 0.12,
    "bear_delta": -0.04, "base_delta": 0.0, "bull_delta": 0.04,
    "weights": {"bear": 0.25, "base": 0.50, "bull": 0.25},
}


def _validate_dcf_params(r, tg, n, hg) -> str | None:
    """Deterministic guards: refuse nonsensical parameters rather than printing a
    broken number. Returns an error string, or None if the params are sane."""
    if not (isinstance(n, int) and 1 <= n <= 30):
        return f"horizon_years must be an integer in [1, 30], got {n}"
    if not (isinstance(r, (int, float)) and r > 0):
        return f"discount_rate must be > 0, got {r}"
    if tg is None or tg <= -1:
        return f"terminal_growth must be > -1, got {tg}"
    if r <= tg:
        return (f"discount_rate ({r}) must exceed terminal_growth ({tg}) — "
                f"Gordon terminal value diverges otherwise")
    if hg is None or hg <= -1:
        return f"high_growth must be > -1, got {hg}"
    return None


def _two_stage_ev(fcf0, high_g, term_g, r, n):
    """Two-stage DCF -> enterprise value, plus terminal-value concentration."""
    pv = 0.0
    fcf_t = fcf0
    for t in range(1, n + 1):
        g_t = high_g + (term_g - high_g) * (t - 1) / (n - 1) if n > 1 else term_g
        fcf_t = fcf_t * (1 + g_t)
        pv += fcf_t / (1 + r) ** t
    tv = fcf_t * (1 + term_g) / (r - term_g)
    pv_tv = tv / (1 + r) ** n
    ev = pv + pv_tv
    tv_concentration = round(pv_tv / ev, 4) if ev else None
    return ev, tv_concentration


def run_dcf(tool_input: dict, state=None) -> dict:
    ticker = tool_input["ticker"].upper()
    if state is not None and state.ticker and ticker != state.ticker.upper():
        return {"error": f"ticker mismatch: run is for '{state.ticker}', "
                         f"run_dcf requested '{ticker}'", "ticker": ticker}

    fin, err = _upstream(state, "get_financials", ticker)
    if err:
        return {**err, "ticker": ticker}
    if "financials" not in fin:
        return {"error": "get_financials returned no financials", "ticker": ticker}
    prices, _ = _upstream(state, "get_prices", ticker)
    f = fin["financials"]

    # FCFF (unlevered free cash flow to the firm) — the correct base for an
    # ENTERPRISE DCF: FCFF = EBIT*(1-T) + D&A - CapEx - dNWC, discounted at WACC,
    # then the net-debt bridge to equity. We REFUSE if the core lines are missing
    # rather than falling back to net income (an equity measure) or CFO-capex (a
    # levered figure) — either would make "enterprise value" methodologically wrong.
    ebit = f.get("ebit")
    dna = f.get("depreciation_amortization")
    capex = f.get("capex")
    missing = [n for n, v in (("EBIT", ebit), ("D&A", dna), ("CapEx", capex)) if v is None]
    if missing:
        return {"error": (f"DCF not computable from available statements — missing "
                          f"FCFF component(s): {', '.join(missing)}. An enterprise DCF "
                          f"needs EBIT, D&A and CapEx; net income is not a valid "
                          f"substitute."),
                "ticker": ticker, "value_basis": "not_computable"}

    tax_prov = f.get("tax_provision")
    pretax = f.get("pretax_income")
    if tax_prov is not None and pretax not in (None, 0):
        tax_rate = max(0.0, min(0.5, tax_prov / pretax))
        tax_basis = "effective (tax provision / pretax income)"
    else:
        tax_rate = 0.25
        tax_basis = "default 25% (tax provision/pretax income unavailable)"

    dnwc = f.get("change_in_working_capital")
    dnwc_flag = None
    if dnwc is None:
        dnwc = 0.0
        dnwc_flag = "change in working capital unavailable — assumed 0"

    capex_outflow = abs(capex)          # capex is reported negative; use outflow magnitude
    fcf0 = ebit * (1 - tax_rate) + dna - capex_outflow - dnwc
    fcf_source = "FCFF = EBIT*(1-T) + D&A - CapEx - dNWC (unlevered, python)"
    if fcf0 <= 0:
        return {"error": (f"DCF not computable — FCFF base is non-positive "
                          f"({round(fcf0)}); a two-stage growth DCF is not a suitable "
                          f"model for a firm not generating positive unlevered cash flow."),
                "ticker": ticker, "value_basis": "not_applicable_negative_fcff"}

    a = dict(_DCF_DEFAULTS)

    if tool_input.get("base_growth") is not None and tool_input.get("high_growth") is None:
        a["high_growth"] = tool_input["base_growth"]
    for k in ("horizon_years", "discount_rate", "terminal_growth", "high_growth"):
        if tool_input.get(k) is not None:
            a[k] = tool_input[k]

    r, tg, n, hg = a["discount_rate"], a["terminal_growth"], a["horizon_years"], a["high_growth"]

    param_error = _validate_dcf_params(r, tg, n, hg)
    if param_error:
        return {"error": f"run_dcf invalid parameters: {param_error}", "ticker": ticker}

    ev, tvc = {}, {}
    for scen, delta in (("bear", a["bear_delta"]), ("base", a["base_delta"]), ("bull", a["bull_delta"])):
        scen_hg = hg + delta
        # each scenario's high_growth must also stay sane
        if scen_hg <= -1:
            return {"error": f"run_dcf: {scen} high_growth {scen_hg} <= -1", "ticker": ticker}
        e, c = _two_stage_ev(fcf0, scen_hg, tg, r, n)
        ev[scen], tvc[scen] = e, c

    # Net-debt bridge: COMPLETE only when BOTH sides are known. A missing side is
    # NOT treated as zero (that would silently overstate/understate equity).
    total_debt = f.get("total_debt")
    cash = f.get("cash_and_equivalents")
    bridge_complete = (total_debt is not None) and (cash is not None)

    if bridge_complete:
        net_debt = total_debt - cash
        equity = {k: v - net_debt for k, v in ev.items()}
        bridge_status = "complete"
        bridge_note = "equity = EV - net debt (both debt and cash known)"
        value_basis = "equity_value"
    else:
        net_debt = None
        equity = dict(ev)          # report EV only; do NOT assume the missing side is 0
        bridge_status = "incomplete"
        missing = [nm for nm, val in (("total_debt", total_debt), ("cash", cash)) if val is None]
        bridge_note = (f"net-debt bridge incomplete (missing: {', '.join(missing)}) — "
                       f"reporting ENTERPRISE VALUE only, not equity value")
        value_basis = "enterprise_value_only"

    shares = prices.get("shares_outstanding") if prices else None
    current_price = prices.get("current_price") if prices else None
    w = a["weights"]

    # EQUITY-DERIVED figures are only meaningful when the bridge is COMPLETE.
    # With an incomplete bridge we have enterprise value only — computing an
    # "EV per share" and comparing it to the equity share price is economically
    # meaningless (it ignores net debt), so those fields are None. We report
    # enterprise value only.
    if bridge_complete:
        per_share = {k: (v / shares if shares else None) for k, v in equity.items()}
        weighted_equity = sum(equity[k] * w[k] for k in equity)
        weighted_ps = weighted_equity / shares if shares else None
        upside = round(weighted_ps / current_price - 1, 4) if (weighted_ps and current_price) else None
        value_per_share = {k: (round(v, 2) if v else None) for k, v in per_share.items()}
        scenario_weighted_ps = round(weighted_ps, 2) if weighted_ps else None
    else:
        value_per_share = None
        scenario_weighted_ps = None
        upside = None

    return {
        "ticker": ticker,
        "value_basis": value_basis,
        "enterprise_value": {k: round(v, 0) for k, v in ev.items()},
        "equity_value": ({k: round(v, 0) for k, v in equity.items()} if bridge_complete else None),
        "value_per_share": value_per_share,
        # scenario weights are analyst-assigned, NOT empirically estimated probabilities
        "scenario_weighted_per_share": scenario_weighted_ps,
        "current_price": current_price,
        "implied_upside": upside,
        "terminal_value_concentration": tvc,
        "assumptions": {
            "fcf_base": round(fcf0), "fcf_source": fcf_source,
            "fcff_inputs": {"ebit": ebit, "tax_rate": round(tax_rate, 4),
                            "tax_basis": tax_basis, "d_and_a": dna,
                            "capex": capex_outflow, "change_in_nwc": dnwc,
                            "dnwc_note": dnwc_flag},
            "model": "two-stage: linear growth fade over horizon, then Gordon terminal",
            "high_growth": hg, "terminal_growth": tg, "horizon_years": n, "discount_rate": r,
            "scenario_deltas": {"bear": a["bear_delta"], "base": a["base_delta"], "bull": a["bull_delta"]},
            "weights": w,
            "weight_basis": "analyst-assigned scenario weights; not empirically estimated probabilities",
            "net_debt": net_debt,
            "net_debt_bridge_status": bridge_status,
            "net_debt_note": bridge_note,
        },
        "computed_by": "run_dcf v2 (python)",
    }


# --- peer_outlier_check ---------------------------------------------------

def _pe_for(ticker: str) -> float | None:
    """Fetch a peer's market cap and net income via the data layer, return P/E.
    Only positive earnings yield a meaningful P/E."""
    fin = data.get_financials({"ticker": ticker})
    prices = data.get_prices({"ticker": ticker})
    ni = fin.get("financials", {}).get("net_income") if "financials" in fin else None
    mcap = prices.get("market_cap") if "error" not in prices else None
    if ni is not None and ni > 0 and mcap:
        return mcap / ni
    return None


def peer_outlier_check(tool_input: dict, state=None) -> dict:
    """
    Is the target's P/E an outlier vs an EXPLICIT peer set? Peer SELECTION is an
    analyst input. Robust median/MAD modified-z is the primary verdict; mean/z is
    a secondary comparison. Negative-earnings peers (no meaningful P/E) are dropped.
    """
    ticker = tool_input["ticker"].upper()
    if state is not None and state.ticker and ticker != state.ticker.upper():
        return {"error": f"ticker mismatch: run is for '{state.ticker}', "
                         f"peer_outlier_check requested '{ticker}'", "ticker": ticker}
    peers = [p.upper() for p in tool_input.get("peers", []) if p]
    peers = [p for p in dict.fromkeys(peers) if p != ticker]   # dedup + drop self
    metric = tool_input.get("metric", "pe")
    if metric != "pe":
        return {"error": "peer_outlier_check: only 'pe' supported", "ticker": ticker}
    if len(peers) < 2:
        return {"error": "peer_outlier_check needs at least 2 distinct peers", "ticker": ticker}

    prices, _ = _upstream(state, "get_prices", ticker)
    fin, _ = _upstream(state, "get_financials", ticker)
    target_ni = fin["financials"].get("net_income") if fin and "financials" in fin else None
    target_mcap = prices.get("market_cap") if prices else None
    if target_ni is None or target_ni <= 0 or not target_mcap:
        return {"error": "peer_outlier_check needs the target's positive earnings + market cap",
                "ticker": ticker,
                "note": ("target P/E not meaningful (non-positive earnings)"
                         if (target_ni is not None and target_ni <= 0) else None)}
    target_pe = target_mcap / target_ni

    # Compute peer P/Es at FULL precision; round only for display.
    peer_pes_full = {}
    for p in peers:
        pe = _pe_for(p)
        if pe is not None:
            peer_pes_full[p] = pe
    peer_pes = {p: round(v, 2) for p, v in peer_pes_full.items()}

    values = list(peer_pes_full.values())
    if len(values) < 2:
        return {"error": "could not compute meaningful P/E for enough peers",
                "ticker": ticker, "peer_pes": peer_pes}

    # PRIMARY: robust stats (median + MAD, Iglewicz-Hoaglin modified z).
    median = statistics.median(values)
    abs_devs = [abs(v - median) for v in values]
    mad = statistics.median(abs_devs)
    if mad > 0:
        modified_z = 0.6745 * (target_pe - median) / mad
        robust_outlier = abs(modified_z) > 3.5
    else:
        modified_z = None
        robust_outlier = None

    # SECONDARY: mean-based, for comparison.
    mean = statistics.mean(values)
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    z = (target_pe - mean) / stdev if stdev else None
    mean_outlier = bool(z is not None and abs(z) > 2)

    # Divergence between robust and mean-based readings -> distrust the mean.
    skew_present = bool(mean and median and abs(mean - median) / abs(median) > 0.15)
    skew_note = (
        f"peer mean ({round(mean,2)}) and median ({round(median,2)}) diverge >15% — "
        f"mean likely skewed by an extreme peer; trust the median."
    ) if skew_present else None

    binary_flip = (robust_outlier is not None) and (robust_outlier != mean_outlier)
    divergence = bool(binary_flip or skew_present)
    divergence_reason = None
    if divergence:
        reasons = []
        if binary_flip:
            reasons.append("robust vs mean-based outlier verdicts disagree")
        if skew_present:
            reasons.append("mean skewed vs median")
        divergence_reason = "; ".join(reasons)

    is_outlier = robust_outlier if robust_outlier is not None else mean_outlier

    return {
        "ticker": ticker,
        "metric": "pe",
        "target_pe": round(target_pe, 2),
        "peer_pes": peer_pes,
        "n_peers": len(peer_pes),
        "peer_median": round(median, 2),
        "peer_mad": round(mad, 2),
        "modified_z": round(modified_z, 2) if modified_z is not None else None,
        "is_outlier": is_outlier,
        "verdict_basis": "median/MAD modified-z (robust)" if robust_outlier is not None
                         else "mean/z (MAD was zero)",
        "peer_mean": round(mean, 2),
        "peer_stdev": round(stdev, 2),
        "z_score": round(z, 2) if z is not None else None,
        "mean_based_outlier": mean_outlier,
        "verdict_divergence": divergence,
        "divergence_reason": divergence_reason,
        "skew_note": skew_note,
        "caveat": "peer selection is an analyst input; robust stats still noisy below ~5 peers",
        "computed_by": "peer_outlier_check (python, median/MAD primary)",
    }
