"""Cross-agent inventory, refusal and immutable source acceptance."""
import json
import shutil
import socket
import pytest

from test_native_reports import legacy,native,hashes,client
from scripts.prepare_native_report_acceptance import prepare
from scripts.prepare_monitoring_report_qa import prepare as monitoring_qa
from scripts.prepare_close_report_qa import prepare as close_qa


def test_combined_real_fixture_cases_preserve_sources_and_support_all_workflows(native,tmp_path,monkeypatch):
    left=tmp_path/'monitoring';right=tmp_path/'close';destination=tmp_path/'combined'
    monitoring_qa(native,left);close_qa(native,right)
    before={p:hashes(p) for p in [native,left,right]}
    def forbidden(*a,**k):raise AssertionError('Acceptance preparation attempted network access')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    receipt=prepare([native,left,right],destination)
    assert receipt['runs']==22 and receipt['production_release_approved'] is False
    api=client(destination);runs=api.get('/api/runs').json()['runs']
    assert {r['workflow'] for r in runs}=={'research','monitoring','events','news','close'}
    for run in runs:assert api.get('/api/runs/'+run['id']+'/report-view').status_code==200
    assert {p:hashes(p) for p in before}==before
    with pytest.raises(FileExistsError):prepare([left,right],destination)


def test_conflicting_run_identity_is_refused_before_destination_publication(native,tmp_path):
    altered=tmp_path/'distinct';shutil.copytree(native,altered)
    path=altered/'catalog.json';raw=json.loads(path.read_text())
    # Overview metadata is a distinct legitimate saved record, not a native amount edit.
    raw['runs'][0]['summary']='Distinct synthetic overview metadata for collision acceptance.'
    path.write_text(json.dumps(raw))
    destination=tmp_path/'refused'
    with pytest.raises(ValueError,match='Conflicting registered run identity'):prepare([native,altered],destination)
    assert not destination.exists()


def test_acceptance_helper_refuses_unsafe_destinations_and_preserves_existing_data(native,tmp_path):
    with pytest.raises(ValueError):prepare([],tmp_path/'empty')
    with pytest.raises(ValueError):prepare([native],native/'inside')
    target=tmp_path/'already';target.mkdir();marker=target/'keep.txt';marker.write_text('preserve')
    with pytest.raises(FileExistsError):prepare([native],target)
    assert marker.read_text()=='preserve'
    link=tmp_path/'alias';link.symlink_to(native,target_is_directory=True)
    with pytest.raises(ValueError):prepare([native],link/'new')
    assert not (native/'new').exists()
