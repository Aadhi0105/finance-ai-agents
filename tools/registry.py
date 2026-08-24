"""
Tool registry (component #3, spec §3.1).

Holds the tool menu shown to the model (name + description + input schema) and
the dispatch table mapping a tool name to its deterministic Python impl.

Two families:
    tools/data.py       -> fetchers   (get_financials, get_prices)
    tools/analytical.py -> computations(compute_ratios, run_dcf, peer_outlier_check)
"""

from __future__ import annotations

from tools import data, analytical


def _build_registry() -> dict:
    return {
        "get_financials": (
            {
                "name": "get_financials",
                "description": "Fetch a company's recent annual financials (revenue, "
                               "gross profit, operating income, net income) for a ticker. "
                               "Raw figures only.",
                "input_schema": {
                    "type": "object",
                    "properties": {"ticker": {"type": "string", "description": "e.g. ASML.AS"}},
                    "required": ["ticker"],
                },
            },
            data.get_financials,
        ),
        "get_prices": (
            {
                "name": "get_prices",
                "description": "Fetch current price, market cap, and shares outstanding for a "
                               "ticker. Needed before P/E, DCF per-share, or peer-multiple work.",
                "input_schema": {
                    "type": "object",
                    "properties": {"ticker": {"type": "string"}},
                    "required": ["ticker"],
                },
            },
            data.get_prices,
        ),
        "compute_ratios": (
            {
                "name": "compute_ratios",
                "description": "Compute margins and growth from fetched financials; also P/E and "
                               "EV/EBIT if get_prices has run. Do NOT compute these yourself.",
                "input_schema": {
                    "type": "object",
                    "properties": {"ticker": {"type": "string"}},
                    "required": ["ticker"],
                },
            },
            analytical.compute_ratios,
        ),
        "run_dcf": (
            {
                "name": "run_dcf",
                "description": "Run a scenario-weighted DCF (bear/base/bull) and return a "
                               "probability-weighted per-share value plus implied upside vs current "
                               "price. Needs get_financials and get_prices first. Optional overrides: "
                               "discount_rate, base_growth, terminal_growth, horizon_years.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "discount_rate": {"type": "number"},
                        "base_growth": {"type": "number"},
                        "terminal_growth": {"type": "number"},
                        "horizon_years": {"type": "integer"},
                    },
                    "required": ["ticker"],
                },
            },
            analytical.run_dcf,
        ),
        "peer_outlier_check": (
            {
                "name": "peer_outlier_check",
                "description": "Given an explicit list of peer tickers, check whether the target's "
                               "P/E is a statistical outlier vs the peer distribution (z-score + IQR). "
                               "You must supply the peers — peer selection is an analyst judgment.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "peers": {"type": "array", "items": {"type": "string"},
                                  "description": "peer tickers, e.g. ['ASM.AS','BESI.AS','LRCX']"},
                        "metric": {"type": "string", "enum": ["pe"], "default": "pe"},
                    },
                    "required": ["ticker", "peers"],
                },
            },
            analytical.peer_outlier_check,
        ),
    }


class ToolRegistry:
    def __init__(self, state):
        self.state = state
        self._reg = _build_registry()

    def schemas(self) -> list:
        return [schema for (schema, _impl) in self._reg.values()]

    def dispatch(self, name: str, tool_input: dict):
        if name not in self._reg:
            return {"error": f"unknown tool: {name}"}
        _schema, impl = self._reg[name]
        return impl(tool_input, self.state)
