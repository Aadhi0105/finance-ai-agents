"""Repository-curated financial tone subset; not a verified official LM dictionary.
Explicit CSV configuration fails closed. Runtime output records content identity,
vocabulary sizes and matched tokens; no contextual sentiment calibration is claimed.
"""

from __future__ import annotations

import os
import re

# Repository-curated positive words; official membership is unverified (working set; full list is ~350).
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

# Repository-curated negative words; official membership is unverified (working set; full list is ~2,300).
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


def load_full(csv_path: str, *, content=None) -> tuple[set, set]:
    """Load explicitly requested category flags. Negative years mean removed entries."""
    import csv
    import io
    from pathlib import Path
    pos, neg = set(), set()
    data = content if content is not None else Path(csv_path).read_bytes()
    with io.StringIO(data.decode('utf-8-sig'), newline='') as f:
        reader = csv.DictReader(f)
        if not {'Word', 'Positive', 'Negative'} <= set(reader.fieldnames or []):
            raise ValueError('dictionary requires Word/Positive/Negative columns')
        for row in reader:
            w = row['Word'].strip().lower()
            if not w or not w.isalpha():
                raise ValueError('invalid dictionary word')
            if int(row['Positive'] or 0) > 0:
                pos.add(w)
            if int(row['Negative'] or 0) > 0:
                neg.add(w)
    if not pos or not neg or pos & neg:
        raise ValueError('dictionary needs disjoint nonempty positive and negative vocabularies')
    return pos, neg


def load_dictionary():
    import hashlib
    import json
    from pathlib import Path
    path = os.environ.get('LM_DICTIONARY_CSV')
    data = Path(path).read_bytes() if path else None
    pos, neg = load_full(path, content=data) if path else (set(_POSITIVE), set(_NEGATIVE))
    data = data if path else json.dumps([sorted(pos), sorted(neg)]).encode()
    metadata = {'mode': 'configured_csv' if path else 'curated_subset',
                'version': Path(path).name if path else 'repository-subset-v1',
                'sha256': hashlib.sha256(data).hexdigest(),
                'positive_words': len(pos), 'negative_words': len(neg),
                'official_membership_verified': False, 'language': 'en',
                'method': 'token counts; no negation, context or entity attribution'}
    return pos, neg, metadata


def score_text(text: str, dictionary=None) -> dict:
    pos_set, neg_set, metadata = dictionary or load_dictionary()
    words = [w.lower() for w in _WORD.findall(text or '')]
    pos = [w for w in words if w in pos_set]
    neg = [w for w in words if w in neg_set]
    tone = len(pos) + len(neg)
    return {'score': (len(pos)-len(neg))/tone if tone else None,
            'pos_hits': len(pos), 'neg_hits': len(neg), 'tone_words': tone,
            'matched_positive': pos, 'matched_negative': neg, 'dictionary': metadata}
