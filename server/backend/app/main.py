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
from .access.photo_stack_transport import router as photo_stack_router
from .access.members import router as member_router
from .access.stories import router as story_router
from .access.story_workspace import router as story_workspace_router
from .access.selected_story_transport import router as selected_story_router
from .access.memory_group_transport import router as memory_group_router, GroupVectorConfiguration
from .access.memory_stories import router as memory_router
from .access.memory_transport import router as memory_community_router
from .access.memory_book_edition_transport import router as memory_edition_router
from .access.people import router as people_router
from .access.people_review import router as people_review_router
from .access.tags import router as tag_router
from .access.albums import router as album_router
from .access.boundary import ClosedBoundary
from .access.discovery_transport import router as discovery_router
from .access.semantic_search_transport import router as semantic_search_router
from .access.semantic_search import SemanticSearchRuntime
from .access.assistant import router as assistant_router
from .access.assistant_workspace_transport import router as assistant_workspace_router
from .access.upload_transport import router as upload_router
from .access.upload_review import router as upload_review_router
from .access.annotations import router as annotation_router
from .access.duplicates import router as duplicate_router
from .access.captions import router as caption_router
from .access.library_organization import router as organization_router
from .routers.ui import router as ui_router
from .updates import router as updates_router


def create_app(*, access_runtime=None, media_runtime=None, discovery_runtime=None,
               upload_runtime=None, upload_review_runtime=None, semantic_search_runtime=None,
               annotation_intake_enabled=False, assistant_enabled=False,
               memory_collaboration_enabled=False, memory_originals_enabled=False,
               memory_generation_enabled=False, memory_editorial_enabled=False,
               memory_editions_enabled=False, family_note_erasure_enabled=False,
               assistant_asr=None, assistant_tts=None, assistant_journal=None,
               assistant_workspace_store=None, assistant_kinship_provider=None, assistant_intent_planner=None, update_root=None,
               story_title_suggester=None, memory_groups_enabled=False, memory_group_vectors=None,
               assistant_reply_speech_enabled=False, assistant_saved_memory_cards_enabled=False,
               assistant_semantic_search_enabled=False,
               assistant_agent_runtime=None, assistant_agent_budget=None,
               selected_story_provider=None, selected_story_drafts_enabled=False):
    if semantic_search_runtime is not None and (
            type(semantic_search_runtime) is not SemanticSearchRuntime or
            semantic_search_runtime.access is not access_runtime or
            semantic_search_runtime.discovery is not discovery_runtime):
        raise ValueError('Explicit matching semantic search runtime required')
    if (type(assistant_semantic_search_enabled) is not bool or
            (assistant_semantic_search_enabled and
             (not assistant_enabled or semantic_search_runtime is None))):
        raise ValueError('Explicit assistant and semantic runtime opt-in required')
    if type(memory_groups_enabled) is not bool:
        raise ValueError('Explicit memory group opt-in required')
    if memory_group_vectors is not None and (not memory_groups_enabled or
            type(memory_group_vectors) is not GroupVectorConfiguration):
        raise ValueError('Explicit enabled memory group vector configuration required')
    if story_title_suggester is not None and not callable(getattr(story_title_suggester, 'suggest', None)):
        raise ValueError('Explicit story title adapter required')
    if type(annotation_intake_enabled) is not bool:
        raise ValueError('Explicit annotation intake opt-in required')
    if type(assistant_enabled) is not bool:
        raise ValueError('Explicit assistant opt-in required')
    if assistant_intent_planner is not None and (not assistant_enabled or
            not callable(getattr(assistant_intent_planner, 'propose', None))):
        raise ValueError('Explicit enabled assistant intent planner required')
    if type(assistant_reply_speech_enabled) is not bool:
        raise ValueError('Explicit private reply speech opt-in required')
    if type(assistant_saved_memory_cards_enabled) is not bool:
        raise ValueError('Explicit saved-memory cards opt-in required')
    from .access.assistant_workspace_store import AssistantWorkspaceStore
    if assistant_workspace_store is not None and (
            not assistant_enabled or type(assistant_workspace_store) is not AssistantWorkspaceStore):
        raise ValueError('Explicit enabled assistant workspace store required')
    if assistant_kinship_provider is not None and (
            not assistant_enabled or not callable(getattr(assistant_kinship_provider, 'get', None))):
        raise ValueError('Explicit enabled assistant kinship provider required')
    agent_supervisor = None
    if assistant_agent_runtime is not None:
        if (not assistant_enabled or assistant_workspace_store is None or
                discovery_runtime is None or access_runtime is None or
                discovery_runtime.access is not access_runtime):
            raise ValueError('Agent requires matching assistant, workspace and discovery')
        from .access.assistant_agent import AgentSupervisor
        agent_supervisor = AgentSupervisor(assistant_agent_runtime, budget=assistant_agent_budget)
    elif assistant_agent_budget is not None:
        raise ValueError('Agent budget requires an injected runtime')
    if assistant_saved_memory_cards_enabled and (not assistant_enabled or
            not memory_collaboration_enabled or
            type(assistant_workspace_store) is not AssistantWorkspaceStore):
        raise ValueError('Saved-memory cards require assistant, workspace and collaboration')
    if assistant_reply_speech_enabled:
        from .access.assistant_journal import Journal
        from .access.assistant_speech import LocalAssistantTts
        if (not assistant_enabled or not isinstance(assistant_tts, LocalAssistantTts)
                or type(assistant_journal) is not Journal
                or type(assistant_workspace_store) is not AssistantWorkspaceStore):
            raise ValueError('Private reply speech requires assistant TTS, journal and workspace')
    if type(family_note_erasure_enabled) is not bool:
        raise ValueError('Explicit family note erasure opt-in required')
    if any(type(flag) is not bool for flag in (memory_collaboration_enabled,
            memory_originals_enabled, memory_generation_enabled, memory_editorial_enabled,
            memory_editions_enabled)):
        raise ValueError('Explicit memory opt-in required')
    if (memory_originals_enabled or memory_generation_enabled or memory_editorial_enabled or
            memory_editions_enabled) and not memory_collaboration_enabled:
        raise ValueError('Memory contributions/generation require collaboration opt-in')
    if (type(selected_story_drafts_enabled) is not bool or
            (selected_story_drafts_enabled and selected_story_provider is None)):
        raise ValueError('Explicit selected-story API opt-in and provider required')
    selected_story_lifecycle = None
    if selected_story_provider is not None:
        if not memory_collaboration_enabled:
            raise ValueError('Selected-story provider requires collaboration opt-in')
        from .access.selected_story_lifecycle import SelectedStoryLifecycle
        selected_story_lifecycle = SelectedStoryLifecycle(access_runtime, selected_story_provider,
            memory_groups_enabled=memory_groups_enabled)
    @asynccontextmanager
    async def lifespan(app):
        maintenance = None
        memory_maintenance = None
        workspace_maintenance = None
        journal = app.state.assistant_journal
        workspace = app.state.assistant_workspace_store
        try:
            if app.state.selected_story_lifecycle is not None:
                app.state.selected_story_lifecycle.start()
                app.state.selected_story_operations = app.state.selected_story_lifecycle.operations
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
            if workspace is not None:
                try:
                    await run_in_threadpool(workspace.prune)
                    app.state.assistant_workspace_healthy = True
                except Exception:
                    app.state.assistant_workspace_healthy = False
                async def prune_workspace():
                    while True:
                        await asyncio.sleep(3600)
                        try:
                            await run_in_threadpool(workspace.prune)
                            app.state.assistant_workspace_healthy = True
                        except Exception:
                            app.state.assistant_workspace_healthy = False
                workspace_maintenance = asyncio.create_task(prune_workspace())
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
            yield
        finally:
            try:
                if app.state.selected_story_lifecycle is not None:
                    await app.state.selected_story_lifecycle.close()
            finally:
                if app.state.assistant_agent_supervisor is not None:
                    await app.state.assistant_agent_supervisor.close()
                if maintenance is not None:
                    maintenance.cancel()
                    with suppress(asyncio.CancelledError):
                        await maintenance
                if memory_maintenance is not None:
                    memory_maintenance.cancel()
                    with suppress(asyncio.CancelledError):
                        await memory_maintenance
                if workspace_maintenance is not None:
                    workspace_maintenance.cancel()
                    with suppress(asyncio.CancelledError):
                        await workspace_maintenance
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None,
                  redirect_slashes=False, lifespan=lifespan)
    app.state.access_runtime = access_runtime
    app.state.selected_story_drafts_enabled = selected_story_drafts_enabled
    app.state.selected_story_lifecycle = selected_story_lifecycle
    app.state.selected_story_operations = None
    app.state.inference_admission = (selected_story_lifecycle.admission
                                     if selected_story_lifecycle is not None else None)
    # No provider discovery or live configuration fallback. Qualification and
    # runtime wiring are separate from mounting the protected, default-off route.
    from threading import Lock
    app.state.story_title_suggester = story_title_suggester
    app.state.story_title_lock = Lock()
    app.state.media_runtime = media_runtime
    app.state.discovery_runtime = discovery_runtime
    app.state.semantic_search_runtime = semantic_search_runtime
    app.state.assistant_semantic_search_enabled = assistant_semantic_search_enabled
    app.state.assistant_enabled = assistant_enabled
    app.state.memory_groups_enabled = memory_groups_enabled
    app.state.memory_group_vectors = memory_group_vectors
    app.state.memory_collaboration_enabled = memory_collaboration_enabled
    app.state.memory_originals_enabled = memory_originals_enabled
    app.state.memory_generation_enabled = memory_generation_enabled
    app.state.memory_editorial_enabled = memory_editorial_enabled
    app.state.memory_editions_enabled = memory_editions_enabled
    app.state.family_note_erasure_enabled = family_note_erasure_enabled
    app.state.memory_retention_healthy = True
    app.state.assistant_asr = assistant_asr
    app.state.assistant_tts = assistant_tts
    app.state.assistant_journal = assistant_journal
    app.state.assistant_reply_speech_enabled = assistant_reply_speech_enabled
    app.state.assistant_saved_memory_cards_enabled = assistant_saved_memory_cards_enabled
    app.state.assistant_journal_healthy = True
    app.state.assistant_workspace_store = assistant_workspace_store
    app.state.assistant_kinship_provider = assistant_kinship_provider
    app.state.assistant_intent_planner = assistant_intent_planner
    app.state.assistant_workspace_healthy = assistant_workspace_store is not None
    app.state.assistant_agent_supervisor = agent_supervisor
    app.state.upload_runtime = upload_runtime
    app.state.upload_review_runtime = upload_review_runtime
    app.state.annotation_intake_enabled = annotation_intake_enabled
    app.state.update_root = update_root
    app.include_router(account_router)
    app.include_router(media_router)
    app.include_router(library_router)
    app.include_router(photo_stack_router)
    app.include_router(member_router)
    app.include_router(story_router)
    app.include_router(story_workspace_router)
    app.include_router(selected_story_router)
    app.include_router(memory_group_router)
    app.include_router(memory_router)
    app.include_router(memory_edition_router)
    app.include_router(memory_community_router)
    app.include_router(people_router)
    app.include_router(people_review_router)
    app.include_router(tag_router)
    app.include_router(album_router)
    app.include_router(ui_router)
    app.include_router(discovery_router)
    if semantic_search_runtime is not None:
        app.include_router(semantic_search_router)
    app.include_router(assistant_router)
    app.include_router(assistant_workspace_router)
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
