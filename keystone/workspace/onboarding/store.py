"""Private immutable input objects with transactional import receipts.

The ledger controls visibility. Files promoted without a committed version remain
private orphans. No filesystem discovery, automatic deletion or financial writes.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sqlite3
import threading
import uuid

from keystone.maintenance import ROOT, control_write_gate, gate
from keystone.operation import sync_directory
from ..catalog import ID, read_confined, read_json
from ..job_contract import now
from ..job_files import write_new, flush_tree
from ..job_store import private_member
from . import contracts as c

APPLICATION_ID = 0x4B534931


def ident(value):
    if not isinstance(value, str) or re.fullmatch(ID, value) is None: raise c.InputError()
    return value


def create_workspace(destination, name):
    root = Path(destination).absolute()
    if (root.exists() or root.is_symlink() or not isinstance(name, str) or not 0<len(name.strip())<=160
            or any(p.is_symlink() for p in root.parents)):
        raise c.InputError('input_unavailable', 409)
    if ROOT in root.parents and not any(p in root.parents for p in (ROOT/'state/workspaces', ROOT/'output')):
        raise c.InputError('input_unavailable', 409)
    from ..catalog import ManifestV3
    with gate(exclusive=True):
        root.mkdir(parents=True, mode=0o700, exist_ok=False)
        for name_ in ('inputs', 'staging', 'permissions', 'reports', 'reports/runs'):
            (root/name_).mkdir(mode=0o700)
        descriptor = dict(schema_version=1, kind='keystone.private-workspace', id='workspace-'+uuid.uuid4().hex,
                          name=name, created_at=now(), production_release_approved=False)
        write_new(root/'workspace.json', c.canonical(descriptor))
        manifest=ManifestV3(schema_version=3, kind='keystone.private-workspace-reports', classification='private',
            workspace_id=descriptor['id'], prepared_at=now(), code_commit=None, code_worktree_dirty=True,
            preparer_sha256=c.sha(Path(__file__).read_bytes()), production_release_approved=False, runs=[])
        write_new(root/'reports/catalog.json', c.canonical(manifest.model_dump()))
        path=root/'inputs.sqlite3'
        write_new(path,b'')
        with sqlite3.connect(path) as con:
            con.executescript('''
                PRAGMA journal_mode=DELETE;
                PRAGMA synchronous=EXTRA;
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE objects(sequence INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
                    id TEXT NOT NULL UNIQUE, value TEXT NOT NULL, sha256 TEXT NOT NULL);
                CREATE TABLE imports(sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
                    key_hash TEXT NOT NULL UNIQUE, descriptor TEXT NOT NULL, descriptor_sha TEXT NOT NULL,
                    state TEXT NOT NULL, receipt TEXT NOT NULL, receipt_sha TEXT NOT NULL);
                CREATE TABLE events(sequence INTEGER PRIMARY KEY AUTOINCREMENT, import_id TEXT NOT NULL
                    REFERENCES imports(id), state TEXT NOT NULL, receipt_sha TEXT NOT NULL);
            ''')
            con.execute('INSERT INTO metadata VALUES (?,?)',('workspace',descriptor['id']))
            con.execute(f'PRAGMA application_id={APPLICATION_ID}')
            con.execute('PRAGMA user_version=1')
        flush_tree(root)
    return root


class InputStore:
    def __init__(self, root, *, recover=False):
        self.root=Path(root).absolute()
        self._lock=threading.Lock()
        try:
            if any(p.is_symlink() for p in (self.root,*self.root.parents)): raise ValueError()
            self._root_identity=private_member(self.root,directory=True)
            descriptor=read_json(self.read('workspace.json',65536))
            if (set(descriptor)!={'schema_version','kind','id','name','created_at','production_release_approved'}
                    or type(descriptor['schema_version']) is not int or descriptor['schema_version']!=1
                    or descriptor['kind']!='keystone.private-workspace' or descriptor['production_release_approved'] is not False):
                raise ValueError()
            ident(descriptor['id']); c.instant(descriptor['created_at'])
            self.descriptor=descriptor
            self._descriptor_sha=c.fingerprint(descriptor)
            self.path=self.root/'inputs.sqlite3'
            self._db_identity=private_member(self.path)
            for part in ('inputs','staging','permissions','reports','reports/runs'):
                private_member(self.root/part,directory=True)
            if recover:
                # SQLite may need to roll back a hot DELETE journal after a
                # writer dies. Only explicit startup/operator actions acquire
                # this writable control transaction; HTTP reads never do so.
                with control_write_gate(queue_only=True),self.connect(write=True):pass
            else:
                with self.connect():pass
        except Exception:
            raise c.InputError('input_unavailable',503) from None

    def read(self, relative, limit=c.MAX_PACKAGE):
        data=read_confined(self.root,relative,limit)
        private_member(self.root/relative)
        return data

    @contextmanager
    def connect(self, write=False):
        con=None
        try:
            if (private_member(self.root,directory=True)!=self._root_identity
                    or private_member(self.path)!=self._db_identity or self.path.stat().st_size>64_000_000
                    or c.sha(self.read('workspace.json',65536))!=c.sha(c.canonical(self.descriptor))):
                raise ValueError()
            for suffix in ('-journal','-wal','-shm'):
                p=self.path.with_name(self.path.name+suffix)
                if p.exists() or p.is_symlink(): private_member(p)
            con=sqlite3.connect(self.path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,
                                isolation_level=None,timeout=1)
            con.execute('PRAGMA foreign_keys=ON')
            if write: con.execute('PRAGMA synchronous=EXTRA')
            con.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            if (con.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID
                    or con.execute('PRAGMA user_version').fetchone()[0]!=1
                    or con.execute('PRAGMA journal_mode').fetchone()[0]!='delete'
                    or con.execute('PRAGMA quick_check').fetchone()[0]!='ok'
                    or con.execute('PRAGMA foreign_key_check').fetchone() is not None
                    or con.execute('SELECT value FROM metadata WHERE key=?',('workspace',)).fetchone()!=(self.descriptor['id'],)):
                raise ValueError()
            yield con
            if write: con.commit()
        except (c.InputError, BlockingIOError):
            if con: con.rollback()
            raise
        except Exception:
            if con: con.rollback()
            raise c.InputError('input_unavailable',503) from None
        finally:
            if con: con.close()

    @contextmanager
    def write(self):
        if not self._lock.acquire(timeout=1): raise c.InputError('input_busy',409)
        try:
            with control_write_gate(queue_only=True),self.connect(write=True) as con: yield con
        except BlockingIOError: raise c.InputError('input_busy',409) from None
        finally: self._lock.release()

    @staticmethod
    def _object(con, kind, id_):
        row=con.execute('SELECT kind,value,sha256 FROM objects WHERE id=?',(ident(id_),)).fetchone()
        if row is None or row[0]!=kind: raise c.InputError('input_not_found',404)
        data=row[1].encode('utf-8')
        if len(data)>131072 or c.sha(data)!=row[2]: raise c.InputError('input_unavailable',503)
        return read_json(data)

    @staticmethod
    def _put(con,kind,id_,value):
        data=c.canonical(value)
        if len(data)>131072: raise c.InputError('input_too_large',413)
        con.execute('INSERT INTO objects(kind,id,value,sha256) VALUES (?,?,?,?)',(kind,ident(id_),data.decode(),c.sha(data)))

    def object(self,kind,id_):
        with self.connect() as con: return self._object(con,kind,id_)

    def list(self,kind,limit=25,before=None):
        if type(limit) is not int or not 1<=limit<=100: raise c.InputError()
        with self.connect() as con:
            cursor=2**63-1
            if before is not None:
                row=con.execute('SELECT sequence FROM objects WHERE kind=? AND id=?',(kind,ident(before))).fetchone()
                if row is None: raise c.InputError()
                cursor=row[0]
            rows=con.execute('SELECT id FROM objects WHERE kind=? AND sequence<? ORDER BY sequence DESC LIMIT ?',
                             (kind,cursor,limit+1)).fetchall()
            values=[self._object(con,kind,x[0]) for x in rows[:limit]]
            return {'items':values,'next_cursor':values[-1]['id'] if len(rows)>limit else None}

    def create_entity(self,value):
        try: request=c.EntityRequest.model_validate(value)
        except ValueError: raise c.InputError() from None
        entity=c.Entity(**request.model_dump(),id='entity-'+uuid.uuid4().hex,created_at=now()).model_dump()
        if len(c.canonical(entity))>30_000:raise c.InputError('input_too_large',413)
        with self.write() as con:
            if con.execute("SELECT count(*) FROM objects WHERE kind='entity'").fetchone()[0]>=100:
                raise c.InputError('input_capacity',409)
            self._put(con,'entity',entity['id'],entity)
        return entity

    def create_dataset(self,value):
        try: req=c.DatasetRequest.model_validate(value)
        except ValueError: raise c.InputError() from None
        with self.write() as con:
            entity=self._object(con,'entity',req.entity_id)
            if (req.workflow in {'research','news','close'} and entity['kind']!='company'
                    or req.workflow in {'research','news'} and entity['ticker'] is None
                    or req.workflow=='events' and entity['kind']!='group'):
                raise c.InputError()
            if con.execute("SELECT count(*) FROM objects WHERE kind='dataset'").fetchone()[0]>=c.MAX_DATASETS:
                raise c.InputError('input_capacity',409)
            data=dict(req.model_dump(),id='dataset-'+uuid.uuid4().hex,created_at=now())
            self._put(con,'dataset',data['id'],data)
        return data

    def install_permission(self,record,evidence):
        """Operator-only API. Never exposed by the HTTP router."""
        try: policy=c.Permission.model_validate(record)
        except ValueError: raise c.InputError() from None
        if (policy.workspace_id!=self.descriptor['id'] or not 0<len(evidence)<=c.MAX_PACKAGE
                or c.sha(evidence)!=policy.evidence_sha256): raise c.InputError('input_policy_refused',403)
        with control_write_gate(),self.write() as con:
            self._object(con,'entity',policy.entity_id)
            old=con.execute('SELECT 1 FROM objects WHERE id=?',(policy.id,)).fetchone()
            if old:
                if self._object(con,'permission',policy.id)!=record: raise c.InputError('input_conflict',409)
                if self.read('permissions/'+policy.id+'/evidence')!=evidence: raise c.InputError('input_unavailable',503)
                return record
            folder=self.root/'permissions'/policy.id
            folder.mkdir(mode=0o700)
            write_new(folder/'evidence',evidence)
            write_new(folder/'record.json',c.canonical(record))
            flush_tree(folder);sync_directory(folder.parent)
            self._put(con,'permission',policy.id,record)
        return record

    def revoke_permission(self,id_,reason):
        if not isinstance(reason,str) or not 1<=len(reason.strip())<=500: raise c.InputError()
        with control_write_gate(),self.write() as con:
            self._object(con,'permission',id_)
            rev='revoked-'+c.sha(id_.encode())[:32]
            if con.execute('SELECT 1 FROM objects WHERE id=?',(rev,)).fetchone(): return
            self._put(con,'revocation',rev,dict(id=rev,permission_id=id_,reason=reason,created_at=now()))

    def policies(self,metadata,payload_sha,entity):
        pins=[];categories=set();backup=[]
        with self.connect() as con:
            for source in metadata['sources']:
                id_=source['permission_record_id']
                try:
                    raw=self._object(con,'permission',id_); policy=c.Permission.model_validate(raw)
                    if (policy.workspace_id!=self.descriptor['id'] or policy.entity_id!=entity['id']
                            or policy.payload_sha256!=payload_sha or policy.category!=source['category']
                            or policy.provider_or_owner!=source['provider_or_owner']
                            or policy.rights.local_retention!='allowed' or policy.rights.local_processing!='allowed'
                            or policy.expires_at and c.instant(policy.expires_at)<=datetime.now(timezone.utc)
                            or con.execute('SELECT 1 FROM objects WHERE id=?',('revoked-'+c.sha(id_.encode())[:32],)).fetchone()
                            or self.read('permissions/'+id_+'/record.json',65536)!=c.canonical(raw)
                            or c.sha(self.read('permissions/'+id_+'/evidence'))!=policy.evidence_sha256):
                        raise ValueError()
                except Exception: raise c.InputError('input_policy_refused',403) from None
                categories.add(c.CLASSIFICATIONS[policy.category])
                pins.append({'id':id_,'sha256':c.fingerprint(raw)})
                if policy.rights.local_backup!='allowed': backup.append(id_)
        return dict(permission_pins=sorted({p['id']:p for p in pins}.values(),key=lambda x:x['id']),
                    classification=next(iter(categories)) if len(categories)==1 else 'mixed',
                    backup_holds=sorted(set(backup)))

    def usage(self,con):
        size=0
        for name in ('inputs','staging'):
            for path in (self.root/name).rglob('*'):
                if path.is_dir(): private_member(path,directory=True)
                else: private_member(path);size+=path.stat().st_size
        reservations=0
        for raw, in con.execute("SELECT descriptor FROM imports WHERE state IN ('reserved','receiving','validating','interrupted','delivery_failed')"):
            reservations+=3*read_json(raw.encode())['package_bytes']+65536
        return size+reservations

    @staticmethod
    def _attempt(con,id_):
        row=con.execute('SELECT descriptor,descriptor_sha,state,receipt,receipt_sha FROM imports WHERE id=?',(ident(id_),)).fetchone()
        if row is None: raise c.InputError('input_not_found',404)
        if c.sha(row[0].encode())!=row[1] or c.sha(row[3].encode())!=row[4]: raise c.InputError('input_unavailable',503)
        receipt=read_json(row[3].encode())
        event=con.execute('SELECT state,receipt_sha FROM events WHERE import_id=? ORDER BY sequence DESC LIMIT 1',(id_,)).fetchone()
        if receipt['id']!=id_ or receipt['state']!=row[2] or event!=(row[2],row[4]): raise c.InputError('input_unavailable',503)
        return read_json(row[0].encode()),receipt

    def attempt(self,id_):
        with self.connect() as con: return self._attempt(con,id_)

    def attempts(self,limit=25,before=None):
        with self.connect() as con:
            cursor=2**63-1
            if before is not None:
                row=con.execute('SELECT sequence FROM imports WHERE id=?',(ident(before),)).fetchone()
                if row is None:raise c.InputError()
                cursor=row[0]
            rows=con.execute('SELECT id FROM imports WHERE sequence<? ORDER BY sequence DESC LIMIT ?',(cursor,limit+1)).fetchall()
            values=[self._attempt(con,x[0])[1] for x in rows[:limit]]
            return dict(items=values,next_cursor=values[-1]['id'] if len(rows)>limit else None)

    def versions(self,dataset_id,limit=25,before=None):
        self.object('dataset',dataset_id)
        with self.connect() as con:
            values=[self._object(con,'version',x[0]) for x in con.execute("SELECT id FROM objects WHERE kind='version' ORDER BY sequence DESC")]
        values=[v for v in values if v['dataset_id']==dataset_id]
        if before is not None:
            indexes=[i for i,v in enumerate(values) if v['id']==before]
            if not indexes:raise c.InputError()
            values=values[indexes[0]+1:]
        selected=[self.version(v['id']) for v in values[:limit]]
        return dict(items=selected,next_cursor=selected[-1]['id'] if len(values)>limit else None)

    @staticmethod
    def _transition(con,id_,receipt):
        data=c.canonical(receipt).decode();hash_=c.sha(data.encode())
        con.execute('UPDATE imports SET state=?,receipt=?,receipt_sha=? WHERE id=?',(receipt['state'],data,hash_,id_))
        con.execute('INSERT INTO events(import_id,state,receipt_sha) VALUES (?,?,?)',(id_,receipt['state'],hash_))

    def check_preflight(self,req):
        dataset=self.object('dataset',req.dataset_id);entity=self.object('entity',dataset['entity_id'])
        meta=req.metadata
        if (meta['dataset']['entity_id']!=entity['id'] or meta['workflow']!=dataset['workflow']
                or meta['payload_format']!=dataset['payload_format']): raise c.InputError()
        listing=meta['dataset']['listing']
        if (listing is not None and listing['ticker']!=entity['ticker'] or entity['ticker'] and listing is None):
            raise c.InputError()
        # The current saved-source adapters do not establish an exchange/share
        # class mapping. Refuse that unsupported substitution before retention.
        if meta['payload_format'] != c.FRESH_RESEARCH and listing is not None and any(listing[k] is not None for k in ('exchange','share_class')):
            raise c.InputError()
        if meta['dataset']['supersedes_version_id']:
            if self.object('version',meta['dataset']['supersedes_version_id'])['dataset_id']!=dataset['id']: raise c.InputError()
        return self.policies(meta,req.payload_sha256,entity)

    def inspect_package(self,dataset_id,data):
        """Read-only bounded preview using the same canonicalization as ingestion.

        No reservation, retention, semantic validation, accounting write or job.
        """
        value=c.envelope(c.bounded_json(data))
        if value['schema_version'] in {2,3} and len(data)>1_000_000:raise c.InputError('input_too_large',413)
        descriptor=c.Preflight(schema_version=value['schema_version'],dataset_id=ident(dataset_id),package_bytes=len(data),
            package_sha256=c.sha(data),payload_sha256=c.fingerprint(value['payload']),
            metadata={k:v for k,v in value.items() if k!='payload'})
        policy=self.check_preflight(descriptor)
        return dict(schema_version=1,descriptor=descriptor.model_dump(),policy=policy,financial_approval=False,
                    validation='pending_import',processing='not_started')

    def reserve(self,value,key):
        try: req=c.Preflight.model_validate(value)
        except ValueError: raise c.InputError() from None
        kh=c.request_key(key);descriptor=req.model_dump();fp=c.fingerprint(descriptor)
        self.check_preflight(req)
        with self.write() as con:
            old=con.execute('SELECT id FROM imports WHERE key_hash=?',(kh,)).fetchone()
            if old:
                existing,receipt=self._attempt(con,old[0])
                if c.fingerprint(existing)!=fp: raise c.InputError('input_conflict',409)
                return receipt,True
            pending=con.execute("SELECT count(*) FROM imports WHERE state NOT IN ('accepted','rejected')").fetchone()[0]
            if (pending>=c.MAX_PENDING or con.execute('SELECT count(*) FROM imports').fetchone()[0]>=c.MAX_ATTEMPTS
                    or self.usage(con)+3*req.package_bytes+65536>c.MAX_INPUT_BYTES): raise c.InputError('input_capacity',409)
            id_='import-'+uuid.uuid4().hex
            receipt=dict(id=id_,state='reserved',created_at=now(),dataset_id=req.dataset_id,version_id=None,
                         reason=None,financial_approval=False)
            con.execute('INSERT INTO imports(id,key_hash,descriptor,descriptor_sha,state,receipt,receipt_sha) VALUES (?,?,?,?,?,?,?)',
                (id_,kh,c.canonical(descriptor).decode(),fp,'reserved',c.canonical(receipt).decode(),c.fingerprint(receipt)))
            con.execute('INSERT INTO events(import_id,state,receipt_sha) VALUES (?,?,?)',(id_,'reserved',c.fingerprint(receipt)))
        return receipt,False

    def transition(self,id_,state,**values):
        allowed={'reserved':{'receiving'},'receiving':{'validating','interrupted','rejected'},
                 'validating':{'accepted','rejected','interrupted','delivery_failed'},
                 'interrupted':{'receiving','accepted'},'delivery_failed':{'accepted'}}
        with self.write() as con:
            _,old=self._attempt(con,id_)
            if state not in allowed.get(old['state'],set()): raise c.InputError('input_conflict',409)
            result={**old,**values,'state':state}
            self._transition(con,id_,result)
            return result

    def research_scope(self,entity_id,con=None):
        if con is None:
            with self.connect() as connection:return self.research_scope(entity_id,connection)
        for row in con.execute("SELECT id FROM objects WHERE kind='version' ORDER BY sequence"):
            v=self._object(con,'version',row[0]);contract=v['contract']
            if contract['metadata']['payload_format']==c.FRESH_RESEARCH and contract['metadata']['dataset']['entity_id']==entity_id:
                if contract['listing_scope']['first_version_id']!=v['id']:raise c.InputError('input_unavailable',503)
                return contract['listing_scope']
        return None

    def verify_research_scope(self,con,contract,version_id=None):
        from .research.contracts import scope
        pin=contract['listing_scope'];old=self.research_scope(contract['metadata']['dataset']['entity_id'],con)
        if (pin!=contract['validation']['listing_scope'] or pin['scope_sha256']!=c.fingerprint(scope(contract['metadata']))
                or old is not None and old!=pin or old is None and version_id is not None and pin['first_version_id']!=version_id):
            raise c.InputError('input_conflict',409)

    def version(self,id_,*,processing=False):
        version=self.object('version',id_)
        for name,proof in version['files'].items():
            data=self.read('inputs/'+version['id']+'/'+name)
            if len(data)!=proof['bytes'] or c.sha(data)!=proof['sha256']: raise c.InputError('input_unavailable',503)
        contract=read_json(self.read('inputs/'+id_+'/contract.json'))
        c.validation_receipt(contract['validation'])
        if contract!=version['contract'] or c.fingerprint(contract)!=version['contract_sha256']: raise c.InputError('input_unavailable',503)
        if c.fingerprint(self.object('dataset',version['dataset_id']))!=contract['dataset_sha256']:
            raise c.InputError('input_unavailable',503)
        entity=self.object('entity',contract['metadata']['dataset']['entity_id'])
        if c.fingerprint(entity)!=contract['entity_sha256']: raise c.InputError('input_unavailable',503)
        policy=self.policies(contract['metadata'],contract['payload_sha256'],entity)
        if policy!=contract['policy']: raise c.InputError('input_policy_refused',403)
        if contract['metadata']['payload_format']==c.FRESH_RESEARCH:
            with self.connect() as con:self.verify_research_scope(con,contract,id_)
        if processing and not contract['validation']['eligible']: raise c.InputError('input_invalid',409)
        return version

    def accept(self,id_,folder):
        descriptor,old=self.attempt(id_)
        if old['state']=='accepted': return old
        validation=c.validation_receipt(read_json(read_confined(folder,'validation.json',65536))).model_dump()
        payload=read_confined(folder,'payload.json')
        package=read_confined(folder,'package.json')
        entity=self.object('entity',descriptor['metadata']['dataset']['entity_id'])
        policy=self.policies(descriptor['metadata'],descriptor['payload_sha256'],entity)
        if (c.sha(package)!=descriptor['package_sha256'] or len(package)!=descriptor['package_bytes']
                or c.sha(payload)!=descriptor['payload_sha256'] or validation['payload_sha256']!=descriptor['payload_sha256']):
            raise c.InputError('input_unavailable',503)
        contract=dict(schema_version=1,dataset_id=descriptor['dataset_id'],metadata=descriptor['metadata'],
                      dataset_sha256=c.fingerprint(self.object('dataset',descriptor['dataset_id'])),
                      payload_sha256=descriptor['payload_sha256'],entity_sha256=c.fingerprint(entity),
                      policy=policy,validation=validation)
        local=descriptor['metadata']['payload_format']==c.FRESH_RESEARCH
        if local:contract['listing_scope']=validation['listing_scope']
        fp=c.fingerprint(contract)
        with self.write() as con:
            if local:self.verify_research_scope(con,contract)
            _,current=self._attempt(con,id_)
            if current['state'] not in {'validating','interrupted','delivery_failed'}: raise c.InputError('input_conflict',409)
            for v_id, in con.execute("SELECT id FROM objects WHERE kind='version'"):
                v=self._object(con,'version',v_id)
                if v['contract_sha256']==fp:
                    receipt={**current,'state':'accepted','version_id':v_id,'reason':'duplicate_version'}
                    self._transition(con,id_,receipt);return receipt
            if con.execute("SELECT count(*) FROM objects WHERE kind='version'").fetchone()[0]>=c.MAX_VERSIONS:
                raise c.InputError('input_capacity',409)
            if (folder/'contract.json').exists():
                if read_confined(folder,'contract.json')!=c.canonical(contract):raise c.InputError('input_conflict',409)
            else:write_new(folder/'contract.json',c.canonical(contract))
            id_v=read_json(read_confined(folder,'context.json'))['research_candidate_version_id'] if local else 'version-'+uuid.uuid4().hex
            if {p.name for p in folder.iterdir()}!={'package.json','preflight.json','context.json','payload.json','validation.json','contract.json'}:
                raise c.InputError('input_unavailable',503)
            files={p.name:{'bytes':p.stat().st_size,'sha256':c.sha(p.read_bytes())} for p in folder.iterdir()}
            flush_tree(folder)
            version=dict(id=id_v,dataset_id=descriptor['dataset_id'],created_at=now(),contract=contract,
                         contract_sha256=fp,files=files,import_id=id_)
            prepared=dict(schema_version=1,import_id=id_,transfer_id=current['transfer_id'],version=version)
            journal=folder.parent/'prepared.json'
            write_new(journal,c.canonical(dict(prepared=prepared,sha256=c.fingerprint(prepared))))
            flush_tree(folder.parent)
            if self.usage(con)>c.MAX_INPUT_BYTES:raise c.InputError('input_capacity',409)
            return self._finish_prepared(con,id_,current,prepared)

    def _finish_prepared(self,con,id_,receipt,prepared):
        descriptor,_=self._attempt(con,id_)
        version=prepared['version'];contract=version['contract']
        c.validation_receipt(contract['validation'])
        if con.execute("SELECT count(*) FROM objects WHERE kind='version'").fetchone()[0]>=c.MAX_VERSIONS:
            raise c.InputError('input_capacity',409)
        if (prepared['schema_version']!=1 or prepared['import_id']!=id_ or prepared['transfer_id']!=receipt.get('transfer_id')
                or version['import_id']!=id_ or version['dataset_id']!=descriptor['dataset_id']
                or c.fingerprint(contract)!=version['contract_sha256'] or contract['metadata']!=descriptor['metadata']
                or contract['payload_sha256']!=descriptor['payload_sha256']
                or set(version['files'])!={'package.json','preflight.json','context.json','payload.json','validation.json','contract.json'}):
            raise c.InputError('input_unavailable',503)
        entity=self._object(con,'entity',contract['metadata']['dataset']['entity_id'])
        if c.fingerprint(self._object(con,'dataset',version['dataset_id']))!=contract['dataset_sha256']:
            raise c.InputError('input_unavailable',503)
        if c.fingerprint(entity)!=contract['entity_sha256']:raise c.InputError('input_unavailable',503)
        if self.policies(contract['metadata'],contract['payload_sha256'],entity)!=contract['policy']:
            raise c.InputError('input_policy_refused',403)
        if contract['metadata']['payload_format'] == c.FRESH_CLOSE:
            from .close_state import current
            current(self,contract['validation']['accounting_source'])
        if contract['metadata']['payload_format']==c.FRESH_RESEARCH:self.verify_research_scope(con,contract,version['id'])
        target=self.root/'inputs'/ident(version['id'])
        source=self.root/'staging'/ident(id_)/ident(prepared['transfer_id'])
        if target.exists() and source.exists():raise c.InputError('input_unavailable',503)
        folder=target if target.exists() else source
        private_member(folder,directory=True)
        if {p.name for p in folder.iterdir()}!=set(version['files']):raise c.InputError('input_unavailable',503)
        for name,proof in version['files'].items():
            value=read_confined(folder,name)
            private_member(folder/name)
            if c.sha(value)!=proof['sha256'] or len(value)!=proof['bytes']:raise c.InputError('input_unavailable',503)
        if (c.sha(read_confined(folder,'package.json'))!=descriptor['package_sha256']
                or c.sha(read_confined(folder,'payload.json'))!=descriptor['payload_sha256']
                or read_json(read_confined(folder,'contract.json'))!=contract
                or read_json(read_confined(folder,'validation.json'))!=contract['validation']
                or read_json(read_confined(folder,'preflight.json'))!=descriptor):raise c.InputError('input_unavailable',503)
        if not target.exists():
            if self.usage(con)>c.MAX_INPUT_BYTES:raise c.InputError('input_capacity',409)
            self._promote(source,target);sync_directory(target.parent)
        self._put(con,'version',version['id'],version)
        complete={**receipt,'state':'accepted','version_id':version['id'],'reason':None}
        self._transition(con,id_,complete)
        return complete

    def recover(self,id_):
        """Explicit delivery-only acceptance; caller excludes server/validator sessions."""
        with self.write() as con:
            _,receipt=self._attempt(con,id_)
            if receipt['state']=='accepted':
                self.version(receipt['version_id'])
                return receipt
            if receipt['state'] not in {'validating','interrupted','delivery_failed'}:raise c.InputError('input_conflict',409)
            raw=read_json(self.read('staging/'+ident(id_)+'/prepared.json',131072))
            if set(raw)!={'prepared','sha256'} or c.fingerprint(raw['prepared'])!=raw['sha256']:
                raise c.InputError('input_unavailable',503)
            return self._finish_prepared(con,id_,receipt,raw['prepared'])

    def interrupt_imports(self):
        with self.write() as con:
            ids=[row[0] for row in con.execute("SELECT id FROM imports WHERE state IN ('receiving','validating')")]
            for id_ in ids:
                _,receipt=self._attempt(con,id_)
                self._transition(con,id_,{**receipt,'state':'interrupted','reason':'input_interrupted'})

    def backup_plan(self):
        """Explicit file inventory; caller stops the server and takes exclusive maintenance."""
        from keystone.contracts import validate_plan
        with self.connect() as con:
            permissions=[self._object(con,'permission',x[0]) for x in con.execute("SELECT id FROM objects WHERE kind='permission'")]
            for raw in permissions:
                policy=c.Permission.model_validate(raw)
                if (policy.rights.local_backup!='allowed' or policy.rights.local_retention!='allowed'
                        or policy.expires_at and c.instant(policy.expires_at)<=datetime.now(timezone.utc)
                        or con.execute('SELECT 1 FROM objects WHERE id=?',('revoked-'+c.sha(policy.id.encode())[:32],)).fetchone()):
                    raise c.InputError('input_policy_refused',403)
                if (self.read('permissions/'+policy.id+'/record.json',65536)!=c.canonical(raw)
                        or c.sha(self.read('permissions/'+policy.id+'/evidence'))!=policy.evidence_sha256):
                    raise c.InputError('input_unavailable',503)
            version_ids=[x[0] for x in con.execute("SELECT id FROM objects WHERE kind='version'")]
            accounting_entities={self._object(con,'close_intent',x[0])['entity_id']
                                 for x in con.execute("SELECT id FROM objects WHERE kind='close_intent'").fetchall()}
        for id_ in version_ids:self.version(id_)
        from ..review.notes import validate_notes
        validate_notes(self)
        members=[('workspace.json','file','configuration'),('inputs.sqlite3','file','logs'),
                 ('inputs','tree','inputs'),('staging','tree','inputs'),('permissions','tree','configuration'),
                 ('reports','tree','logs')]
        for path,kind in [('control/jobs.sqlite3','file'),('control/jobs','tree'),('control/operations','tree'),('control/restore-history.json','file')]:
            if (self.root/path).exists():members.append((path,kind,'logs'))
        # A stopped/failed validator can leave a disposable database copy. It
        # must be inspected before backup; never copy a live DB as a tree member.
        if any((self.root/'staging').rglob('*.duckdb*')):
            raise c.InputError('input_unavailable',503)
        accounting = self.root/'accounting'
        for entity_id in accounting_entities:
            private_member(accounting/ident(entity_id)/'state.duckdb')
        if accounting.exists() or accounting.is_symlink():
            private_member(accounting,directory=True)
            for directory in accounting.iterdir():
                private_member(directory,directory=True)
                self.object('entity',directory.name)
                if {p.name for p in directory.iterdir()} - {'state.duckdb','state.duckdb.wal','state.duckdb.lock'}:
                    raise c.InputError('input_unavailable',503)
                for member in directory.iterdir():private_member(member)
                db=directory/'state.duckdb';private_member(db)
                members.append((str(db.relative_to(self.root)),'database','agent4_state'))
        sources=[dict(name=path,path=str((self.root/path).resolve()),kind=kind,role=role) for path,kind,role in members]
        plan=dict(schema_version=1,scope='Private onboarding files and control receipts; local snapshot only; explicit restore-private and queued-work review required.',
            sources=sources,datasets=[dict(id=self.descriptor['id'],source='Operator-scoped input and permission records',
                classification='confidential',period='Per-version retained dates',currency='Per-input declared currency',
                units='Per-input contract',permission='reviewed',permission_evidence='Private operator records and payload-bound evidence',
                freshness_policy='Saved evidence; no automatic refresh',source_names=[x['name'] for x in sources])])
        return validate_plan(plan)

    @staticmethod
    def _promote(source,target):
        if target.exists() or target.is_symlink(): raise c.InputError('input_conflict',409)
        os.rename(source,target)
