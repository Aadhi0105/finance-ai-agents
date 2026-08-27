"""
Model triage for Agent 2 (spec §3.3, component #3 — the model as *triager*).

The key architectural difference from Agent 1: there, the model DROVE the loop
and did the analysis. Here, the deterministic cycle has ALREADY detected — the
model never detects. It triages the accumulated flags: groups them by entity,
judges which are corroborated vs isolated, DECIDES whether to re-check ambiguous
ones before escalation, and writes a prioritised commentary.

That re-check decision is Agent 2's agentic branch — the analogue of Agent 1's
consensus-null fork. And corroboration is computed deterministically in
`recheck_flag` (the LLM never does the math; it decides *whether* to call it and
reads the verdict).

This layer REUSES the shared spine: agent/loop.py (the hand-rolled tool-use loop)
and agent/models.py (Stub/Anthropic model clients). Same loop, different job.
"""

from __future__ import annotations

import os

from agent.loop import run_agent
from agent.state import RunState
from agent.models import StubModel, AnthropicModel, ModelResponse, TextBlock, ToolUseBlock
from state.classify import SURFACED


TRIAGE_SYSTEM = (
    "You are a credit-monitoring triage analyst. Deterministic checks have ALREADY "
    "produced the flags below — you do NOT detect anything yourself; you triage.\n\n"
    "Your job: (1) group flags by entity, (2) judge which are CORROBORATED (several "
    "independent signals agree, or the move is sustained) versus ISOLATED (a single "
    "signal, possibly a data glitch), (3) DECIDE whether any ambiguous flag should be "
    "re-checked before escalation — if so, call recheck_flag — and (4) write a short, "
    "prioritised commentary with a recommended action per entity.\n\n"
    "Do not invent numbers. Call inspect_item to see an item's history/flags, and "
    "recheck_flag to get a deterministic corroboration verdict. Escalate corroborated "
    "flags; recommend verification (not escalation) for isolated ones."
)


# --- deterministic triage tools -------------------------------------------

def _toward_breach(f) -> bool:
    bd = f.get("_breach_detail", {}) or {}
    return bool(bd.get("toward_breach"))


def inspect_item(store, flags: dict, item_id: str) -> dict:
    """Return an item's recent history and its current flags (context for the model)."""
    f = flags.get(item_id)
    if not f:
        return {"error": f"{item_id} not among this cycle's flags"}
    recent = [r["value"] for r in store.get_history_series(item_id)][-8:]
    return {
        "item_id": item_id, "entity": f["entity"], "metric": f["metric"],
        "recent_values": recent,
        "threshold_status": f["status"], "breached": f["breached"],
        "anomaly_significant": f.get("anomaly_significant"), "anomaly_z": f.get("anomaly_z"),
        "drifting": f.get("drifting"), "breach_prob": f.get("breach_prob"),
    }


def recheck_flag(store, flags: dict, item_id: str) -> dict:
    """
    Deterministic corroboration analysis. Counts how many INDEPENDENT signals flag
    this item, and whether an anomaly (if present) is an isolated single-cycle
    deviation. Verdict guides escalate-vs-verify. The model calls this; it does
    not compute it.
    """
    f = flags.get(item_id)
    if not f:
        return {"error": f"{item_id} not flagged this cycle"}

    signals = []
    if f["breached"] and f["status"] in SURFACED and "BREACH" in f["status"]:
        signals.append("threshold_breach")
    if f.get("anomaly_significant"):
        signals.append("anomaly")
    if f.get("drifting") and _toward_breach(f):
        signals.append("drift_toward_breach")
    if f.get("breach_tail") and _toward_breach(f):
        signals.append("high_breach_probability")

    # Isolated-anomaly test: is the anomalous value a single-cycle deviation from
    # an otherwise stable recent history?
    recent = [r["value"] for r in store.get_history_series(item_id)]
    isolated_anomaly = False
    if f.get("anomaly_significant") and len(recent) >= 4:
        prior = recent[:-1]
        import statistics
        med = statistics.median(prior)
        # anomalous point far from the prior median while the prior itself was tight
        prior_spread = statistics.pstdev(prior) if len(prior) > 1 else 0.0
        isolated_anomaly = prior_spread < abs(recent[-1] - med) / 3

    corroborated = len(signals) >= 2
    other_signals = [s for s in signals if s != "anomaly"]

    if corroborated and isolated_anomaly and other_signals:
        # Several signals agree, but the anomaly is a single-cycle spike: the
        # underlying issue is real (threshold/drift/probability corroborate it),
        # yet the anomaly's MAGNITUDE may be a bad data point.
        verdict = "corroborated_but_verify"
        recommendation = ("escalate the covenant issue (corroborated by "
                          f"{', '.join(other_signals)}), but verify the anomaly value "
                          "before trusting its magnitude — single-cycle deviation")
    elif corroborated:
        verdict = "corroborated"
        recommendation = "escalate — multiple independent signals agree"
    elif isolated_anomaly:
        verdict = "isolated"
        recommendation = "verify before escalation — single-cycle deviation, possible data glitch"
    else:
        verdict = "weak"
        recommendation = "monitor — single signal, not yet corroborated"

    return {
        "item_id": item_id, "entity": f["entity"],
        "n_signals": len(signals), "signals": signals,
        "isolated_anomaly": isolated_anomaly,
        "verdict": verdict, "recommendation": recommendation,
        "computed_by": "recheck_flag (python, deterministic)",
    }


# --- triage registry (schemas + dispatch, driving the shared loop) --------

class TriageRegistry:
    def __init__(self, store, surfaced_rows: list[dict]):
        self.store = store
        self.flags = {r["item_id"]: r for r in surfaced_rows}

    def schemas(self) -> list:
        return [
            {"name": "inspect_item",
             "description": "Get an item's recent history and current flags.",
             "input_schema": {"type": "object",
                              "properties": {"item_id": {"type": "string"}},
                              "required": ["item_id"]}},
            {"name": "recheck_flag",
             "description": "Get a deterministic corroboration verdict for a flagged item "
                            "(corroborated / isolated / weak) to decide escalate vs verify.",
             "input_schema": {"type": "object",
                              "properties": {"item_id": {"type": "string"}},
                              "required": ["item_id"]}},
        ]

    def dispatch(self, name: str, tool_input: dict):
        item_id = tool_input.get("item_id", "")
        if name == "inspect_item":
            return inspect_item(self.store, self.flags, item_id)
        if name == "recheck_flag":
            return recheck_flag(self.store, self.flags, item_id)
        return {"error": f"unknown triage tool: {name}"}


# --- offline stub script (proves the triage shape deterministically) ------

def _build_triage_stub(surfaced_rows):
    """
    Scripted triage that exercises the shape: inspect the most ambiguous flag,
    re-check it, then write a grouped commentary. Stands in for the live model's
    reasoning (which agent/models.AnthropicModel provides when a key is set).
    """
    # Pick an anomaly item to re-check (the ambiguous case), if any.
    anomaly_item = next((r["item_id"] for r in surfaced_rows
                         if r.get("anomaly_significant")), None)
    target = anomaly_item or (surfaced_rows[0]["item_id"] if surfaced_rows else None)

    steps = []
    if target:
        steps.append(lambda m: ModelResponse(
            stop_reason="tool_use",
            content=[ToolUseBlock(id="s0", name="inspect_item", input={"item_id": target})]))
        steps.append(lambda m: ModelResponse(
            stop_reason="tool_use",
            content=[ToolUseBlock(id="s1", name="recheck_flag", input={"item_id": target})]))
    steps.append(lambda m: ModelResponse(
        stop_reason="end_turn",
        content=[TextBlock(text=(
            "[stub triage] Grouped the flags by entity; re-checked the ambiguous "
            "anomaly and used its corroboration verdict to decide escalate-vs-verify. "
            "Live mode replaces this with the model's written triage over the same flags."))]))
    return steps


# --- entry -----------------------------------------------------------------

def run_triage(store, surfaced_rows: list[dict], live: bool = False) -> str:
    """Run model triage over a cycle's surfaced flags. Stub offline; real model if live."""
    if not surfaced_rows:
        return ""

    registry = TriageRegistry(store, surfaced_rows)
    state = RunState(ticker="__monitor__")

    if live and "ANTHROPIC_API_KEY" in os.environ:
        model = AnthropicModel()
    else:
        model = StubModel(script=_build_triage_stub(surfaced_rows))

    goal = "Triage these monitoring flags:\n" + _format_flags(surfaced_rows)
    return run_agent(model=model, registry=registry, state=state,
                     system=TRIAGE_SYSTEM, goal=goal)


def _format_flags(rows) -> str:
    out = []
    for r in rows:
        bits = [f"status={r['status']}"]
        if r.get("anomaly_significant"):
            bits.append(f"anomaly(z={r['anomaly_z']})")
        if r.get("drifting"):
            bits.append(f"drift(slope={r['drift_slope']})")
        if r.get("breach_tail"):
            bits.append(f"breach_prob={r['breach_prob']}")
        out.append(f"- {r['item_id']} ({r['entity']}): {r['metric']} — {', '.join(bits)}")
    return "\n".join(out)
