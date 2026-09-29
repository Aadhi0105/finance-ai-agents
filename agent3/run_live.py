"""Run historical earnings analysis; optional sourced review plan, never a forecast."""
import argparse
import json
import os
import sys
from agent3.orchestrator import analyze_event_type, render_brief
from agent3.catalyst_state import CatalystStore


def main(argv):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ticker'); parser.add_argument('event_type')
    parser.add_argument('--peers',nargs='*',default=None)
    parser.add_argument('--study-plan',help='JSON containing reviewed dates, benchmarks, peers and planned hypotheses')
    args=parser.parse_args(argv)
    plan=None
    if args.study_plan:
        with open(args.study_plan) as f: plan=json.load(f)
    store=CatalystStore()
    try:
        r=analyze_event_type(args.event_type,source='yfinance',ticker=args.ticker,peers=args.peers,
                             live_propose=os.environ.get('AGENT3_LIVE_PROPOSE')=='1',store=store,study_plan=plan)
        print(render_brief(r))
        return 2 if r.get('verdict')=='REFUSED' else 3 if r['gate']['verdict']!='PASS' else 0
    finally:
        store.close()


if __name__=='__main__':
    raise SystemExit(main(sys.argv[1:]))
