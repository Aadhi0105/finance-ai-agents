"""
Sentiment scoring stage (Agent 3, Track B) — pluggable.

The scorer OWNS the number; the funnel owns the structure. Scoring is isolated
behind one interface (`.score(item) -> {score, confidence, scorer, ...}`) with
several implementations, mirroring the platform's stub/live pattern:

  - StubScorer        : deterministic fixture/hash score. No torch, no network —
                        the funnel is provable offline.
  - LoughranMcDonaldScorer : real financial lexicon (transparent, auditable).
  - FinbertScorer     : real transformer (ProsusAI/finbert). Lazy-loads torch +
                        transformers and downloads weights on first use, so it
                        runs on a machine with network + the deps — not in CI.
  - DivergenceScorer  : runs a transformer AND the lexicon; their DISAGREEMENT is
                        a free, quantitative confidence signal. Agreement -> high
                        confidence; divergence -> low confidence + a flag the
                        validation gate can act on ("shaky score, human eyes").

Governing principle carries: the model never scores sentiment — a scorer does,
and the number is auditable. Score convention: float in [-1, +1] plus a
confidence in [0, 1].
"""

from __future__ import annotations

import os

from agent3 import lm_lexicon


def _text_of(item: dict) -> str:
    return f"{item.get('headline', '')} {item.get('body', '')}".strip()


class StubScorer:
    """Deterministic offline scorer (fixture score, or a reproducible pseudo-score)."""

    name = "stub"

    def score(self, item: dict) -> dict:
        if "stub_score" in item:
            s = float(item["stub_score"])
            conf = float(item.get("stub_confidence", 0.8))
        else:
            text = _text_of(item).lower()
            h = sum(ord(c) for c in text)
            s = round(((h % 201) - 100) / 100.0, 3)
            conf = 0.5
        return {"score": max(-1.0, min(1.0, s)), "confidence": conf, "scorer": self.name}


class LoughranMcDonaldScorer:
    """Real financial-lexicon scorer — transparent and fully offline. Confidence
    scales with how many tone words were found (more evidence -> more confident)."""

    name = "lm"

    def score(self, item: dict) -> dict:
        r = lm_lexicon.score_text(_text_of(item))
        tone = r["tone_words"]
        conf = 0.3 if tone == 0 else min(0.9, 0.4 + 0.1 * tone)
        return {"score": r["score"], "confidence": round(conf, 3), "scorer": self.name,
                "pos_hits": r["pos_hits"], "neg_hits": r["neg_hits"]}


class FinbertScorer:
    """Real FinBERT (ProsusAI/finbert). Lazy-loads torch + transformers and
    downloads weights on first use — so it runs on a networked machine with the
    deps installed, not in the build container. Score = P(positive) - P(negative)."""

    name = "finbert"

    def __init__(self, model_name: str = "ProsusAI/finbert"):
        self.model_name = model_name
        self._pipe = None

    def _pipeline(self):
        if self._pipe is None:
            from transformers import pipeline  # heavy import, deferred
            self._pipe = pipeline("text-classification", model=self.model_name,
                                  top_k=None, truncation=True)
        return self._pipe

    def score(self, item: dict) -> dict:
        text = _text_of(item)
        if not text:
            return {"score": 0.0, "confidence": 0.3, "scorer": self.name}
        out = self._pipeline()(text)[0]   # list of {label, score}
        probs = {d["label"].lower(): d["score"] for d in out}
        s = probs.get("positive", 0.0) - probs.get("negative", 0.0)
        # confidence = how far from neutral the model is
        conf = round(min(1.0, abs(s) + probs.get("positive", 0) + probs.get("negative", 0)) / 2 + 0.5, 3)
        return {"score": round(s, 4), "confidence": min(0.95, conf), "scorer": self.name,
                "probs": {k: round(v, 3) for k, v in probs.items()}}


class DivergenceScorer:
    """Runs a primary (transformer) scorer AND the LM lexicon; combines them and
    turns their DISAGREEMENT into a confidence signal.

      - agreement (same sign, close magnitude) -> high confidence, flag_review False
      - divergence (opposite signs, or one strong/one flat) -> low confidence,
        flag_review True (the validation gate can route these to human eyes)

    The combined score is the primary's number (the transformer is context-aware);
    the lexicon's job is to CHECK it, not to average it away.
    """

    name = "divergence"

    def __init__(self, primary=None, secondary=None, diverge_threshold: float = 0.5):
        self.primary = primary or _default_primary()
        self.secondary = secondary or LoughranMcDonaldScorer()
        self.diverge_threshold = diverge_threshold

    def score(self, item: dict) -> dict:
        p = self.primary.score(item)
        q = self.secondary.score(item)
        ps, qs = p["score"], q["score"]
        divergence = abs(ps - qs) / 2.0                 # in [0, 1]
        opposite_signs = (ps > 0.05 and qs < -0.05) or (ps < -0.05 and qs > 0.05)
        flag = opposite_signs or divergence >= self.diverge_threshold
        # confidence: primary's own confidence, discounted by divergence
        conf = round(max(0.1, p.get("confidence", 0.6) * (1.0 - divergence)), 3)
        return {
            "score": ps,                                # trust the transformer's number
            "confidence": conf,
            "scorer": f"{self.primary.name}+{self.secondary.name}",
            "primary_score": ps, "secondary_score": qs,
            "divergence": round(divergence, 4),
            "flag_review": bool(flag),
            "reason": ("scorers disagree — flag for review" if flag
                       else "scorers agree"),
        }


def _default_primary():
    """FinBERT if available/allowed, else the stub (keeps offline runs working)."""
    if os.environ.get("AGENT_SENTIMENT_SCORER") == "finbert":
        return FinbertScorer()
    return StubScorer()


def get_scorer(source: str | None = None):
    """Return the scorer for the current mode.
      - default / 'stub'      : deterministic offline stub.
      - 'lm'                  : the real Loughran-McDonald lexicon (offline).
      - 'finbert'             : real FinBERT alone (networked machine).
      - 'divergence'          : FinBERT primary + LM check, disagreement-as-confidence.
    """
    src = source or os.environ.get("AGENT_SENTIMENT_SCORER", "stub")
    if src == "lm":
        return LoughranMcDonaldScorer()
    if src == "finbert":
        return FinbertScorer()
    if src == "divergence":
        return DivergenceScorer()
    return StubScorer()
