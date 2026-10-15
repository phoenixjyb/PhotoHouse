package dev.photohouse.connected.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.Collections
import java.util.UUID

/**
 * Immutable create mutation for the protected story endpoint. All lists are copied and wrapped,
 * including the nested chapter lists, so edits to caller-owned input cannot change a retry body.
 */
class ProtectedStoryWorkspaceCreate private constructor(
    val selectionRevision: String,
    val title: String,
    val theme: String,
    val language: String,
    chapters: List<SavedMemoryStoryChapter>,
    val mutationId: UUID,
    val sourcePolicy: String? = null,
    val revision: Long = 0,
    contributionReferences: List<SavedMemoryChapterContributionReferences>? = null,
) {
    val chapters: List<SavedMemoryStoryChapter> = immutableChapters(chapters)
    val assetIds: List<String> = Collections.unmodifiableList(this.chapters.flatMap { it.assetIds })
    private val contributionRefsJson: String? = contributionReferences?.let { groups ->
        JsonArray(groups.map { group -> JsonObject(mapOf(
            "chapter_id" to JsonPrimitive(group.chapterId),
            "contribution_ids" to JsonArray(group.contributionIds.map(::JsonPrimitive)),
        )) }).toString()
    }

    /** Legacy requests retain eight fields; source-review requests add one policy field. */
    fun bodyJson(): String {
        val chapterJson = JsonArray(chapters.map { chapter -> JsonObject(mapOf(
            "id" to JsonPrimitive(chapter.id),
            "title" to JsonPrimitive(chapter.title),
            "narration" to JsonPrimitive(chapter.narration),
            "asset_ids" to JsonArray(chapter.assetIds.map(::JsonPrimitive)),
            "evidence_ids" to JsonArray(chapter.evidenceIds.map(::JsonPrimitive)),
        )) }).toString()
        return JsonObject(linkedMapOf(
            "title" to JsonPrimitive(title),
            "theme" to JsonPrimitive(theme),
            "language" to JsonPrimitive(language),
            "asset_ids" to JsonPrimitive(assetIds.joinToString(",")),
            "chapters" to JsonPrimitive(chapterJson),
            "selection_revision" to JsonPrimitive(selectionRevision),
            "revision" to JsonPrimitive(revision.toString()),
            "mutation_id" to JsonPrimitive(mutationId.toString()),
        ).apply {
            sourcePolicy?.let { put("source_policy", JsonPrimitive(it)) }
            contributionRefsJson?.let { put("contribution_refs", JsonPrimitive(it)) }
        }).toString()
    }

    override fun toString(): String =
        "ProtectedStoryWorkspaceCreate(selectionRevision=$selectionRevision, mutationId=$mutationId, content=[redacted])"

    companion object {
        internal fun create(
            selectionRevision: String,
            title: String,
            theme: String,
            language: String,
            chapters: List<SavedMemoryStoryChapter>,
            mutationId: UUID,
            sourcePolicy: String? = null,
            revision: Long = 0,
            contributionReferences: List<SavedMemoryChapterContributionReferences>? = null,
        ) = ProtectedStoryWorkspaceCreate(selectionRevision, title, theme, language, chapters, mutationId,
            sourcePolicy, revision, contributionReferences?.map { it.copy(contributionIds = ArrayList(it.contributionIds)) })

        private fun immutableChapters(chapters: List<SavedMemoryStoryChapter>): List<SavedMemoryStoryChapter> =
            Collections.unmodifiableList(chapters.map { chapter ->
                chapter.copy(
                    assetIds = Collections.unmodifiableList(ArrayList(chapter.assetIds)),
                    evidenceIds = Collections.unmodifiableList(ArrayList(chapter.evidenceIds)),
                )
            })
    }
}

/** Builds a create mutation from the current server draft and user-authored text edits. */
internal object ProtectedStoryWorkspaceCreateWire {
    private const val MAX_ASSETS = 24
    private const val MAX_CHAPTERS = 6
    private const val MAX_ASSETS_PER_CHAPTER = 4
    private const val MAX_EVIDENCE_PER_CHAPTER = 12

    fun encode(
        draft: ProtectedStoryWorkspaceDraft,
        title: String,
        chapters: List<SavedMemoryStoryChapter>,
        mutationId: String,
        sourcePolicy: String? = null,
        revision: Long = 0,
        contributionReferences: List<SavedMemoryChapterContributionReferences>? = null,
    ): String = guardedInput {
        input(PhoneDiscoveryWire.validLibrary(draft.libraryId))
        input(draft.selectionRevision.matches(Regex("[0-9a-f]{64}")))
        input(draft.theme in SAVED_MEMORY_STORY_THEMES && draft.language in setOf("zh", "en"))
        input(sourcePolicy == null || sourcePolicy == ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1)
        input(revision >= 0 && revision < Long.MAX_VALUE)
        input((contributionReferences == null) == (revision == 0L))
        val frozenReferences = contributionReferences?.map { it.copy(contributionIds = ArrayList(it.contributionIds)) }
        validateText(title, 160, 640, allowNewline = false, allowBlank = false)
        val uuid = runCatching { UUID.fromString(mutationId) }.getOrNull()
        input(uuid != null && uuid.toString() == mutationId)

        val selectedIds = draft.items.map { it.asset.id }
        validateAssetIds(selectedIds)
        input(draft.items.map { it.asset.id }.distinct().size == draft.items.size)
        input(draft.chapters.isNotEmpty() && draft.chapters.size <= MAX_CHAPTERS)
        input(draft.chapters.map { it.id } == (1..draft.chapters.size).map { "chapter-$it" })
        if (revision == 0L) {
            if (sourcePolicy == null) {
                // Legacy creates retain the deterministic preview grouping contract.
                input(draft.chapters.size == (selectedIds.size + MAX_ASSETS_PER_CHAPTER - 1) / MAX_ASSETS_PER_CHAPTER)
                input(draft.chapters.map { it.assetIds } == selectedIds.chunked(MAX_ASSETS_PER_CHAPTER))
            } else {
                // Explicitly reviewed new drafts may carry a user-arranged layout.
                input(draft.chapters.all { it.assetIds.size in 1..MAX_ASSETS_PER_CHAPTER })
                input(draft.chapters.flatMap { it.assetIds } == selectedIds)
            }
        } else {
            // Saved stories may have valid editorial groupings that differ from preview chunks.
            input(draft.chapters.all { it.assetIds.size in 1..MAX_ASSETS_PER_CHAPTER })
            input(draft.chapters.flatMap { it.assetIds } == selectedIds)
        }
        input(chapters.size == draft.chapters.size)
        input(chapters.map { it.id } == draft.chapters.map { it.id })
        frozenReferences?.let { groups ->
            val expected = draft.chapters.map { it.id }
            input(groups.size == expected.size && groups.map { it.chapterId } == expected)
            groups.forEach { group ->
                input(group.contributionIds.size <= 12 && group.contributionIds.distinct().size == group.contributionIds.size)
                group.contributionIds.forEach { ref ->
                    input(runCatching { UUID.fromString(ref).toString() == ref }.getOrDefault(false))
                }
            }
            val encoded = JsonArray(groups.map { group -> JsonObject(mapOf(
                "chapter_id" to JsonPrimitive(group.chapterId),
                "contribution_ids" to JsonArray(group.contributionIds.map(::JsonPrimitive)),
            )) }).toString()
            input(encoded.toByteArray(Charsets.UTF_8).size <= 16 * 1024)
        }

        val evidenceByAsset = draft.items.associate { item ->
            item.asset.id to item.evidence.map { it.id }.toSet()
        }
        val editedChapters = chapters.mapIndexed { index, edited ->
            val source = draft.chapters[index]
            input(edited.assetIds == source.assetIds)
            input(sourcePolicy != null || edited.evidenceIds == source.evidenceIds)
            validateText(edited.title, 160, 640, allowNewline = false, allowBlank = false)
            validateText(edited.narration, Int.MAX_VALUE, 6000, allowNewline = true, allowBlank = true)
            input(source.assetIds.isNotEmpty() && source.assetIds.size <= MAX_ASSETS_PER_CHAPTER)
            input(source.assetIds.distinct().size == source.assetIds.size)
            input(edited.evidenceIds.size <= MAX_EVIDENCE_PER_CHAPTER && edited.evidenceIds.distinct().size == edited.evidenceIds.size)
            val eligibleEvidence = source.assetIds.flatMap { evidenceByAsset[it].orEmpty() }.toSet()
            input(edited.evidenceIds.all { ref ->
                ref.matches(Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")) &&
                    ref in eligibleEvidence
            })
            input(source.title.codePointCount(0, source.title.length) <= 160)
            validateText(source.title, 160, 640, allowNewline = false, allowBlank = true)
            validateText(source.narration, Int.MAX_VALUE, 6000, allowNewline = true, allowBlank = true)
            SavedMemoryStoryChapter(source.id, edited.title, edited.narration, source.assetIds.toList(), edited.evidenceIds.toList())
        }
        input(editedChapters.flatMap { it.assetIds } == selectedIds)
        ProtectedStoryWorkspaceCreate.create(draft.selectionRevision, title, draft.theme, draft.language,
            editedChapters, uuid!!, sourcePolicy, revision, frozenReferences).bodyJson()
    }

    private fun validateAssetIds(ids: List<String>) {
        input(ids.size in 1..MAX_ASSETS && ids.distinct().size == ids.size)
        ids.forEach { id -> input(id.matches(Regex("[1-9][0-9]{0,18}")) && id.toLongOrNull()?.toString() == id) }
    }

    private fun validateText(value: String, maxCodePoints: Int, maxBytes: Int, allowNewline: Boolean, allowBlank: Boolean) {
        input(value.codePointCount(0, value.length) <= maxCodePoints)
        val bytes = try {
            Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value)).remaining()
        } catch (_: Exception) { throw IllegalArgumentException("Invalid story create input") }
        input(bytes <= maxBytes && value.none { it == '\u0000' || it.isISOControl() && !(allowNewline && it in "\n\t") })
        input(allowBlank || value.isNotBlank())
    }

    private fun input(ok: Boolean) { require(ok) { "Invalid story create input" } }

    private inline fun <T> guardedInput(block: () -> T): T = try { block() }
        catch (e: ApiFailure) { throw e }
        catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_INPUT) }
}
