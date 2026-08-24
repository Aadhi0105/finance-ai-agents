"""
The orchestrator — the agent loop (component #1, spec §3.1).

This is the ~50-line hand-rolled controller from §3.2: no LangChain, no CrewAI.
It implements the raw Anthropic tool-use protocol:

    1. Send the model: system prompt + tool menu + conversation so far.
    2. Model replies with EITHER tool_use blocks OR a final text answer.
    3. If tool_use: run each tool, append tool_result blocks, go to 1.
    4. If end_turn: return the final answer.

The loop is model-agnostic (see agent/models.py) and tool-agnostic (see
tools/registry.py). It contains no finance logic and does no math — it only
routes. That separation is what lets us prove it offline and audit it later.
"""

from __future__ import annotations

from agent.models import ModelClient, ModelResponse
from agent.state import RunState
from tools.registry import ToolRegistry


MAX_ITERS = 12  # hard stop so a misbehaving model can't spin forever


def run_agent(
    *,
    model: ModelClient,
    registry: ToolRegistry,
    state: RunState,
    system: str,
    goal: str,
) -> str:
    """Drive the loop until the model emits a final answer (or we hit MAX_ITERS)."""
    messages: list = [{"role": "user", "content": goal}]
    tools = registry.schemas()

    for iteration in range(MAX_ITERS):
        state.record_note(f"iteration {iteration}: asking model")
        resp: ModelResponse = model.respond(system=system, messages=messages, tools=tools)

        # Persist the assistant turn (both text and tool_use blocks) as-is.
        messages.append({"role": "assistant", "content": _blocks_to_api(resp.content)})

        if resp.stop_reason != "tool_use":
            final = _first_text(resp.content)
            state.record_note("model produced final answer")
            return final

        # Execute every tool the model requested this turn.
        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            output = registry.dispatch(block.name, block.input)
            state.record_tool(block.name, block.input, output)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(output),
            })
        # Feed results back as the next user turn, per the tool-use protocol.
        messages.append({"role": "user", "content": tool_results})

    state.record_note("hit MAX_ITERS without a final answer")
    return "[loop] stopped: reached iteration cap without a final answer."


# --- small helpers --------------------------------------------------------

def _blocks_to_api(blocks) -> list:
    """Convert our dataclass blocks back into API-shaped dicts for the history."""
    out = []
    for b in blocks:
        if b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        elif b.type == "text":
            out.append({"type": "text", "text": b.text})
    return out


def _first_text(blocks) -> str:
    for b in blocks:
        if b.type == "text":
            return b.text
    return ""
