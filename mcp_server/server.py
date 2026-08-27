"""
MCP server exposing Agent 2's three SHARED statistical checks over stdio (mcp 2.x).

Why these three, and only these three (spec §3.3 MCP boundary): they are the
tools with a second consumer — Agent 2 uses them now, Agent 3 will use them next.
A tool that crosses a genuine boundary earns a place on the server. threshold_check,
the state store, and the data-refresh tools stay LOCAL — putting them here would
be MCP-as-decoration.

The server WRAPS the pure functions in tools/statistical_checks.py — it does not
reimplement them. That single source of truth is what makes the local and MCP
paths provably identical.

Run:  python -m mcp_server.server   (speaks MCP over stdin/stdout)
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from tools.statistical_checks import (
    anomaly_significance_check as _anomaly,
    drift_check as _drift,
    breach_probability as _breach,
)

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


if __name__ == "__main__":
    server.run("stdio")
