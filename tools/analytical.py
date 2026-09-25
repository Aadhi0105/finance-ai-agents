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
import math
from tools.financial_contract import finite, financial_error, price_error, annual_pair, checked_output
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
    if res.get("error"):
        return None, {"error": f"{name} failed: {res['error']}"}
    return res, None


# --- compute_ratios -------------------------------------------------------

@checked_output
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
    if financial_error(f):
        return {"ticker": ticker, "error": financial_error(f)}

    revenue = f.get("revenue")
    gross_profit = f.get("gross_profit")
    operating_income = f.get("operating_income")
    ebit = f.get("ebit")
    ebit_basis = "reported EBIT"
    if ebit is None:
        ebit = operating_income
        ebit_basis = "operating income proxy (EBIT unavailable)"
    net_income = f.get("net_income")
    revenue_prior = f.get("revenue_prior")

    def _ratio(numer, denom):
        if numer is None or denom is None or denom <= 0:
            return None
        return round(numer / denom, 4)

    ratios = {
        "gross_margin": _ratio(gross_profit, revenue),
        "operating_margin": _ratio(operating_income, revenue),
        "net_margin": _ratio(net_income, revenue),
        "revenue_growth_yoy": (
            _ratio(revenue - revenue_prior, revenue_prior)
            if (revenue is not None and revenue_prior is not None and revenue_prior > 0
                and annual_pair(f.get("period"), f.get("prior_period"))) else None
        ),
    }

    prices, perr = _upstream(state, "get_prices", ticker)
    assumptions = {"ebit_basis": f.get("ebit_basis", ebit_basis)}
    if ratios["revenue_growth_yoy"] is None:
        assumptions["revenue_growth_yoy"] = "requires positive prior revenue and comparable consecutive annual periods"
    if prices and price_error(prices, f):
        return {"ticker": ticker, "error": price_error(prices, f)}
    if perr and state and "get_prices" in state.results:
        return {**perr, "ticker": ticker}
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
            if ebit is None:
                ratios["ev_ebit"] = None
                multiple_status["ev_ebit"] = "not_computable_no_ebit"
            elif ebit <= 0:
                ratios["ev_ebit"] = None
                multiple_status["ev_ebit"] = "not_meaningful_negative_ebit"
            else:
                ratios["ev_ebit"] = round(ev / ebit, 4)
    else:
        assumptions["multiples"] = "P/E and EV/EBIT skipped: market cap unavailable (get_prices missing or incomplete)"

    return {
        "ticker": ticker,
        "ratios": ratios,
        "multiple_status": multiple_status,
        "assumptions": assumptions,
        "currency": f["currency"], "period": f["period"],
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
    if not (type(n) is int and 1 <= n <= 30):
        return f"horizon_years must be an integer in [1, 30], got {n}"
    if not (finite(r) and r > 0):
        return f"discount_rate must be > 0, got {r}"
    if not finite(tg) or tg <= -1:
        return f"terminal_growth must be > -1, got {tg}"
    if r <= tg:
        return (f"discount_rate ({r}) must exceed terminal_growth ({tg}) — "
                f"Gordon terminal value diverges otherwise")
    if not finite(hg) or hg <= -1:
        return f"high_growth must be > -1, got {hg}"
    return None


def _two_stage_ev(fcf0, high_g, term_g, r, n):
    """Two-stage DCF -> enterprise value, plus terminal-value concentration."""
    pv = 0.0
    fcf_t = fcf0
    for t in range(1, n + 1):
        g_t = high_g + (term_g - high_g) * (t - 1) / (n - 1) if n > 1 else high_g
        fcf_t = fcf_t * (1 + g_t)
        pv += fcf_t / (1 + r) ** t
    tv = fcf_t * (1 + term_g) / (r - term_g)
    pv_tv = tv / (1 + r) ** n
    ev = pv + pv_tv
    tv_concentration = round(pv_tv / ev, 4) if ev else None
    return ev, tv_concentration


@checked_output
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
    prices, perr = _upstream(state, "get_prices", ticker)
    f = fin["financials"]
    ferr = financial_error(f)
    if ferr:
        return {"ticker": ticker, "error": ferr}
    if perr and state and "get_prices" in state.results:
        return {**perr, "ticker": ticker}
    if prices and price_error(prices, f):
        return {"ticker": ticker, "error": price_error(prices, f)}
    warnings = list(fin.get("warnings", []))
    if f.get("working_capital_basis"):
        warnings.append(f["working_capital_basis"])


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
    override_tax = tool_input.get("tax_rate")
    if override_tax is not None:
        if not finite(override_tax) or not 0 <= override_tax <= 1:
            return {"ticker": ticker, "error": "tax_rate must be finite in [0, 1]"}
        tax_rate, tax_basis = override_tax, "analyst-supplied tax rate"
    elif (tax_prov is not None and pretax is not None and pretax > 0
          and 0 <= tax_prov / pretax <= 1):
        tax_rate = tax_prov / pretax
        tax_basis = "effective (tax provision / positive pretax income); no silent clamp"
    else:
        tax_rate = 0.25
        tax_basis = "default 25% (usable effective tax rate unavailable)"
        warnings.append(tax_basis)

    dnwc = f.get("change_in_working_capital")
    dnwc_flag = None
    if dnwc is None:
        dnwc = 0.0
        dnwc_flag = "change in working capital unavailable — assumed 0"
        warnings.append(dnwc_flag)
    elif f.get("working_capital_convention") != "balance_change":
        return {"ticker": ticker, "error": "working capital must declare balance_change convention"}

    capex_outflow = capex              # normalized positive outflow at the data boundary
    fcf0 = ebit * (1 - tax_rate) + dna - capex_outflow - dnwc
    fcf_source = "FCFF = EBIT*(1-T) + D&A - CapEx - dNWC (unlevered, python)"
    if not finite(fcf0):
        return {"ticker": ticker, "error": "FCFF arithmetic overflow"}
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

    weights = tool_input.get("weights", a["weights"])
    if (not isinstance(weights, dict) or set(weights) != {"bear", "base", "bull"}
        or any(not finite(v) or v < 0 for v in weights.values())
        or not math.isclose(sum(weights.values()), 1.0, rel_tol=0, abs_tol=1e-12)):
        return {"ticker": ticker, "error": "weights must contain bear/base/bull, be finite non-negative and sum to 1"}
    a["weights"] = weights
    ev, tvc, scen_growth = {}, {}, {}
    for scen, delta in (("bear", a["bear_delta"]), ("base", a["base_delta"]), ("bull", a["bull_delta"])):
        scen_hg = hg + delta
        # each scenario's high_growth must also stay sane
        if scen_hg <= -1:
            return {"error": f"run_dcf: {scen} high_growth {scen_hg} <= -1", "ticker": ticker}
        try:
            e, c = _two_stage_ev(fcf0, scen_hg, tg, r, n)
        except (OverflowError, ZeroDivisionError):
            return {"ticker": ticker, "error": "DCF arithmetic overflow; revise assumptions"}
        if not finite(e) or (c is not None and not finite(c)):
            return {"ticker": ticker, "error": "DCF produced non-finite results; revise assumptions"}
        ev[scen], tvc[scen] = e, c
        scen_growth[scen] = round(scen_hg, 4)

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
    if shares is None:
        warnings.append("shares unavailable; per-share valuation not computable")
    if current_price is None:
        warnings.append("current price unavailable; implied upside not computable")

    # EQUITY-DERIVED figures are only meaningful when the bridge is COMPLETE.
    # With an incomplete bridge we have enterprise value only — computing an
    # "EV per share" and comparing it to the equity share price is economically
    # meaningless (it ignores net debt), so those fields are None. We report
    # enterprise value only.
    if bridge_complete:
        per_share = {k: (v / shares if shares else None) for k, v in equity.items()}
        weighted_equity = sum(equity[k] * w[k] for k in equity)
        weighted_ps = weighted_equity / shares if shares else None
        upside = round(weighted_ps / current_price - 1, 4) if (weighted_ps is not None and current_price is not None) else None
        value_per_share = {k: (round(v, 2) if v is not None else None) for k, v in per_share.items()}
        scenario_weighted_ps = round(weighted_ps, 2) if weighted_ps is not None else None
    else:
        value_per_share = None
        scenario_weighted_ps = None
        upside = None

    distressed = bridge_complete and any(v < 0 for v in equity.values())
    if distressed:
        warnings.append("negative residual equity in one or more scenarios: distress indication, not a tradable negative share price")
        value_per_share = {k: v if equity[k] >= 0 else None for k, v in value_per_share.items()}
        scenario_weighted_ps, upside = None, None
    return {
        "ticker": ticker, "currency": f["currency"], "period": f["period"],
        "warnings": warnings, "applicability": "distressed_equity" if distressed else "positive_fcff_model",
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
            "fcf_base": fcf0, "ebit_basis": f.get("ebit_basis", "reported EBIT"), "fcf_source": fcf_source,
            "fcff_inputs": {"ebit": ebit, "tax_rate": round(tax_rate, 4),
                            "tax_basis": tax_basis, "d_and_a": dna,
                            "capex": capex_outflow, "change_in_nwc": dnwc,
                            "dnwc_note": dnwc_flag},
            "model": "two-stage: linear growth fade over horizon, then Gordon terminal",
            "high_growth": hg, "terminal_growth": tg, "horizon_years": n, "discount_rate": r,
            "discount_rate_basis": "analyst-supplied WACC assumption; not a calculated company WACC",
            "scenario_deltas": {"bear": a["bear_delta"], "base": a["base_delta"], "bull": a["bull_delta"]},
            # per-scenario high-growth rates (base + delta) — first-class so a note
            # citing "16% bull-case growth" grounds against a genuinely computed value.
            "scenario_high_growth": scen_growth,
            "weights": w,
            "weight_basis": "analyst-assigned scenario weights; not empirically estimated probabilities",
            "net_debt": net_debt,
            "net_debt_bridge_status": bridge_status,
            "net_debt_note": bridge_note,
        },
        "computed_by": "run_dcf v2 (python)",
    }


# --- peer_outlier_check ---------------------------------------------------

def _peer_record(ticker):
    try:
        fin = data.get_financials({"ticker": ticker})
        prices = data.get_prices({"ticker": ticker})
        f = fin.get("financials", {})
        error = fin.get("error") or prices.get("error") or financial_error(f) or price_error(prices, f)
        ni, cap = f.get("net_income"), prices.get("market_cap")
        if not error and (ni is None or ni <= 0 or cap is None):
            error = "positive earnings and market cap required"
        return {"pe": cap / ni if not error else None, "reason": error,
                "period": f.get("period"), "currency": f.get("currency"),
                "price_as_of": prices.get("as_of"),
                "financials": fin if not error else None, "prices": prices if not error else None}
    except Exception as exc:
        return {"pe": None, "reason": f"provider failure ({type(exc).__name__})"}


def _pe_for(ticker: str) -> float | None:
    return _peer_record(ticker)["pe"]


@checked_output
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
    raw_peers = tool_input.get("peers", [])
    if not isinstance(raw_peers, list) or any(not isinstance(p, str) for p in raw_peers):
        return {"ticker": ticker, "error": "peers must be a list of ticker strings"}
    peers = [p.strip().upper() for p in raw_peers if p.strip()]
    peers = [p for p in dict.fromkeys(peers) if p != ticker]   # dedup + drop self
    metric = tool_input.get("metric", "pe")
    if metric != "pe":
        return {"error": "peer_outlier_check: only 'pe' supported", "ticker": ticker}
    if len(peers) < 2:
        return {"error": "peer_outlier_check needs at least 2 distinct peers", "ticker": ticker}

    prices, perr = _upstream(state, "get_prices", ticker)
    fin, ferr = _upstream(state, "get_financials", ticker)
    if perr or ferr:
        return {**(perr or ferr), "ticker": ticker}
    f = fin.get("financials", {})
    error = financial_error(f) or price_error(prices, f)
    if error:
        return {"ticker": ticker, "error": error}
    target_ni = fin["financials"].get("net_income") if fin and "financials" in fin else None
    target_mcap = prices.get("market_cap") if prices else None
    if target_ni is None or target_ni <= 0 or not target_mcap:
        return {"error": "peer_outlier_check needs the target's positive earnings + market cap",
                "ticker": ticker,
                "note": ("target P/E not meaningful (non-positive earnings)"
                         if (target_ni is not None and target_ni <= 0) else None)}
    target_pe = target_mcap / target_ni

    # Compute peer P/Es at FULL precision; round only for display.
    peer_pes_full, excluded, evidence = {}, {}, {}
    for p in peers:
        record = _peer_record(p)
        evidence[p] = record
        if record["pe"] is not None:
            peer_pes_full[p] = record["pe"]
        else:
            excluded[p] = record["reason"]
    peer_pes = {p: round(v, 2) for p, v in peer_pes_full.items()}

    values = list(peer_pes_full.values())
    if len(values) < 2:
        return {"error": "could not compute meaningful P/E for enough peers",
                "ticker": ticker, "peer_pes": peer_pes, "excluded_peers": excluded, "peer_evidence": evidence}

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
    mean_outlier = abs(z) > 2 if z is not None else None

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
    basis = "median/MAD modified-z (robust)" if robust_outlier is not None else "mean/z (MAD was zero)"
    if mad == 0 and stdev == 0:
        # No finite standardized score exists. Report the deviation explicitly;
        # do not present a false statistical all-clear or invent an infinite z.
        is_outlier = None
        basis = "indeterminate: zero peer dispersion"
    comparison_status = "insufficient_dispersion" if is_outlier is None else "screening_only"

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
        "verdict_basis": basis, "comparison_status": comparison_status,
        "deviation_from_median": round(target_pe / median - 1, 4),
        "excluded_peers": excluded, "peer_evidence": evidence,
        "target_period": f["period"], "target_price_as_of": prices.get("as_of"),
        "peer_mean": round(mean, 2),
        "peer_stdev": round(stdev, 2),
        "z_score": round(z, 2) if z is not None else None,
        "mean_based_outlier": mean_outlier,
        "verdict_divergence": divergence,
        "divergence_reason": divergence_reason,
        "skew_note": skew_note,
        "warnings": (["fewer than 5 usable peers; screening statistics are fragile"] if len(values) < 5 else [])
                    + (["peer fiscal periods differ; annual P/E comparison is not period-aligned"]
                       if any(record.get("period") != f["period"] for record in evidence.values() if record.get("pe") is not None) else []),
        "caveat": "peer selection is an analyst input; annual earnings are not TTM; statistics do not establish economic comparability",
        "computed_by": "peer_outlier_check (python, median/MAD primary)",
    }


# --- compute_derived ------------------------------------------------------

@checked_output
def compute_derived(tool_input: dict, state=None) -> dict:
    """
    Compute a FIXED MENU of named derived comparison figures — deterministically —
    so the written note can CITE them (grounded) instead of computing them in the
    model's head. Narrow by design: every metric is a named, hand-verified formula,
    not a general "compute any ratio" interface (which would ground an arbitrary,
    possibly-wrong, model-chosen formula and defeat the auditability guarantee).

    Metrics (each returned only when its inputs are available):
      - consensus_implied_revenue_growth : (+1y / 0y - 1) from consensus revenue
        estimates — what analysts imply for next-year growth.
      - valuation_gap : the DCF's implied upside/downside vs price (surfaces
        run_dcf's own implied_upside so the note cites it, not a re-derivation).
      - growth_vs_history : consensus-implied growth MINUS the company's historical
        revenue CAGR — the exact comparison the model reaches for.

    The LLM decides WHICH comparison to make; Python computes the number. Every
    output lands in the run record and grounds against the note.
    """
    ticker = tool_input["ticker"].upper()
    if state is not None and state.ticker and ticker != state.ticker.upper():
        return {"error": f"ticker mismatch: run is for '{state.ticker}', "
                         f"compute_derived requested '{ticker}'", "ticker": ticker}

    out = {"ticker": ticker, "computed_by": "compute_derived (python)"}
    metrics = {}

    # consensus-implied next-year revenue growth
    cons, _ = _upstream(state, "get_consensus", ticker)
    implied_growth = None
    if cons and cons.get("available") and cons.get("consensus"):
        rev = cons["consensus"].get("revenue_estimate_avg", {}) or {}
        y0, y1 = rev.get("0y"), rev.get("+1y")
        if finite(y0) and y0 > 0 and finite(y1) and y1 > 0:
            implied_growth = y1 / y0 - 1
            metrics["consensus_implied_revenue_growth"] = {
                "value": round(implied_growth, 4), "as_pct": round(implied_growth * 100, 1),
                "basis": "consensus revenue_estimate_avg: (+1y / 0y) - 1",
                "inputs": {"revenue_0y": y0, "revenue_1y": y1}}

    # valuation gap (surface the DCF's implied_upside for citation)
    dcf, _ = _upstream(state, "run_dcf", ticker)
    if dcf and finite(dcf.get("implied_upside")):
        up = dcf["implied_upside"]
        metrics["valuation_gap"] = {
            "value": up, "as_pct": round(up * 100, 1),
            "basis": "run_dcf scenario-weighted value vs current price",
            "direction": "upside" if up > 0 else "downside" if up < 0 else "at_value"}

    # consensus-implied growth vs the company's own historical CAGR
    trend, _ = _upstream(state, "get_historical_trend", ticker)
    hist_cagr = trend.get("revenue_cagr") if trend else None
    if implied_growth is not None and finite(hist_cagr):
        delta = round(implied_growth - hist_cagr, 4)
        metrics["growth_vs_history"] = {
            "value": delta, "percentage_points": round(delta * 100, 1),
            "unit": "percentage_points",
            "consensus_implied_growth": implied_growth,
            "historical_cagr": hist_cagr,
            "basis": "consensus-implied next-year growth MINUS historical revenue CAGR",
            "reading": ("consensus implies faster growth than history" if delta > 0
                        else "consensus implies slower growth than history" if delta < 0
                        else "consensus growth equals historical growth")}

    if not metrics:
        return {**out, "metrics": {}, "note": "no derived metrics computable "
                "(need consensus and/or a completed DCF / historical trend first)"}
    out["metrics"] = metrics
    return out
