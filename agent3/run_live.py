"""
Live Track-A run — RUN THIS ON A MACHINE THAT CAN REACH YAHOO (not the build
container). It exercises the full live path on real data:

  one ticker -> pinned peer set -> yfinance earnings dates + prices per peer
  -> drop-and-report thin peers -> assemble events -> run the event study
  -> scenario.

Usage:
    python -m agent3.run_live ALO.PA european_rail
    python -m agent3.run_live ASML.AS semicap_earnings --peers ASM.AS BESI.AS LRCX AMAT KLAC

Peers: with no --peers, the OFFLINE STUB peer set is used (deterministic). Set
AGENT3_LIVE_PROPOSE=1 with an ANTHROPIC_API_KEY to have the model propose peers.
The peer set used is PINNED and printed, so the result is reproducible.
"""

from __future__ import annotations

import os
import sys

from agent3.track_a import load_event_set
from tools.event_study import run_event_study
from agent3.scenario import scenario_from_event_study


def main(argv):
    if len(argv) < 2:
        print("usage: python -m agent3.run_live TICKER EVENT_TYPE [--peers T1 T2 ...]")
        return 1
    ticker = argv[0]
    event_type = argv[1]
    peers = None
    if "--peers" in argv:
        peers = argv[argv.index("--peers") + 1:]
    live_propose = os.environ.get("AGENT3_LIVE_PROPOSE") == "1"

    print(f"=== LIVE Track-A: {ticker} ({event_type}) ===")
    es = load_event_set(event_type, source="yfinance", ticker=ticker,
                        peers=peers, live_propose=live_propose)

    pinned = es.get("pinned_peer_set", {})
    print(f"\nPinned peer set (proposed_by={pinned.get('proposed_by')}, "
          f"sector={pinned.get('sector')}):")
    print(f"  {es.get('pinned_peers')}")
    if pinned.get("rationale"):
        print(f"  rationale: {pinned['rationale']}")

    print("\nPer-peer assembly report:")
    for r in es.get("per_peer_report", []):
        if "error" in r:
            print(f"  {r['ticker']:<8} ERROR: {r['error']}")
        else:
            print(f"  {r['ticker']:<8} earnings_dates={r.get('earnings_dates')} "
                  f"assembled={r.get('assembled')} "
                  f"skipped_short={r.get('skipped_short_history')} "
                  f"skipped_align={r.get('skipped_align')}")

    print(f"\nTotal usable events: {es.get('n_events')}  |  verdict: {es.get('verdict')}")
    if es.get("verdict") == "REFUSED":
        print(f"  REFUSED: {es.get('reason')}")
        return 0

    study = run_event_study(es["events"], event_type)
    print(f"\nEVENT STUDY: CAAR={study['caar']:+.4f}  t={study['t_stat']}  "
          f"significant={study['caar_significant']}  N={study['n_events']}")
    print(f"  power: {study.get('power_note')}")

    scen = scenario_from_event_study(study)
    print(f"\nSCENARIO: verdict={scen['verdict']} confidence={scen['confidence']}")
    if scen.get("distribution"):
        d = scen["distribution"]
        print(f"  next comparable catalyst: p25={d['p25']:+.4f} median={d['median_car']:+.4f} "
              f"p75={d['p75']:+.4f} | P(positive)={d['prob_positive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
