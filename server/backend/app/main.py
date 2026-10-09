"""PhotoHouse HTTP entry point: no configuration, storage or worker side effects.

The application starts closed. Deployment must explicitly supply reviewed access
and media runtimes; no environment/database discovery or legacy fallback exists.
"""
import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool
from .access.transport import router as account_router
from .access.media import router as media_router
from .access.library import router as library_router
from .access.members import router as member_router
from .access.stories import router as story_router
from .access.story_workspace import router as story_workspace_router
from .access.memory_stories import router as memory_router
from .access.memory_transport import router as memory_community_router
from .access.memory_book_edition_transport import router as memory_edition_router
from .access.people import router as people_router
from .access.tags import router as tag_router
from .access.albums import router as album_router
from .access.boundary import ClosedBoundary
from .access.discovery_transport import router as discovery_router
from .access.assistant import router as assistant_router
from .access.upload_transport import router as upload_router
from .access.upload_review import router as upload_review_router
from .access.annotations import router as annotation_router
from .access.duplicates import router as duplicate_router
from .access.captions import router as caption_router
from .access.library_organization import router as organization_router
from .routers.ui import router as ui_router
from .updates import router as updates_router


def create_app(*, access_runtime=None, media_runtime=None, discovery_runtime=None,
               upload_runtime=None, upload_review_runtime=None,
               annotation_intake_enabled=False, assistant_enabled=False,
               memory_collaboration_enabled=False, memory_originals_enabled=False,
               memory_generation_enabled=False, memory_editorial_enabled=False,
               memory_editions_enabled=False,
               assistant_asr=None, assistant_tts=None, assistant_journal=None, update_root=None,
               story_title_suggester=None):
    if story_title_suggester is not None and not callable(getattr(story_title_suggester, 'suggest', None)):
        raise ValueError('Explicit story title adapter required')
    if type(annotation_intake_enabled) is not bool:
        raise ValueError('Explicit annotation intake opt-in required')
    if type(assistant_enabled) is not bool:
        raise ValueError('Explicit assistant opt-in required')
    if any(type(flag) is not bool for flag in (memory_collaboration_enabled,
            memory_originals_enabled, memory_generation_enabled, memory_editorial_enabled,
            memory_editions_enabled)):
        raise ValueError('Explicit memory opt-in required')
    if (memory_originals_enabled or memory_generation_enabled or memory_editorial_enabled or
            memory_editions_enabled) and not memory_collaboration_enabled:
        raise ValueError('Memory contributions/generation require collaboration opt-in')
    @asynccontextmanager
    async def lifespan(app):
        maintenance = None
        memory_maintenance = None
        journal = app.state.assistant_journal
        if app.state.memory_collaboration_enabled:
            from .access.memory_jobs import maintenance as prune_memories
            await run_in_threadpool(prune_memories, app.state.access_runtime)
        if journal is not None:
            await run_in_threadpool(journal.maintenance, interrupt=True)
            async def prune():
                while True:
                    await asyncio.sleep(3600)
                    try:
                        await run_in_threadpool(journal.maintenance)
                        app.state.assistant_journal_healthy = True
                    except Exception:
                        # Never log input/provider details. Refuse new processing
                        # until a later successful purge restores retention.
                        app.state.assistant_journal_healthy = False
            maintenance = asyncio.create_task(prune())
        if app.state.memory_collaboration_enabled:
            async def prune_memory_history():
                while True:
                    await asyncio.sleep(3600)
                    try:
                        await run_in_threadpool(prune_memories, app.state.access_runtime)
                        app.state.memory_retention_healthy = True
                    except Exception:
                        app.state.memory_retention_healthy = False
            memory_maintenance = asyncio.create_task(prune_memory_history())
        try:
            yield
        finally:
            if maintenance is not None:
                maintenance.cancel()
                with suppress(asyncio.CancelledError):
                    await maintenance
            if memory_maintenance is not None:
                memory_maintenance.cancel()
                with suppress(asyncio.CancelledError):
                    await memory_maintenance
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None,
                  redirect_slashes=False, lifespan=lifespan)
    app.state.access_runtime = access_runtime
    # No provider discovery or live configuration fallback. Qualification and
    # runtime wiring are separate from mounting the protected, default-off route.
    from threading import Lock
    app.state.story_title_suggester = story_title_suggester
    app.state.story_title_lock = Lock()
    app.state.media_runtime = media_runtime
    app.state.discovery_runtime = discovery_runtime
    app.state.assistant_enabled = assistant_enabled
    app.state.memory_collaboration_enabled = memory_collaboration_enabled
    app.state.memory_originals_enabled = memory_originals_enabled
    app.state.memory_generation_enabled = memory_generation_enabled
    app.state.memory_editorial_enabled = memory_editorial_enabled
    app.state.memory_editions_enabled = memory_editions_enabled
    app.state.memory_retention_healthy = True
    app.state.assistant_asr = assistant_asr
    app.state.assistant_tts = assistant_tts
    app.state.assistant_journal = assistant_journal
    app.state.assistant_journal_healthy = True
    app.state.upload_runtime = upload_runtime
    app.state.upload_review_runtime = upload_review_runtime
    app.state.annotation_intake_enabled = annotation_intake_enabled
    app.state.update_root = update_root
    app.include_router(account_router)
    app.include_router(media_router)
    app.include_router(library_router)
    app.include_router(member_router)
    app.include_router(story_router)
    app.include_router(story_workspace_router)
    app.include_router(memory_router)
    app.include_router(memory_edition_router)
    app.include_router(memory_community_router)
    app.include_router(people_router)
    app.include_router(tag_router)
    app.include_router(album_router)
    app.include_router(ui_router)
    app.include_router(discovery_router)
    app.include_router(assistant_router)
    app.include_router(upload_router)
    app.include_router(upload_review_router)
    app.include_router(annotation_router)
    app.include_router(duplicate_router)
    app.include_router(caption_router)
    app.include_router(organization_router)
    app.include_router(updates_router)
    app.add_middleware(ClosedBoundary, routes=app.routes)
    return app


app = create_app()
