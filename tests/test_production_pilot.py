"""Prevent rehearsal evidence from silently becoming release approval."""
import pytest
from scripts.check_keystone_pilot import MATRIX, gate_records, pending_manifest, run_acceptance


def test_every_gate_remains_unassessed_for_new_candidate():
    gates = gate_records(MATRIX.read_text())
    assert len(gates) == 26
    # Even a historical pass does not approve a different candidate.
    for gate in gates:
        gate['baseline_status'] = 'passed'
    result = pending_manifest({'code_commit': 'abc', 'worktree_dirty': True}, gates)
    assert all(g['candidate_status'] == 'not assessed' and not g['reviewer'] for g in result['gates'])
    assert result['production_release_approved'] is False
    assert result['production_accepted_capabilities'] == []
    assert result['release_signoff'] is None
    assert result['human_uat']['status'] == 'not started'


def test_missing_duplicate_or_malformed_gate_refused():
    text = MATRIX.read_text()
    row = next(line for line in text.splitlines() if line.startswith('| V1-'))
    for damaged in (text.replace(row, ''), text + '\n' + row, text.replace(row, row + ' extra |')):
        with pytest.raises(ValueError):
            gate_records(damaged)


def test_existing_destination_never_overwritten(tmp_path):
    marker = tmp_path / 'pilot.json'
    marker.write_text('existing evidence')
    with pytest.raises(FileExistsError):
        run_acceptance(tmp_path)
    assert marker.read_text() == 'existing evidence'


def test_doctor_failure_is_retained_without_approval(tmp_path, monkeypatch):
    from keystone import environment
    monkeypatch.setattr(environment, 'inspect_environment', lambda: dict(
        code_commit='abc', worktree_dirty=True, status='review_required'))
    with pytest.raises(ValueError, match='doctor'):
        run_acceptance(tmp_path / 'failed')
    import json
    record = json.loads((tmp_path / 'failed/pilot.json').read_text())
    assert record['rehearsal']['status'] == 'failed'
    assert record['production_release_approved'] is False
