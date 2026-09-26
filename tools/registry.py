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
from tools.input_validation import validate_input

TICKER_PATTERN = r"^[A-Za-z0-9^][A-Za-z0-9.^=_-]{0,31}$"


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
        "get_consensus": (
            {
                "name": "get_consensus",
                "description": "Fetch forward analyst consensus (price target, revenue/EPS estimates). "
                               "Consensus is often unavailable and returns available=false — when it "
                               "does, DO NOT guess: call get_historical_trend and compare against the "
                               "company's own trajectory instead.",
                "input_schema": {
                    "type": "object",
                    "properties": {"ticker": {"type": "string"}},
                    "required": ["ticker"],
                },
            },
            data.get_consensus,
        ),
        "get_historical_trend": (
            {
                "name": "get_historical_trend",
                "description": "Fetch the company's own multi-year revenue, net-margin trajectory and "
                               "revenue CAGR — the fallback comparison basis when consensus is "
                               "unavailable.",
                "input_schema": {
                    "type": "object",
                    "properties": {"ticker": {"type": "string"}},
                    "required": ["ticker"],
                },
            },
            data.get_historical_trend,
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
                "description": "Run a two-stage scenario-weighted DCF (bear/base/bull): growth fades "
                               "from a high starting rate to terminal over the horizon, uses real free "
                               "cash flow, and applies a net-debt bridge to return EQUITY value per share "
                               "plus implied upside vs current price. Needs get_financials and get_prices "
                               "first. Optional overrides: discount_rate, high_growth, terminal_growth, "
                               "horizon_years, tax_rate, weights. Currency and period compatibility are required.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "discount_rate": {"type": "number"},
                        "high_growth": {"type": "number", "description": "year-1 growth; fades to terminal"},
                        "terminal_growth": {"type": "number"},
                        "horizon_years": {"type": "integer", "minimum": 1, "maximum": 30},
                        "tax_rate": {"type": "number", "minimum": 0, "maximum": 1},
                        "weights": {"type": "object", "properties": {
                            k: {"type": "number", "minimum": 0, "maximum": 1}
                            for k in ("bear", "base", "bull")},
                            "required": ["bear", "base", "bull"], "additionalProperties": False},
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
                               "P/E is a statistical outlier vs the peer distribution (median/MAD, with mean/z fallback). "
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
        "compute_derived": (
            {
                "name": "compute_derived",
                "description": "Compute named derived comparison figures "
                               "deterministically so you can CITE them instead of "
                               "computing them yourself: consensus-implied revenue "
                               "growth, the DCF valuation gap, and consensus-implied "
                               "growth vs the historical CAGR. Call this for ANY "
                               "quantitative comparison. Needs get_consensus / run_dcf "
                               "/ get_historical_trend to have run first.",
                "input_schema": {
                    "type": "object",
                    "properties": {"ticker": {"type": "string"}},
                    "required": ["ticker"],
                },
            },
            analytical.compute_derived,
        ),
    }


class ToolRegistry:
    def __init__(self, state):
        self.state = state
        self._reg = _build_registry()
        for schema, _impl in self._reg.values():
            spec = schema['input_schema']
            spec['additionalProperties'] = False
            spec['properties']['ticker'].update(pattern=TICKER_PATTERN, minLength=1)
            if 'peers' in spec['properties']:
                spec['properties']['peers']['items'].update(pattern=TICKER_PATTERN, minLength=1)

    def schemas(self) -> list:
        return [schema for (schema, _impl) in self._reg.values()]

    def dispatch(self, name: str, tool_input: dict):
        if name not in self._reg:
            return {"error": f"unknown tool: {name}"}
        schema, impl = self._reg[name]
        error = validate_input(schema['input_schema'], tool_input)
        if error:
            return {"error": error, "error_type": "invalid_arguments"}
        if self.state.ticker and tool_input['ticker'].upper() != self.state.ticker.upper():
            return {"error": "ticker differs from run subject", "error_type": "ticker_mismatch"}
        pinned = self.state.configuration.get('peers')
        if name == 'peer_outlier_check' and pinned:
            supplied = [ticker.upper() for ticker in tool_input['peers']]
            expected = [ticker.upper() for ticker in pinned]
            if len(supplied) != len(set(supplied)) or set(supplied) != set(expected):
                return {"error": "peers differ from the explicitly requested set",
                        "error_type": "peer_set_mismatch"}
        return impl(tool_input, self.state)
