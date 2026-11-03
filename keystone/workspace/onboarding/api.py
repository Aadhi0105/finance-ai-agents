"""Protected backend intake routes. Permission installation is operator-only."""
import re
import asyncio

from fastapi import Request
from fastapi.responses import JSONResponse,Response
from starlette.concurrency import run_in_threadpool

from . import contracts as c


def media(request,maximum,*,key=False):
    if request.query_params:raise c.InputError()
    h=request.headers
    types=h.getlist('content-type');encoding=h.getlist('content-encoding');lengths=h.getlist('content-length')
    if (len(types)!=1 or types[0].lower() not in {'application/json','application/json; charset=utf-8'}
            or len(encoding)>1 or encoding and encoding!=['identity']):raise c.InputError('input_media_refused',415)
    if len(lengths)>1 or lengths and (not re.fullmatch(r'[0-9]{1,10}',lengths[0]) or int(lengths[0])>maximum):
        raise c.InputError('input_too_large',413)
    if key and len(h.getlist('idempotency-key'))!=1:raise c.InputError()


async def small_body(request):
    media(request,131072)
    data=bytearray()
    try:
        async with asyncio.timeout(c.TRANSFER_SECONDS):
            async for chunk in request.stream():
                if len(data)+len(chunk)>131072:raise c.InputError('input_too_large',413)
                data.extend(chunk)
    except TimeoutError:raise c.InputError('input_interrupted',408) from None
    return c.bounded_json(bytes(data))


def page(request):
    q=request.query_params
    if any(k not in {'limit','before'} or len(q.getlist(k))!=1 for k in q):raise c.InputError()
    raw=q.get('limit','25')
    if not re.fullmatch(r'[1-9][0-9]{0,2}',raw) or not 1<=int(raw)<=100:raise c.InputError()
    return int(raw),q.get('before')


def add_routes(app,session):
    inputs=session.inputs

    @app.exception_handler(c.InputError)
    async def input_error(request,error):
        return JSONResponse(error.envelope(),status_code=error.status)

    @app.api_route('/api/entities',methods=['GET','HEAD'])
    async def entities(request:Request):
        limit,before=page(request)
        return await run_in_threadpool(inputs.list,'entity',limit,before)

    @app.api_route('/api/datasets',methods=['GET','HEAD'])
    async def datasets(request:Request):
        limit,before=page(request)
        return await run_in_threadpool(inputs.list,'dataset',limit,before)

    @app.api_route('/api/datasets/{dataset_id}',methods=['GET','HEAD'])
    async def dataset(dataset_id:str,request:Request):
        if request.query_params:raise c.InputError()
        return await run_in_threadpool(inputs.object,'dataset',dataset_id)

    @app.api_route('/api/datasets/{dataset_id}/versions',methods=['GET','HEAD'])
    async def versions(dataset_id:str,request:Request):
        limit,before=page(request)
        return await run_in_threadpool(inputs.versions,dataset_id,limit,before)

    @app.api_route('/api/datasets/{dataset_id}/versions/{version_id}',methods=['GET','HEAD'])
    async def version(dataset_id:str,version_id:str,request:Request):
        if request.query_params:raise c.InputError()
        value=await run_in_threadpool(inputs.version,version_id)
        if value['dataset_id']!=dataset_id:raise c.InputError('input_not_found',404)
        return value

    @app.api_route('/api/datasets/{dataset_id}/versions/{version_id}/files/{name}',methods=['GET','HEAD'])
    async def file(dataset_id:str,version_id:str,name:str,request:Request):
        if request.query_params:raise c.InputError()
        value=await run_in_threadpool(inputs.version,version_id)
        if value['dataset_id']!=dataset_id or name not in value['files']:raise c.InputError('input_not_found',404)
        data=await run_in_threadpool(inputs.read,'inputs/'+version_id+'/'+name)
        proof=value['files'][name]
        if len(data)!=proof['bytes'] or c.sha(data)!=proof['sha256']:raise c.InputError('input_unavailable',503)
        return Response(data,media_type='application/json',headers={
            'Content-Disposition':'attachment; filename="'+name+'"','Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'"})

    @app.api_route('/api/imports',methods=['GET','HEAD'])
    async def imports(request:Request):
        limit,before=page(request)
        return await run_in_threadpool(inputs.attempts,limit,before)

    @app.api_route('/api/imports/{id_}',methods=['GET','HEAD'])
    async def receipt(id_:str,request:Request):
        if request.query_params:raise c.InputError()
        _,value=await run_in_threadpool(inputs.attempt,id_)
        return value

    if session.imports_enabled:
        @app.post('/api/datasets/{dataset_id}/inspect')
        async def inspect_package(dataset_id:str,request:Request):
            media(request,c.MAX_PACKAGE)
            data=bytearray()
            try:
                async with asyncio.timeout(c.TRANSFER_SECONDS):
                    async for chunk in request.stream():
                        if len(data)+len(chunk)>c.MAX_PACKAGE:raise c.InputError('input_too_large',413)
                        data.extend(chunk)
            except TimeoutError:raise c.InputError('input_interrupted',408) from None
            return await run_in_threadpool(inputs.inspect_package,dataset_id,bytes(data))

        @app.post('/api/entities')
        async def create_entity(request:Request):
            return await run_in_threadpool(inputs.create_entity,await small_body(request))

        @app.post('/api/datasets')
        async def create_dataset(request:Request):
            return await run_in_threadpool(inputs.create_dataset,await small_body(request))

        @app.post('/api/imports')
        async def reserve(request:Request):
            media(request,131072,key=True)
            value,replayed=await run_in_threadpool(inputs.reserve,await small_body(request),request.headers['idempotency-key'])
            return JSONResponse(dict(import_attempt=value,replayed=replayed),status_code=200 if replayed else 201)

        @app.put('/api/imports/{id_}/package')
        async def transfer(id_:str,request:Request):
            media(request,c.MAX_PACKAGE,key=True)
            return await session.transfer(id_,request,request.headers['idempotency-key'])
