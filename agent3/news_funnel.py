"""
Track B — news funnel (Agent 3, local, fixture-first).

Turns a stream of raw news items into per-entity-per-day SIGNALS, deterministically.
Track B carries BREADTH; the rigorous claims ride Track A. Sentiment from this
funnel never feeds a tested Track-A result — the firewall is absolute.

The funnel, in order:
  1. ingest      — normalise items; the published TIMESTAMP is sacred (point-in-time
                   integrity is born here; nothing downstream uses look-ahead info).
  2. dedup/cluster — the same wire story from 20 outlets is ONE signal, not 20.
                   Near-duplicate headlines collapse to a single representative,
                   so coverage volume is never mistaken for signal strength.
  3. relevance   — keep only items that actually mention the entity (drop passing
                   mentions / noise).
  4. score       — a pluggable scorer assigns sentiment (stub offline / FinBERT
                   live). The funnel owns structure; the scorer owns the number.
  5. aggregate   — collapse to an entity-day SIGNAL carrying level AND dispersion
                   AND count AND confidence — so consumers know how much to trust it.

Deterministic Python; fixture-first (no torch, no network).
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict

from agent3.sentiment import get_scorer


# --- 1. ingest -------------------------------------------------------------

def ingest(raw_items: list[dict]) -> list[dict]:
    """Normalise raw items. Requires a published timestamp (point-in-time integrity)
    and drops anything without one — an item we can't time-stamp can't be used."""
    out = []
    for it in raw_items:
        ts = it.get("published_at")
        if not ts:
            continue  # no timestamp -> unusable (no look-ahead risk allowed)
        out.append({
            "id": it.get("id"),
            "published_at": ts,
            "day": ts[:10],                       # YYYY-MM-DD (point-in-time day)
            "entities": [e.upper() for e in it.get("entities", [])],
            "headline": it.get("headline", ""),
            "body": it.get("body", ""),
            "source": it.get("source", ""),
            **({"stub_score": it["stub_score"]} if "stub_score" in it else {}),
            **({"stub_confidence": it["stub_confidence"]} if "stub_confidence" in it else {}),
        })
    return out


# --- 2. dedup / cluster ----------------------------------------------------

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "has", "have", "is", "to", "of", "in", "on", "as",
         "beats", "beat", "beaten", "and", "its", "for"}
_DUP_THRESHOLD = 0.6   # Jaccard >= this => same story


def _word_set(headline: str) -> set:
    return set(w for w in _WORD.findall(headline.lower()) if w not in _STOP)


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def dedup_cluster(items: list[dict]) -> list[dict]:
    """Collapse NEAR-duplicate stories (same day, same entities) to one
    representative, recording how many outlets carried it (cluster_size). Uses
    Jaccard similarity on headline word-sets, not exact matching, so trivial
    rewording still collapses — coverage volume is tracked but never treated as
    extra signal."""
    reps: list[dict] = []
    for it in items:
        ws = _word_set(it["headline"])
        matched = None
        for rep in reps:
            if rep["day"] == it["day"] and rep["entities"] == it["entities"] \
                    and _jaccard(rep["_wordset"], ws) >= _DUP_THRESHOLD:
                matched = rep
                break
        if matched is None:
            rep = dict(it)
            rep["cluster_size"] = 1
            rep["sources"] = [it.get("source", "")]
            rep["_wordset"] = ws
            reps.append(rep)
        else:
            matched["cluster_size"] += 1
            matched["sources"].append(it.get("source", ""))
    for rep in reps:
        rep.pop("_wordset", None)
    return reps


# --- 3. relevance ----------------------------------------------------------

def relevance_filter(items: list[dict], universe: set[str] | None = None) -> list[dict]:
    """Keep items that name at least one entity (optionally within a watched
    universe). Drops noise with no entity anchor."""
    out = []
    for it in items:
        ents = it["entities"]
        if not ents:
            continue
        if universe is not None:
            ents = [e for e in ents if e in universe]
            if not ents:
                continue
            it = {**it, "entities": ents}
        out.append(it)
    return out


# --- 4. score --------------------------------------------------------------

def score_items(items: list[dict], scorer=None) -> list[dict]:
    """Attach a sentiment score to each clustered item via the pluggable scorer."""
    scorer = scorer or get_scorer()
    out = []
    for it in items:
        sc = scorer.score(it)
        out.append({**it, "sentiment": sc["score"], "sentiment_confidence": sc["confidence"],
                    "scorer": sc["scorer"]})
    return out


# --- 5. aggregate -> entity-day signal ------------------------------------

def aggregate(items: list[dict]) -> list[dict]:
    """
    Collapse scored items to one SIGNAL per (entity, day). The signal carries:
      - level       : count-weighted mean sentiment
      - dispersion  : stdev of sentiment across stories (do they agree?)
      - count       : number of INDEPENDENT stories (clusters), not outlets
      - confidence  : scales up with count and scorer confidence, down with dispersion
    """
    buckets: dict = defaultdict(list)
    for it in items:
        for ent in it["entities"]:
            buckets[(ent, it["day"])].append(it)

    signals = []
    for (ent, day), group in sorted(buckets.items()):
        scores = [g["sentiment"] for g in group]
        confs = [g["sentiment_confidence"] for g in group]
        count = len(group)
        level = round(statistics.mean(scores), 4)
        dispersion = round(statistics.pstdev(scores), 4) if count > 1 else 0.0
        mean_conf = statistics.mean(confs)

        # Confidence: more independent stories + higher scorer confidence + lower
        # disagreement -> more trustworthy. Bounded [0,1].
        count_factor = min(1.0, count / 5.0)          # saturates at ~5 stories
        agree_factor = max(0.0, 1.0 - dispersion)     # 0 dispersion -> 1
        confidence = round(mean_conf * (0.5 + 0.5 * count_factor) * (0.5 + 0.5 * agree_factor), 4)

        signals.append({
            "entity": ent, "day": day,
            "level": level, "dispersion": dispersion, "count": count,
            "confidence": confidence,
            "total_coverage": sum(g.get("cluster_size", 1) for g in group),
            "computed_by": "news_funnel.aggregate (python)",
        })
    return signals


# --- orchestration ---------------------------------------------------------

def run_funnel(raw_items: list[dict], universe: set[str] | None = None,
               scorer=None) -> dict:
    """Full funnel: raw items -> entity-day signals, with stage counts for audit."""
    ingested = ingest(raw_items)
    clustered = dedup_cluster(ingested)
    relevant = relevance_filter(clustered, universe)
    scored = score_items(relevant, scorer)
    signals = aggregate(scored)
    return {
        "signals": signals,
        "funnel": {
            "raw": len(raw_items), "ingested": len(ingested),
            "after_dedup": len(clustered), "after_relevance": len(relevant),
            "entity_days": len(signals),
        },
    }
