"""
Agent 1 — Equity Research.

Run modes:
    python run.py                 -> OFFLINE. Scripted StubModel + fixture data.
                                     Proves the loop plumbing deterministically,
                                     no API key, no network.

    python run.py --live ASML.AS  -> LIVE. Real Anthropic model decides the tool
                                     sequence; data from yfinance. Requires
                                     ANTHROPIC_API_KEY (loaded from .env) and
                                     `pip install -r requirements.txt`.

The loop, tools, state, and tool-use protocol are identical across modes. Only
the model and the data source change.
"""

from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()  # loads ANTHROPIC_API_KEY from .env on the live path
except ImportError:
    pass  # offline path needs no key, so dotenv is optional

from agent.loop import run_agent
from agent.state import RunState
from agent.models import StubModel, AnthropicModel, ModelResponse, TextBlock, ToolUseBlock
from tools.registry import ToolRegistry


SYSTEM = (
    "You are an equity-research agent. Produce a defensible fundamental view on the "
    "given ticker. You must NOT compute any numbers yourself: call tools for every "
    "figure, read their results, then write the view.\n\n"
    "Tools: get_financials (raw figures), get_prices (price/market cap/shares), "
    "compute_ratios (margins, growth, and — once prices are fetched — P/E and EV/EBIT), "
    "run_dcf (scenario-weighted valuation, needs financials + prices), "
    "peer_outlier_check (is the P/E an outlier vs peers you supply).\n\n"
    "A sensible order: fetch financials and prices, compute ratios, run a DCF, check "
    "peers, then write a note stating a view, the evidence, and what would change it."
)

# For offline peer-outlier demo, these peers have fixtures in fixtures/.
_OFFLINE_PEERS = ["ASM.AS", "BESI.AS", "LRCX"]


def build_offline_script(ticker: str):
    """
    Scripted turns that exercise every tool through the loop, deterministically.
    Stands in for what Claude decides on the live path.
    """
    def call(tool_id, name, inp):
        return lambda messages: ModelResponse(
            stop_reason="tool_use",
            content=[ToolUseBlock(id=tool_id, name=name, input=inp)],
        )

    def final(messages):
        return ModelResponse(
            stop_reason="end_turn",
            content=[TextBlock(text=(
                f"[stub note] View on {ticker}: financials, prices, ratios, a "
                f"scenario-weighted DCF, and a peer-outlier check all computed "
                f"deterministically (see trace). Live mode replaces this text with "
                f"the model's written note over the same figures."
            ))],
        )

    return [
        call("t0", "get_financials", {"ticker": ticker}),
        call("t1", "get_prices", {"ticker": ticker}),
        call("t2", "compute_ratios", {"ticker": ticker}),
        call("t3", "run_dcf", {"ticker": ticker}),
        call("t4", "peer_outlier_check", {"ticker": ticker, "peers": _OFFLINE_PEERS}),
        final,
    ]


def _emit_artifacts(ticker: str, mode: str, note: str, state) -> None:
    """After the loop: validate, fetch chart data, write the sidecar, build the report.
    Charts are LOCKED output, not a model decision — so history is fetched here,
    outside the reasoning loop."""
    from datetime import datetime
    from tools.data import get_price_history, home_index_ticker
    from validation import gate
    import composer

    # Confidence gate: score the run's own logged outputs (deterministic).
    validation = gate.assess(state.results)
    _print_validation(validation)

    price_history = get_price_history(ticker)
    idx_ticker = home_index_ticker(ticker)
    index_history = None
    if idx_ticker:
        ih = get_price_history(idx_ticker)
        index_history = {"index_ticker": idx_ticker, "source": ih.get("source"),
                         "history": ih.get("history", [])}

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("output", f"{ticker}_{stamp}")

    sidecar_path = composer.write_sidecar(
        ticker=ticker, mode=mode, note=note, analysis=state.results,
        price_history=price_history, index_history=index_history,
        validation=validation, out_dir=out_dir,
    )
    report_path = composer.build_report(sidecar_path, out_dir)
    print(f"\nARTIFACTS:\n  {sidecar_path}\n  {report_path}\n  {os.path.join(out_dir, 'charts')}/ (5 charts)")


def _print_validation(v: dict) -> None:
    banner = "PASS" if v["verdict"] == "pass" else "⚠ FLAGGED FOR REVIEW"
    print(f"\n----- VALIDATION: {banner} "
          f"(confidence={v['confidence']}, score={v['score']}, "
          f"{v['n_pass']} pass / {v['n_warn']} warn / {v['n_fail']} fail) -----")
    for c in v["checks"]:
        if c["status"] != "pass":
            print(f"  [{c['status'].upper()}] {c['check']}: {c['detail']}")
    if v["verdict"] != "pass":
        print("  -> not for emission as-is; route to human review.")
    print("-----")


def run_offline(ticker: str = "ASML.AS") -> None:
    os.environ.setdefault("AGENT_DATA_SOURCE", "fixture")
    state = RunState(ticker=ticker)
    registry = ToolRegistry(state)
    model = StubModel(script=build_offline_script(ticker))
    final = run_agent(model=model, registry=registry, state=state,
                      system=SYSTEM, goal=f"Produce a defensible fundamental view on {ticker}.")
    state.print_trace()
    print("FINAL ANSWER:\n" + final)
    _emit_artifacts(ticker, "offline", final, state)


def run_live(ticker: str) -> None:
    os.environ["AGENT_DATA_SOURCE"] = "yfinance"
    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("Set ANTHROPIC_API_KEY (e.g. in .env) for --live mode.")
    state = RunState(ticker=ticker)
    registry = ToolRegistry(state)
    model = AnthropicModel()
    final = run_agent(model=model, registry=registry, state=state,
                      system=SYSTEM, goal=f"Produce a defensible fundamental view on {ticker}.")
    state.print_trace()
    print("FINAL ANSWER:\n" + final)
    _emit_artifacts(ticker, "live", final, state)


def rebuild(model_json_path: str) -> None:
    """Regenerate report.html from a saved model.json ALONE — no yfinance, no
    model. The proof that the report is rebuildable from the sidecar."""
    import composer
    report_path = composer.build_report(model_json_path)
    print(f"Rebuilt report from sidecar only:\n  {report_path}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--live":
        tkr = sys.argv[2] if len(sys.argv) >= 3 else "ASML.AS"
        run_live(tkr)
    elif len(sys.argv) >= 2 and sys.argv[1] == "--rebuild":
        if len(sys.argv) < 3:
            sys.exit("Usage: python run.py --rebuild output/<TICKER>_<stamp>/model.json")
        rebuild(sys.argv[2])
    else:
        run_offline()
