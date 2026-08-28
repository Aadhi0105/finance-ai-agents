"""
Peer proposal (Agent 3, Track A) — model-proposes-and-pins.

The user's goal is "type one ticker, the rest takes care of itself", so the model
PROPOSES the comparable peer set from a single ticker. The reproducibility risk
(a significant result that changes when peers change) is solved not by forbidding
the model from choosing, but by PINNING its choice into the run record: the
proposed set is captured and reported, so re-running reuses the pinned set and
gets the identical answer.

  - propose_peers(ticker)      -> model proposes; offline uses a deterministic stub.
  - a --peers override         -> caller forces a set (propose is skipped).
  - the returned set is PINNED  -> stored with the run for exact reproducibility.

The validation gate (assembly step) is the backstop: it refuses / caveats a peer
set that is too heterogeneous to be comparable. Model proposes; gate disposes.
"""

from __future__ import annotations

import json
import os

from agent.models import StubModel, AnthropicModel, ModelResponse, TextBlock

_PROPOSE_SYSTEM = (
    "You are an equity-research assistant assembling a COMPARABLE peer set for an "
    "event study. Given one ticker, propose 5-10 peers that share the same sector, "
    "business model, and rough size — companies whose earnings would be driven by "
    "the same forces, so pooling their earnings events is defensible. Return ONLY a "
    "JSON object: {\"sector\": \"...\", \"peers\": [\"TICK1.XX\", ...], \"rationale\": \"...\"}. "
    "Use correct exchange suffixes (.PA Paris, .DE Xetra, .AS Amsterdam, .SW Swiss, "
    ".L London, .MI Milan; none for US). Do not include the input ticker itself."
)

# Deterministic offline stub peer sets (so the flow is provable without a model).
_STUB_PEERS = {
    "ALO.PA": {"sector": "rail rolling-stock & signalling",
               "peers": ["SIE.DE", "KNRRY", "WAB", "ABBNY", "SU.PA"],
               "rationale": "European/global rail & industrial automation peers"},
    "ASML.AS": {"sector": "semiconductor capital equipment",
                "peers": ["ASM.AS", "BESI.AS", "LRCX", "AMAT", "KLAC", "TER"],
                "rationale": "front/back-end semicap equipment makers"},
}


def _pin(ticker: str, proposal: dict, source: str) -> dict:
    peers = [p for p in proposal.get("peers", []) if p and p != ticker]
    return {
        "ticker": ticker,
        "sector": proposal.get("sector", "unspecified"),
        "peers": peers,                       # PINNED — the exact set used
        "rationale": proposal.get("rationale", ""),
        "proposed_by": source,
        "n_peers": len(peers),
    }


def propose_peers(ticker: str, override: list[str] | None = None,
                  live: bool = False) -> dict:
    """
    Return a PINNED peer set for `ticker`.
      - override given  -> use it verbatim (proposed_by='override').
      - live + API key  -> the model proposes.
      - otherwise       -> deterministic offline stub.
    """
    if override:
        return _pin(ticker, {"sector": "user-specified", "peers": override,
                             "rationale": "explicit --peers override"}, "override")

    if live and "ANTHROPIC_API_KEY" in os.environ:
        proposal = _propose_via_model(ticker)
        return _pin(ticker, proposal, "model")

    stub = _STUB_PEERS.get(ticker.upper())
    if stub is None:
        # Unknown ticker offline: honest empty proposal (the gate will refuse).
        return _pin(ticker, {"sector": "unknown", "peers": [],
                             "rationale": "no offline stub for this ticker; run live for a model proposal"},
                    "stub")
    return _pin(ticker, stub, "stub")


def _propose_via_model(ticker: str) -> dict:
    """Ask the real model for a peer set; parse its JSON. Live path only."""
    model = AnthropicModel()
    resp = model.create(
        system=_PROPOSE_SYSTEM,
        messages=[{"role": "user", "content": f"Ticker: {ticker}. Propose the comparable peer set."}],
        tools=[],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    try:
        return json.loads(text[text.find("{"): text.rfind("}") + 1])
    except Exception:
        return {"sector": "parse_error", "peers": [], "rationale": f"could not parse model output: {text[:120]}"}
