"""
Live Track-B run — RUN ON A MACHINE WITH NETWORK + (optionally) FinBERT deps.

Fetches current news for an entity, scores it, and runs the funnel to an
entity-day sentiment signal — the daily-brief BREADTH view.

    python -m agent3.run_news ASML.AS
    AGENT_SENTIMENT_SCORER=divergence python -m agent3.run_news ASML.AS

Scorer via AGENT_SENTIMENT_SCORER:
    stub        (default) deterministic, offline
    lm          real Loughran-McDonald lexicon (offline, no deps)
    finbert     real FinBERT alone (needs: pip install transformers torch)
    divergence  FinBERT primary + LM cross-check, disagreement-as-confidence

FinBERT downloads ~400MB of weights on first use. If it's not installed, use
'lm' for a fully-offline real financial-sentiment score.

HONEST SCOPE: free news is current-only — this is the daily sentiment brief, not
historical sentiment-return analysis (which Track B never does; Track A owns
event-timed rigor).
"""

from __future__ import annotations

import os
import sys

from agent3.news_live import fetch_entity_news
from agent3.news_funnel import run_funnel
from agent3.sentiment import get_scorer


def main(argv):
    if not argv:
        print("usage: python -m agent3.run_news TICKER")
        return 1
    ticker = argv[0]
    scorer_name = os.environ.get("AGENT_SENTIMENT_SCORER", "stub")

    print(f"=== LIVE Track-B: {ticker}  (scorer={scorer_name}) ===")
    fetched = fetch_entity_news(ticker)
    print(f"  news: {fetched['raw_count']} raw -> {fetched['shaped_count']} timestamped")
    print(f"  scope: {fetched['scope_note']}")
    if not fetched["items"]:
        print("  no usable news items (empty or all un-timestamped).")
        return 0

    scorer = get_scorer(scorer_name)
    res = run_funnel(fetched["items"], universe={ticker.upper()}, scorer=scorer)
    print(f"\n  funnel: {res['funnel']}")
    print("\n  entity-day signals:")
    for s in res["signals"]:
        print(f"    {s['entity']:<9} {s['day']}  level={s['level']:+.3f} "
              f"dispersion={s['dispersion']:.3f} count={s['count']} "
              f"conf={s['confidence']:.3f} coverage={s['total_coverage']}")

    # Show a few scored headlines with any divergence flags (divergence scorer only)
    print("\n  sample scored headlines:")
    for it in fetched["items"][:5]:
        sc = scorer.score(it)
        flag = " [FLAG: scorers disagree]" if sc.get("flag_review") else ""
        print(f"    {sc['score']:+.2f} (conf {sc.get('confidence',0):.2f}){flag}  {it['headline'][:55]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
