"""
Shared test setup. Every test is DETERMINISTIC and OFFLINE — no API calls, no
network — which is exactly what Agent 1's design makes possible.
"""

import os
import pytest

@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    """Isolate tests from ambient live-data settings; tests may override explicitly."""
    monkeypatch.setenv("AGENT_DATA_SOURCE", "fixture")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


from agent.state import RunState


def make_state(ticker="TST", financials=None, prices=None, extra=None):
    """A RunState pre-loaded with tool results, for unit-testing the analytical
    tools without running the whole loop."""
    # Explicit synthetic contract for hand-authored calculation inputs.
    s = RunState(ticker=ticker)
    if financials is not None:
        financials = {"currency": "EUR", "monetary_unit": "base", "period_type": "annual",
                      "period": "2025-12-31", "prior_period": "2024-12-31",
                      "working_capital_convention": "balance_change", "capex_convention": "outflow_magnitude",
                      "statement_periods": {"income": financials.get("period", "2025-12-31")}, **financials}
    if prices is not None:
        prices = {"currency": (financials or {}).get("currency", "EUR"),
                  "monetary_unit": "base", **prices}
    if financials is not None:
        s.results["get_financials"] = {"ticker": ticker, "financials": financials}
    if prices is not None:
        s.results["get_prices"] = {"ticker": ticker, **prices}
    for k, v in (extra or {}).items():
        s.results[k] = v
    return s


@pytest.fixture
def state_factory():
    return make_state
