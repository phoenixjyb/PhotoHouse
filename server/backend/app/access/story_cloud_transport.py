"""Author-only cloud previews. Reading a story never sends data externally."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .library import LibraryRoute, _query
from .memory_stories import call, refinement_resolver
from .stories import _uuid
from .transport import TransportError, _body, _memory_runtime, credentials_from_request
from .story_cloud_proofreading import CloudProofreadingError

router = APIRouter(route_class=LibraryRoute)


def _service(request):
    return request.app.state.story_cloud_proofreading


def _closed_failure(error):
    status = 409 if error.category in {'confirmation_mismatch', 'preview_expired', 'preview_unavailable'} else 503
    if error.category in {'invalid_input', 'confirmation_required'}:
        status = 422
    return TransportError(status, 'Cloud proofreading unavailable; review a new preview before sending')


async def _source(request, ident, revision):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    return await run_in_threadpool(call, _memory_runtime(request, allow_query=True),
        'proofreading_source', token, query['library'], _uuid(ident), revision,
        story_refinement_context=refinement_resolver(request))


def _ground(story, people):
    from .story_name_grounding import ground_text
    chapters, repairs = [], []
    for chapter in story['chapters']:
        grounded = ground_text(chapter['narration'], people)
        chapters.append({**chapter, 'narration': grounded['text']})
        repairs.extend({'chapter_id': chapter['id'], **item} for item in grounded['repairs'])
    return {**story, 'chapters': chapters}, repairs


@router.post('/memory-stories/{story_id}/proofreading/preview')
async def preview(story_id: str, request: Request):
    body = await _body(request, {'revision'}, max_body=1024)
    binding, story, people = await _source(request, story_id, body['revision'])
    try:
        grounded, repairs = await run_in_threadpool(_ground, story, people)
        result = await run_in_threadpool(_service(request).preview, binding, grounded, people)
    except CloudProofreadingError as error:
        raise _closed_failure(error) from None
    result.update(base_revision=binding['revision'], grounding_repairs=repairs)
    return JSONResponse(result)


@router.post('/memory-stories/{story_id}/proofreading/confirm')
async def confirm(story_id: str, request: Request):
    body = await _body(request, {'revision', 'preview_id', 'request_sha256', 'confirmed'}, max_body=2048)
    binding, _story, _people = await _source(request, story_id, body['revision'])
    if body['confirmed'] != 'yes':
        raise TransportError(422, 'Explicit preview confirmation required')
    try:
        result = await run_in_threadpool(_service(request).confirm,
            body['preview_id'], binding, body['request_sha256'], True)
    except CloudProofreadingError as error:
        raise _closed_failure(error) from None
    # Reauthorize after the external await, including selection/deletion/context.
    current, _story, _people = await _source(request, story_id, body['revision'])
    if current != binding:
        raise TransportError(409, 'Story changed; result was not adopted')
    return JSONResponse({**result, 'base_revision': binding['revision']})
