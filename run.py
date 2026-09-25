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
    "peer_outlier_check (is the P/E an outlier vs peers you supply), "
    "get_consensus (forward analyst estimates), get_historical_trend (the company's "
    "own multi-year trajectory).\n\n"
    "IMPORTANT — comparison basis: call get_consensus to anchor your growth/valuation "
    "view against analyst expectations. Consensus is often unavailable (available=false). "
    "When it is, DO NOT invent estimates — call get_historical_trend and assess the "
    "company against its OWN multi-year trajectory instead. Always state explicitly which "
    "basis you used (analyst consensus, or own-history fallback).\n\n"
    "A sensible order: fetch financials and prices, compute ratios, run a DCF, check "
    "peers, establish a comparison basis (consensus or history), then write a note "
    "stating a view, the evidence, the basis used, and what would change it."
    "\n\n"
    "CRITICAL — numerical evidence: never type numbers, numeric words, percentages, "
    "currency amounts or multiples in your own prose. Put a named evidence marker "
    "on its OWN LINE, e.g. [[claim:operating_margin]] or [[claim:dcf_value]]. Python "
    "renders the complete sentence with company, metric, period, unit and source. "
    "Do not add your own label beside a marker. Use only available current results. "
    "Available IDs: revenue, net_income, ebit, current_price, market_cap, shares, "
    "gross_margin, operating_margin, net_margin, revenue_growth, pe, ev_ebit, "
    "dcf_value, dcf_gap, fcff, net_debt, discount_rate, initial_growth, terminal_growth, "
    "horizon, tax_rate, historical_growth, peer_median, peer_count, "
    "bear_value, base_value, bull_value, bear_ev, base_ev, bull_ev, "
    "consensus_revenue_current_year, consensus_revenue_next_year, consensus_target. "
    "For consensus_growth or growth_vs_history, call compute_derived first. "
    "Include at least one valid marker. Explain interpretation and limitations "
    "qualitatively in separate paragraphs. Unknown figures must be left out."

)

# For offline peer-outlier demo, these peers have fixtures in fixtures/.
_OFFLINE_PEERS = ["ASM.AS", "BESI.AS", "LRCX"]


def build_offline_script(ticker: str):
    """
    Scripted turns that exercise every tool through the loop, deterministically —
    INCLUDING the consensus-null branch: get_consensus returns available=false,
    so the script then calls get_historical_trend (the fallback basis). This
    stands in for the decision the live model makes.
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
                f"deterministically. Consensus was unavailable, so the comparison "
                f"basis fell back to the company's own history (see trace). Live mode "
                f"replaces this text with the model's written note over the same figures.\n"
                "[[claim:operating_margin]]\n[[claim:dcf_value]]\n[[claim:historical_growth]]"
            ))],
        )

    return [
        call("t0", "get_financials", {"ticker": ticker}),
        call("t1", "get_prices", {"ticker": ticker}),
        call("t2", "compute_ratios", {"ticker": ticker}),
        call("t3", "run_dcf", {"ticker": ticker}),
        call("t4", "peer_outlier_check", {"ticker": ticker, "peers": _OFFLINE_PEERS}),
        call("t5", "get_consensus", {"ticker": ticker}),          # returns available=false
        call("t6", "get_historical_trend", {"ticker": ticker}),   # <- the branch decision
        final,
    ]


def _emit_artifacts(ticker: str, mode: str, note: str, state) -> None:
    """After the loop: validate, fetch chart data, write the sidecar, build the report.
    Charts are LOCKED output, not a model decision — so history is fetched here,
    outside the reasoning loop."""
    from datetime import datetime
    from tools.data import get_price_history, home_index_ticker
    from validation import gate
    from validation import note_grounding
    import composer

    validation = gate.assess(state.results, calls=state.calls)
    grounding = note_grounding.ground_note(note, state.results)
    checks = validation["checks"] + [{
        "check": "note_grounding", "status": "pass" if grounding["passed"] else "fail",
        "detail": grounding["note"] if grounding["passed"] else str(grounding["unmatched"]),
    }]
    validation = gate.aggregate_checks(checks)
    validation["note_grounding"] = grounding
    note = grounding["rendered_note"]
    print("NOTE (" + validation["verdict"] + "):\n" + note)

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

    model_id = os.environ.get("AGENT_MODEL", "claude-sonnet-4-5-20250929") if mode == "live" else "StubModel"
    fin = (state.results.get("get_financials") or {}).get("financials", {}) or {}
    currency = fin.get("currency") or (state.results.get("get_prices") or {}).get("currency")

    sidecar_path = composer.write_sidecar(
        ticker=ticker, mode=mode, note=note, analysis=state.results,
        price_history=price_history, index_history=index_history,
        validation=validation, out_dir=out_dir,
        calls=state.calls, model_id=model_id, currency=currency,
    )
    report_path = composer.build_report(sidecar_path, out_dir)
    print(f"\nARTIFACTS:\n  {sidecar_path}\n  {report_path}\n  {os.path.join(out_dir, 'charts')}/ (5 charts)")


def _print_validation(v: dict) -> None:
    banner = "PASS" if v["verdict"] == "pass" else "⚠ FLAGGED FOR REVIEW"
    print(f"\n----- VALIDATION: {banner} "
          f"(confidence={v['confidence']}, score={v['score']}, "
          f"{v['n_pass']} pass / {v.get('n_info_finding',0)} finding / "
          f"{v.get('n_quality_warn',0)} quality-warn / {v['n_fail']} fail) -----")
    for c in v["checks"]:
        if c["status"] != "pass":
            print(f"  [{c['status'].upper()}] {c['check']}: {c['detail']}")
    if v["verdict"] != "pass":
        print("  -> flagged: emitted as report_REVIEW.html, not approved output.")
    print("-----")


def run_offline(ticker: str = "ASML.AS") -> None:
    os.environ.setdefault("AGENT_DATA_SOURCE", "fixture")
    state = RunState(ticker=ticker)
    registry = ToolRegistry(state)
    model = StubModel(script=build_offline_script(ticker))
    final = run_agent(model=model, registry=registry, state=state,
                      system=SYSTEM, goal=f"Produce a defensible fundamental view on {ticker}.")
    state.print_trace()
    _emit_artifacts(ticker, "offline", final, state)


def run_live(ticker: str, peers: list[str] | None = None) -> None:
    os.environ["AGENT_DATA_SOURCE"] = "yfinance"
    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("Set ANTHROPIC_API_KEY (e.g. in .env) for --live mode.")
    state = RunState(ticker=ticker)
    registry = ToolRegistry(state)
    model = AnthropicModel()
    goal = f"Produce a defensible fundamental view on {ticker}."
    if peers:
        # Pinned peer set: the model MUST use exactly these for peer_outlier_check
        # (curated comparables) rather than proposing its own, which can be
        # economically mismatched (e.g. carmakers for a rail manufacturer).
        goal += (f" For peer_outlier_check, you MUST use exactly this peer set and "
                 f"propose no others: {', '.join(peers)}.")
    final = run_agent(model=model, registry=registry, state=state,
                      system=SYSTEM, goal=goal)
    state.print_trace()
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
        peers = None
        if "--peers" in sys.argv:
            peers = sys.argv[sys.argv.index("--peers") + 1:]
        run_live(tkr, peers=peers)
    elif len(sys.argv) >= 2 and sys.argv[1] == "--rebuild":
        if len(sys.argv) < 3:
            sys.exit("Usage: python run.py --rebuild output/<TICKER>_<stamp>/model.json")
        rebuild(sys.argv[2])
    else:
        run_offline()
