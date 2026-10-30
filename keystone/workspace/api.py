"""Loopback-only read interface; no agent imports, database writes or provider calls."""
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .catalog import Catalog, CatalogError, read_confined
from .report_views.errors import NativeViewError

ROOT = Path(__file__).resolve().parents[2]
APP_CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox allow-same-origin allow-downloads"


def create_app(workspace, frontend=None):
    catalog = Catalog(workspace)
    frontend = Path(frontend) if frontend is not None else ROOT / 'web/dist'
    app = FastAPI(title='Keystone local report workspace', docs_url=None,
                  redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def local_read_boundary(request: Request, call_next):
        native_request = request.url.path.endswith('/report-view')
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
        elif request.method not in {'GET', 'HEAD'}:
            response = JSONResponse({'detail': 'This workspace is read-only.'}, status_code=405,
                                    headers={'Allow': 'GET, HEAD'})
            if native_request:
                response = JSONResponse(NativeViewError('read_only_workspace').envelope(), status_code=405,
                                        headers={'Allow': 'GET, HEAD'})
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
        if request.url.path.endswith('/report-view'):
            return JSONResponse(NativeViewError().envelope(), status_code=503)
        return JSONResponse({'detail': 'Saved evidence is missing, changed or invalid. Prepare a fresh synthetic workspace.'}, status_code=503)

    @app.exception_handler(NativeViewError)
    async def native_error(request, error):
        return JSONResponse(error.envelope(), status_code=error.status)

    @app.api_route('/api/workspace', methods=['GET', 'HEAD'])
    def workspace_info():
        manifest = catalog.load()
        return {**manifest.model_dump(exclude={'runs'}), 'read_only': True,
                'live_data_enabled': False, 'paid_models_enabled': False,
                'runs': [catalog.public_run(r) for r in manifest.runs]}

    @app.api_route('/api/runs', methods=['GET', 'HEAD'])
    def list_runs(agent: str | None = None):
        if agent is not None and agent not in {'agent1', 'agent2', 'agent3', 'agent4'}:
            raise HTTPException(422, 'Unknown agent filter.')
        return {'runs': [catalog.public_run(r) for r in catalog.load().runs if agent is None or r.agent == agent]}

    def registered_run(run_id):
        run = next((r for r in catalog.load().runs if r.id == run_id), None)
        if run is None:
            raise HTTPException(404, 'Saved run not found.')
        return run

    @app.api_route('/api/runs/{run_id}', methods=['GET', 'HEAD'])
    def get_run(run_id: str):
        return catalog.public_run(registered_run(run_id))

    @app.api_route('/api/runs/{run_id}/report-view', methods=['GET', 'HEAD'])
    def report_view(run_id: str):
        from .report_views.delivery import load_view
        run = next((r for r in catalog.load().runs if r.id == run_id), None)
        if run is None:
            raise NativeViewError('saved_run_not_found')
        return load_view(catalog, run)

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
