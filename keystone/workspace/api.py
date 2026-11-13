"""Loopback report reads and explicitly enabled, protected offline job admission."""
from contextlib import asynccontextmanager
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .catalog import Catalog, CatalogError, read_confined, read_json
from .job_contract import JobError, MAX_REQUEST_BYTES, capabilities
from .report_views.errors import NativeViewError
from .review.contracts import ReviewError

ROOT = Path(__file__).resolve().parents[2]
APP_CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox allow-same-origin allow-downloads"


def create_app(workspace, frontend=None, *, admission=None, private=None):
    catalog = Catalog(workspace)
    if private is not None and admission is not private:
        raise ValueError('Private reads and job admission must share their session.')
    try:
        raw = read_json(read_confined(catalog.root,'catalog.json',2_000_000))
    except CatalogError:
        raw = {}
    if isinstance(raw,dict) and raw.get('schema_version') == 3 and private is None:
        raise ValueError('A private catalogue requires its authenticated workspace session.')
    frontend = Path(frontend) if frontend is not None else ROOT / 'web/dist'
    @asynccontextmanager
    async def lifespan(app):
        try:
            if admission is not None:
                await run_in_threadpool(admission.start_worker)
            yield
        finally:
            if admission is not None:
                await run_in_threadpool(admission.close)

    app = FastAPI(title='Keystone local report workspace', docs_url=None,
                  redoc_url=None, openapi_url=None, lifespan=lifespan)
    if admission is not None and admission.catalog.root.resolve() != catalog.root.resolve():
        raise ValueError('Job admission and report workspace must agree.')

    def load_catalog():
        manifest=catalog.load()
        if private is not None and (manifest.schema_version!=3 or manifest.workspace_id!=private.inputs.descriptor['id']):
            from .onboarding.contracts import InputError
            raise InputError('input_unavailable',503)
        return manifest

    @app.middleware('http')
    async def local_read_boundary(request: Request, call_next):
        native_request = request.url.path.endswith('/report-view')
        job_request = request.url.path == '/api/jobs' or request.url.path.startswith('/api/jobs/')
        host = request.headers.get('host', '')
        origin = request.headers.get('origin')
        valid_host = bool(re.fullmatch(r'(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?', host))
        origin_ok = not origin or origin in {f'http://{host}', f'https://{host}'}
        if (not valid_host or not origin_ok or
                (request.url.path.startswith('/api/') and '/files/' not in request.url.path
                 and request.headers.get('sec-fetch-site') == 'cross-site')):
            response = JSONResponse({'detail': 'Local same-origin access required.'}, status_code=403)
            if native_request:
                response = JSONResponse(NativeViewError('local_access_required').envelope(), status_code=403)
        elif (request.method not in {'GET', 'HEAD'} and not (
              admission is not None and request.method == 'POST' and request.url.path == '/api/jobs'
              or private is not None and private.review_notes_enabled and request.method == 'POST'
                 and re.fullmatch(r'/api/runs/[a-z0-9_-]+/review-notes', request.url.path)
              or private is not None and private.review_corrections_enabled and request.method == 'POST'
                 and re.fullmatch(r'/api/runs/[a-z0-9_-]+/review-corrections', request.url.path)
              or private is not None and private.review_decisions_enabled and request.method == 'POST'
                 and re.fullmatch(r'/api/runs/[a-z0-9_-]+/review-decisions', request.url.path)
              or private is not None and private.imports_enabled and (
                  request.method == 'POST' and request.url.path in {'/api/entities','/api/datasets','/api/imports'}
                  or request.method == 'POST' and re.fullmatch(r'/api/datasets/[a-z0-9_-]+/inspect',request.url.path)
                  or request.method == 'PUT' and re.fullmatch(r'/api/imports/[a-z0-9_-]+/package',request.url.path)))):
            response = JSONResponse({'detail': 'This workspace is read-only.'}, status_code=405,
                                    headers={'Allow': 'GET, HEAD'})
            if native_request:
                response = JSONResponse(NativeViewError('read_only_workspace').envelope(), status_code=405,
                                        headers={'Allow': 'GET, HEAD'})
        else:
            try:
                if private is not None and request.url.path.startswith('/api/') and request.url.path != '/api/execution':
                    private.authorize(request)
                elif job_request and admission is not None:
                    admission.authorize(request)
            except JobError as error:
                response = JSONResponse(error.envelope(), status_code=error.status)
            else:
                response = await call_next(request)
        response.headers.setdefault('Content-Security-Policy', APP_CSP)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
        if request.method == 'HEAD':
            return Response(status_code=response.status_code, headers=dict(response.headers))
        return response

    @app.exception_handler(CatalogError)
    async def inventory_error(request, error):
        if private is not None:
            from .onboarding.contracts import InputError
            return JSONResponse(InputError('input_unavailable',503).envelope(),status_code=503)
        if request.url.path.endswith('/report-view'):
            return JSONResponse(NativeViewError().envelope(), status_code=503)
        return JSONResponse({'detail': 'Saved evidence is missing, changed or invalid. Prepare a fresh synthetic workspace.'}, status_code=503)

    @app.exception_handler(NativeViewError)
    async def native_error(request, error):
        return JSONResponse(error.envelope(), status_code=error.status)

    @app.exception_handler(JobError)
    async def job_error(request, error):
        return JSONResponse(error.envelope(), status_code=error.status,
                            headers={'Retry-After': '1'} if error.code == 'job_control_busy' else None)

    @app.exception_handler(ReviewError)
    async def review_error(request, error):
        return JSONResponse(error.envelope(), status_code=error.status)

    @app.api_route('/api/execution', methods=['GET', 'HEAD'])
    def execution_capabilities():
        if private is not None:
            return private.capabilities()
        return capabilities(admission is not None, admission.worker_enabled if admission is not None else False,
                            admission.worker_requested if admission is not None else False)

    if private is not None:
        from .onboarding.api import add_routes
        add_routes(app,private)

        @app.api_route('/api/operations',methods=['GET','HEAD'])
        def operations(request: Request):
            from .operations import observe
            if request.query_params:
                from .onboarding.contracts import InputError
                raise InputError()
            return observe(private)

        @app.api_route('/api/storage',methods=['GET','HEAD'])
        def storage_observation(request: Request):
            from .lifecycle import observe_storage
            if request.query_params:
                from .onboarding.contracts import InputError
                raise InputError()
            return observe_storage(private.inputs)

    if admission is not None:
        @app.post('/api/jobs')
        async def submit_job(request: Request):
            if request.query_params or len(request.headers.getlist('idempotency-key')) != 1:
                raise JobError('job_request_invalid', 422)
            if (len(request.headers.getlist('content-type')) != 1
                    or request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json'
                    or len(request.headers.getlist('content-encoding')) > 1
                    or request.headers.get('content-encoding') not in (None, 'identity')):
                raise JobError('job_media_type_refused', 415)
            lengths = request.headers.getlist('content-length')
            if len(lengths) > 1 or lengths and not re.fullmatch(r'[0-9]{1,10}', lengths[0]):
                raise JobError('job_request_invalid', 422)
            transport_limit=8192 if private is not None else MAX_REQUEST_BYTES
            if lengths and int(lengths[0]) > transport_limit:
                raise JobError('job_request_too_large', 413)
            data = bytearray()
            async for chunk in request.stream():
                if len(data) + len(chunk) > transport_limit:
                    raise JobError('job_request_too_large', 413)
                data.extend(chunk)
            try:
                value = read_json(bytes(data))
            except ValueError:
                raise JobError('job_request_invalid', 422) from None
            if len(data)>MAX_REQUEST_BYTES and (not isinstance(value,dict) or value.get('schema_version')!=3):raise JobError('job_request_too_large',413)
            job, replayed = await run_in_threadpool(admission.submit, value, request.headers['idempotency-key'])
            return JSONResponse(dict(job=job, replayed=replayed, worker_enabled=job['worker_enabled'],
                next_action='Queued; the local worker is disabled.'
                if job['status'] == 'queued' and not job['worker_enabled']
                else 'Inspect saved job status and evidence; financial review remains required.'),
                status_code=200 if replayed else 202, headers={'Location': '/api/jobs/' + job['job_id']})

        @app.api_route('/api/jobs', methods=['GET', 'HEAD'])
        async def list_jobs(request: Request):
            return await run_in_threadpool(admission.list, request.query_params)

        @app.api_route('/api/jobs/{job_id}', methods=['GET', 'HEAD'])
        async def get_job(job_id: str, request: Request):
            if request.query_params:
                raise JobError('job_request_invalid', 422)
            return await run_in_threadpool(admission.get, job_id)

    @app.api_route('/api/workspace', methods=['GET', 'HEAD'])
    def workspace_info():
        manifest = load_catalog()
        if private is not None:
            for run in manifest.runs: private.source_version(run)
        return {**manifest.model_dump(exclude={'runs'}), **({'workspace_name':private.inputs.descriptor['name']} if private else {}), 'read_only': not (private.imports_enabled or private.jobs_enabled or private.review_notes_enabled or private.review_corrections_enabled or private.review_decisions_enabled) if private else True,
                'live_data_enabled': False, 'paid_models_enabled': False,
                'input_admission_enabled': private.imports_enabled if private else False,
                'job_admission_enabled': private.jobs_enabled if private else admission is not None,
                'job_worker_enabled': admission.worker_enabled if admission is not None else False,
                'review_notes_enabled': private.review_notes_enabled if private else False,
                'review_corrections_enabled': private.review_corrections_enabled if private else False,
                'review_decisions_enabled': private.review_decisions_enabled if private else False,
                'operations_supported': private is not None,
                'storage_supported': private is not None,
                'runs': [catalog.public_run(r) for r in manifest.runs]}

    @app.api_route('/api/runs', methods=['GET', 'HEAD'])
    def list_runs(agent: str | None = None):
        if agent is not None and agent not in {'agent1', 'agent2', 'agent3', 'agent4'}:
            raise HTTPException(422, 'Unknown agent filter.')
        runs = [r for r in load_catalog().runs if agent is None or r.agent == agent]
        if private is not None:
            for run in runs: private.source_version(run)
        return {'runs': [catalog.public_run(r) for r in runs]}

    def registered_run(run_id):
        run = next((r for r in load_catalog().runs if r.id == run_id), None)
        if run is None:
            raise HTTPException(404, 'Saved run not found.')
        if private is not None: private.source_version(run)
        return run

    @app.api_route('/api/runs/{run_id}', methods=['GET', 'HEAD'])
    def get_run(run_id: str):
        return catalog.public_run(registered_run(run_id))

    @app.api_route('/api/runs/{run_id}/report-view', methods=['GET', 'HEAD'])
    def report_view(run_id: str):
        from .report_views.delivery import load_view
        run = next((r for r in load_catalog().runs if r.id == run_id), None)
        if run is None:
            raise NativeViewError('saved_run_not_found')
        if private is not None: private.source_version(run)
        return load_view(catalog, run)

    @app.api_route('/api/runs/{run_id}/review', methods=['GET', 'HEAD'])
    def review_snapshot(run_id: str, request: Request):
        if request.query_params:
            raise ReviewError('review_request_invalid', 422)
        return review_context(run_id)

    def review_context(run_id, manifest=None):
        from .report_views.delivery import load_view
        from .review.projection import project_review
        manifest = load_catalog() if manifest is None else manifest
        run = next((r for r in manifest.runs if r.id == run_id), None)
        if run is None:
            raise ReviewError('review_run_not_found', 404)
        if private is not None:
            private.source_version(run)
        view = load_view(catalog, run)
        return project_review(manifest, run, view)

    @app.api_route('/api/runs/{run_id}/review-notes', methods=['GET', 'HEAD'])
    def review_notebook(run_id: str, request: Request):
        from .review.notes import NotesStore, notebook
        if request.query_params:
            raise ReviewError('review_request_invalid', 422)
        snapshot = review_context(run_id)['snapshot']
        return (NotesStore(private.inputs).notebook(snapshot, enabled=private.review_notes_enabled)
                if private else notebook(snapshot))

    if private is not None and private.review_notes_enabled:
        @app.post('/api/runs/{run_id}/review-notes')
        async def append_review_note(run_id: str, request: Request):
            import asyncio
            from .onboarding.api import media
            from .onboarding import contracts as c
            from .review.notes import MAX_NOTE_BYTES, NotesStore
            media(request, MAX_NOTE_BYTES, key=True)
            data = bytearray()
            try:
                async with asyncio.timeout(c.TRANSFER_SECONDS):
                    async for chunk in request.stream():
                        if len(data) + len(chunk) > MAX_NOTE_BYTES:
                            raise c.InputError('input_too_large', 413)
                        data.extend(chunk)
            except TimeoutError:
                raise c.InputError('input_interrupted', 408) from None
            note, replayed = await run_in_threadpool(NotesStore(private.inputs).append,
                lambda: review_context(run_id), c.bounded_json(bytes(data)), request.headers['idempotency-key'])
            return JSONResponse(dict(note=note, replayed=replayed, financial_approval=False),
                                status_code=200 if replayed else 201)

    @app.api_route('/api/runs/{run_id}/review-corrections', methods=['GET', 'HEAD'])
    def review_corrections(run_id: str, request: Request):
        from .onboarding import contracts as c
        from .review.corrections import CorrectionsStore
        query = request.query_params
        if (any(k != 'replacement_version_id' or len(query.getlist(k)) != 1 for k in query)
                or 'replacement_version_id' in query and not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,99}', query['replacement_version_id'])):
            raise ReviewError('review_request_invalid', 422)
        manifest = load_catalog()
        checked = {}
        def context(ident):
            if ident not in checked:
                checked[ident] = review_context(ident, manifest)
            return checked[ident]
        snapshot = context(run_id)['snapshot']
        if private is None:
            return JSONResponse(c.InputError('review_correction_unsupported', 409).envelope(), status_code=409)
        return CorrectionsStore(private.inputs).lineage(snapshot, context, manifest,
            enabled=private.review_corrections_enabled, replacement_version_id=query.get('replacement_version_id'))

    if private is not None and private.review_corrections_enabled:
        @app.post('/api/runs/{run_id}/review-corrections')
        async def append_review_correction(run_id: str, request: Request):
            import asyncio
            from .onboarding.api import media
            from .onboarding import contracts as c
            from .review.corrections import CorrectionsStore, MAX_CORRECTION_BYTES
            media(request, MAX_CORRECTION_BYTES, key=True)
            data = bytearray()
            try:
                async with asyncio.timeout(c.TRANSFER_SECONDS):
                    async for chunk in request.stream():
                        if len(data) + len(chunk) > MAX_CORRECTION_BYTES:
                            raise c.InputError('input_too_large', 413)
                        data.extend(chunk)
            except TimeoutError:
                raise c.InputError('input_interrupted', 408) from None
            record, replayed = await run_in_threadpool(CorrectionsStore(private.inputs).append,
                review_context, run_id, c.bounded_json(bytes(data)), request.headers['idempotency-key'])
            return JSONResponse(dict(correction=record, replayed=replayed, financial_approval=False),
                                status_code=200 if replayed else 201)

    @app.api_route('/api/runs/{run_id}/review-decisions', methods=['GET', 'HEAD'])
    def review_decisions(run_id: str, request: Request):
        from .review.decisions import DecisionsStore, journal
        query = request.query_params
        if (any(k not in {'before','revision'} or len(query.getlist(k)) != 1 for k in query)
                or 'before' in query and re.fullmatch(r'decision-[a-f0-9]{32}', query['before']) is None
                or 'revision' in query and re.fullmatch(r'[0-9]{1,6}', query['revision']) is None):
            raise ReviewError('review_request_invalid', 422)
        manifest = load_catalog(); checked = {}
        def context(ident):
            if ident not in checked:
                checked[ident] = review_context(ident, manifest)
            return checked[ident]
        snapshot = context(run_id)['snapshot']
        options = dict(before=query.get('before'), revision=int(query['revision']) if 'revision' in query else None)
        if private is None:
            if query:
                raise ReviewError('review_request_invalid', 422)
            return journal(snapshot)
        return DecisionsStore(private.inputs).journal(snapshot, context, enabled=private.review_decisions_enabled, **options)

    if private is not None and private.review_decisions_enabled:
        @app.post('/api/runs/{run_id}/review-decisions')
        async def append_review_decision(run_id: str, request: Request):
            import asyncio
            from .onboarding.api import media
            from .onboarding import contracts as c
            from .review.decisions import MAX_DECISION_BYTES, DecisionsStore
            media(request, MAX_DECISION_BYTES, key=True)
            data = bytearray()
            try:
                async with asyncio.timeout(c.TRANSFER_SECONDS):
                    async for chunk in request.stream():
                        if len(data) + len(chunk) > MAX_DECISION_BYTES:
                            raise c.InputError('input_too_large', 413)
                        data.extend(chunk)
            except TimeoutError:
                raise c.InputError('input_interrupted', 408) from None
            record, replayed = await run_in_threadpool(DecisionsStore(private.inputs).append,
                review_context, run_id, c.bounded_json(bytes(data)), request.headers['idempotency-key'])
            return JSONResponse(dict(record=record, replayed=replayed, financial_approval=False), status_code=200 if replayed else 201)

    @app.api_route('/api/runs/{run_id}/files/{name:path}', methods=['GET', 'HEAD'])
    def get_file(run_id: str, name: str):
        run = registered_run(run_id)
        artifact = next((a for a in run.artifacts if a.name == name), None)
        if artifact is None:
            raise HTTPException(404, 'Registered artifact not found.')
        media = {'.html': 'text/html', '.json': 'application/json', '.png': 'image/png'}[Path(name).suffix]
        headers = {'Content-Security-Policy': REPORT_CSP if media == 'text/html' else "default-src 'none'; frame-ancestors 'self'"}
        if media == 'application/json':
            headers['Content-Disposition'] = f'attachment; filename="{Path(name).name}"'
        if private is not None:
            headers['Content-Disposition'] = f'attachment; filename="{Path(name).name}"'
        return Response(catalog.read(run.id, artifact), media_type=media, headers=headers)

    @app.api_route('/', methods=['GET', 'HEAD'])
    def index():
        try:
            return Response(read_confined(frontend, 'index.html', 1_000_000), media_type='text/html')
        except CatalogError:
            return JSONResponse({'detail': 'Frontend not built. Run the web build first.'}, status_code=503)

    @app.api_route('/assets/{name}', methods=['GET', 'HEAD'])
    def asset(name: str):
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:js|css)', name):
            raise HTTPException(404, 'Asset not found.')
        try:
            data = read_confined(frontend, f'assets/{name}')
        except CatalogError:
            raise HTTPException(404, 'Asset not found.') from None
        return Response(data, media_type='text/javascript' if name.endswith('.js') else 'text/css')

    return app
