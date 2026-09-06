"""
Shared test setup. Every test is DETERMINISTIC and OFFLINE — no API calls, no
network — which is exactly what Agent 1's design makes possible.
"""

import os
import pytest

os.environ.setdefault("AGENT_DATA_SOURCE", "fixture")

from agent.state import RunState


def make_state(ticker="TST", financials=None, prices=None, extra=None):
    """A RunState pre-loaded with tool results, for unit-testing the analytical
    tools without running the whole loop."""
    s = RunState(ticker=ticker)
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
