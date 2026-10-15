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
    suspend fun storySourceCapabilities(token: Bearer, library: String): ByteArray =
        throw ApiFailure(FailureKind.HTTP, 404)
    suspend fun storyTitles(token: Bearer, library: String, json: String, sourceReview: Boolean): ByteArray =
        if (sourceReview) throw ApiFailure(FailureKind.HTTP, 403) else storyTitles(token, library, json)
    suspend fun createGroupedStory(token: Bearer, library: String, json: String, sourceReview: Boolean): ByteArray =
        if (sourceReview) throw ApiFailure(FailureKind.HTTP, 403) else createGroupedStory(token, library, json)
    suspend fun updateGroupedStory(
        token: Bearer, library: String, storyId: String, json: String,
        sourceReview: Boolean, contributionReferences: Boolean,
    ): ByteArray = throw ApiFailure(FailureKind.HTTP, 404)
    /** Optional v1 same-recorded-day candidate lookup; legacy adapters remain unsupported. */
    suspend fun relatedStoryMedia(token: Bearer, library: String, json: String): ByteArray =
        throw ApiFailure(FailureKind.INVALID_INPUT)
}

/** Frozen, process-only body. A retry sends these exact bytes with the same mutation ID. */
class PendingGroupedStorySave internal constructor(
    internal val binding: MemoryCommunityBinding,
    internal val body: String,
    assetIds: List<String>,
    val sourceReview: Boolean = false,
    val targetStoryId: String? = null,
    val baseRevision: Long = 0,
    val contributionReferences: Boolean = false,
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

    suspend fun sourceCapabilities(editorCurrent: () -> Boolean): ProtectedStoryWorkspaceSourceCapabilities? =
        scoped(editorCurrent = editorCurrent) { bound ->
            try { owned({ api.storySourceCapabilities(bound.token, bound.libraryId) }, ProtectedStoryWorkspaceWire::decodeSourceCapabilities) }
            catch (failure: ApiFailure) {
                if (failure.status in setOf(400, 404, 503)) null else throw failure
            }
        }

    suspend fun suggestTitles(
        draft: ProtectedStoryWorkspaceDraft, sourceReview: Boolean = false, editorCurrent: () -> Boolean,
    ): List<ProtectedStoryWorkspaceTitle> = scoped(editorCurrent = editorCurrent) { bound ->
        if (draft.libraryId != bound.libraryId) throw ApiFailure(FailureKind.INVALID_INPUT)
        val assetIds = draft.items.map { it.asset.id }
        val evidenceByAsset = draft.items.associate { item -> item.asset.id to item.evidence.map { it.id }.toSet() }
        val chapterInputs = draft.chapters.map { chapter ->
            ProtectedStoryWorkspaceChapterInput(chapter.id, chapter.narration,
                if (sourceReview) chapter.evidenceIds else null,
                if (sourceReview) chapter.assetIds else null)
        }
        if (sourceReview) {
            val fallbackLayout = assetIds.chunked(4)
            if (chapterInputs.any { it.assetIds == null } && chapterInputs.size != fallbackLayout.size)
                throw ApiFailure(FailureKind.INVALID_INPUT)
            chapterInputs.forEachIndexed { index, chapter ->
                val chapterAssets = chapter.assetIds ?: fallbackLayout[index]
                val eligibleEvidence = chapterAssets.flatMap { evidenceByAsset[it].orEmpty() }.toSet()
                if (chapter.evidenceIds.orEmpty().any { it !in eligibleEvidence })
                    throw ApiFailure(FailureKind.INVALID_INPUT)
            }
        }
        val body = ProtectedStoryWorkspaceWire.encodeTitleRequest(assetIds,
            draft.theme, draft.language, draft.selectionRevision, chapterInputs,
            if (sourceReview) ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1 else null)
        owned({ api.storyTitles(bound.token, bound.libraryId, body, sourceReview) }) {
            ProtectedStoryWorkspaceWire.decodeTitles(it, draft, if (sourceReview) ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1 else null)
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
        mutationId: String, reviewed: Boolean, sourceReview: Boolean = false, editorCurrent: () -> Boolean,
    ): PendingGroupedStorySave {
        val bound = binding()
        current(bound, editorCurrent)
        if (!reviewed || draft.libraryId != bound.libraryId) throw ApiFailure(FailureKind.INVALID_INPUT)
        return PendingGroupedStorySave(bound,
            ProtectedStoryWorkspaceCreateWire.encode(draft, title, chapters, mutationId,
                if (sourceReview) ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1 else null),
            draft.items.map { it.asset.id }, sourceReview)
    }

    /** Freeze a full edit against the exact saved revision and complete contribution-link map. */
    fun freezeUpdate(
        story: SavedMemoryStory,
        references: SavedMemoryStoryContributionReferences,
        title: String,
        chapters: List<SavedMemoryStoryChapter>,
        mutationId: String,
        reviewed: Boolean,
        sourceReview: Boolean,
        sourcePolicy: String?,
        editorCurrent: () -> Boolean,
    ): PendingGroupedStorySave {
        val bound = binding()
        current(bound, editorCurrent)
        val expectedChapterIds = story.chapters.map { it.id }
        val referenceChapters = references.chapters.map { it.copy(contributionIds = it.contributionIds.toList()) }
        if (!reviewed || !story.canEdit || story.libraryId != bound.libraryId || story.revision <= 0 ||
            story.revision >= Long.MAX_VALUE ||
            story.id != runCatching { java.util.UUID.fromString(story.id).toString() }.getOrNull() ||
            references.id != story.id || references.libraryId != story.libraryId || references.revision != story.revision ||
            referenceChapters.map { it.chapterId } != expectedChapterIds || expectedChapterIds.size !in 1..6 ||
            expectedChapterIds.withIndex().any { (index, id) -> id != "chapter-${index + 1}" } ||
            referenceChapters.any { group -> group.contributionIds.size > 12 ||
                group.contributionIds.distinct().size != group.contributionIds.size ||
                group.contributionIds.any { id -> runCatching { java.util.UUID.fromString(id).toString() == id }.getOrDefault(false).not() } })
            throw ApiFailure(FailureKind.INVALID_INPUT)
        val chosenPolicy = when {
            story.sourcePolicy != null -> story.sourcePolicy.also {
                if (!sourceReview || sourcePolicy != it) throw ApiFailure(FailureKind.INVALID_INPUT)
            }
            sourceReview -> sourcePolicy?.takeIf { it == ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1 }
                ?: throw ApiFailure(FailureKind.INVALID_INPUT)
            else -> sourcePolicy?.let { throw ApiFailure(FailureKind.INVALID_INPUT) }
        }
        val draft = ProtectedStoryWorkspaceDraft(story.libraryId, story.selectionRevision, story.title,
            story.theme, story.language, story.items, story.chapters, story.questions)
        val body = ProtectedStoryWorkspaceCreateWire.encode(draft, title, chapters, mutationId,
            chosenPolicy, revision = story.revision, contributionReferences = referenceChapters)
        return PendingGroupedStorySave(bound, body, story.items.map { it.asset.id }, sourceReview,
            targetStoryId = story.id, baseRevision = story.revision, contributionReferences = true)
    }

    suspend fun save(pending: PendingGroupedStorySave, editorCurrent: () -> Boolean): SavedMemoryStory =
        scoped(pending.binding, editorCurrent) { bound ->
            val expectedId = pending.targetStoryId
            val minimumUpdateRevision = if (expectedId != null) {
                if (pending.baseRevision !in 1 until Long.MAX_VALUE ||
                    expectedId != runCatching { java.util.UUID.fromString(expectedId).toString() }.getOrNull())
                    throw ApiFailure(FailureKind.INVALID_INPUT)
                pending.baseRevision + 1
            } else null
            val saved = owned({
                if (expectedId == null) api.createGroupedStory(bound.token, bound.libraryId, pending.body, pending.sourceReview)
                else api.updateGroupedStory(bound.token, bound.libraryId, expectedId, pending.body,
                    pending.sourceReview, pending.contributionReferences)
            }) {
                if (expectedId == null) {
                    ProtectedMemoryStoriesWire.decode(it, bound.libraryId, pending.assetIds,
                        sourceReview = pending.sourceReview)
                } else {
                    val current = ProtectedMemoryStoriesWire.detail(it, bound.libraryId, expectedId,
                        minimumUpdateRevision!!, sourceReview = pending.sourceReview)
                    if (!current.canEdit || pending.sourceReview &&
                        current.sourcePolicy != ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1 ||
                        current.revision == minimumUpdateRevision && current.items.map { item -> item.asset.id } != pending.assetIds)
                        throw ApiFailure(FailureKind.INVALID_RESPONSE)
                    current
                }
            }
            saved
        }
}
