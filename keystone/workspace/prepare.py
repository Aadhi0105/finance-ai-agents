"""Generate explicitly registered synthetic examples with the existing engines.

This operator-only preparation is separate from the read-only web server. Existing
destinations are never reused. The inventory is published last; partial work is not
an available workspace. No issuer filings or existing output trees are imported.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from .catalog import Catalog, Manifest

ROOT = Path(__file__).resolve().parents[2]


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False, default=str) + '\n')


def number(value, *, percent=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return 'Unavailable'
    return f'{value:.1%}' if percent else f'{value:,.2f}'


def metric(label, value, basis):
    return dict(label=label, value=str(value), basis=basis)


def prepare_workspace(destination, *, native=False):
    from keystone.maintenance import gate
    destination = Path(destination).absolute()
    old_mask = os.umask(0o077)
    previous = {k: os.environ.get(k) for k in ('AGENT_DATA_SOURCE', 'AGENT_STATS_VIA_MCP', 'LM_DICTIONARY_CSV', 'MPLBACKEND')}
    try:
        with gate(exclusive=True):
            destination.mkdir(parents=True, exist_ok=False)
            os.environ.update(AGENT_DATA_SOURCE='fixture', AGENT_STATS_VIA_MCP='0',
                              LM_DICTIONARY_CSV='', MPLBACKEND='Agg')
            with redirect_stdout(io.StringIO()):
                manifest = _generate(destination, publish=not native)
                if native:
                    from .report_views.publish import register_views
                    register_views(destination, manifest)
            Catalog(destination).load()
        return destination
    finally:
        os.umask(old_mask)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _generate(destination, *, publish=True):
    created = datetime.now(timezone.utc).isoformat()
    private = destination / '_private'
    private.mkdir()
    runs = []

    def add(ident, agent, workflow, title, entity, period, source_id, summary,
            metrics, limitations, files, checks=(), status='completed'):
        folder = destination / 'runs' / ident
        folder.mkdir(parents=True)
        artifacts = []
        for index, (source, name, label, kind) in enumerate(files):
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            data = target.read_bytes()
            artifacts.append(dict(id=f'file-{index}', name=name, label=label, kind=kind,
                                  sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)))
        report = next(a for a in artifacts if a['kind'] == 'report')
        runs.append(dict(id=ident, agent=agent, workflow=workflow, title=title, entity=entity,
            period=period, prepared_at=created, source_run_id=str(source_id),
            execution_status=status, review_status='review_required', summary=summary,
            metrics=metrics, checks=list(checks),
            limitations=['Synthetic demonstration. Figures are not verified company facts.', *limitations],
            artifacts=artifacts, report_id=report['id']))

    # Agent 1: use the real saved-model and HTML pipeline; retain its publication hold.
    from run import run_offline
    code = run_offline('ASML.AS', output_root=private / 'research')
    if code != 3:
        raise ValueError('Unexpected synthetic research outcome.')
    model, = (private / 'research').glob('*/model.json')
    research = json.loads(model.read_text())
    financials = research['analysis']['get_financials']['financials']
    report = model.parent / 'report_REVIEW.html'
    files = [(report, 'report_REVIEW.html', 'Research report', 'report'),
             (model, 'model.json', 'Saved analysis and validation', 'evidence'),
             (ROOT / 'fixtures/ASML.AS.json', 'input.json', 'Financial input fixture', 'input')]
    # Register only charts generated in this new, dedicated run directory.
    files += [(p, 'charts/' + p.name, p.stem.replace('_', ' ').title(), 'chart')
              for p in sorted((model.parent / 'charts').glob('*.png'))]
    add('research-example', 'agent1', 'research', 'Annual research', 'ASML · fixture',
        financials['period'], research.get('run_id', model.parent.name),
        'Annual financial analysis with a retained publication hold and a saved evidence trail.',
        [metric('Revenue', number(financials['revenue']), 'EUR · base units · annual fixture'),
         metric('Net income', number(financials['net_income']), 'EUR · base units · annual fixture'),
         metric('Comparison basis', 'Own history', 'Fixture analyst consensus is unavailable')],
        ['Review-required publication is preserved.', 'Historical fixture inputs; no live quote or analyst refresh.'],
        files, ['Original model.json retained', 'Existing research renderer used'])

    # Agent 2: new isolated fixture state, then read-only export of its ninth cycle.
    from scheduler.cycle import run_cycle
    from monitoring.reporting import export_report, load_snapshot
    monitor_db = private / 'monitor.duckdb'
    for _ in range(9):
        cycle = run_cycle(db_path=str(monitor_db))
    snapshot = load_snapshot(monitor_db, cycle=9, audit_dir=private / 'no-audits')
    monitor_html = export_report(monitor_db, private / 'monitor.html', cycle=9, audit_dir=private / 'no-audits')
    save_json(private / 'monitor.json', snapshot)
    rows = snapshot['current']
    add('monitoring-example', 'agent2', 'monitoring', 'Financial monitoring', 'Example company watchlist',
        '2026-01-09 · cycle 9', 9,
        'Saved monitoring observations, threshold exceptions and original history from an isolated fixture watchlist.',
        [metric('Saved cycle', '9', 'Selected saved cycle'),
         metric('Monitored items', len(rows), 'Rows in the saved snapshot'),
         metric('Threshold breaches', sum(r.get('breached') is True for r in rows), 'Saved classifications · analyst policy')],
        ['Synthetic thresholds do not establish contractual covenant compliance.',
         'Report browsing does not refresh observations or decide corrections.'],
        [(Path(monitor_html), 'report.html', 'Monitoring report', 'report'),
         (private / 'monitor.json', 'snapshot.json', 'Saved cycle snapshot', 'evidence'),
         (ROOT / 'fixtures/covenants.json', 'input.json', 'Synthetic watchlist', 'input')],
        ['Saved cycle exported without a refresh'])

    # Agent 3A: replay the saved synthetic study through the existing bundle gate.
    from agent3.execution import Attempt
    from agent3.track_a import load_event_set
    from agent3.orchestrator import analyze_assembled
    from agent3.bundles import seal, read_bundle, replay, export_html
    assembled = load_event_set('semicap_earnings', source='fixture')
    events = Attempt.create(private / 'events', {'event_type': 'semicap_earnings', 'source': 'fixture'})
    events.checkpoint('assembled', {'assembled_inputs': assembled, 'n_event_types_tested': 1})
    result = analyze_assembled('semicap_earnings', assembled)
    events.checkpoint('result', {'result': result})
    events.finish(result['status'])
    event_bundle = seal(events)
    bundle = read_bundle(event_bundle)
    rebuilt = replay(bundle)
    if rebuilt['verification'] != 'matched':
        raise ValueError('Event replay did not match.')
    (private / 'events.html').write_text(export_html(bundle, rebuilt))
    save_json(private / 'events-replay.json', rebuilt)
    study = result.get('study', {})
    add('events-example', 'agent3', 'events', 'Historical event study', 'Semiconductor peers · fixture',
        'Retained synthetic event windows', events.record['run_id'],
        'A replay-checked historical study. Descriptive diagnostics remain separate from publication approval.',
        [metric('Historical events', study.get('n_events', 'Unavailable'), 'Count from the saved study'),
         metric('Replay', rebuilt['verification'].title(), 'Retained inputs and saved deterministic stages'),
         metric('Publication', 'Held for review', 'No forward-return forecast')],
        ['Synthetic price windows are not observed market returns.',
         'No interpolated event path, forward probability or accepted predictive calibration.'],
        [(private / 'events.html', 'report.html', 'Event-study report', 'report'),
         (event_bundle, 'bundle.json', 'Sealed event evidence', 'evidence'),
         (private / 'events-replay.json', 'replay.json', 'Replay verification', 'evidence')],
        ['Bundle integrity checked', 'Offline replay matched'], status=events.record['status'])

    # Agent 3B: invented headlines/publishers, rather than syndicated text.
    from agent3.news_funnel import run_funnel
    from agent3.sentiment import StubScorer
    cutoff = '2026-01-28T23:59:00Z'
    items = [dict(id='example-1', headline='Example Rail opens a fictional maintenance facility',
        body='Synthetic exercise text: growth and investment.', entities=['DEMO'],
        source='Synthetic bulletin', url='https://example.org/synthetic-1', language='en',
        published_at='2026-01-28T12:00:00Z', retrieved_at=cutoff, stub_score=0.3, stub_confidence=None),
        dict(id='example-2', headline='Example Rail reports a fictional delivery delay',
        body='Synthetic exercise text: uncertainty and delay.', entities=['DEMO'],
        source='Synthetic bulletin', url='https://example.org/synthetic-2', language='en',
        published_at='2026-01-28T14:00:00Z', retrieved_at=cutoff, stub_score=-0.3, stub_confidence=None)]
    request = dict(ticker='DEMO', aliases=['Example Rail'], max_age_days=7, data_mode='fixture', scorer='stub', as_of=cutoff)
    news = Attempt.create(private / 'news', request)
    result = run_funnel(items, {'DEMO'}, StubScorer(), aliases={'DEMO': ['Example Rail']}, as_of=cutoff, data_mode='fixture')
    news.checkpoint('news_scoring', {'input_items': items, 'as_of': cutoff})
    news.checkpoint('news_result', {'result': result})
    news.finish(result['status'])
    news_bundle = seal(news)
    bundle = read_bundle(news_bundle)
    rebuilt = replay(bundle)
    if rebuilt['verification'] != 'matched':
        raise ValueError('News replay did not match.')
    (private / 'news.html').write_text(export_html(bundle, rebuilt))
    save_json(private / 'news-input.json', {'classification': 'synthetic', 'items': items})
    add('news-example', 'agent3', 'news', 'News evidence review', 'Example Rail · fictional company',
        '2026-01-28 · saved cutoff', news.record['run_id'],
        'Invented headlines demonstrate relevance, saved evidence and held diagnostic tone. No live feed is connected.',
        [metric('Input items', len(items), 'Invented headlines'),
         metric('Replay', 'Matched', 'Saved fixture scores; no new inference'),
         metric('Tone', 'Withheld', 'Stub scores are demonstration-only')],
        ['News timestamps describe the saved cutoff, not current freshness.',
         'Stub scores are not accepted financial sentiment or a trading signal.'],
        [(private / 'news.html', 'report.html', 'News evidence report', 'report'),
         (news_bundle, 'bundle.json', 'Sealed news evidence', 'evidence'),
         (private / 'news-input.json', 'input.json', 'Invented headline inputs', 'input')],
        ['Bundle integrity checked', 'Offline replay matched'], status=news.record['status'])

    # Agent 4: a real close on the synthetic amount-based fixture, then saved rendering.
    from agent4.close import execute_close
    from agent4.state import VarianceStore
    from agent4.report import render_report, validate_bundle
    request = json.loads((ROOT / 'fixtures/agent4/close-june.json').read_text())
    with VarianceStore(private / 'variance.duckdb') as store:
        saved = execute_close(store, request)
        validate_bundle(saved)
        (private / 'close.html').write_text(render_report(saved, [saved]))
        save_json(private / 'close.json', saved['bundle'])
    tree = saved['bundle']['report']['full_hierarchy']
    add('close-example', 'agent4', 'close', 'Monthly financial close', 'Example Ltd · fictional company',
        request['close_period'], request['run_id'],
        'Saved budget-versus-actual close with reconciled amounts, input versions and retained lineage.',
        [metric('Budget profit', f"EUR {tree['budget_cents'] / 100:,.2f}", 'Saved close · amount-based'),
         metric('Actual profit', f"EUR {tree['actual_cents'] / 100:,.2f}", 'Saved close · amount-based'),
         metric('Variance', f"EUR {(tree['actual_cents'] - tree['budget_cents']) / 100:+,.2f}", 'Actual less budget · synthetic')],
        ['Accounting checks do not establish business causes or finance approval.',
         'Authorised real-company acceptance remains pending.'],
        [(private / 'close.html', f"{saved['bundle']['run_id']}.html", 'Financial close report', 'report'),
         (private / 'close.json', f"{saved['bundle']['run_id']}.json", 'Saved close and lineage', 'evidence'),
         (ROOT / 'fixtures/agent4/close-june.json', 'input.json', 'Synthetic budget and actuals', 'input')],
        ['Saved bundle validated', 'Budget and actuals reconciled'])

    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=False)
    manifest = Manifest.model_validate(dict(schema_version=1, kind='keystone.synthetic-workspace',
        classification='synthetic', prepared_at=created, code_commit=commit.stdout.strip() or None,
        code_worktree_dirty=bool(subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT,
            capture_output=True, text=True, check=False).stdout.strip()),
        preparer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        production_release_approved=False, runs=runs))
    # Publish the catalogue only after every engine/export completed successfully.
    if publish:
        save_json(destination / 'catalog.json', manifest.model_dump())
    return manifest
