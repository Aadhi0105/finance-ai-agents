"""
Working memory for one agent run.

Component #4 in the spec (§3.1): accumulates fetched data + intermediate
computations across loop iterations so later steps can see earlier ones. It is
deliberately dumb — a keyed store plus an append-only trace — because the
intelligence lives in the model and the determinism lives in the tools. State
just remembers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunState:
    ticker: str
    # Every tool result, keyed by tool name (last write wins for a given tool).
    results: dict[str, Any] = field(default_factory=dict)
    # Human-readable, append-only record of what happened, in order.
    trace: list[str] = field(default_factory=list)

    def record_tool(self, name: str, tool_input: dict, output: Any) -> None:
        self.results[name] = output
        self.trace.append(f"TOOL  {name}({tool_input}) -> {output!r}")

    def record_note(self, text: str) -> None:
        self.trace.append(f"NOTE  {text}")

    def print_trace(self) -> None:
        print("\n----- RUN TRACE -----")
        for line in self.trace:
            print(line)
        print("----- END TRACE -----\n")
