"""Operational exports preserve state and distinguish evidence provenance."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from monitoring.reporting import export_report, load_snapshot, render_report
from monitoring.recovery import decide, retry_triage, digest
from scheduler.cycle import run_cycle
from state.store import StateStore
from test_agent2_recovery import held, inspect


def test_export_held_approved_and_rejected_without_mutating(held, tmp_path):
    db, _, runs, token = held
    before = inspect(db)
    page = export_report(db, tmp_path/'held.html').read_text()
    assert 'REVIEW REQUIRED' in page and 'correction_requires_review' in page
    assert 'Previous value: 4' in page and 'proposed: 2' in page
    assert inspect(db) == before
    decide(db, token, 'approve', '<script>alert(1)</script>', 'Verified & corrected')
    before = inspect(db)
    page = export_report(db, tmp_path/'approved.html', cycle=3).read_text()
    assert 'WIDENING' in page and 'NEW_BREACH' in page
    assert 'Compare original and restated history' in page
    assert '<script>' not in page and '&lt;script&gt;' in page
    assert 'No pending correction reviews.' in page
    assert inspect(db) == before and before['runs'] == runs


def test_rejection_retains_history_and_is_visible(held, tmp_path):
    db, _, _, token = held
    decide(db, token, 'reject', 'Reviewer', 'Source withdrawn')
    page = export_report(db, tmp_path/'report.html').read_text()
    assert 'REJECT' in page and 'Source withdrawn' in page
    assert 'retain effective history' in page
    assert [r['value'] for r in inspect(db)['history']] == [1, 4, 5]


def test_retry_provenance_excludes_other_database_and_legacy(held, tmp_path):
    db, _, _, _ = held
    root = tmp_path/'audits'
    result = retry_triage(db, 3, audit_dir=root)
    assert result['status'] == 'completed'
    saved = json.loads(Path(result['audit_path']).read_text())
    other = root/'cycle-3-other'/'model.json'
    other.parent.mkdir()
    saved['retry_context']['db_path'] = str(tmp_path/'other.db')
    other.write_text(json.dumps(saved))
    legacy = root/'cycle-3-legacy'/'model.json'
    legacy.parent.mkdir()
    saved['retry_context'] = None
    legacy.write_text(json.dumps(saved))
    snapshot = load_snapshot(db, 3, root)
    assert len(snapshot['attempts']) == 1
    page = render_report(snapshot)
    assert 'original evidence, not current state' in page
    assert 'offline_stub' in page
    assert not load_snapshot(db, 2, root)['attempts']


def test_withheld_attempt_never_publishes_commentary(held, tmp_path):
    db, _, runs, _ = held
    path = tmp_path/'audits'/'cycle-3-failed'/'model.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'evidence_context': {'db_path': db, 'cycle_digest': digest(runs[2])},
        'execution': {'status': 'failed', 'started_at': '2026-01-01'},
        'publication': 'withheld', 'commentary': 'UNVALIDATED_MODEL_TEXT'}))
    page = render_report(load_snapshot(db, 3, tmp_path/'audits'))
    # Raw evidence is deliberately available in collapsed details; never rendered as commentary.
    assert '<pre>UNVALIDATED_MODEL_TEXT</pre>' not in page
    assert 'Commentary withheld or unavailable.' in page


def test_empty_missing_invalid_and_cli(tmp_path):
    db = tmp_path/'empty.db'
    with pytest.raises(ValueError, match='does not exist'):
        export_report(db, tmp_path/'report.html')
    assert not db.exists()
    store = StateStore(str(db)); store.close()
    assert 'No saved cycles' in export_report(db, tmp_path/'empty.html').read_text()
    with pytest.raises(ValueError, match='unavailable'):
        load_snapshot(db, 9)
    with pytest.raises(ValueError, match='positive'):
        load_snapshot(db, 0)
    result = run_cycle(db_path=str(db))
    completed = subprocess.run([sys.executable, 'monitor.py', '--db', str(db), '--report',
        str(tmp_path/'cli.html'), '--report-cycle', str(result['cycle'])], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert 'Baseline:' in (tmp_path/'cli.html').read_text()


def test_unavailable_and_threshold_directions(tmp_path):
    db = tmp_path/'state.db'
    run_cycle(db_path=str(db))
    snapshot = load_snapshot(db)
    snapshot['run'].update(status='review_required', rows=[], skipped=[{'item_id':'x', 'reason':'provider_unavailable'}])
    snapshot['current'][0].update(direction='above', value=None, breach_prob=None)
    page = render_report(snapshot)
    assert 'provider_unavailable' in page and 'compliance was not reassessed' in page
    assert 'At or above' in page and 'Unavailable' in page


def test_normal_cli_triage_is_linked_and_pending_state_is_marked(held, tmp_path, monkeypatch):
    import monitor
    from monitoring.triage import run_triage_record
    db, _, runs, token = held
    root = tmp_path/'audits'
    monkeypatch.setattr(monitor, '_DB', db)
    monkeypatch.setattr(monitor, 'run_triage_record',
                        lambda *a, **kw: run_triage_record(*a, audit_dir=root, **kw))
    monitor._triage_if_needed(runs[2], False)
    snapshot = load_snapshot(db, 3, root)
    assert len(snapshot['attempts']) == 1
    assert 'REVIEW PENDING; retained observation' in render_report(snapshot)
    decide(db, token, 'approve', 'Reviewer', 'Verified')
    page = render_report(load_snapshot(db, 3, root))
    assert f'href="#decision-{token}"' in page
    assert f"id='decision-{token}'" in page
