"""Bounded Agent 2 acceptance; isolated databases, optional paid live CLI triage.

Run: python -m scripts.check_agent2_acceptance [--live] [--env-file PATH]
No existing monitor state is modified. Results are retained in a unique directory.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def verify_scenarios(cycles):
    """Expected fixture outcomes, independently specified of transport parity."""
    expected = [(5, 'gamma_liquidity', 'RESOLVED', False),
                (7, 'delta_leverage', 'NEW_BREACH', True),
                (9, 'acme_int_cover', 'NEW_BREACH', True),
                (10, 'acme_int_cover', 'RESOLVED', False),
                (10, 'acme_leverage', 'NEW_BREACH', True)]
    for number, item, status, breached in expected:
        row = next(row for row in cycles[number - 1]['rows'] if row['item_id'] == item)
        assert row['status'] == status and row['breached'] is breached, (number, item)
        assert item in {row['item_id'] for row in cycles[number - 1]['surfaced']}
    anomaly = next(row for row in cycles[8]['rows'] if row['item_id'] == 'acme_int_cover')
    assert anomaly['anomaly_significant'] is True
    assert all('beta_leverage' not in {r['item_id'] for r in c['surfaced']} for c in cycles)
    assert any(row['item_id'] == 'acme_leverage' and not row['breached']
               for c in cycles[:9] for row in c['surfaced'])


def exercise(directory):
    from scheduler.cycle import run_cycle
    from state.store import StateStore
    from monitoring.triage import HistorySnapshot, run_triage_record
    db = str(directory / 'monitor.duckdb')
    cycles = [run_cycle(db_path=db) for _ in range(12)]
    verify_scenarios(cycles)
    assert cycles[0]['baseline'] and not cycles[0]['surfaced']
    assert cycles[-1]['status'] == cycles[-2]['status'] == 'no_new_observations'
    store = StateStore(db)
    try:
        assert store.next_cycle() == 13
        for cycle in cycles:
            assert store.get_run(cycle['cycle']) == cycle
        snapshots = [(cycle, HistorySnapshot(store, cycle['surfaced'], cycle['cycle']))
                     for cycle in cycles if cycle['surfaced']]
    finally:
        store.close()
    for cycle, snapshot in snapshots:
        result = run_triage_record(snapshot, cycle['surfaced'], cycle=cycle['cycle'],
                                   audit_dir=directory / 'triage')
        assert result['status'] == 'completed'
        audit = json.loads(Path(result['audit_path']).read_text())
        assert audit['publication'] == 'published'
        assert len(audit['calls']) == 2
    replay = run_cycle(db_path=db, asof_cycle=9)
    assert replay == {**cycles[8], 'replayed': True}
    catchup_db = str(directory / 'catchup.duckdb')
    run_cycle(db_path=catchup_db)
    catchup = run_cycle(db_path=catchup_db, asof_cycle=9)
    assert catchup['gap'] == 7
    return {'cycles': cycles, 'catchup': catchup, 'triaged_cycles': len(snapshots)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Make paid model calls for fixture cycle 9')
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'output' / 'agent2-acceptance')
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        args.worker.mkdir(parents=True, exist_ok=True)
        (args.worker / 'cycles.json').write_text(json.dumps(exercise(args.worker), indent=2, allow_nan=False))
        return 0
    directory = args.output.resolve() / uuid4().hex
    directory.mkdir(parents=True)
    summary = {'status': 'running', 'data_mode': 'bundled_fixtures', 'live_requested': args.live}
    try:
        for mode in ('local', 'mcp'):
            summary['stage'] = mode
            env = {**os.environ, 'AGENT_STATS_VIA_MCP': '1' if mode == 'mcp' else '0'}
            run = subprocess.run([sys.executable, '-m', 'scripts.check_agent2_acceptance',
                                  '--worker', str(directory / mode)], cwd=ROOT, env=env,
                                 capture_output=True, text=True, timeout=180)
            if run.returncode:
                raise RuntimeError(f'{mode} worker failed (exit {run.returncode})')
        local = json.loads((directory / 'local/cycles.json').read_text())
        mcp = json.loads((directory / 'mcp/cycles.json').read_text())
        assert local == mcp, 'Local/MCP divergence'
        summary.update(transport_parity=True, cycles_per_transport=12,
                       triaged_cycles_per_transport=local['triaged_cycles'], replay=True, catchup=True)
        if args.live:
            summary['stage'] = 'credentials'
            from dotenv import load_dotenv
            if args.env_file:
                load_dotenv(args.env_file, override=False)
            from monitoring.triage import prepare_live
            prepare_live()
            db = str(directory / 'live.duckdb')
            env = {**os.environ, 'AGENT_STATS_VIA_MCP': '0'}
            # Each command is a fresh process, just as in an operator's terminal.
            for name, command in [('baseline', ['--run', '8']), ('live', ['--once', '--live']),
                                  ('replay', ['--catchup', '9', '--live']), ('state', ['--state'])]:
                summary['stage'] = name
                run = subprocess.run([sys.executable, str(ROOT / 'monitor.py'), '--db', db, *command],
                                     cwd=directory, env=env, capture_output=True, text=True, timeout=240)
                (directory / f'{name}.txt').write_text(run.stdout)
                summary['last_cli_exit'] = run.returncode
                if run.returncode:
                    raise RuntimeError(f'{name} CLI failed (exit {run.returncode}); inspect saved stdout/audit')
                if name == 'live':
                    audit_path = next(line.removeprefix('Triage audit: ') for line in run.stdout.splitlines()
                                      if line.startswith('Triage audit: '))
                    audit = json.loads(Path(audit_path).read_text())
                    assert audit['model_mode'] == 'live' and audit['publication'] == 'published'
                    assert audit['execution']['status'] == 'completed'
                    assert audit['calls'], 'Live acceptance requires observed tool use'
                    (directory / 'live-model.json').write_text(json.dumps(audit, indent=2, allow_nan=False))
                    summary['live'] = {'audit_path': audit_path,
                        'model': audit['execution']['configuration'].get('model_id'),
                        'tool_calls': len(audit['calls']), 'publication': audit['publication']}
                elif name == 'replay':
                    assert 'Triage skipped: saved cycle replay' in run.stdout
                    assert 'Triage audit:' not in run.stdout
            from state.store import StateStore
            store = StateStore(db)
            try:
                assert store.next_cycle() == 10
                for number in range(1, 10):
                    assert store.get_run(number) == local['cycles'][number - 1]
            finally:
                store.close()
            summary['live']['committed_ledger_verified'] = True
        summary.update(status='passed', stage='complete')
    except (Exception, KeyboardInterrupt) as exc:
        summary.update(status='failed', error_type=type(exc).__name__)
    (directory / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    print(json.dumps({'summary': str(directory / 'summary.json'), **summary}, indent=2))
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
