"""Agent 1 financial contract: base currency units, annual periods, finite scalars.

Working capital is a balance change: positive means cash absorbed, hence it is
SUBTRACTED in FCFF. Provider cash-flow contributions must be negated at ingestion.
No implicit FX, ADR-ratio, or major/minor quote-unit conversion is performed.
"""

import math
from datetime import date
from functools import wraps


def finite(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def checked_output(function):
    """Keep arithmetic overflow out of published financial results (strict JSON)."""
    def nonfinite(value):
        if isinstance(value, dict):
            return any(nonfinite(v) for v in value.values())
        if isinstance(value, (tuple, list)):
            return any(nonfinite(v) for v in value)
        return isinstance(value, (float, int)) and not isinstance(value, bool) and not finite(value)

    @wraps(function)
    def checked(tool_input, state=None):
        try:
            result = function(tool_input, state)
            if not nonfinite(result):
                return result
        except (OverflowError, ZeroDivisionError):
            pass
        return {"ticker": tool_input.get("ticker"),
                "error": "financial arithmetic produced non-finite results; revise inputs"}
    return checked


def currency_valid(currency):
    return isinstance(currency, str) and len(currency) == 3 and currency.isalpha() and currency.isupper()


def number(value):
    """Provider scalar -> JSON-safe float or explicit missingness; preserve zero."""
    if value is None or isinstance(value, (bool, str)):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def annual_pair(current, prior):
    try:
        current, prior = date.fromisoformat(current), date.fromisoformat(prior)
        # Allows 52/53-week fiscal calendars, refuses stub/quarterly periods.
        return 350 <= (current - prior).days <= 380
    except (ValueError, TypeError):
        return False


def financial_error(financials):
    if not currency_valid(financials.get("currency")) or financials.get("monetary_unit") != "base":
        return "financial statements require reporting currency and base monetary units"
    if financials.get("period_type") != "annual":
        return "financial statements must use annual periods"
    try:
        date.fromisoformat(financials["period"])
    except (KeyError, TypeError, ValueError):
        return "financial statements require an ISO statement date"
    periods = financials.get("statement_periods")
    if not isinstance(periods, dict) or periods.get("income") != financials["period"]:
        return "statement_periods must identify the income statement date"
    for name, period in periods.items():
        if period is not None and period != financials["period"]:
            return f"{name} period {period} differs from income period {financials['period']}"
    numeric = ("revenue", "gross_profit", "operating_income", "net_income", "revenue_prior",
               "ebit", "depreciation_amortization", "capex", "tax_provision", "pretax_income",
               "change_in_working_capital", "total_debt", "cash_and_equivalents", "free_cash_flow")
    for key in numeric:
        value = financials.get(key)
        if value is not None and not finite(value):
            return f"{key} must be finite numeric data or None"
    if financials.get("capex") is not None and financials.get("capex_convention") != "outflow_magnitude":
        return "capex must declare outflow_magnitude convention"
    for key in ("total_debt", "cash_and_equivalents", "depreciation_amortization", "capex"):
        if financials.get(key) is not None and financials[key] < 0:
            return f"{key} must be non-negative"
    return None


def price_error(prices, financials):
    if not currency_valid(prices.get("currency")) or prices.get("monetary_unit") != "base":
        return "prices require quote currency and base monetary units"
    if prices["currency"] != financials.get("currency"):
        return "reporting and quote currencies differ; explicit FX normalization required"
    for key in ("market_cap", "current_price", "shares_outstanding"):
        value = prices.get(key)
        if value is not None and (not finite(value) or value <= 0):
            return f"{key} must be finite and positive"
    # Detect many ADR/share-unit and stale quote mismatches without guessing a ratio.
    cap, price, shares = (prices.get(k) for k in ("market_cap", "current_price", "shares_outstanding"))
    if all(v is not None for v in (cap, price, shares)):
        if not math.isclose(cap, price * shares, rel_tol=0.05):
            return "market cap differs from price × shares by >5%; share/quote basis must be reconciled"
    return None
