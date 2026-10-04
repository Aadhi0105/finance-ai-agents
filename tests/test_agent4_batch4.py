"""Independent waterfall geometry, report grounding and atomic publication checks."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest
from agent4.close import execute_close
from agent4.hierarchy import rollup, ReconciliationError
from agent4.output import variance_waterfall_svg, waterfall_rows
from agent4.report import export_reports, render_report, render_status, validate_bundle
from agent4.state import VarianceStore, digest


def leaf(b,a,kind='revenue'):
    return rollup({'name':'R&D <Revenue>', 'leaf':{'name':'R&D <Revenue>','type':kind,'budget':{'amount':str(b)},'actual':{'amount':str(a)}}})


@pytest.mark.parametrize('b,a', [(-1,-2),(-2,-1),(-1,2),(2,-1),(0,0),(1,1),(0,1),(1,0),(10000000000000,10000000000000.01)])
def test_bridge_geometry_and_independent_tie(b,a):
    tree=leaf(b,a)
    rows=waterfall_rows(tree)
    assert sum(r['value_cents'] for r in rows[1:-1])+tree['budget_cents']==tree['actual_cents']
    assert rows[1]['value_cents']==tree['actual_cents']-tree['budget_cents']
    svg=ET.fromstring(variance_waterfall_svg(tree))
    assert svg.attrib['role']=='img'
    assert svg.find('{*}title') is not None and svg.find('{*}desc') is not None
    _,_,width,height=map(float,svg.attrib['viewBox'].split())
    for r in svg.findall('{*}rect'):
        x,y,w,h=[float(r.attrib[k]) for k in ('x','y','width','height')]
        assert 0<=x<=x+w<=width and 0<=y<=y+h<=height
    for line in svg.findall('{*}line'):
        assert 0<=float(line.attrib['y1'])<=height
        assert 0<=float(line.attrib['y2'])<=height


def test_cost_root_steps_use_account_units_and_adverse_colour():
    tree=rollup({'name':'Costs','root_measure':'cost','children':[
        {'name':'Payroll','sign':'add','leaf':{'name':'Payroll','type':'fixed_cost','budget':{'amount':10},'actual':{'amount':15}}}]})
    rows=waterfall_rows(tree)
    assert rows[1]['value_cents']==500 and not rows[1]['favourable']
    assert rows[-1]['end_cents']==1500


def test_leaf_residual_owned_once():
    tree=leaf(1,2)
    tree['drivers'][0]['cents']-=1;tree['residual_cents']=1;tree['rounding_tolerance_cents']=1
    rows=waterfall_rows(tree)
    assert [r['value_cents'] for r in rows]==[100,99,1,200]
    assert rows[-2]['label']=='Rounding residual'


@pytest.mark.parametrize('width,height',[(True,360),(0,360),(720,200),(721.1,360),(720,5000)])
def test_bad_dimensions(width,height):
    with pytest.raises(ValueError):variance_waterfall_svg(leaf(1,2),width,height)


def test_changed_tree_refused():
    tree=leaf(1,2);tree['actual_cents']=300
    with pytest.raises(ReconciliationError):variance_waterfall_svg(tree)


def req():
    return json.loads(Path('fixtures/agent4/close-june.json').read_text())


@pytest.fixture
def saved(tmp_path):
    with VarianceStore(tmp_path/'state.db') as store:
        run=execute_close(store,req())
        yield store,run,tmp_path


def test_report_disclosures_and_saved_headline(saved):
    store,run,path=saved
    html=render_report(run,[run])
    for text in ['Synthetic demonstration','€60.00','€65.00','€5.00','Original submitted actuals delta','Effective actuals used','Prior observations','Forecast assumptions','close-june.json','Accounting and claim checks passed']:
        assert text in html
    assert '<script' not in html
    assert 'default-src' in html
    assert 'role="region"' in html
    assert 'scope="col"' in html


@pytest.mark.parametrize('field',['digest','claim','tree','forecast','sources','context'])
def test_contradictory_saved_evidence_refused(saved,field):
    _,run,_=saved;run=deepcopy(run);b=run['bundle'];r=b['report']
    if field=='digest':run['bundle_digest']='bad'
    if field=='claim':r['commentary'][0]['text']='Profit was 99% higher'
    if field=='tree':r['full_hierarchy']['actual_cents']+=1
    if field=='forecast':r['reforecasts']={}
    if field=='sources':b['sources']['effective_actuals'][0]['amount_cents']+=1
    if field=='context':b['request']['entity']='Other';b['request_digest']=digest(b['request'])
    if field!='digest':run['bundle_digest']=digest(b)
    with pytest.raises((ValueError,ReconciliationError)):validate_bundle(run)


def test_escape_names_and_status_pages(tmp_path):
    r=req();r['entity']='<script>alert(1)</script>';r['tree']['name']='Profit <img src=x onerror=alert(1)>'
    with VarianceStore(tmp_path/'state.db') as store:
        run=execute_close(store,r);html=render_report(run,[run])
    assert '<script>' not in html and '<img src=x' not in html
    assert '&lt;script&gt;' in html
    for status in ('empty','held','error'):
        html=render_status(status,'<img onerror=bad>')
        assert 'No financial conclusions' in html and '<img' not in html


def test_linked_original_and_corrected_versions(saved):
    store,run,tmp=saved
    r=req();r.update(run_id='corrected',supersedes='close-june');r['actuals']={'version':'restated','source':'correction.csv','rows':[{'line':'sales','period':'2026-01-31','amount_cents':12000}]}
    execute_close(store,r)
    result=export_reports(store,'corrected',tmp/'reports');folder=Path(result['html_path']).parent
    assert (folder/'close-june.html').exists()
    assert json.loads((folder/'close-june.json').read_text())==run['bundle']
    html=(folder/'corrected.html').read_text()
    assert 'href="close-june.html"' in html and 'restated' in html and 'actual-june' in html
    before={p.name:p.read_bytes() for p in folder.iterdir()}
    assert export_reports(store,'corrected',tmp/'reports')['html_path']==result['html_path']
    assert before=={p.name:p.read_bytes() for p in folder.iterdir()}


def test_failed_html_publish_recovers_without_recompute(saved,monkeypatch):
    import agent4.report as report
    store,run,tmp=saved;original=report.os.replace
    def fail(*args):raise OSError('disk full')
    monkeypatch.setattr(report.os,'replace',fail)
    with pytest.raises(OSError):export_reports(store,'close-june',tmp/'reports')
    assert not list((tmp/'reports').glob('reports-*'))
    assert store.get_run('close-june')['bundle_digest']==run['bundle_digest']
    monkeypatch.setattr(report.os,'replace',original)
    output=export_reports(store,'close-june',tmp/'reports')
    assert Path(output['html_path']).is_file()
    assert store.delivery_history('close-june')[-1]['status']=='delivered'


def test_export_conflict_never_overwrites(saved):
    store,_,tmp=saved;result=export_reports(store,'close-june',tmp)
    target=Path(result['html_path']);target.write_text('changed')
    with pytest.raises(ValueError,match='conflicts'):export_reports(store,'close-june',tmp)
    assert target.read_text()=='changed'


def test_missing_run_and_database_cli(tmp_path):
    cmd=[sys.executable,'-m','agent4.report','--db',str(tmp_path/'missing.db'),'--run-id','missing','--output-dir',str(tmp_path)]
    result=subprocess.run(cmd,capture_output=True,text=True)
    assert result.returncode==2 and 'does not exist' in result.stderr
    assert not (tmp_path/'missing.db').exists()


def test_close_cli_html_and_report_cli_recovery(tmp_path):
    db=tmp_path/'db';out=tmp_path/'out'
    result=subprocess.run([sys.executable,'-m','agent4.close','--input','fixtures/agent4/close-june.json','--db',str(db),'--output-dir',str(out),'--html'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    first=json.loads(result.stdout)
    assert Path(first['html_path']).exists()
    result=subprocess.run([sys.executable,'-m','agent4.report','--db',str(db),'--output-dir',str(out),'--run-id','close-june'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['html_path']==first['html_path']
