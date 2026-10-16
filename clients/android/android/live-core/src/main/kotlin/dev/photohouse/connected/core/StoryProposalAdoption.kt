package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import java.util.Collections
import java.util.UUID

/** Immutable input for a user's unsaved saved-story edit. */
data class StoryProposalAdoptionDraft internal constructor(
    val storyId: String,
    val libraryId: String,
    val revision: Long,
    val jobId: String,
    val jobKind: String,
    val selectionRevision: String,
    /** Null means keep the current title. */
    val title: String?,
    val chapters: List<StoryProposalAdoptionChapter>,
    val questions: List<String>,
)

data class StoryProposalAdoptionChapter internal constructor(
    val id: String,
    val narration: String,
    val sourceIds: List<String>,
)

/**
 * Converts a ready, review-required story proposal into detached wording for a saved-story edit.
 * A citation may only refer to evidence or a contribution already linked to that same chapter.
 */
fun storyProposalAdoptionDraft(
    story: SavedMemoryStory,
    references: SavedMemoryStoryContributionReferences,
    job: MemoryJob,
    selectedChapterIds: List<String>,
    adoptTitle: Boolean,
): StoryProposalAdoptionDraft? = runCatching {
    require(story.canEdit && story.revision > 0 && story.revision < Long.MAX_VALUE)
    require(canonicalUuid(story.id))
    require(story.libraryId.isNotBlank())
    require(story.selectionRevision.matches(Regex("[0-9a-fA-F]{64}")))

    val chapterIds = story.chapters.map { it.id }
    require(chapterIds.isNotEmpty() && chapterIds.size <= MAX_CHAPTERS)
    require(chapterIds.distinct().size == chapterIds.size)
    require(chapterIds.withIndex().all { (index, id) -> id == "chapter-${index + 1}" })
    require(references.id == story.id && references.libraryId == story.libraryId && references.revision == story.revision)
    require(references.chapters.map { it.chapterId } == chapterIds)
    require(references.chapters.all { refs ->
        refs.contributionIds.size <= MAX_CONTRIBUTIONS_PER_CHAPTER &&
            refs.contributionIds.distinct().size == refs.contributionIds.size &&
            refs.contributionIds.all(::canonicalUuid)
    })

    require(selectedChapterIds.isNotEmpty() && selectedChapterIds.distinct().size == selectedChapterIds.size)
    require(selectedChapterIds.all { it in chapterIds })
    require(canonicalUuid(job.id) && job.state == "ready" && job.needsReview && job.baseRevision == story.revision)
    require(job.kind == "narrative" || job.kind == "chat")
    val rawNarrative = when (job.kind) {
        "narrative" -> job.result ?: throw IllegalArgumentException()
        "chat" -> {
            val result = job.result ?: throw IllegalArgumentException()
            require(result.keys == CHAT_RESULT_KEYS)
            require(int(result["version"], 1, 1) == 1)
            require(string(result["kind"], 16) == "proposal")
            string(result["reply"], 4000, allowNewline = true)
            strings(result["source_ids"], MAX_SOURCES, 128)
            strings(result["questions"], 3, 512, allowNewline = true)
            result["proposal"] as? JsonObject ?: throw IllegalArgumentException()
        }
        else -> throw IllegalArgumentException()
    }
    val narrative = decodeNarrative(rawNarrative)
    require(narrative.chapters.map { it.id } == chapterIds)

    val title = if (adoptTitle) {
        val candidate = narrative.title
        require(candidate.isNotBlank() && candidate.none { it == '\n' || it == '\r' || it == '\u2028' || it == '\u2029' || it.isISOControl() })
        require(candidate.codePointCount(0, candidate.length) <= MAX_TITLE_CODE_POINTS)
        require(ProtectedMemoryCommunityWire.strictUtf8(candidate).size <= MAX_ADOPTED_TITLE_BYTES)
        candidate
    } else null

    val selected = selectedChapterIds.toSet()
    val byId = story.chapters.associateBy { it.id }
    val refsById = references.chapters.associateBy { it.chapterId }
    val adoptedChapters = narrative.chapters.filter { it.id in selected }.map { proposed ->
        val current = byId.getValue(proposed.id)
        val contributionIds = refsById.getValue(proposed.id).contributionIds.map { "contribution-$it" }.toSet()
        val allowedSources = current.evidenceIds.toSet() + contributionIds + "editorial-${story.id}-${current.id}"
        require(proposed.sourceIds.all { it in allowedSources })
        StoryProposalAdoptionChapter(proposed.id, proposed.narration, immutable(proposed.sourceIds))
    }
    require(adoptedChapters.isNotEmpty())
    StoryProposalAdoptionDraft(
        story.id,
        story.libraryId,
        story.revision,
        job.id,
        job.kind,
        story.selectionRevision,
        title,
        immutable(adoptedChapters),
        immutable(narrative.questions),
    )
}.getOrNull()

private data class DecodedNarrative(
    val title: String,
    val chapters: List<DecodedChapter>,
    val questions: List<String>,
)

private data class DecodedChapter(val id: String, val narration: String, val sourceIds: List<String>)

private fun decodeNarrative(value: JsonObject): DecodedNarrative {
    require(value.keys == NARRATIVE_KEYS)
    require(int(value["version"], 1, 1) == 1)
    require(boolean(value["needs_review"]))
    val title = string(value["title"], 512)
    val rawChapters = value["chapters"] as? JsonArray ?: throw IllegalArgumentException()
    require(rawChapters.isNotEmpty() && rawChapters.size <= MAX_CHAPTERS)
    val chapters = rawChapters.map { element ->
        val chapter = element as? JsonObject ?: throw IllegalArgumentException()
        require(chapter.keys == CHAPTER_KEYS)
        DecodedChapter(
            string(chapter["id"], 128),
            string(chapter["narration"], 6000, allowBlank = true, allowNewline = true),
            strings(chapter["source_ids"], MAX_SOURCES, 128),
        )
    }
    require(chapters.map { it.id }.distinct().size == chapters.size)
    val questions = strings(value["questions"], 6, 512, allowNewline = true)
    return DecodedNarrative(title, chapters, questions)
}

private fun strings(value: JsonElement?, maxCount: Int, maxBytes: Int, allowNewline: Boolean = false): List<String> {
    val array = value as? JsonArray ?: throw IllegalArgumentException()
    require(array.size <= maxCount)
    val values = array.map { string(it, maxBytes, allowNewline = allowNewline) }
    require(values.distinct().size == values.size)
    return values
}

private fun string(value: JsonElement?, maxBytes: Int, allowBlank: Boolean = false, allowNewline: Boolean = false): String {
    val primitive = value as? JsonPrimitive ?: throw IllegalArgumentException()
    require(primitive.isString)
    val content = primitive.content
    require(content.isNotBlank() || allowBlank)
    require(ProtectedMemoryCommunityWire.strictUtf8(content).size <= maxBytes)
    require(content.none { it == '\u0000' || it.isISOControl() && !(allowNewline && it in "\n\t") })
    return content
}

private fun int(value: JsonElement?, min: Int, max: Int): Int {
    val primitive = value as? JsonPrimitive ?: throw IllegalArgumentException()
    require(!primitive.isString && primitive.content.matches(Regex("0|[1-9][0-9]*")))
    return primitive.content.toIntOrNull()?.takeIf { it in min..max } ?: throw IllegalArgumentException()
}

private fun boolean(value: JsonElement?): Boolean {
    val primitive = value as? JsonPrimitive ?: throw IllegalArgumentException()
    require(!primitive.isString)
    return primitive.booleanOrNull ?: throw IllegalArgumentException()
}

private fun canonicalUuid(value: String): Boolean = runCatching { UUID.fromString(value).toString() == value }.getOrDefault(false)

private fun <T> immutable(values: Collection<T>): List<T> =
    Collections.unmodifiableList(ArrayList(values))

private const val MAX_CHAPTERS = 6
private const val MAX_CONTRIBUTIONS_PER_CHAPTER = 12
private const val MAX_SOURCES = 96
private const val MAX_TITLE_CODE_POINTS = 160
private const val MAX_ADOPTED_TITLE_BYTES = 640
private val NARRATIVE_KEYS = setOf("version", "title", "chapters", "questions", "needs_review")
private val CHAPTER_KEYS = setOf("id", "narration", "source_ids")
private val CHAT_RESULT_KEYS = setOf("version", "kind", "reply", "source_ids", "questions", "proposal")
