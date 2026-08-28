"""
Sentiment scoring stage (Agent 3, Track B) — pluggable.

The scorer OWNS the number; the funnel owns the structure. So scoring is isolated
behind one interface with two implementations, mirroring the platform's
stub/live pattern (StubModel/AnthropicModel, fixture/yfinance):

  - StubScorer  : deterministic, reads a pre-assigned score from the fixture (or a
                  reproducible hash-based pseudo-score). No torch, no network — so
                  the whole funnel is provable offline.
  - FinbertScorer (later): a real transformer + the Loughran-McDonald lexicon; the
                  DISAGREEMENT between the two becomes a free confidence signal.

Governing principle carries: the model never scores sentiment — a scorer does, and
the number is auditable.

Score convention: a float in [-1, +1] (negative..positive) plus a per-item
confidence in [0, 1].
"""

from __future__ import annotations


class StubScorer:
    """Deterministic offline scorer. Uses a fixture-provided score when present,
    else a reproducible pseudo-score derived from the text (never random)."""

    name = "stub"

    def score(self, item: dict) -> dict:
        if "stub_score" in item:
            s = float(item["stub_score"])
            conf = float(item.get("stub_confidence", 0.8))
        else:
            # Reproducible fallback: deterministic function of the headline text,
            # so offline runs are stable without any pre-assigned score.
            text = (item.get("headline", "") + item.get("body", "")).lower()
            h = sum(ord(c) for c in text)
            s = round(((h % 201) - 100) / 100.0, 3)   # in [-1, +1]
            conf = 0.5
        return {"score": max(-1.0, min(1.0, s)), "confidence": conf, "scorer": self.name}


def get_scorer(source: str | None = None):
    """Return the scorer for the current mode. Live FinBERT is wired in a later
    checkpoint; offline always uses the deterministic stub."""
    import os
    src = source or os.environ.get("AGENT_SENTIMENT_SCORER", "stub")
    if src == "finbert":
        raise NotImplementedError("FinBERT scorer is wired in a later checkpoint (fixture-first)")
    return StubScorer()
