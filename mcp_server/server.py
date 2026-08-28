"""
MCP server exposing the platform's SHARED analytical tools over stdio (mcp 2.x).

Why these tools, and only these (spec §3.3 MCP boundary): each has more than one
consumer. The three statistical checks are used by Agent 2 (covenant monitoring)
AND Agent 3 (event studies). run_event_study is added by Agent 3 — the server's
one growth point — and it INTERNALLY calls the shared significance family rather
than reimplementing it, so significance has one source of truth across covenants
and event studies. threshold_check, the state stores, and the data-refresh /
Track-A assembly layers stay LOCAL — putting them here would be MCP-as-decoration.

The server WRAPS the pure functions (tools/statistical_checks.py, tools/event_study.py)
— it does not reimplement them. That single source of truth is what makes the
local and MCP paths provably identical.

Two unrelated consumers (covenant monitoring + event studies) calling this one
server is the literal proof that the spine is a real abstraction, not decoration.

Run:  python -m mcp_server.server   (speaks MCP over stdin/stdout)
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from tools.statistical_checks import (
    anomaly_significance_check as _anomaly,
    drift_check as _drift,
    breach_probability as _breach,
)
from tools.event_study import run_event_study as _event_study

server = MCPServer("agent-stats")


@server.tool()
def anomaly_significance_check(values: list[float], min_obs: int = 6,
                              z_flag: float = 3.5) -> dict:
    """Robust modified z-score: is the latest value a significant outlier vs the
    item's own history?"""
    return _anomaly(values, min_obs=min_obs, z_flag=z_flag)


@server.tool()
def drift_check(times: list[float], values: list[float], min_obs: int = 6,
                threshold: float | None = None, direction: str | None = None) -> dict:
    """OLS value~time with a t-test on the slope and prediction band: is there a
    significant trend, and how many cycles to breach?"""
    return _drift(times, values, min_obs=min_obs, threshold=threshold, direction=direction)


@server.tool()
def breach_probability(values: list[float], threshold: float, direction: str,
                       horizon: int = 6, min_obs: int = 6, tail_at: float = 0.25) -> dict:
    """First-passage (barrier-crossing) probability of breaching within a horizon,
    from the series' own drift and volatility."""
    return _breach(values, threshold, direction, horizon=horizon, min_obs=min_obs, tail_at=tail_at)


@server.tool()
def run_event_study(events: list[dict], event_type: str = "unspecified",
                    placebo_events: list[dict] | None = None) -> dict:
    """Multi-event market-model CAAR study with a significance test (shared t-test
    machinery) and an always-on placebo. Added by Agent 3; reuses the significance
    family the other tools also use."""
    return _event_study(events, event_type=event_type, placebo_events=placebo_events)


if __name__ == "__main__":
    server.run("stdio")
