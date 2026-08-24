"""
Tool registry (component #3, spec §3.1).

Holds the tool menu shown to the model (name + description + input schema) and
the dispatch table that maps a tool name to its deterministic Python impl.

The two tool *families* from the spec live here as separate modules:
    tools/data.py       -> fetchers (get_financials, later: get_prices, ...)
    tools/analytical.py -> computations (compute_ratios, later: run_dcf, ...)

For the SKELETON we register exactly one of each — the minimum needed to prove
the loop can call a fetcher, feed its output to a computation, and read both
results back. Everything else is added at the next checkpoint.
"""

from __future__ import annotations

from typing import Callable

from tools import data, analytical


# Each entry: name -> (schema, impl)
def _build_registry() -> dict:
    return {
        "get_financials": (
            {
                "name": "get_financials",
                "description": (
                    "Fetch a company's recent annual financials (revenue, gross "
                    "profit, operating income, net income) for a ticker. Returns "
                    "raw figures only — no ratios, no interpretation."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "e.g. ASML.AS"}
                    },
                    "required": ["ticker"],
                },
            },
            data.get_financials,
        ),
        "compute_ratios": (
            {
                "name": "compute_ratios",
                "description": (
                    "Given a financials object (as returned by get_financials), "
                    "compute margin and growth ratios deterministically. The model "
                    "must NOT compute these itself — call this tool."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "same ticker used for get_financials"}
                    },
                    "required": ["ticker"],
                },
            },
            analytical.compute_ratios,
        ),
    }


class ToolRegistry:
    def __init__(self, state):
        # Tools can read/write working memory (e.g. compute_ratios reads the
        # financials that get_financials already stored). We pass state in so a
        # computation can consume a prior fetch without the model re-passing it.
        self.state = state
        self._reg = _build_registry()

    def schemas(self) -> list:
        return [schema for (schema, _impl) in self._reg.values()]

    def dispatch(self, name: str, tool_input: dict):
        if name not in self._reg:
            return {"error": f"unknown tool: {name}"}
        _schema, impl = self._reg[name]
        # Impls receive (tool_input, state) so analytical tools can read prior
        # results from working memory. Keeps the model's job to "which tool",
        # not "carry every number around by hand".
        return impl(tool_input, self.state)
