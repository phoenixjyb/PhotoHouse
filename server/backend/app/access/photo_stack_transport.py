"""Protected optional index reads and explicit personal display choices."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .library import LibraryRoute, _integer, _query
from .library_photo_stacks import LibraryPhotoStacks, FIELDS_WRITE
from .service import AccessService
from .transport import _runtime, credentials_from_request, _body, TransportError

router=APIRouter(route_class=LibraryRoute)


def _call(runtime,action,*args,**kwargs):
    with runtime.connection_factory() as db:
        return getattr(LibraryPhotoStacks(AccessService(db,clock=runtime.clock)),action)(*args,**kwargs)


@router.get('/photo-stacks/gallery')
async def gallery(request: Request):
    token,_=credentials_from_request(request,allow_query=True)
    query=_query(request,{'library','page','media'})
    if query.get('media','all') not in {'all','image'}:
        raise TransportError(400,'Invalid indexed gallery request')
    value=await run_in_threadpool(_call,_runtime(request,allow_query=True),'gallery',token,query['library'],
        page=_integer(query.get('page','1'),100000),media=query.get('media','all'))
    return JSONResponse(value)


@router.post('/photo-stacks/preferences')
async def preferences(request: Request):
    token,_=credentials_from_request(request,allow_query=True)
    query=_query(request,{'library'})
    body=await _body(request,FIELDS_WRITE)
    return JSONResponse(await run_in_threadpool(_call,_runtime(request,allow_query=True),
        'update',token,query['library'],body))
