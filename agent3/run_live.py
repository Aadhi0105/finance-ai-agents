"""
Live Track-A run — RUN THIS ON A MACHINE THAT CAN REACH YAHOO (not the build
container). It is a thin CLI wrapper around the orchestrator, so a live run gets
the FULL rigorous path: assembly -> event study -> validation gate (incl.
placebo) -> gate-aware scenario -> persistence. (Previously this command ran a
lighter parallel path that skipped validation, placebo, and persistence.)

Usage:
    python -m agent3.run_live ALO.PA european_rail
    python -m agent3.run_live ASML.AS semicap_earnings --peers ASM.AS BESI.AS LRCX AMAT KLAC

Peers: with no --peers, the OFFLINE STUB peer set is used (deterministic). Set
AGENT3_LIVE_PROPOSE=1 with an ANTHROPIC_API_KEY to have the model propose peers.
The peer set used is PINNED and printed.
"""

from __future__ import annotations

import os
import sys

from agent3.orchestrator import analyze_event_type
from agent3.catalyst_state import CatalystStore


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
    store = CatalystStore()
    res = analyze_event_type(event_type, source="yfinance", ticker=ticker,
                             peers=peers, live_propose=live_propose, store=store)

    pinned = res.get("pinned_peer_set", {})
    if pinned:
        print(f"\nPinned peer set (proposed_by={pinned.get('proposed_by')}, "
              f"sector={pinned.get('sector')}):")
        print(f"  {res.get('pinned_peers')}")

    print("\nPer-peer assembly report:")
    for r in res.get("per_peer_report", []):
        if "error" in r:
            print(f"  {r['ticker']:<8} ERROR: {r['error']}")
        elif r.get("excluded"):
            print(f"  {r['ticker']:<8} EXCLUDED — {r.get('reason')}")
        else:
            print(f"  {r['ticker']:<8} earnings={r.get('earnings_dates')} "
                  f"assembled={r.get('assembled')} placebos={r.get('placebos')} "
                  f"skipped_short={r.get('skipped_short_history')} "
                  f"skipped_align={r.get('skipped_align')}")

    if res.get("verdict") == "REFUSED":
        print(f"\nREFUSED at assembly: {res.get('reason')}")
        store.close()
        return 0

    study, gate, scen = res["study"], res["gate"], res["scenario"]
    print(f"\nEVENT STUDY: CAAR={study['caar']:+.4f}  t={study['t_stat']}  "
          f"significant={study['caar_significant']}  N={study['n_events']}")
    if study.get("placebo"):
        print(f"  placebo: {study['placebo'].get('interpretation')}")
    print(f"\nGATE: {gate['verdict']} (confidence {gate['confidence']})")
    for c in gate["checks"]:
        if c["status"] != "pass":
            print(f"  [{c['status']}] {c['check']}: {c['detail']}")

    print(f"\nSCENARIO: {scen['verdict']} "
          f"(publication_state={scen.get('publication_state')})")
    if scen.get("distribution"):
        d = scen["distribution"]
        print(f"  next comparable catalyst: p25={d['p25']:+.4f} "
              f"median={d['median_car']:+.4f} p75={d['p75']:+.4f} "
              f"| P(positive)={d['prob_positive']}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
