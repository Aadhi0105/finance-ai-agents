"""
Analytical tools — the computation family (spec §3.1). THE DIFFERENTIATING SET.

Governing principle (applies from line one): the LLM never does the math. Every
number this repo reports comes out of a deterministic Python function like the
one below. The model decides to CALL compute_ratios and then READS the result —
it does not compute margins in its head.

SKELETON scope: one computation, `compute_ratios` (margins + revenue growth).
It intentionally needs only financials (no price yet), so the skeleton stays at
exactly one data tool. P/E, DCF, factor exposure, peer-outlier all arrive at the
next checkpoint as siblings of this function.

compute_ratios reads the financials that get_financials already put in working
memory, rather than making the model pass every figure back through a tool call.
This mirrors the real design: state carries data between steps.
"""

from __future__ import annotations


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
            if (revenue is not None and revenue_prior not in (None, 0))
            else None
        ),
    }
    return {"ticker": ticker, "ratios": ratios, "computed_by": "compute_ratios (python)"}
