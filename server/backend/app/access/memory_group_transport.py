"""Default-off library memory groups; suggestions never mutate membership."""
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .library import LibraryRoute, _integer, _query
from .memory_groups import MemoryGroups, MEMORY_GROUP_FIELDS, _csv
from .memory_group_schema import GROUP_REVISIONS, verify_memory_group_schema
from .service import AccessService
from .stories import _uuid
from .transport import TransportError, _body, _runtime, credentials_from_request
from .visual_candidates import VectorSpaceIdentity
from .visual_vector_artifacts import identity_sha256
from .visual_vector_loader import VisualVectorReads

router = APIRouter(route_class=LibraryRoute)


@dataclass(frozen=True, repr=False)
class GroupVectorConfiguration:
    """Operator-pinned prepared vectors, without model discovery or inference."""
    vector_root: Path
    identity: VectorSpaceIdentity

    def __post_init__(self):
        if (not isinstance(self.vector_root, Path) or not self.vector_root.is_absolute()
                or '..' in self.vector_root.parts or identity_sha256(self.identity) is None):
            raise ValueError('Explicit qualified group vector configuration required')


def capabilities(runtime, token, library, enabled, vectors):
    with runtime.connection_factory() as db:
        access = AccessService(db, clock=runtime.clock)
        with access._transaction():
            member = access._require(token, library, 'library.read')
            versions=[tuple(row) for row in db.execute('SELECT version_num FROM alembic_version')]
            ready = (enabled and len(versions)==1 and versions[0][0] in GROUP_REVISIONS
                and verify_memory_group_schema(db))
            return {'version': 1, 'enabled': bool(ready),
                    'manual': bool(ready and member['role'] in {'owner', 'contributor'}),
                    'suggestions': bool(ready and vectors is not None),
                    'max_members': 24, 'needs_review': True}


def call(runtime, action, *args):
    with runtime.connection_factory() as db:
        return getattr(MemoryGroups(AccessService(db, clock=runtime.clock)), action)(*args)


def proposal(runtime, token, library, body, vectors):
    seeds = tuple(str(value) for value in _csv(body['asset_ids'], 'asset_ids',
        maximum=24, required=True))
    excluded = tuple(str(value) for value in _csv(body['excluded_asset_ids'],
        'excluded_asset_ids', maximum=512))
    if set(seeds) & set(excluded):
        raise TransportError(400, 'Invalid group selection')
    with runtime.connection_factory() as db:
        access = AccessService(db, clock=runtime.clock)
        if vectors is None:
            # Even unavailable proposals must resolve the complete seed scope.
            with access._transaction():
                access._require(token, library, 'library.read')
                MemoryGroups(access)._assets(token, library, [int(value) for value in seeds])
            result = None
        else:
            result = VisualVectorReads(access, vectors.vector_root, vectors.identity).memory_group_items(
                token, library, seeds, excluded_ids=excluded)
        if isinstance(result, dict):
            return result
        return {'version': 1, 'status': 'unavailable', 'library_id': library,
                'seed_asset_ids': list(seeds), 'needs_review': True, 'items': []}


async def scope(request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    runtime = _runtime(request, allow_query=True)
    # Authenticate before exposing feature/storage availability.
    caps = await run_in_threadpool(capabilities, runtime, token, query['library'],
        request.app.state.memory_groups_enabled, request.app.state.memory_group_vectors)
    if not caps['enabled']:
        raise TransportError(503, 'Memory groups unavailable')
    return runtime, token, query['library']


def response(value, *, status=200):
    result = JSONResponse(value, status_code=status)
    if len(result.body) > 1024 * 1024:
        raise TransportError(503, 'Memory group response unavailable')
    return result


@router.get('/memory-groups/capabilities')
async def group_capabilities(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    library = _query(request, {'library'})['library']
    return response(await run_in_threadpool(capabilities, _runtime(request, allow_query=True),
        token, library, request.app.state.memory_groups_enabled,
        request.app.state.memory_group_vectors))


@router.post('/memory-groups/proposals')
async def group_proposal(request: Request):
    runtime, token, library = await scope(request)
    body = await _body(request, {'asset_ids', 'excluded_asset_ids'}, max_body=24576)
    return response(await run_in_threadpool(proposal, runtime, token, library, body,
        request.app.state.memory_group_vectors))


@router.get('/assets/{asset_id}/memory-groups')
async def asset_groups(asset_id: str, request: Request):
    runtime, token, library = await scope(request)
    return response(await run_in_threadpool(call, runtime, 'list_for_asset', token,
        library, _integer(asset_id, 2**63 - 1)))


@router.get('/memory-groups/{group_id}')
async def group(group_id: str, request: Request):
    runtime, token, library = await scope(request)
    return response(await run_in_threadpool(call, runtime, 'get', token, library, _uuid(group_id)))


@router.post('/memory-groups')
async def create_group(request: Request):
    runtime, token, library = await scope(request)
    body = await _body(request, MEMORY_GROUP_FIELDS, max_body=24576)
    return response(await run_in_threadpool(call, runtime, 'save', token, library, body), status=201)


@router.put('/memory-groups/{group_id}')
async def update_group(group_id: str, request: Request):
    runtime, token, library = await scope(request)
    body = await _body(request, MEMORY_GROUP_FIELDS, max_body=24576)
    return response(await run_in_threadpool(call, runtime, 'save', token, library, body, _uuid(group_id)))
