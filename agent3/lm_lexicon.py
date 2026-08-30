"""
Loughran-McDonald financial sentiment lexicon (Agent 3, Track B).

LM is a purpose-built FINANCIAL sentiment dictionary — general-purpose lists mark
"liability" or "cost" as negative when in finance they're neutral, which is why a
finance-specific lexicon matters. This module holds a curated WORKING SUBSET of
the real LM positive/negative word lists (the lists are publicly documented). It
is deliberately not the full ~2,700-word Master Dictionary — point `load_full()`
at the official CSV to use the complete lexicon in production.

Why a lexicon at all when we also have FinBERT? Because the DISAGREEMENT between a
transformer (context-aware, opaque) and a lexicon (transparent, rule-based) is a
free, quantitative confidence signal: when they agree, trust the score; when they
diverge, flag it for human review. The lexicon is deterministic and auditable —
you can see exactly which words drove the score.
"""

from __future__ import annotations

import os
import re

# A curated subset of genuine LM positive words (working set; full list is ~350).
_POSITIVE = {
    "able", "abundance", "achieve", "achieved", "achievement", "achievements",
    "advance", "advanced", "advancement", "advances", "advantage", "advantaged",
    "advantageous", "advantages", "assure", "assured", "attain", "attained",
    "attractive", "beneficial", "benefit", "benefited", "benefits", "best",
    "better", "bolstered", "boom", "booming", "boost", "boosted", "breakthrough",
    "brilliant", "collaborate", "collaboration", "compliment", "confident",
    "constructive", "creative", "creativity", "delight", "delighted", "dependable",
    "desirable", "distinction", "distinctive", "effective", "efficiencies",
    "efficiency", "efficient", "empower", "enable", "enabled", "encouraged",
    "encouraging", "enhance", "enhanced", "enhancement", "enhances", "enhancing",
    "enjoy", "enthusiasm", "enthusiastic", "excellence", "excellent", "exceptional",
    "exceptionally", "excited", "exciting", "exclusive", "exemplary", "fantastic",
    "favorable", "favorably", "favorite", "gain", "gained", "gaining", "gains",
    "good", "great", "greater", "greatest", "growth", "happy", "honor", "ideal",
    "impress", "impressive", "improve", "improved", "improvement", "improvements",
    "improves", "improving", "incredible", "influential", "innovate", "innovation",
    "innovations", "innovative", "insightful", "inspiration", "integrity",
    "invent", "invention", "leadership", "leading", "loyal", "lucrative",
    "opportunities", "opportunity", "optimistic", "outperform", "outperformed",
    "outperforming", "outperforms", "perfect", "pleased", "popular", "positive",
    "positively", "preeminent", "premier", "prestigious", "proactive",
    "proficient", "profitability", "profitable", "profitably", "progress",
    "prospered", "prosperity", "prosperous", "rebound", "rebounded", "regain",
    "resolve", "reward", "rewarded", "rewarding", "satisfaction", "satisfactory",
    "satisfied", "solid", "spectacular", "stability", "stabilize", "stabilized",
    "stable", "strength", "strengthen", "strengthened", "strengthening",
    "strengthens", "strong", "stronger", "strongest", "succeed", "succeeded",
    "success", "successful", "successfully", "superior", "surpass", "surpassed",
    "surpasses", "surpassing", "tremendous", "unmatched", "unparalleled",
    "unsurpassed", "upside", "upturn", "valuable", "versatile", "vibrant", "win",
    "winner", "winning", "worthy",
}

# A curated subset of genuine LM negative words (working set; full list is ~2,300).
_NEGATIVE = {
    "abandon", "abandoned", "abandoning", "abandonment", "abnormal", "abnormally",
    "adverse", "adversely", "adversity", "aggravate", "aggravated", "alarming",
    "allegation", "allegations", "alleged", "allegedly", "annoy", "anomalies",
    "anomaly", "antitrust", "argue", "argument", "arrears", "assault", "attrition",
    "bad", "badly", "bailout", "bankrupt", "bankruptcies", "bankruptcy", "bans",
    "barred", "barrier", "barriers", "bottleneck", "boycott", "breach", "breached",
    "breaches", "breakdown", "bribe", "bribery", "burden", "burdened", "burdensome",
    "calamity", "cancel", "canceled", "cancellation", "cancellations", "cancelled",
    "catastrophe", "catastrophic", "caution", "cautionary", "cautioned",
    "cautious", "cease", "ceased", "challenge", "challenged", "challenges",
    "challenging", "claim", "collapse", "collapsed", "concern", "concerned",
    "concerns", "confront", "confusion", "contraction", "corruption", "costly",
    "crisis", "critical", "cutback", "damage", "damaged", "damages", "danger",
    "dangerous", "decline", "declined", "declines", "declining", "decrease",
    "decreased", "decreases", "decreasing", "default", "defaulted", "defaults",
    "defect", "defective", "defects", "deficiencies", "deficiency", "deficient",
    "deficit", "delay", "delayed", "delaying", "delays", "deteriorate",
    "deteriorated", "deteriorating", "deterioration", "difficult", "difficulties",
    "difficulty", "diminish", "diminished", "diminishing", "disappoint",
    "disappointed", "disappointing", "disappointment", "disaster", "disastrous",
    "dispute", "disputed", "disputes", "disruption", "disruptions", "downgrade",
    "downgraded", "downturn", "drop", "dropped", "erosion", "error", "errors",
    "exposure", "fail", "failed", "failing", "failure", "failures", "fear",
    "fears", "fine", "fined", "fines", "force", "forced", "fraud", "fraudulent",
    "headwind", "headwinds", "hurt", "impair", "impaired", "impairment",
    "impairments", "insolvency", "investigation", "investigations", "lawsuit",
    "lawsuits", "layoff", "layoffs", "litigation", "lose", "losing", "loss",
    "losses", "lost", "negative", "negatively", "penalties", "penalty", "plummet",
    "plummeted", "poor", "poorly", "pressure", "pressured", "pressures", "problem",
    "problematic", "problems", "recall", "recalled", "recalls", "recession",
    "restructuring", "risk", "risks", "risky", "sabotage", "scrutiny", "setback",
    "setbacks", "severe", "severely", "shortfall", "shortfalls", "shortage",
    "shortages", "shutdown", "slowdown", "slowed", "slowing", "slump", "slumped",
    "sluggish", "stagnant", "stagnation", "strain", "stress", "terminate",
    "terminated", "threat", "threats", "trouble", "troubled", "troubles",
    "turmoil", "unable", "uncertain", "uncertainties", "uncertainty", "undermine",
    "undermined", "unfavorable", "unforeseen", "unprofitable", "unresolved",
    "unstable", "unsuccessful", "volatile", "volatility", "warn", "warned",
    "warning", "warnings", "weak", "weaken", "weakened", "weakening", "weaker",
    "weakness", "weaknesses", "worse", "worsen", "worsened", "worsening", "worst",
    "writedown", "writedowns", "writeoff", "writeoffs",
}

_WORD = re.compile(r"[a-zA-Z]+")


def load_full(csv_path: str) -> tuple[set, set]:
    """Load the full LM Master Dictionary CSV (columns include 'Word', 'Positive',
    'Negative' with non-zero year-flags for membership). Returns (positive, negative)
    lowercased word sets. Falls back to the built-in subset on any error."""
    import csv
    pos, neg = set(), set()
    try:
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                w = (row.get("Word") or "").strip().lower()
                if not w:
                    continue
                if (row.get("Positive") or "0") not in ("0", "", None):
                    pos.add(w)
                if (row.get("Negative") or "0") not in ("0", "", None):
                    neg.add(w)
        if pos and neg:
            return pos, neg
    except Exception:
        pass
    return set(_POSITIVE), set(_NEGATIVE)


def _lexicon() -> tuple[set, set]:
    csv_path = os.environ.get("LM_DICTIONARY_CSV")
    if csv_path and os.path.exists(csv_path):
        return load_full(csv_path)
    return _POSITIVE, _NEGATIVE


def score_text(text: str) -> dict:
    """Lexicon sentiment for a piece of text. Returns a score in [-1, +1] plus the
    positive/negative hit counts (auditable — you can see what drove it)."""
    pos_set, neg_set = _lexicon()
    words = [w.lower() for w in _WORD.findall(text or "")]
    if not words:
        return {"score": 0.0, "pos_hits": 0, "neg_hits": 0, "tone_words": 0}
    p = sum(1 for w in words if w in pos_set)
    n = sum(1 for w in words if w in neg_set)
    tone = p + n
    score = 0.0 if tone == 0 else (p - n) / tone
    return {"score": round(score, 4), "pos_hits": p, "neg_hits": n, "tone_words": tone}
