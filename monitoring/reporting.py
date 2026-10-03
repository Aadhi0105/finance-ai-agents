"""Portable, read-only Agent 2 reports. Saved evidence is always HTML escaped."""
from datetime import datetime, timezone
from html import escape
import json
import math
from pathlib import Path
import os
import tempfile

from monitoring.recovery import digest
from state.store import StateStore, _json_date


def text(value):
    return escape(str(value if value is not None else 'Unavailable'), quote=True)


def number(value):
    if not isinstance(value, (float, int)) or isinstance(value, bool) or not math.isfinite(value):
        return 'Unavailable'
    return f'{value:,.4g}'


def evidence(value, label='View saved evidence'):
    return f'<details><summary>{text(label)}</summary><pre>{text(json.dumps(value, indent=2, ensure_ascii=False, default=_json_date))}</pre></details>'


def observations(rows):
    if not rows:
        return '<p>No observations in this view. Compliance was not reassessed.</p>'
    cells = []
    for row in rows:
        direction = {'below': 'At or below', 'above': 'At or above'}.get(row.get('direction'), 'Direction unavailable:')
        state = row.get('status', 'Unavailable')
        if row.get('_pending_review'):
            state += ' · REVIEW PENDING; retained observation'
        metric = row.get('metric')
        labels = {'current_ratio': 'Current ratio (×)', 'operating_interest_coverage': 'Operating interest coverage (×)',
                  'net_debt_to_operating_ebitda_proxy': 'Net debt / operating EBITDA proxy (×)'}
        metric_label = labels.get(metric, metric)
        revision_link = (f'<a href="#decision-{text(row["revision_id"])}">Correction decision</a>'
                         if row.get('revision_id') else '')
        if row.get('retired_to'):
            state += ' · Retired; replaced by ' + row['retired_to']
        signals = ', '.join(label for key, label in [('anomaly_significant', 'Anomaly'), ('drifting', 'Drift'), ('breach_tail', 'Tail risk')] if row.get(key) is True)
        if signals:
            state += ' · ' + signals
        if row.get('breach_prob') is None:
            state += ' · Probability unavailable'
        breach = 'Breached' if row.get('breached') is True else ('Within threshold' if row.get('breached') is False else 'Unavailable')
        cells.append('<tr>' + ''.join(f'<td>{value}</td>' for value in [
            f"{text(row.get('entity'))}<small>{text(row.get('item_id'))}</small>",
            text(metric_label), text(row.get('data_ts')), number(row.get('value')),
            f"{direction} {number(row.get('threshold'))}",
            f"{text(state)}<small>{breach}</small>{revision_link}",
            evidence(row)]) + '</tr>')
    return '<div class="table-scroll" tabindex="0" role="region" aria-label="Observations table"><table><thead><tr>' + ''.join(f'<th scope="col">{h}</th>' for h in ['Company / item', 'Metric', 'Observation date', 'Value', 'Requirement', 'Classification', 'Evidence']) + '</tr></thead><tbody>' + ''.join(cells) + '</tbody></table></div>'


def load_snapshot(db_path, cycle=None, audit_dir=None):
    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError('Monitoring database does not exist; run a monitoring cycle first.')
    if cycle is not None and (type(cycle) is not int or cycle < 1):
        raise ValueError('Report cycle must be a positive integer.')
    store = StateStore(str(path), read_only=True)
    try:
        runs = [json.loads(r[0]) for r in store.con.execute('SELECT payload FROM cycle_runs ORDER BY cycle').fetchall()]
        selected = next((r for r in runs if r['cycle'] == cycle), None) if cycle else (runs[-1] if runs else None)
        if cycle and selected is None:
            raise ValueError('Requested saved cycle is unavailable.')
        current = []
        for row in store.full_state():
            detail = store.get_observation_evidence(row['item_id'], row['data_ts']) or {}
            current.append({**detail, **row, '_pending_review': bool(store.pending_review(row['item_id']))})
        snapshot = dict(run=selected, current=current, reviews=store.reviews(), decisions=store.decisions(),
                        data_mode=store.source_mode(), cycles=[r['cycle'] for r in runs])
    finally:
        store.close()
    attempts, unreadable = [], 0
    root = Path(audit_dir).expanduser() if audit_dir else Path(__file__).resolve().parents[1] / 'output' / 'monitor-triage'
    if selected:
        for audit in sorted(root.glob('cycle-*/model.json')):
            try:
                record = json.loads(audit.read_text())
                context = record.get('retry_context') or record.get('evidence_context') or {}
                if context.get('db_path') != str(path) or context.get('cycle_digest') != digest(selected):
                    continue
                attempts.append({'artifact': str(audit), **record})
            except (OSError, ValueError, TypeError, AttributeError):
                unreadable += 1
    snapshot.update(attempts=attempts, unreadable_audits=unreadable,
                    exported_at=datetime.now(timezone.utc).isoformat())
    return snapshot


def render_report(snapshot):
    run = snapshot['run']
    parts = ['<header><p class="eyebrow">KEYSTONE · AGENT 2</p><h1>Monitoring report</h1>',
             f"<p>Exported {text(snapshot['exported_at'])}. Static snapshot; refresh by exporting again.</p></header>"]
    mode = snapshot.get('data_mode')
    parts.append('<aside>' + ('Live annual statement observations. Thresholds are analyst policies, not contractual covenants. Observation dates are statement periods, not publication dates.' if mode == 'yfinance' else 'Bundled fixture data — illustrative, not a live market feed.' if mode == 'bundled_fixtures' else 'Data source unavailable.') + '</aside>')
    parts.append('<nav><a href="#saved">Saved cycle</a><a href="#current">Effective state</a><a href="#reviews">Pending reviews</a><a href="#decisions">Decisions</a><a href="#triage">Triage attempts</a></nav>')
    parts.append('<section id="saved"><h2>Original saved cycle</h2>')
    if run is None:
        parts.append('<p>No saved cycles. No monitoring assessment is available.</p>')
    else:
        status = run.get('status', 'unavailable')
        parts.append(f"<div class=notice><strong>Cycle {text(run['cycle'])} · {text(status.replace('_', ' ').upper())}</strong><p>Cycle data date: {text(run.get('data_ts'))}. Individual observation dates appear below.</p></div>")
        if run.get('baseline'):
            parts.append('<p>Baseline: classification and alerting suppressed; detection begins on subsequent observations.</p>')
        if run.get('gap'):
            parts.append(f"<p>Catch-up gap: {text(run['gap'])} missed cycles. Changes may have originated during this gap.</p>")
        if not run.get('rows'):
            parts.append('<p><strong>No new observations — compliance was not reassessed. Prior state is retained.</strong></p>')
        elif not run.get('surfaced') and not run.get('baseline'):
            parts.append('<p>No newly surfaced exceptions; prior breaches may remain active.</p>')
        parts.append('<h3>Coverage and held observations</h3>')
        for skipped in run.get('skipped', []):
            parts.append(f"<article><strong>{text(skipped.get('item_id'))}: {text(skipped.get('reason'))}</strong>{evidence(skipped)}</article>")
        if not run.get('skipped'):
            parts.append('<p>No skipped observations recorded for this cycle.</p>')
        parts.append('<h3>Assessed observations</h3>' + observations(run.get('rows', [])))
        parts.append(evidence(run, 'Original cycle evidence and report'))
    parts.append('</section><section id="current"><h2>Current effective state</h2><p>As of export, across all saved cycles. This may differ from the original selected cycle after later observations or approved corrections. It is not a fresh market assessment. Supported annual ratios use multiples (×). Other metrics retain their saved identifiers; consult evidence for their definitions and units.</p>')
    parts.append(observations(snapshot['current']) + '</section><section id="reviews"><h2>Pending correction reviews</h2><p>Read-only view. Decisions remain in the existing CLI approval workflow.</p>')
    if not snapshot['reviews']:
        parts.append('<p>No pending correction reviews.</p>')
    for review in snapshot['reviews']:
        candidate = review.get('candidate') or {}
        parts.append(f"<article><h3>{text(review.get('entity') or review.get('item_id'))}</h3><p>{text(review.get('reason'))} · observation {text(candidate.get('data_ts'))}</p><p>Previous value: {number(review.get('previous_value', (review.get('previous') or {}).get('value')))} → proposed: {number(candidate.get('value'))}</p><p>Review ID: {text(review.get('review_id'))}</p>{evidence(review)}</article>")
    parts.append('</section><section id="decisions"><h2>Correction decision history</h2><p>Original cycle reports remain unchanged. Reviewer names are local attribution, not authenticated signatures.</p>')
    if not snapshot['decisions']:
        parts.append('<p>No correction decisions recorded.</p>')
    for decision in sorted(snapshot['decisions'], key=lambda d: d.get('decided_at', '')):
        parts.append(f"<article id='decision-{text(decision.get('review_id'))}'><h3>{text(decision.get('action', '').upper())} · {text(decision.get('item_id'))}</h3><p>{text(decision.get('decided_at'))} · Reviewer: {text(decision.get('reviewer'))}</p><p>Reason: {text(decision.get('reason'))}</p><p>{text(decision.get('effect'))}</p><p>Review ID: {text(decision.get('review_id'))}</p>")
        if decision.get('after'):
            parts.append('<details><summary>Compare original and restated history</summary><h4>Before decision</h4>' + observations(decision.get('before', [])) + '<h4>After decision</h4>' + observations(decision['after']) + '</details>')
        parts.append(evidence(decision, 'Decision evidence') + '</article>')
    parts.append('</section><section id="triage"><h2>Triage attempt history for selected cycle</h2><p>Attempts use original saved evidence, not current effective state. A retry does not advance the monitoring cycle.</p>')
    if not snapshot['attempts']:
        parts.append('<p>No linked audit attempts available. Older unlinked audits are not attributed to this database. This does not establish that triage succeeded.</p>')
    if snapshot['unreadable_audits']:
        parts.append('<p>Some audit files could not be read; this history may be incomplete.</p>')
    for attempt in sorted(snapshot['attempts'], key=lambda a: str(a.get('execution', {}).get('started_at', ''))):
        execution = attempt.get('execution') or {}
        status = attempt.get('publication_status') or execution.get('status', 'unknown')
        parts.append(f"<article><h3>{text(status)} · {text(attempt.get('model_mode'))}</h3><p>{text(execution.get('started_at'))}</p><p>Reason: {text(attempt.get('publication_reason') or (execution.get('outcome') or {}).get('reason'))}</p><p>Audit artifact: {text(attempt['artifact'])}</p>")
        if attempt.get('publication') == 'published' and status == 'completed':
            parts.append('<pre>' + text(attempt.get('commentary', '')) + '</pre>')
        else:
            parts.append('<p>Commentary withheld or unavailable.</p>')
        parts.append(evidence(attempt, 'Raw audit evidence (may include unvalidated model text)') + '</article>')
    parts.append('</section>')
    css = '''*{box-sizing:border-box}body{margin:0;background:#f2f5f6;color:#172f38;font:16px/1.55 system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:32px 20px}h1{font-size:2.3rem;margin:.25em 0}h2{margin-top:0}header,section,aside{margin-bottom:22px}section,aside{padding:22px;background:white;border:1px solid #d5e0e4;border-radius:12px}aside,.notice{background:#edf3f7;padding:16px;border-left:4px solid #486e80}nav{display:flex;flex-wrap:wrap;gap:16px;margin:24px 0}a{color:#185775}p,td,pre,summary{overflow-wrap:anywhere}article{border-top:1px solid #d5e0e4;padding:16px 0}small{display:block;color:#50616b}pre{white-space:pre-wrap;font-size:13px;background:#f2f5f6;padding:12px}summary{cursor:pointer;color:#185775;padding:8px 0}table{border-collapse:collapse;width:100%;min-width:760px}th,td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #d5e0e4}td{max-width:250px}th{font-size:13px}.table-scroll{overflow-x:auto}a:focus-visible,summary:focus-visible,.table-scroll:focus-visible{outline:3px solid #b36c16;outline-offset:3px}.eyebrow{letter-spacing:.13em;font-size:12px}@media(max-width:600px){main{padding:18px 12px}section,aside{padding:14px}h1{font-size:1.8rem}}'''
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Agent 2 monitoring report</title><style>' + css + '</style></head><body><main>' + ''.join(parts) + '</main></body></html>'


def export_report(db_path, output, *, cycle=None, audit_dir=None):
    target = Path(output).expanduser().resolve()
    if target.suffix.lower() != '.html':
        raise ValueError('Report output must use an .html extension.')
    if target == Path(db_path).expanduser().resolve():
        raise ValueError('Report output cannot overwrite the database.')
    html = render_report(load_snapshot(db_path, cycle, audit_dir))
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=target.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(html)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)
    return target
