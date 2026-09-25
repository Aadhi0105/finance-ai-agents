"""
Agent 1 — Equity Research.

Run modes:
    python run.py                 -> OFFLINE. Scripted StubModel + fixture data.
                                     Proves the loop plumbing deterministically,
                                     no API key, no network.

    python run.py --live ASML.AS  -> LIVE. Real Anthropic model decides the tool
                                     sequence; data from yfinance. Requires
                                     ANTHROPIC_API_KEY (loaded from .env) and
                                     `pip install -r requirements.txt`.

The loop, tools, state, and tool-use protocol are identical across modes. Only
the model and the data source change.
"""

from __future__ import annotations

import os
import sys

from agent.loop import run_agent
from agent.state import RunState
from agent.models import StubModel, AnthropicModel, ModelResponse, TextBlock, ToolUseBlock
from tools.registry import ToolRegistry


SYSTEM = (
    "You are an equity-research agent. Produce a defensible fundamental view on the "
    "given ticker. You must NOT compute any numbers yourself: call tools for every "
    "figure, read their results, then write the view.\n\n"
    "Tools: get_financials (raw figures), get_prices (price/market cap/shares), "
    "compute_ratios (margins, growth, and — once prices are fetched — P/E and EV/EBIT), "
    "run_dcf (scenario-weighted valuation, needs financials + prices), "
    "peer_outlier_check (is the P/E an outlier vs peers you supply), "
    "get_consensus (forward analyst estimates), get_historical_trend (the company's "
    "own multi-year trajectory).\n\n"
    "IMPORTANT — comparison basis: call get_consensus to anchor your growth/valuation "
    "view against analyst expectations. Consensus is often unavailable (available=false). "
    "When it is, DO NOT invent estimates — call get_historical_trend and assess the "
    "company against its OWN multi-year trajectory instead. Always state explicitly which "
    "basis you used (analyst consensus, or own-history fallback).\n\n"
    "A sensible order: fetch financials and prices, compute ratios, run a DCF, check "
    "peers, establish a comparison basis (consensus or history), then write a note "
    "stating a view, the evidence, the basis used, and what would change it."
    "\n\n"
    "CRITICAL — numerical evidence: never type numbers, numeric words, percentages, "
    "currency amounts or multiples in your own prose. Put a named evidence marker "
    "on its OWN LINE, e.g. [[claim:operating_margin]] or [[claim:dcf_value]]. Python "
    "renders the complete sentence with company, metric, period, unit and source. "
    "Do not add your own label beside a marker. Use only available current results. "
    "Available IDs: revenue, net_income, ebit, current_price, market_cap, shares, "
    "gross_margin, operating_margin, net_margin, revenue_growth, pe, ev_ebit, "
    "dcf_value, dcf_gap, fcff, net_debt, discount_rate, initial_growth, terminal_growth, "
    "horizon, tax_rate, historical_growth, peer_median, peer_count, "
    "bear_value, base_value, bull_value, bear_ev, base_ev, bull_ev, "
    "consensus_revenue_current_year, consensus_revenue_next_year, consensus_target. "
    "For consensus_growth or growth_vs_history, call compute_derived first. "
    "Include at least one valid marker. Explain interpretation and limitations "
    "qualitatively in separate paragraphs. Unknown figures must be left out."

)

# For offline peer-outlier demo, these peers have fixtures in fixtures/.
_OFFLINE_PEERS = ["ASM.AS", "BESI.AS", "LRCX"]


def build_offline_script(ticker: str):
    """
    Scripted turns that exercise every tool through the loop, deterministically —
    INCLUDING the consensus-null branch: get_consensus returns available=false,
    so the script then calls get_historical_trend (the fallback basis). This
    stands in for the decision the live model makes.
    """
    def call(tool_id, name, inp):
        return lambda messages: ModelResponse(
            stop_reason="tool_use",
            content=[ToolUseBlock(id=tool_id, name=name, input=inp)],
        )

    def final(messages):
        return ModelResponse(
            stop_reason="end_turn",
            content=[TextBlock(text=(
                f"[stub note] View on {ticker}: financials, prices, ratios, a "
                f"scenario-weighted DCF, and a peer-outlier check all computed "
                f"deterministically. Consensus was unavailable, so the comparison "
                f"basis fell back to the company's own history (see trace). Live mode "
                f"replaces this text with the model's written note over the same figures.\n"
                "[[claim:operating_margin]]\n[[claim:dcf_value]]\n[[claim:historical_growth]]"
            ))],
        )

    return [
        call("t0", "get_financials", {"ticker": ticker}),
        call("t1", "get_prices", {"ticker": ticker}),
        call("t2", "compute_ratios", {"ticker": ticker}),
        call("t3", "run_dcf", {"ticker": ticker}),
        call("t4", "peer_outlier_check", {"ticker": ticker, "peers": _OFFLINE_PEERS}),
        call("t5", "get_consensus", {"ticker": ticker}),          # returns available=false
        call("t6", "get_historical_trend", {"ticker": ticker}),   # <- the branch decision
        final,
    ]


def _new_output(ticker, output_root="output"):
    import re
    import uuid
    from pathlib import Path
    from agent.state import utc_now
    from tools.registry import TICKER_PATTERN
    if not re.fullmatch(TICKER_PATTERN, ticker):
        raise ValueError("invalid ticker")
    run_id = utc_now().replace(":", "").replace("-", "") + "_" + uuid.uuid4().hex[:12]
    out = Path(output_root) / (ticker + "_" + run_id)
    out.mkdir(parents=True, exist_ok=False)
    return str(out), run_id


def _snapshot(ticker, mode, note, state, out_dir, run_id=None, provenance=None):
    import composer
    if not note and state.outcome:
        note = state.outcome.text
    fin = (state.results.get('get_financials') or {}).get('financials') or {}
    return composer.write_sidecar(
        ticker=ticker, mode=mode, note=note, note_template=note, analysis=state.results,
        calls=state.calls, execution=state.execution_record(), out_dir=out_dir,
        run_id=run_id, model_id=state.configuration.get('model_id'),
        currency=fin.get('currency'), provenance=provenance)


def _emit_artifacts(ticker, mode, note, state, out_dir=None, run_id=None, provenance=None):
    """Save analysis first; acquisition/render failures cannot erase that record."""
    import json
    from pathlib import Path
    import composer
    from tools.data import get_price_history, home_index_ticker
    from validation.publication import assess_record
    if out_dir is None:
        out_dir, run_id = _new_output(ticker)
    sidecar = _snapshot(ticker, mode, note, state, out_dir, run_id, provenance)
    print("Saved analysis: " + sidecar)
    with open(sidecar) as stream:
        record = json.load(stream)
    record['validation'], record['note'] = assess_record(record)
    composer.save_record(sidecar, record)
    index = home_index_ticker(ticker)
    for stage, symbol, key in [('fetch_price_history', ticker, 'price_history'),
                               ('fetch_index_history', index, 'index_history')]:
        if symbol is None:
            continue
        try:
            data = get_price_history(symbol)
            if not isinstance(data, dict) or data.get('error') or not data.get('history'):
                raise ValueError('history unavailable')
            if key == 'index_history':
                data['index_ticker'] = symbol
            record['chart_data'][key] = data
        except KeyboardInterrupt:
            record['artifacts']['status'] = 'failed'
            record['artifacts']['errors'].append({'stage': stage, 'error_type': 'KeyboardInterrupt'})
            composer.save_record(sidecar, record)
            return 130
        except Exception as exc:
            record['artifacts']['errors'].append({'stage': stage, 'error_type': type(exc).__name__})
        # Preserve each acquisition independently; no charts run before this.
        composer.save_record(sidecar, record)
    try:
        report = composer.build_report(sidecar)
    except KeyboardInterrupt:
        print('Report interrupted; saved analysis remains at ' + sidecar, file=sys.stderr)
        return 130
    except Exception as exc:
        print('Report failed (' + type(exc).__name__ + '); saved analysis remains at ' + sidecar, file=sys.stderr)
        return 1
    with open(sidecar) as stream:
        record = json.load(stream)
    _print_validation(record['validation'])
    print('NOTE (' + record['validation']['verdict'] + '):\n' + record['note'])
    print('Report: ' + report)
    print('Charts saved: ' + str(len(record['artifacts'].get('charts', []))))
    return _exit_code(record)


def _exit_code(record):
    execution = record.get('execution') or {}
    outcome = execution.get('outcome') or {}
    if outcome.get('reason') == 'interrupted':
        return 130
    if execution.get('status') == 'failed' or (record.get('artifacts') or {}).get('status') in ('failed', 'degraded'):
        return 1
    if execution.get('status') != 'completed':
        return 4
    return 0 if (record.get('validation') or {}).get('verdict') == 'pass' else 3


def _print_validation(v):
    print('Validation: ' + v['verdict'] + ' (evidence confidence: ' + v['confidence'] + ')')
    for check in v['checks']:
        if check['status'] != 'pass':
            print('  [' + check['status'] + '] ' + check['check'] + ': ' + check['detail'])


def _execute(ticker, mode, peers=None, output_root='output', trace=False):
    import composer
    # Set explicitly: ambient environment and .env cannot select a live source
    # for an offline run. Restore the caller's environment when used as a library.
    previous = os.environ.get('AGENT_DATA_SOURCE')
    state = RunState(ticker=ticker)
    out_dir, run_id = _new_output(ticker, output_root)
    provenance = composer._git_provenance()
    os.environ['AGENT_DATA_SOURCE'] = 'fixture' if mode == 'offline' else 'yfinance'
    state.configuration.update(mode=mode, data_source=os.environ['AGENT_DATA_SOURCE'], peers=peers or [])
    goal = f'Produce a defensible fundamental view on {ticker}.'
    if peers:
        goal += ' For peer_outlier_check, use exactly this peer set: ' + ', '.join(peers) + '.'
    note = ''
    try:
        _snapshot(ticker, mode, note, state, out_dir, run_id, provenance)
        try:
            if mode == 'live':
                from dotenv import load_dotenv
                load_dotenv()
                os.environ['AGENT_DATA_SOURCE'] = 'yfinance'
                if not os.environ.get('ANTHROPIC_API_KEY'):
                    state.finish('failed', reason='missing_api_key')
                    _snapshot(ticker, mode, note, state, out_dir, run_id, provenance)
                    print('Live mode requires ANTHROPIC_API_KEY. Saved run: ' + out_dir, file=sys.stderr)
                    return 1
                model = AnthropicModel()
            else:
                model = StubModel(script=build_offline_script(ticker))
            registry = ToolRegistry(state)
            result = run_agent(model=model, registry=registry, state=state, system=SYSTEM, goal=goal,
                checkpoint=lambda current: _snapshot(ticker, mode, '', current, out_dir, run_id, provenance))
            note = result.text
        except KeyboardInterrupt:
            state.finish('incomplete', note, 'interrupted')
        except Exception as exc:
            # Includes persistence errors: stop execution instead of continuing
            # unrecorded model calls. Attempt a final snapshot, then let I/O fail
            # clearly if the storage itself is unavailable.
            note = state.outcome.text if state.outcome else note
            state.finish('failed', note, 'execution_error_' + type(exc).__name__)
        _snapshot(ticker, mode, note, state, out_dir, run_id, provenance)
        if trace:
            state.print_trace()
        if state.outcome and state.outcome.reason == 'interrupted':
            print('Interrupted; saved run: ' + out_dir)
            return 130
        return _emit_artifacts(ticker, mode, note, state, out_dir, run_id, provenance)
    finally:
        if previous is None:
            os.environ.pop('AGENT_DATA_SOURCE', None)
        else:
            os.environ['AGENT_DATA_SOURCE'] = previous


def run_offline(ticker='ASML.AS', *, output_root='output', trace=False):
    return _execute(ticker.upper(), 'offline', output_root=output_root, trace=trace)


def run_live(ticker, peers=None, *, output_root='output', trace=False):
    return _execute(ticker.upper(), 'live', peers=peers, output_root=output_root, trace=trace)


def rebuild(model_json_path):
    import json
    import composer
    path = composer.build_report(model_json_path)
    with open(model_json_path) as stream:
        record = json.load(stream)
    print('Rebuilt and revalidated report: ' + path)
    return _exit_code(record)


def main(argv=None):
    import argparse
    import re
    from tools.registry import TICKER_PATTERN

    def ticker(value):
        if not re.fullmatch(TICKER_PATTERN, value):
            raise argparse.ArgumentTypeError('invalid ticker')
        return value.upper()

    parser = argparse.ArgumentParser(description='Agent 1 equity research. Exit: 0 approved, 1 failure, 2 usage, 3 review, 4 incomplete, 130 interrupted.')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--live', metavar='TICKER', type=ticker)
    modes.add_argument('--offline', metavar='TICKER', type=ticker, help='explicit offline ticker (default ASML.AS)')
    modes.add_argument('--rebuild', metavar='MODEL_JSON')
    parser.add_argument('--peers', nargs='+', type=ticker)
    parser.add_argument('--output', default='output', help='root directory for new runs')
    parser.add_argument('--trace', action='store_true')
    args = parser.parse_args(argv)
    if args.peers and not args.live:
        parser.error('--peers requires --live')
    if args.rebuild and (args.trace or args.output != 'output'):
        parser.error('--rebuild does not accept --trace or --output')
    try:
        if args.rebuild:
            return rebuild(args.rebuild)
        if args.live:
            return run_live(args.live, args.peers, output_root=args.output, trace=args.trace)
        return run_offline(args.offline or 'ASML.AS', output_root=args.output, trace=args.trace)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print('Run failed: ' + type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
