package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import java.util.Collections

/** Optional protected transport. No adapter means no creation controls. */
interface StoryWorkspaceApi {
    suspend fun storyPreview(token: Bearer, library: String, json: String): ByteArray
    suspend fun storyTitleCapabilities(token: Bearer, library: String): ByteArray
    suspend fun storyTitles(token: Bearer, library: String, json: String): ByteArray
    suspend fun createGroupedStory(token: Bearer, library: String, json: String): ByteArray
    /** Optional v1 same-recorded-day candidate lookup; legacy adapters remain unsupported. */
    suspend fun relatedStoryMedia(token: Bearer, library: String, json: String): ByteArray =
        throw ApiFailure(FailureKind.INVALID_INPUT)
}

/** Frozen, process-only body. A retry sends these exact bytes with the same mutation ID. */
class PendingGroupedStorySave internal constructor(
    internal val binding: MemoryCommunityBinding,
    internal val body: String,
    assetIds: List<String>,
) {
    val assetIds: List<String> = Collections.unmodifiableList(ArrayList(assetIds))
    override fun toString() = "PendingGroupedStorySave(content omitted)"
}

class StoryWorkspaceRepository(
    private val api: StoryWorkspaceApi,
    private val currentBinding: () -> MemoryCommunityBinding?,
    private val onDenied: () -> Unit = {},
) {
    private fun current(expected: MemoryCommunityBinding, editorCurrent: () -> Boolean) {
        val now = currentBinding()
        if (now == null || now.token !== expected.token || now.libraryId != expected.libraryId ||
            now.generation != expected.generation || !editorCurrent())
            throw CancellationException("Protected story scope changed")
    }

    private fun binding(): MemoryCommunityBinding =
        (currentBinding() ?: throw CancellationException("Protected scope ended")).also {
            if (!PhoneDiscoveryWire.validLibrary(it.libraryId) || it.generation < 0)
                throw ApiFailure(FailureKind.INVALID_INPUT)
        }

    private suspend fun <T> scoped(
        expected: MemoryCommunityBinding = binding(), editorCurrent: () -> Boolean,
        action: suspend (MemoryCommunityBinding) -> T,
    ): T {
        current(expected, editorCurrent)
        return try {
            val result = action(expected)
            currentCoroutineContext().ensureActive()
            current(expected, editorCurrent)
            result
        } catch (failure: ApiFailure) {
            currentCoroutineContext().ensureActive()
            current(expected, editorCurrent)
            if (failure.status in setOf(401, 403)) onDenied()
            throw failure
        } catch (_: IllegalArgumentException) {
            current(expected, editorCurrent)
            throw ApiFailure(FailureKind.INVALID_INPUT)
        }
    }

    private suspend fun <T> owned(call: suspend () -> ByteArray, decode: (ByteArray) -> T): T {
        val bytes = call()
        return try { decode(bytes) } finally { bytes.fill(0) }
    }

    suspend fun preview(
        assetIds: List<String>, theme: String, language: String, title: String,
        editorCurrent: () -> Boolean,
    ): ProtectedStoryWorkspaceDraft {
        val ids = assetIds.toList()
        val body = ProtectedStoryWorkspaceWire.encodePreviewRequest(ids, theme, language, title)
        return scoped(editorCurrent = editorCurrent) { bound ->
            owned({ api.storyPreview(bound.token, bound.libraryId, body) }) {
                ProtectedStoryWorkspaceWire.decodePreview(it, bound.libraryId, ids, theme, language)
            }
        }
    }

    suspend fun titleCapabilities(editorCurrent: () -> Boolean): ProtectedStoryWorkspaceTitleCapabilities =
        scoped(editorCurrent = editorCurrent) { bound ->
            try {
                owned({ api.storyTitleCapabilities(bound.token, bound.libraryId) },
                    ProtectedStoryWorkspaceWire::decodeTitleCapabilities)
            } catch (failure: ApiFailure) {
                if (failure.status in setOf(404, 503)) ProtectedStoryWorkspaceTitleCapabilities(false, 3)
                else throw failure
            }
        }

    suspend fun suggestTitles(
        draft: ProtectedStoryWorkspaceDraft, editorCurrent: () -> Boolean,
    ): List<ProtectedStoryWorkspaceTitle> = scoped(editorCurrent = editorCurrent) { bound ->
        if (draft.libraryId != bound.libraryId) throw ApiFailure(FailureKind.INVALID_INPUT)
        val body = ProtectedStoryWorkspaceWire.encodeTitleRequest(draft.items.map { it.asset.id },
            draft.theme, draft.language, draft.selectionRevision,
            draft.chapters.map { ProtectedStoryWorkspaceChapterInput(it.id, it.narration) })
        owned({ api.storyTitles(bound.token, bound.libraryId, body) }) {
            ProtectedStoryWorkspaceWire.decodeTitles(it, draft)
        }
    }

    suspend fun relatedMedia(
        seedAssetIds: List<String>, beforeId: String?, editorCurrent: () -> Boolean,
    ): StoryRelatedMediaPage {
        val ids = seedAssetIds.toList()
        val body = StoryRelatedMediaWire.encodeRequest(ids, beforeId)
        return scoped(editorCurrent = editorCurrent) { bound ->
            owned({ api.relatedStoryMedia(bound.token, bound.libraryId, body) }) {
                StoryRelatedMediaWire.decode(it, bound.libraryId, ids, beforeId)
            }
        }
    }

    fun freeze(
        draft: ProtectedStoryWorkspaceDraft, title: String, chapters: List<SavedMemoryStoryChapter>,
        mutationId: String, reviewed: Boolean, editorCurrent: () -> Boolean,
    ): PendingGroupedStorySave {
        val bound = binding()
        current(bound, editorCurrent)
        if (!reviewed || draft.libraryId != bound.libraryId) throw ApiFailure(FailureKind.INVALID_INPUT)
        return PendingGroupedStorySave(bound,
            ProtectedStoryWorkspaceCreateWire.encode(draft, title, chapters, mutationId),
            draft.items.map { it.asset.id })
    }

    suspend fun save(pending: PendingGroupedStorySave, editorCurrent: () -> Boolean): SavedMemoryStory =
        scoped(pending.binding, editorCurrent) { bound ->
            owned({ api.createGroupedStory(bound.token, bound.libraryId, pending.body) }) {
                ProtectedMemoryStoriesWire.decode(it, bound.libraryId, pending.assetIds)
            }
        }
}
