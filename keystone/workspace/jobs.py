"""Opt-in local job admission over registered synthetic saved evidence."""
import hashlib
import os
from pathlib import Path
import re
import secrets
import tempfile
from urllib.parse import urlsplit
import uuid

from keystone.maintenance import control_write_gate
from keystone.operation import sync_directory
from .catalog import Catalog, run_identity
from .job_contract import (JOB_ID, PROFILES, JobError, JobRecord, JobRequest,
                           SourceBinding, fingerprint, now)
from .job_store import JobStore, private_member


class Admission:
    """One operator-enabled server session; a restart rotates its bearer token."""
    def __init__(self, workspace, directory, origin, *, enable_worker=False):
        self.store = None
        self.token = None
        self.worker_requested = enable_worker
        self.worker = None
        try:
            if not re.fullmatch(r'http://(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?', origin):
                raise JobError('job_origin_refused', 403)
            port = urlsplit(origin).port
            if port is not None and not 1 <= port <= 65535:
                raise JobError('job_origin_refused', 403)
            self.origin = origin
            self.authority = urlsplit(origin).netloc
            self.catalog = Catalog(workspace)
            self.catalog.load()
            self.store = JobStore(directory, workspace)
            # Admission-only SQLite writes can queue alongside the enabled worker.
            # The shared maintenance lease still excludes snapshots/restoration;
            # only the separate worker role can mutate execution or report state.
            self.store.queue_only = enable_worker
            self.token_file = self.store.root / 'access-token.key'
            token = secrets.token_urlsafe(32)
            with control_write_gate():
                if self.token_file.exists() or self.token_file.is_symlink():
                    private_member(self.token_file)
                fd, name = tempfile.mkstemp(prefix='.token-', dir=self.store.root)
                try:
                    with os.fdopen(fd, 'w') as stream:
                        stream.write(token + '\n')
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(name, self.token_file)
                    sync_directory(self.store.root)
                finally:
                    if Path(name).exists():
                        Path(name).unlink()
            self.token = token
        except Exception as exc:
            self.close()
            if isinstance(exc, JobError):
                raise
            raise JobError('job_store_unavailable') from None

    def close(self):
        self.token = None
        if self.worker is not None:
            self.worker.close()
            self.worker = None
        if self.store is not None:
            self.store.close()

    def start_worker(self):
        if self.worker_requested and self.worker is None:
            from .worker_process import WorkerProcess
            self.worker = WorkerProcess(self.catalog.root, self.store.root)

    @property
    def worker_enabled(self):
        return self.worker is not None and self.worker.running

    def public_job(self, job, *, worker_enabled=None):
        enabled = self.worker_enabled if worker_enabled is None else worker_enabled
        return {**job, 'schema_version':2, 'admission_schema_version':1, 'worker_enabled': enabled,
                'recovery_required': job['status'] in {'outcome_unknown','delivery_failed'}
                    or job['status']=='running' and self.worker_requested and not enabled,
                'result_url': '#/runs/' + job['execution']['result']['run_id']
                if job['status'] in {'completed','review_required'} else None}

    def authorize(self, request):
        headers = request.headers
        if (len(headers.getlist('host')) != 1 or headers.get('host') != self.authority
                or request.url.scheme != 'http'
                or len(headers.getlist('origin')) > 1
                or headers.get('origin') not in (None, self.origin)
                or len(headers.getlist('sec-fetch-site')) > 1
                or headers.get('sec-fetch-site') not in (None, 'same-origin', 'none')
                or request.method in {'POST','PUT','PATCH','DELETE'} and (headers.get('origin') != self.origin
                    or headers.get('sec-fetch-site') not in (None, 'same-origin'))):
            raise JobError('job_origin_refused', 403)
        if (self.token is None or len(headers.getlist('authorization')) != 1
                or not secrets.compare_digest(headers.get('authorization', '').encode(), ('Bearer ' + self.token).encode())):
            raise JobError('job_access_required', 403)

    @staticmethod
    def _safe(action):
        try:
            return action()
        except JobError:
            raise
        except Exception:
            # No request values, filesystem paths, SQL errors or raw agent output.
            raise JobError('job_store_unavailable') from None

    def submit(self, value, key):
        try:
            request = JobRequest.model_validate(value)
            if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{7,95}', key):
                raise ValueError('Unsupported request key.')
        except (ValueError, TypeError):
            raise JobError('job_request_invalid', 422) from None
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        request_sha256 = fingerprint(request.model_dump())
        old = self._safe(lambda: self.store.existing(key_hash, request_sha256))
        if old is not None:
            # Replay reports the original admission, not a fresh source validation.
            return self.public_job(old), True
        try:
            manifest = self.catalog.load()
            run = next(r for r in manifest.runs if r.id == request.source_run_id)
            registration = getattr(run, 'native_view', None)
            if run.workflow != request.workflow or registration is None:
                raise ValueError('No supported registered source.')
            binding = SourceBinding(run_id=run.id, workflow=run.workflow,
                run_sha256=fingerprint(run_identity(run)),
                primary_artifact_id=registration.source_artifact_ids[0],
                native_view=registration, artifacts=run.artifacts)
        except Exception:
            raise JobError('job_source_unavailable', 503) from None
        ident = uuid.uuid4().hex
        record = JobRecord(job_id='job-' + ident, operation_id='web-' + ident,
            request=request, request_sha256=request_sha256, created_at=now(),
            profile=PROFILES[request.workflow], source=binding)
        job, replayed = self._safe(lambda: self.store.admit(key_hash, record))
        return self.public_job(job), replayed

    def get(self, job_id):
        if not re.fullmatch(JOB_ID, job_id):
            raise JobError('job_not_found', 404)
        value = self._safe(lambda: self.store.get(job_id))
        return {**value, 'job': self.public_job(value['job'])}

    def list(self, query):
        try:
            if any(k not in {'limit', 'before'} or len(query.getlist(k)) != 1 for k in query):
                raise ValueError('Unsupported query.')
            raw = query.get('limit', '25')
            if not re.fullmatch(r'[1-9][0-9]{0,2}', raw) or not 1 <= int(raw) <= 100:
                raise ValueError('Invalid page size.')
            before = query.get('before')
            if before is not None and not re.fullmatch(JOB_ID, before):
                raise ValueError('Invalid cursor.')
        except (ValueError, TypeError):
            raise JobError('job_request_invalid', 422) from None
        value = self._safe(lambda: self.store.list(int(raw), before))
        enabled = self.worker_enabled
        return {**value, 'jobs': [self.public_job(j, worker_enabled=enabled) for j in value['jobs']], 'worker_enabled': enabled}
