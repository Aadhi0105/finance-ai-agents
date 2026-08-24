"""
Agent 1 — Equity Research (SKELETON).

Run modes:
    python run.py                 -> OFFLINE. Scripted StubModel + fixture data.
                                     Proves the loop plumbing deterministically,
                                     no API key, no network. This is the §3.2
                                     "prove the trace prints" check.

    python run.py --live ASML.AS  -> LIVE. Real Anthropic model decides the tool
                                     sequence; data from yfinance. Requires
                                     ANTHROPIC_API_KEY and `pip install anthropic
                                     yfinance`.

The point of the offline mode: the loop, the tools, the state, and the
tool-use protocol are all identical across modes. Only the model and the data
source change. If the trace prints correctly offline, the mechanics are sound
before a single live token is spent.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
load_dotenv()

from agent.loop import run_agent
from agent.state import RunState
from agent.models import StubModel, AnthropicModel, ModelResponse, TextBlock, ToolUseBlock
from tools.registry import ToolRegistry


SYSTEM = (
    "You are an equity-research agent. Produce a defensible fundamental view on "
    "the given ticker. You must NOT compute any numbers yourself: call the tools "
    "for every figure, read their results, then write the view. Available tools: "
    "get_financials (fetch raw figures), compute_ratios (turn them into margins "
    "and growth). Finish with a short written note."
)


def build_offline_script(ticker: str):
    """
    A fixed 3-turn script that exercises the full loop:
      turn 0: call get_financials(ticker)
      turn 1: call compute_ratios(ticker)   (reads the fetched financials)
      turn 2: emit a final written note that references the computed ratios
    Each turn is a plain function of the current messages, so it's deterministic
    and needs no model. This stands in for what Claude will decide on the live path.
    """

    def turn0(messages) -> ModelResponse:
        return ModelResponse(
            stop_reason="tool_use",
            content=[ToolUseBlock(id="t0", name="get_financials", input={"ticker": ticker})],
        )

    def turn1(messages) -> ModelResponse:
        return ModelResponse(
            stop_reason="tool_use",
            content=[ToolUseBlock(id="t1", name="compute_ratios", input={"ticker": ticker})],
        )

    def turn2(messages) -> ModelResponse:
        # In offline mode we can't have a real model write prose, so we emit a
        # deterministic placeholder note. The live path replaces this with Claude's
        # synthesis over the same tool results.
        return ModelResponse(
            stop_reason="end_turn",
            content=[TextBlock(text=(
                f"[stub note] View on {ticker}: ratios computed deterministically by "
                f"compute_ratios (see trace). Live mode replaces this text with the "
                f"model's written note over the same figures."
            ))],
        )

    return [turn0, turn1, turn2]


def run_offline(ticker: str = "ASML.AS") -> None:
    os.environ.setdefault("AGENT_DATA_SOURCE", "fixture")
    state = RunState(ticker=ticker)
    registry = ToolRegistry(state)
    model = StubModel(script=build_offline_script(ticker))

    final = run_agent(
        model=model, registry=registry, state=state,
        system=SYSTEM, goal=f"Produce a defensible fundamental view on {ticker}.",
    )

    state.print_trace()
    print("FINAL ANSWER:\n" + final)
    print("\nWORKING MEMORY (results by tool):")
    for k, v in state.results.items():
        print(f"  {k}: {v}")


def run_live(ticker: str) -> None:
    os.environ["AGENT_DATA_SOURCE"] = "yfinance"
    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("Set ANTHROPIC_API_KEY for --live mode.")
    state = RunState(ticker=ticker)
    registry = ToolRegistry(state)
    model = AnthropicModel()  # claude-sonnet-4-6 by default

    final = run_agent(
        model=model, registry=registry, state=state,
        system=SYSTEM, goal=f"Produce a defensible fundamental view on {ticker}.",
    )
    state.print_trace()
    print("FINAL ANSWER:\n" + final)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--live":
        tkr = sys.argv[2] if len(sys.argv) >= 3 else "ASML.AS"
        run_live(tkr)
    else:
        run_offline()
