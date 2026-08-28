"""
MCP client shim for Agent 2.

Exposes anomaly_significance_check / drift_check / breach_probability with the
SAME signatures as tools/statistical_checks.py — but each call goes over the MCP
stdio protocol to mcp_server/server.py instead of importing the function. So
switching run_cycle from local to MCP is a one-line import swap.

The MCP client is async and the server is a subprocess; run_cycle is sync and
calls the checks many times. So we run ONE background asyncio loop in a daemon
thread, open ONE persistent stdio session to the server on it, and marshal each
sync call onto that loop. The subprocess is spawned once, not per call.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import atexit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class _McpStatsClient:
    """Singleton persistent connection to the stats MCP server."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._session = None
        self._ready = threading.Event()
        # Open the session on the background loop.
        asyncio.run_coroutine_threadsafe(self._open(), self._loop)
        self._ready.wait(timeout=30)
        atexit.register(self.close)

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = _McpStatsClient()
        return cls._instance

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _open(self):
        # Spawn `python -m mcp_server.server` as the stdio server subprocess.
        params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"])
        self._cm = stdio_client(params)
        read, write = await self._cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        self._ready.set()

    def call(self, name: str, arguments: dict) -> dict:
        fut = asyncio.run_coroutine_threadsafe(self._call(name, arguments), self._loop)
        return fut.result(timeout=30)

    async def _call(self, name: str, arguments: dict) -> dict:
        resp = await self._session.call_tool(name, arguments)
        # The server returns a single TextContent with JSON.
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                return json.loads(block.text)
        return {"error": "no text content in MCP response"}

    def close(self):
        try:
            asyncio.run_coroutine_threadsafe(self._close(), self._loop).result(timeout=10)
        except Exception:
            pass

    async def _close(self):
        try:
            await self._session_cm.__aexit__(None, None, None)
            await self._cm.__aexit__(None, None, None)
        except Exception:
            pass


# --- sync wrappers with signatures identical to tools/statistical_checks.py ---

def anomaly_significance_check(values, min_obs: int = 6, z_flag: float = 3.5) -> dict:
    return _McpStatsClient.get().call(
        "anomaly_significance_check",
        {"values": list(values), "min_obs": min_obs, "z_flag": z_flag})


def drift_check(times, values, min_obs: int = 6,
                threshold=None, direction=None) -> dict:
    args = {"times": list(times), "values": list(values), "min_obs": min_obs}
    if threshold is not None:
        args["threshold"] = threshold
    if direction is not None:
        args["direction"] = direction
    return _McpStatsClient.get().call("drift_check", args)


def breach_probability(values, threshold, direction, horizon: int = 6,
                       min_obs: int = 6, tail_at: float = 0.25) -> dict:
    return _McpStatsClient.get().call(
        "breach_probability",
        {"values": list(values), "threshold": threshold, "direction": direction,
         "horizon": horizon, "min_obs": min_obs, "tail_at": tail_at})


# Agent 3's tool, served by the SAME server over the SAME session — the literal
# proof that this is one shared spine, not per-agent plumbing.
def run_event_study(events, event_type: str = "unspecified",
                    placebo_events=None) -> dict:
    args = {"events": events, "event_type": event_type}
    if placebo_events is not None:
        args["placebo_events"] = placebo_events
    return _McpStatsClient.get().call("run_event_study", args)
