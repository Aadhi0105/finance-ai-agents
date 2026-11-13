"""Complete physical accounting, preserved history, and stopped reference audits."""
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest

from keystone.workspace.api import create_app
from keystone.workspace import lifecycle as life
from keystone.workspace.job_store import JobStore
from keystone.workspace.onboarding import contracts as c
from keystone.workspace.onboarding.store import InputStore
from keystone.workspace.worker import run_one
from test_workspace_onboarding import session,headers,ORIGIN,ingest as saved_ingest,submit
from test_workspace_local_research import ingest,request
from test_workspace_fresh_close import worker,ingest as close_ingest
from test_workspace_private_recovery import capture
from test_native_reports import hashes,native,legacy
from test_workspace_review_decisions import scope,ready,body as decision_body,post as post_decision,corrections_ready
from test_workspace_review_notes import post as post_note
from test_workspace_review_corrections import post as post_correction


def area(value,key):return next(a for a in value['areas'] if a['key']==key)
def audit(session):
    session.close()
    return life.audit_private(session.inputs.root)


def test_full_root_accounting_is_readonly_and_exposes_no_contents(session):
    before=hashes(session.inputs.root);value=life.observe_storage(session.inputs)
    assert value['state']=='observed'
    assert value['total_bytes']==sum(p.stat().st_size for p in session.inputs.root.rglob('*') if p.is_file())
    assert value['total_files']==len(before)
    assert area(value,'runtime')['files']>=2 and area(value,'runtime')['bytes']>0
    assert hashes(session.inputs.root)==before
    assert session.token not in json.dumps(value) and str(session.inputs.root) not in json.dumps(value)
    assert not value['deletion_supported'] and not value['automatic_deletion'] and not value['document_intake_supported']


def test_storage_contract_matches_checked_in_schema(session):
    schema=json.loads((Path(__file__).parents[1]/'keystone/workspace/storage.schema.json').read_text())
    assert schema==life.Inventory.model_json_schema()
    Draft202012Validator(schema).validate(life.observe_storage(session.inputs))


def test_replaced_root_or_descriptor_cannot_be_presented_as_the_connected_workspace(session,monkeypatch):
    monkeypatch.setattr(session.inputs,'_root_identity',(-1,-1))
    value=life.observe_storage(session.inputs)
    assert value['state']=='unavailable' and value['total_files'] is None


def test_unreadable_input_ledger_does_not_hide_independent_filesystem_observation(session):
    session.inputs.path.write_bytes(b'fictional broken database')
    value=life.observe_storage(session.inputs)
    assert value['state']=='observed' and area(value,'input_ledger')['bytes']==len(b'fictional broken database')
    # Counting the damaged file does not claim its contents or links validated.
    assert value['reference_check']=='requires_stopped_audit'


def test_protected_api_read_head_query_and_all_mutations(session):
    with TestClient(create_app(session.catalog.root,admission=session,private=session),base_url=ORIGIN) as api:
        assert api.get('/api/storage').status_code==403
        assert api.get('/api/storage',headers={**headers(session),'Origin':'https://untrusted.example'}).status_code==403
        good=api.get('/api/storage',headers=headers(session));assert good.status_code==200
        assert 'no-store' in good.headers['cache-control']
        assert api.head('/api/storage',headers=headers(session)).status_code==200
        assert api.get('/api/storage?path=/private',headers=headers(session)).status_code==422
        for method in ('POST','PUT','PATCH','DELETE'):
            assert api.request(method,'/api/storage',headers=headers(session),json={}).status_code==405


@pytest.mark.parametrize('kind',['symlink','hardlink','public_file','special','missing_required','wrong_type','unreadable'])
def test_unsafe_or_missing_members_are_unknown_not_zero(session,tmp_path,kind,monkeypatch):
    root=session.inputs.root;path=root/'inputs'/'evidence'
    if kind=='symlink':path.symlink_to(tmp_path)
    elif kind=='hardlink':
        original=tmp_path/'outside';original.write_bytes(b'outside');path.hardlink_to(original)
    elif kind=='public_file':path.write_bytes(b'private');path.chmod(0o644)
    elif kind=='special':
        import os
        os.mkfifo(path,0o600)
    elif kind=='missing_required':(root/'reports/catalog.json').unlink()
    elif kind=='wrong_type':(root/'reports/catalog.json').unlink();(root/'reports/catalog.json').mkdir(mode=0o700)
    else:
        original=life.os.scandir
        def denied(p):
            if p==root/'inputs':raise OSError('secret-path-and-message')
            return original(p)
        monkeypatch.setattr(life.os,'scandir',denied)
    value=life.observe_storage(session.inputs)
    assert value['state']=='unavailable' and value['total_bytes'] is value['total_files'] is None
    assert area(value,'inputs' if kind not in {'missing_required','wrong_type'} else 'reports')['bytes'] is None
    assert 'secret-path' not in json.dumps(value)


@pytest.mark.parametrize('empty',[True,False])
def test_unrecognised_entries_are_preserved_and_require_inspection(session,empty):
    root=session.inputs.root;folder=root/'unexpected';folder.mkdir(mode=0o700)
    if not empty:(folder/'secret-label').write_bytes(b'not classified');(folder/'secret-label').chmod(0o600)
    before=hashes(root);value=life.observe_storage(session.inputs)
    assert value['state']=='attention' and area(value,'unrecognised')['state']=='attention'
    result=audit(session);assert result['state']=='unavailable'
    assert hashes(root)==before and 'secret-label' not in json.dumps(result)


def test_scan_and_hash_bounds_fail_closed(session,monkeypatch):
    monkeypatch.setattr(life,'MAX_MEMBERS',1)
    value=life.observe_storage(session.inputs)
    assert value['state']=='unavailable' and value['total_files'] is None
    monkeypatch.setattr(life,'MAX_MEMBERS',60000);monkeypatch.setattr(life,'MAX_HASH_BYTES',1)
    with pytest.raises(OverflowError):audit(session)


def test_low_disk_does_not_delete_or_claim_total_quota(session,monkeypatch):
    before=hashes(session.inputs.root)
    monkeypatch.setattr(life.shutil,'disk_usage',lambda _:SimpleNamespace(free=99,total=1_000_000_000))
    value=life.observe_storage(session.inputs)
    assert value['state']=='attention' and value['total_bytes']>0
    assert hashes(session.inputs.root)==before


def test_unavailable_disk_does_not_erase_independent_file_counts(session,monkeypatch):
    monkeypatch.setattr(life.shutil,'disk_usage',lambda _:(_ for _ in ()).throw(OSError('private')))
    value=life.observe_storage(session.inputs)
    assert value['state']=='unavailable' and value['disk_free_bytes'] is None and value['total_files']>0


def test_live_server_refuses_stopped_audit_without_changes(session):
    before=hashes(session.inputs.root)
    with pytest.raises(BlockingIOError):life.audit_private(session.inputs.root)
    assert hashes(session.inputs.root)==before


def test_empty_stopped_audit_does_not_create_or_upgrade_any_files(session):
    before=hashes(session.inputs.root);value=audit(session)
    assert value['state']=='verified' and all(c['state']=='verified' for c in value['checks'])
    assert hashes(session.inputs.root)==before
    assert value['evidence_files']<len(before) and len(value['evidence_sha256'])==64
    assert not value['consistent_backup'] and not value['financial_approval']


def test_readonly_job_reader_cannot_migrate_write_or_create(session):
    before=hashes(session.inputs.root);reader=JobStore.reader(session.store.root,session.catalog.root)
    try:
        with pytest.raises(Exception):
            with reader._connect(write=True):pass
        with pytest.raises(Exception):
            with reader._connect(write=False,initial=True):pass
    finally:reader.close()
    assert hashes(session.inputs.root)==before


def test_fresh_research_checks_originals_delivery_and_registered_artifacts(session):
    *_,version=ingest(session);job,_=session.submit(request(version),'lifecycle-research')
    with worker(session) as store:assert run_one(store)==(True,False)
    before=hashes(session.inputs.root);value=audit(session)
    assert value['state']=='verified',value
    assert hashes(session.inputs.root)==before
    assert job['job_id'] not in json.dumps(value)  # Diagnostics omit raw references and labels.


@pytest.mark.parametrize('workflow',['research','monitoring','events','news','close'])
def test_all_saved_report_families_retain_reference_integrity(session,native,workflow):
    version,*_=saved_ingest(session,native,workflow);submit(session,version)
    with worker(session) as store:assert run_one(store)==(True,False)
    assert audit(session)['state']=='verified'


def test_fresh_close_checks_canonical_accounting_without_recalculation(session):
    *_,version=close_ingest(session);submit(session,version,'lifecycle-close')
    with worker(session) as store:assert run_one(store)==(True,False)
    before=hashes(session.inputs.root);value=audit(session)
    assert value['state']=='verified',value
    assert area(life.observe_storage(session.inputs),'accounting')['bytes']>0
    assert hashes(session.inputs.root)==before


@pytest.mark.parametrize('damage',['input','registered_report','job_record','working_input','operation_receipt','missing_report','orphan_job'])
def test_missing_changed_or_orphaned_evidence_cannot_pass(session,damage):
    *_,version=ingest(session);job,_=session.submit(request(version),'lifecycle-damage')
    with worker(session) as store:assert run_one(store)==(True,False)
    if damage=='input':path=session.inputs.root/'inputs'/version['id']/'payload.json'
    elif damage=='registered_report':path=next((session.catalog.root/'runs').rglob('payload.json'))
    elif damage=='working_input':path=session.store.root/'jobs'/job['job_id']/'inputs/payload.json'
    elif damage=='operation_receipt':path=session.store.root/'operations'/job['operation_id']/'operation.json'
    elif damage=='missing_report':
        raw=json.loads((session.catalog.root/'catalog.json').read_text());raw['runs']=[]
        (session.catalog.root/'catalog.json').write_bytes(c.canonical(raw));path=None
    elif damage=='orphan_job':(session.store.root/'jobs'/'job-orphan').mkdir(mode=0o700);path=None
    else:
        with session.store._write() as con:con.execute("UPDATE jobs SET record_sha256=?",('0'*64,))
        path=None
    if path:path.write_bytes(b'changed saved evidence')
    before=hashes(session.inputs.root);value=audit(session)
    assert value['state']=='unavailable',value
    assert hashes(session.inputs.root)==before


def test_permission_withdrawal_is_held_and_preserves_all_evidence(session):
    _,_,permission,version=ingest(session)
    session.inputs.revoke_permission(permission['id'],'Fictional withdrawal')
    before=hashes(session.inputs.root);value=audit(session)
    assert value['state']=='held',value
    assert hashes(session.inputs.root)==before


def test_input_capacity_refusal_preserves_previous_evidence(session,monkeypatch):
    *_,version=ingest(session);before=hashes(session.inputs.root)
    with session.inputs.connect() as con:ident=con.execute('SELECT id FROM imports').fetchone()[0]
    descriptor,_=session.inputs.attempt(ident)
    monkeypatch.setattr(c,'MAX_INPUT_BYTES',1)
    with pytest.raises(c.InputError) as refusal:session.inputs.reserve(descriptor,'lifecycle-capacity-new')
    assert refusal.value.code=='input_capacity'
    after=hashes(session.inputs.root)
    assert after==before
    assert session.inputs.version(version['id'])['id']==version['id']


def test_audit_after_local_restore_preserves_input_report_and_job_identity(session,tmp_path):
    from keystone.workspace.onboarding.recovery import restore_private
    *_,version=ingest(session);session.submit(request(version),'lifecycle-restored')
    with worker(session) as store:assert run_one(store)==(True,False)
    original=hashes(session.inputs.root/'inputs');reports=hashes(session.catalog.root)
    saved=capture(session,tmp_path);restored=restore_private(saved,tmp_path/'restored')
    # Restore deliberately excludes runtime locks; initialise the supported
    # server once, then stop it before the read-only audit.
    from keystone.workspace.onboarding.service import PrivateAdmission
    replacement=PrivateAdmission(restored,ORIGIN);replacement.close()
    before=hashes(restored);value=life.audit_private(restored)
    assert value['state']=='verified',value
    assert hashes(restored)==before and hashes(restored/'inputs')==original and hashes(restored/'reports')==reports


def test_review_notes_and_decisions_are_retained_and_validated(scope):
    session,api,snapshot,permission=scope
    assert post_note((session,api,snapshot,permission)).status_code==201
    assert post_decision(scope).status_code==201
    before=hashes(session.inputs.root);assert audit(session)['state']=='verified'
    assert hashes(session.inputs.root)==before


def test_replacement_versions_and_correction_links_are_retained(corrections_ready):
    assert post_correction(corrections_ready).status_code==201
    session=corrections_ready[0];before=hashes(session.inputs.root)
    assert audit(session)['state']=='verified'
    assert hashes(session.inputs.root)==before


def test_repeated_snapshot_restore_retains_both_recovery_receipts(session,tmp_path):
    from keystone.workspace.onboarding.recovery import restore_private
    from keystone.workspace.onboarding.service import PrivateAdmission
    from keystone import storage
    first=capture(session,tmp_path/'first')
    restored=restore_private(first,tmp_path/'restored-one')
    prior=(restored/'restore-receipt.json').read_bytes();prior_sha=c.sha(prior)
    replacement=PrivateAdmission(restored,ORIGIN);replacement.close()
    inputs=InputStore(restored)
    second=storage.snapshot(inputs.backup_plan(),tmp_path/'second',quiescent=True)
    assert 'restore-receipt.json' in storage.verify(second)['files']
    again=restore_private(second,tmp_path/'restored-two')
    assert (again/'recovery/restore-receipts'/f'{prior_sha}.json').read_bytes()==prior
    current=json.loads((again/'restore-receipt.json').read_text())
    assert current['snapshot_id']!=json.loads(prior)['snapshot_id']
    assert current['changes'][-1]['kind']=='prior_restore_receipt_retained'
    final=PrivateAdmission(again,ORIGIN);final.close()
    assert life.audit_private(again)['state']=='verified'
    # The next plan covers the earlier archive as well as the current receipt.
    assert {'recovery','restore-receipt.json'}<={s['name'] for s in InputStore(again).backup_plan()['sources']}
    assert (restored/'restore-receipt.json').read_bytes()==prior


def test_cli_audit_refuses_live_and_succeeds_stopped_without_private_paths(session,capsys):
    from keystone.workspace.__main__ import main
    command=['audit-private','--workspace',str(session.inputs.root)]
    assert main(command)==2
    captured=capsys.readouterr();assert 'evidence_audit_unavailable' in captured.err
    assert str(session.inputs.root) not in captured.err
    session.close();before=hashes(session.inputs.root)
    assert main(command)==0
    assert json.loads(capsys.readouterr().out)['state']=='verified'
    assert hashes(session.inputs.root)==before


def test_snapshot_cli_refuses_unmapped_evidence_without_losing_existing_snapshot(session,tmp_path,capsys):
    from keystone.workspace.__main__ import main
    from keystone import storage
    session.close();destination=tmp_path/'snapshots'
    command=['snapshot-private','--workspace',str(session.inputs.root),'--destination',str(destination)]
    assert main(command) is None
    first=Path(json.loads(capsys.readouterr().out)['snapshot']);before=storage.verify(first)
    unknown=session.inputs.root/'unmapped.txt';unknown.write_bytes(b'fictional');unknown.chmod(0o600)
    assert main(command)==2
    assert storage.verify(first)==before and unknown.read_bytes()==b'fictional'
    assert [p.name for p in destination.iterdir()]==[first.name]


def test_changed_source_during_stopped_observation_cannot_get_integrity_digest(session,monkeypatch):
    session.close();original=life.scan;calls=[]
    def changing(root,**kw):
        value=original(root,**kw);calls.append(True)
        if len(calls)==1:(root/'inputs.sqlite3').touch()
        else:
            key=next(iter(value[1]));value[1][key]['sha256']='0'*64
        return value
    monkeypatch.setattr(life,'scan',changing)
    value=life.audit_private(session.inputs.root)
    assert value['state']=='unavailable' and value['evidence_sha256'] is None


def test_rehashed_import_receipt_still_needs_its_exact_accepted_version(session):
    *_,version=ingest(session)
    with session.inputs.write() as con:
        _,receipt=session.inputs._attempt(con,version['import_id'])
        receipt['version_id']='version-'+'0'*32
        raw=c.canonical(receipt).decode();sha=c.sha(raw.encode())
        con.execute('UPDATE imports SET receipt=?,receipt_sha=? WHERE id=?',(raw,sha,version['import_id']))
        con.execute('UPDATE events SET receipt_sha=? WHERE import_id=? AND state=?',(sha,version['import_id'],'accepted'))
    value=audit(session)
    assert value['state']=='unavailable' and next(x for x in value['checks'] if x['key']=='inputs')['state']=='unavailable'


def test_permission_hold_cannot_hide_missing_permission_evidence(session):
    _,_,permission,_=ingest(session)
    session.inputs.revoke_permission(permission['id'],'Fictional withdrawal')
    (session.inputs.root/'permissions'/permission['id']/'evidence').unlink()
    value=audit(session)
    assert value['state']=='unavailable'
    assert next(x for x in value['checks'] if x['key']=='permission_evidence')['state']=='unavailable'


def test_inventory_and_stopped_audit_never_open_access_key_contents(session,monkeypatch):
    original=life.os.open
    def no_key(path,*args,**kwargs):
        if Path(path).name=='access-token.key':pytest.fail('Storage inspection opened the access key')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(life.os,'open',no_key)
    assert life.observe_storage(session.inputs)['state']=='observed'
    assert audit(session)['state']=='verified'
