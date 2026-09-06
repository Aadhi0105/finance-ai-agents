"""
Working memory for one agent run.

Component #4 in the spec (§3.1): accumulates fetched data + intermediate
computations across loop iterations so later steps can see earlier ones. It is
deliberately dumb — a keyed store plus an append-only trace — because the
intelligence lives in the model and the determinism lives in the tools. State
just remembers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunState:
    ticker: str
    # Latest result per tool name — for easy dependency lookup (last write wins here,
    # deliberately: a dependent tool wants the most recent inputs).
    results: dict[str, Any] = field(default_factory=dict)
    # Append-only record of EVERY tool call, so the audit trail loses nothing even
    # when a tool is called twice (e.g. run_dcf at two discount rates). This is what
    # makes the "model.json contains every computed number" claim actually true.
    calls: list[dict] = field(default_factory=list)
    # Human-readable, append-only narrative, in order.
    trace: list[str] = field(default_factory=list)

    def record_tool(self, name: str, tool_input: dict, output: Any,
                    duration_ms: float | None = None) -> None:
        self.results[name] = output
        self.calls.append({
            "call_index": len(self.calls),
            "tool": name,
            "input": tool_input,
            "output": output,
            "duration_ms": duration_ms,
            "status": "error" if isinstance(output, dict) and output.get("error") else "success",
        })
        self.trace.append(f"TOOL  {name}({tool_input}) -> {output!r}")

    def record_note(self, text: str) -> None:
        self.trace.append(f"NOTE  {text}")

    def print_trace(self) -> None:
        print("\n----- RUN TRACE -----")
        for line in self.trace:
            print(line)
        print("----- END TRACE -----\n")
