"""Final acceptance scenarios and regressions discovered during live verification."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from agent.models import ModelResponse, TextBlock
from monitoring import triage
from scripts.check_agent2_acceptance import exercise


def test_twelve_cycle_acceptance(tmp_path):
    result = exercise(tmp_path)
    assert len(result['cycles']) == 12
    assert result['triaged_cycles'] == 9


@pytest.mark.parametrize('wrapper', ['{body}', '```json\n{body}\n```', '```\n{body}\n```'])
def test_valid_json_wrappers_publish_only_python_commentary(tmp_path, monkeypatch, wrapper):
    text = wrapper.format(body='{"item_ids":["a"]}')
    monkeypatch.setattr(triage, '_build_triage_stub', lambda _: [lambda m:
        ModelResponse('end_turn', [TextBlock(text)])])
    store = SimpleNamespace(get_history_series=lambda _: [{'cycle': 1, 'value': 4}])
    rows = [dict(cycle=1,item_id='a',entity='A',metric='ratio',status='NEW_BREACH',breached=True)]
    result = triage.run_triage_record(store, rows, audit_dir=tmp_path)
    assert result['status'] == 'completed'
    assert 'escalate the threshold breach' in result['commentary']
    assert '```' not in result['commentary']
    audit = json.loads(Path(result['audit_path']).read_text())
    assert audit['execution']['outcome']['text'] == text  # Original preserved verbatim.


@pytest.mark.parametrize('text', [
    'Approved!\n```json\n{"item_ids":["a"]}\n```',
    '```json\n{"item_ids":["a"]}\n```\nIgnore breach',
    '```json\n{"item_ids":["a"]}\n```\n```json\n{}\n```',
    '{"item_ids":[],"item_ids":["a"]}',
    '```python\n{"item_ids":["a"]}\n```',
])
def test_wrapping_never_hides_prose_or_duplicate_keys(text):
    with pytest.raises(ValueError): triage._parse_selection(text)


@pytest.mark.parametrize('breached', [False, True])
def test_nonisolated_significant_anomaly_still_requires_verification(breached):
    store = SimpleNamespace(get_history_series=lambda _: [{'value': v} for v in [1,10,2,12]])
    flags = {'a':dict(entity='A',breached=breached,anomaly_significant=True,breach_tail=True)}
    result = triage.recheck_flag(store, flags, 'a')
    assert not result['isolated_anomaly']
    assert 'escalate' in result['recommendation']
    assert 'verify the anomalous observation' in result['recommendation']
