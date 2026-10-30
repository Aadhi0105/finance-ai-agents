"""Output regression coverage outside the frozen financial acceptance sources."""

def test_held_distribution_output_is_distinct_from_numeric_run_id(monkeypatch,capsys,tmp_path):
    from uuid import UUID
    from agent3.orchestrator import analyze_event_type,render_brief,render_scan
    from agent3 import run_live
    result=analyze_event_type('semicap_earnings')
    # Simulate an older saved shape with a CALIBRATED scenario under a held gate.
    result['scenario'].update(verdict='CALIBRATED',publication_state='HELD_FOR_REVIEW',
                              distribution={'p25':999,'median_car':1000,'p75':1001})
    from agent3 import execution
    # A legitimate artifact path may contain the numeric distribution sentinel.
    run_id='e16bb9992d6041548f32d8a64f63b4fd'
    monkeypatch.setattr(execution,'uuid4',lambda:UUID(run_id))
    monkeypatch.setattr(execution,'analyze_event_type',lambda *a,**k:result)
    monkeypatch.setattr(run_live,'run_bounded',lambda attempt, timeout:execution.execute(attempt))
    assert run_live.main(['ASML.AS','earnings','--peers','ASM.AS','--db',str(tmp_path/'db.duckdb'),'--output-dir',str(tmp_path/'runs')])==3
    cli_output=capsys.readouterr().out
    assert run_id in cli_output
    output=cli_output+render_brief(result)+render_scan([result])
    assert 'CALIBRATED' not in output
    assert 'Historical quantiles:' not in output and 'p25' not in output
    assert 'HELD_FOR_REVIEW' in output
