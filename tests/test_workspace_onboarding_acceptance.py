"""3D private-boundary faults, bounded concurrency and larger saved histories."""
from concurrent.futures import ThreadPoolExecutor
import asyncio
import errno
from pathlib import Path
import sqlite3
import threading

import pytest
import httpx
from keystone.workspace.api import create_app
from keystone.workspace.catalog import Catalog
from keystone.workspace.onboarding import contracts as c
from test_native_reports import legacy,native,hashes
from test_workspace_onboarding import session,prepare,ingest,client,headers,submit


@pytest.mark.parametrize('fault',['write','fsync','rename','commit'])
def test_disk_failures_keep_prior_evidence_and_never_expose_partial_version(session,native,monkeypatch,fault):
    old,*_=ingest(session,native,'close')
    old_files=hashes(session.inputs.root/'inputs'/old['id'])
    _,data,descriptor,_=prepare(session,native,'close')
    api=client(session);key='storage-fault-'+fault
    response=api.post('/api/imports',json=descriptor,headers=headers(session,key))
    attempt=response.json()['import_attempt']['id']
    import keystone.workspace.onboarding.service as service
    import keystone.workspace.onboarding.store as inputs
    original_write=service.write_new
    original_connect=sqlite3.connect
    original_sync=inputs.sync_directory
    triggered=[]
    class FailCommit(sqlite3.Connection):
        def commit(self):
            if not triggered and self.execute("SELECT count(*) FROM objects WHERE kind='version'").fetchone()[0]>1:
                triggered.append(True);raise OSError(errno.ENOSPC,'private commit failure')
            return super().commit()
    def connect(*a,**kw):
        if str(a[0]).endswith('inputs.sqlite3?mode=rw'):kw['factory']=FailCommit
        return original_connect(*a,**kw)
    def write(path,data):
        if Path(path).name=='package.json':triggered.append(True);raise OSError(errno.ENOSPC,'private write failure')
        return original_write(path,data)
    def sync(path):
        if Path(path)==session.inputs.root/'inputs':triggered.append(True);raise OSError(errno.EIO,'private fsync failure')
        return original_sync(path)
    with monkeypatch.context() as patch:
        if fault=='write':patch.setattr(service,'write_new',write)
        if fault=='fsync':patch.setattr(inputs,'sync_directory',sync)
        if fault=='rename':patch.setattr(session.inputs,'_promote',lambda *_: (triggered.append(True),(_ for _ in ()).throw(OSError(errno.ENOSPC,'private rename failure')))[1])
        if fault=='commit':patch.setattr(inputs.sqlite3,'connect',connect)
        result=api.put('/api/imports/'+attempt+'/package',content=data,headers=headers(session,key))
    assert triggered and result.status_code in {409,503}
    assert 'private ' not in result.text
    assert hashes(session.inputs.root/'inputs'/old['id'])==old_files
    assert session.inputs.version(old['id'])==old
    assert session.inputs.versions(descriptor['dataset_id'])['items']==[]
    assert Catalog(session.catalog.root).load().runs==[]
    if fault!='write':
        recovered=session.inputs.recover(attempt)
        assert recovered['state']=='accepted'
        assert session.inputs.recover(attempt)==recovered
    api.close()


def test_private_reads_and_job_admission_remain_consistent_during_an_import(session,native,monkeypatch):
    version,*_=ingest(session,native,'close')
    transfers=[]
    api=client(session)
    for i in range(2):
        _,data,descriptor,_=prepare(session,native,'close')
        key='concurrent-transfer-'+str(i)
        r=api.post('/api/imports',json=descriptor,headers=headers(session,key))
        transfers.append((r.json()['import_attempt']['id'],data,key))
    entered=threading.Event();release=threading.Event();original=session.validate_and_accept
    def pause(*a):
        entered.set()
        if not release.wait(10):raise RuntimeError('Test pause deadline exceeded')
        return original(*a)
    monkeypatch.setattr(session,'validate_and_accept',pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        ident,data,key=transfers[0]
        first=pool.submit(lambda:api.put('/api/imports/'+ident+'/package',content=data,headers=headers(session,key)))
        try:
            assert entered.wait(5)
            before=hashes(session.inputs.root)
            read=api.get('/api/imports',headers=headers(session))
            assert read.status_code==200
            assert next(x for x in read.json()['items'] if x['id']==ident)['state']=='validating'
            assert api.get('/api/datasets',headers=headers(session)).status_code==200
            assert hashes(session.inputs.root)==before
            job=submit(session,version)
            assert job['status']=='queued' and job['execution']['attempt']==0
            second_id,second_data,second_key=transfers[1]
            second=api.put('/api/imports/'+second_id+'/package',content=second_data,headers=headers(session,second_key))
            assert second.status_code==409 and second.json()['error']['code']=='input_busy'
            assert session.inputs.attempt(second_id)[1]['state']=='reserved'
        finally:release.set()
        assert first.result(timeout=20).status_code==200
    api.close()


def test_private_identity_and_dataset_limits_preserve_existing_records(session):
    entities=[];datasets=[]
    for index in range(100):
        entity=session.inputs.create_entity({'name':f'Fictional entity {index:03d}'})
        dataset=session.inputs.create_dataset(dict(entity_id=entity['id'],title=f'Dataset {index:03d}',
            workflow='monitoring',payload_format=c.FORMATS['monitoring']))
        entities.append(entity);datasets.append(dataset)
    before=hashes(session.inputs.root)
    with pytest.raises(c.InputError,match='input_capacity'):session.inputs.create_entity({'name':'Over the limit'})
    with pytest.raises(c.InputError,match='input_capacity'):
        session.inputs.create_dataset(dict(entity_id=entities[0]['id'],title='Over the limit',workflow='monitoring',payload_format=c.FORMATS['monitoring']))
    assert hashes(session.inputs.root)==before
    for kind,expected in [('entity',entities),('dataset',datasets)]:
        cursor=None;found=[]
        while True:
            page=session.inputs.list(kind,25,cursor);found+=page['items'];cursor=page['next_cursor']
            if cursor is None:break
        assert found==list(reversed(expected))


def test_larger_import_history_paginates_without_loss_and_attempt_cap_keeps_replay(session,native,monkeypatch):
    _,_,descriptor,_=prepare(session,native,'close');ids=[]
    for index in range(60):
        receipt,_=session.inputs.reserve(descriptor,'history-import-'+str(index));ids.append(receipt['id'])
        session.inputs.transition(receipt['id'],'receiving',transfer_id='transfer-fictional')
        session.inputs.transition(receipt['id'],'rejected',reason='input_invalid')
    cursor=None;found=[]
    while True:
        page=session.inputs.attempts(25,cursor);found.extend(v['id'] for v in page['items']);cursor=page['next_cursor']
        if cursor is None:break
    assert found==list(reversed(ids))
    monkeypatch.setattr(c,'MAX_ATTEMPTS',60)
    before=hashes(session.inputs.root)
    with pytest.raises(c.InputError,match='input_capacity'):session.inputs.reserve(descriptor,'over-attempt-cap')
    receipt,replayed=session.inputs.reserve(descriptor,'history-import-0')
    assert replayed and receipt['id']==ids[0]
    assert hashes(session.inputs.root)==before


@pytest.mark.parametrize('field,value',[('exchange','UNVERIFIED'),('share_class','Different class')])
def test_unsupported_listing_substitution_is_refused_before_payload_retention(session,native,field,value):
    _,_,descriptor,_=prepare(session,native,'research')
    descriptor['metadata']['dataset']['listing'][field]=value
    before=hashes(session.inputs.root)
    with pytest.raises(c.InputError):session.inputs.reserve(descriptor,'unsupported-listing-'+field)
    assert hashes(session.inputs.root)==before


@pytest.mark.parametrize('raw',[
    c.canonical({'long':'x'*100001}),
    c.canonical(['x'*100000]*21),
    c.canonical([{}]*50001),
])
def test_structural_resource_limits_refuse_oversized_content(raw):
    with pytest.raises(c.InputError,match='input_too_large'):c.bounded_json(raw)


@pytest.mark.parametrize('fault',['false_length','slow_stream','compression'])
def test_stream_limits_do_not_trust_headers_or_retain_uninspected_bytes(session,native,monkeypatch,fault):
    _,_,descriptor,_=prepare(session,native,'close')
    dataset=descriptor['dataset_id'];before=hashes(session.inputs.root)
    monkeypatch.setattr(c,'MAX_PACKAGE',128)
    monkeypatch.setattr(c,'TRANSFER_SECONDS',.02)
    async def stream():
        yield b'{'
        if fault=='slow_stream':await asyncio.sleep(.1)
        yield b'x'*256
    async def check():
        app=create_app(session.catalog.root,admission=session,private=session)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=session.origin) as api:
            h=headers(session);h['Content-Length']='1'
            if fault=='compression':h['Content-Encoding']='gzip'
            return await api.post('/api/datasets/'+dataset+'/inspect',content=stream(),headers=h)
    response=asyncio.run(check())
    assert response.status_code=={'false_length':413,'slow_stream':408,'compression':415}[fault]
    assert hashes(session.inputs.root)==before


def test_identical_company_names_never_merge_independent_local_identities(session):
    first=session.inputs.create_entity({'name':'Fictional shared name'})
    second=session.inputs.create_entity({'name':'Fictional shared name'})
    assert first['id']!=second['id']
    assert len(session.inputs.list('entity')['items'])==2
