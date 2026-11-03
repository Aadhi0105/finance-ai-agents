"""A real uncommitted SQLite journal is recovered only at explicit startup."""
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from keystone.workspace.api import create_app
from keystone.workspace.onboarding.contracts import InputError
from keystone.workspace.onboarding.service import PrivateAdmission
from keystone.workspace.onboarding.store import create_workspace,InputStore


def files(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_explicit_restart_rolls_back_a_spilled_transaction_without_mutating_http_reads(tmp_path):
    root=create_workspace(tmp_path/'workspace','Fictional crash-recovery case')
    service=PrivateAdmission(root,'http://127.0.0.1:8765',enable_imports=True)
    entity=service.inputs.create_entity({'name':'Committed company'})
    dataset=service.inputs.create_dataset(dict(entity_id=entity['id'],title='Committed dataset',
        workflow='monitoring',payload_format='agent2.snapshot/legacy-1'))
    service.close()
    # Force dirty pages to disk, then lose the owning process without COMMIT.
    script='''import sqlite3,sys,os
con=sqlite3.connect(sys.argv[1],isolation_level=None)
con.execute('PRAGMA cache_size=1')
con.execute('BEGIN IMMEDIATE')
con.execute("UPDATE objects SET value='uncommitted',sha256='wrong' WHERE kind='dataset'")
con.execute('CREATE TABLE uncommitted_spill(value TEXT)')
con.executemany('INSERT INTO uncommitted_spill VALUES (?)',[('x'*4096,)]*40)
os._exit(23)
'''
    process=subprocess.run([sys.executable,'-c',script,str(root/'inputs.sqlite3')])
    assert process.returncode==23 and (root/'inputs.sqlite3-journal').is_file()
    before=files(root)
    with pytest.raises(InputError):InputStore(root)
    assert files(root)==before  # Inspection is not an implicit writable recovery.
    restarted=PrivateAdmission(root,'http://127.0.0.1:8765')
    try:
        assert restarted.inputs.object('dataset',dataset['id'])==dataset
        assert restarted.inputs.object('entity',entity['id'])==entity
        assert restarted.inputs.attempts()['items']==[]
        assert not (root/'inputs.sqlite3-journal').exists()
        stable=files(root)
        api=TestClient(create_app(restarted.catalog.root,admission=restarted,private=restarted),base_url=restarted.origin)
        try:
            response=api.get('/api/entities',headers={'Authorization':'Bearer '+restarted.token})
            assert response.status_code==200 and response.json()['items']==[entity]
        finally:api.close()
        assert files(root)==stable
    finally:restarted.close()
