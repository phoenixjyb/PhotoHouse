package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import dev.photohouse.protocol.DateHint
import kotlinx.serialization.json.*
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.UUID

internal val SAVED_MEMORY_STORY_THEMES = setOf("everyday", "trip", "growing_up", "birthday", "grandparents", "year_in_review")

data class MemoryStoryEvidence(
    val id: String, val source: String, val title: String, val text: String, val revision: Int? = null,
)
data class MemoryStoryAsset(val asset: Asset, val evidence: List<MemoryStoryEvidence>)
data class SavedMemoryStorySummary(
    val id: String, val title: String, val theme: String, val language: String, val revision: Long,
    val coverAssetId: String, val itemCount: Int, val chapterCount: Int, val updatedAt: Long, val canEdit: Boolean,
)
data class SavedMemoryStoryPage(
    val libraryId: String, val page: Int, val pageSize: Int, val hasMore: Boolean, val canCreate: Boolean,
    val items: List<SavedMemoryStorySummary>,
)
data class SavedMemoryStoryChapter(
    val id: String, val title: String, val narration: String, val assetIds: List<String>, val evidenceIds: List<String>,
)
data class SavedMemoryStory(
    val id: String, val libraryId: String, val revision: Long, val createdAt: Long, val updatedAt: Long, val canEdit: Boolean,
    val selectionRevision: String, val title: String, val theme: String, val language: String,
    val items: List<MemoryStoryAsset>, val chapters: List<SavedMemoryStoryChapter>, val questions: List<String>,
)
data class SavedMemoryChapterContributionReferences(val chapterId: String, val contributionIds: List<String>)
data class SavedMemoryStoryContributionReferences(
    val id: String, val libraryId: String, val revision: Long,
    val chapters: List<SavedMemoryChapterContributionReferences>,
)

/** Frozen, revision-bound save of chapter-to-original links. */
data class SavedMemoryStoryContributionReferencesMutation(
    val storyId: String, val revision: Long, val selectionRevision: String,
    val title: String, val theme: String, val language: String,
    val chapters: List<SavedMemoryStoryChapter>, val contributionRefsJson: String,
    val mutationId: String = UUID.randomUUID().toString(),
)

/** Exact, bounded reader contract for saved protected family story drafts. */
internal object ProtectedMemoryStoriesWire {
    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(value: Boolean) { if (!value) bad() }
    private fun obj(value: JsonElement): JsonObject = value as? JsonObject ?: bad()
    private fun str(value: JsonElement?, maxCodePoints: Int, allowNewline: Boolean = false): String {
        val p = value as? JsonPrimitive ?: bad(); check(p.isString)
        val s = p.content
        check(s.codePointCount(0, s.length) <= maxCodePoints && s.none { it == '\u0000' || it < ' ' && !(allowNewline && it in "\n\t") })
        try {
            Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(s))
        } catch (_: Exception) { bad() }
        return s
    }
    private fun field(o: JsonObject, name: String, max: Int, allowNewline: Boolean = false) = str(o[name], max, allowNewline)
    private fun bool(o: JsonObject, name: String): Boolean {
        val p = o[name] as? JsonPrimitive ?: bad(); check(!p.isString)
        return p.booleanOrNull ?: bad()
    }
    private fun integer(value: JsonElement?, max: Int = Int.MAX_VALUE): Int {
        val p = value as? JsonPrimitive ?: bad(); check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toIntOrNull()?.takeIf { it <= max } ?: bad()
    }
    private fun long(value: JsonElement?): Long {
        val p = value as? JsonPrimitive ?: bad(); check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toLongOrNull() ?: bad()
    }
    private fun decimalString(value: JsonElement?, positive: Boolean = false): Long {
        val s = str(value, 19); check(s.matches(Regex(if (positive) "[1-9][0-9]{0,18}" else "0|[1-9][0-9]{0,18}")))
        return s.toLongOrNull() ?: bad()
    }
    private fun exact(o: JsonObject, vararg keys: String) { check(o.keys == keys.toSet()) }
    private fun uuid(s: String) { check(runCatching { UUID.fromString(s).toString() == s }.getOrDefault(false)) }
    private fun assetId(s: String) { check(s.matches(Regex("[1-9][0-9]{0,18}")) && s.toLongOrNull() != null) }
    private fun array(o: JsonObject, name: String, max: Int): JsonArray = (o[name] as? JsonArray)?.also { check(it.size <= max) } ?: bad()
    private fun theme(s: String) { check(s in SAVED_MEMORY_STORY_THEMES) }

    fun page(bytes: ByteArray, library: String, page: Int): SavedMemoryStoryPage = guarded {
        val root = obj(DiscoveryJson.parse(bytes, HttpsPhotoHouseApi.MEMORY_STORIES_LIMIT, 500))
        exact(root, "library_id", "page", "page_size", "has_more", "can_create", "items")
        check(field(root, "library_id", 256) == library && integer(root["page"], 100000) == page)
        check(integer(root["page_size"], 8) == 8)
        val rows = array(root, "items", 8).map { summary(obj(it)) }
        check(rows.map { it.id }.distinct().size == rows.size)
        SavedMemoryStoryPage(library, page, 8, bool(root, "has_more"), bool(root, "can_create"), rows)
    }

    fun detail(bytes: ByteArray, library: String, expectedId: String, expectedRevision: Long): SavedMemoryStory = guarded {
        // The full bounded contract tops out below 900 JSON value nodes. DiscoveryJson
        // separately caps the total at 10,000 and this per-array guard at 1,200.
        val root = obj(DiscoveryJson.parse(bytes, HttpsPhotoHouseApi.MEMORY_STORIES_LIMIT, 1200))
        exact(root, "version", "library_id", "id", "revision", "created_at", "updated_at", "can_edit", "saved", "state", "generator", "needs_review", "selection_revision", "title", "theme", "language", "items", "chapters", "questions")
        check(integer(root["version"], 1) == 1)
        val actualLibrary = field(root, "library_id", 256); val id = field(root, "id", 36); val revision = decimalString(root["revision"], positive = true)
        check(actualLibrary == library && id == expectedId && revision >= expectedRevision)
        uuid(id)
        bool(root, "can_edit") // validated for contract integrity; this read-only slice never enables editing.
        check(bool(root, "saved") && field(root, "state", 16) == "draft" && field(root, "generator", 40) == "family_edited_outline" && bool(root, "needs_review"))
        val selectionRevision = field(root, "selection_revision", 64); check(selectionRevision.matches(Regex("[0-9a-fA-F]{64}")))
        val title = field(root, "title", 160); val theme = field(root, "theme", 32).also(::theme)
        val language = field(root, "language", 2); check(language in setOf("zh", "en"))
        val items = array(root, "items", 24).map { parseItem(obj(it), library) }
        check(items.isNotEmpty() && items.map { it.asset.id }.distinct().size == items.size)
        check(items.flatMap { it.evidence }.map { it.id }.distinct().size == items.sumOf { it.evidence.size })
        val chapters = array(root, "chapters", 6).mapIndexed { index, value -> parseChapter(obj(value), index + 1) }
        check(chapters.isNotEmpty() && chapters.map { it.id }.distinct().size == chapters.size)
        val ordered = chapters.flatMap { it.assetIds }
        check(ordered == items.map { it.asset.id })
        check(chapters.all { chapter ->
            val evidenceIds = items.filter { it.asset.id in chapter.assetIds }.flatMap { it.evidence }.map { it.id }.toSet()
            chapter.evidenceIds.all { it in evidenceIds }
        })
        val questions = array(root, "questions", 3).map { str(it, 500, allowNewline = true).also { q -> check(q.isNotBlank()) } }
        SavedMemoryStory(id, actualLibrary, revision, long(root["created_at"]), long(root["updated_at"]), bool(root, "can_edit"), selectionRevision,
            title, theme, language, items, chapters, questions).also { check(it.createdAt >= 0 && it.updatedAt >= 0) }
    }

    /** Strict create response entry point; the server may return a later revision after a mutation retry. */
    fun decode(bytes: ByteArray, library: String, expectedAssetIds: List<String>): SavedMemoryStory = guarded {
        check(bytes.size <= 256 * 1024)
        check(expectedAssetIds.size in 1..24 && expectedAssetIds.distinct().size == expectedAssetIds.size)
        expectedAssetIds.forEach { id ->
            check(id.matches(Regex("[1-9][0-9]{0,18}")) && id.toLongOrNull()?.toString() == id)
        }
        val root = obj(DiscoveryJson.parse(bytes, HttpsPhotoHouseApi.MEMORY_STORIES_LIMIT, 1200))
        // Read only the server-issued identity here; detail() applies the unchanged exact v1 shape,
        // field, scope, source-reference, and saved-reader validation to the complete response.
        val id = field(root, "id", 36).also(::uuid)
        val revision = decimalString(root["revision"], positive = true)
        val story = detail(bytes, library, id, 1)
        check(story.revision == revision && story.items.map { it.asset.id } == expectedAssetIds)
        story
    }

    /** Additive a0 sidecar; the original saved-story v1 detail decoder remains exact and unchanged. */
    fun contributionReferences(
        bytes: ByteArray, library: String, expectedId: String, expectedRevision: Long,
        expectedChapterIds: List<String>,
    ): SavedMemoryStoryContributionReferences = guarded {
        check(expectedChapterIds.size in 1..6 && expectedChapterIds.distinct().size == expectedChapterIds.size &&
            expectedChapterIds.withIndex().all { (index, id) -> id == "chapter-${index + 1}" })
        val root = obj(DiscoveryJson.parse(bytes, 16 * 1024, 64))
        exact(root, "version", "id", "library_id", "revision", "chapters")
        check(integer(root["version"], 1) == 1)
        val id = field(root, "id", 36).also(::uuid)
        val actualLibrary = field(root, "library_id", 256)
        val revision = decimalString(root["revision"], positive = true)
        check(id == expectedId && actualLibrary == library && revision == expectedRevision)
        val groups = array(root, "chapters", 6).map { raw ->
            val group = obj(raw)
            exact(group, "id", "contribution_ids")
            val chapterId = field(group, "id", 10)
            check(chapterId in expectedChapterIds)
            val ids = array(group, "contribution_ids", 12).map { rawId ->
                field(JsonObject(mapOf("id" to rawId)), "id", 36).also(::uuid)
            }
            check(ids.distinct().size == ids.size)
            SavedMemoryChapterContributionReferences(chapterId, ids)
        }
        check(groups.map { it.chapterId } == expectedChapterIds)
        SavedMemoryStoryContributionReferences(id, actualLibrary, revision, groups)
    }

    fun contributionReferencesMutation(m: SavedMemoryStoryContributionReferencesMutation): ByteArray = try {
        require(m.revision > 0 && m.selectionRevision.matches(Regex("[0-9a-f]{64}")))
        val chapters = JsonArray(m.chapters.map { chapter -> JsonObject(mapOf(
            "id" to JsonPrimitive(chapter.id), "title" to JsonPrimitive(chapter.title),
            "narration" to JsonPrimitive(chapter.narration),
            "asset_ids" to JsonArray(chapter.assetIds.map(::JsonPrimitive)),
            "evidence_ids" to JsonArray(chapter.evidenceIds.map(::JsonPrimitive)),
        )) })
        JsonObject(mapOf("title" to JsonPrimitive(m.title), "theme" to JsonPrimitive(m.theme),
            "language" to JsonPrimitive(m.language),
            "asset_ids" to JsonPrimitive(m.chapters.flatMap { it.assetIds }.joinToString(",")),
            "chapters" to JsonPrimitive(chapters.toString()), "selection_revision" to JsonPrimitive(m.selectionRevision),
            "revision" to JsonPrimitive(m.revision.toString()), "mutation_id" to JsonPrimitive(m.mutationId),
            "contribution_refs" to JsonPrimitive(m.contributionRefsJson))).toString().toByteArray(Charsets.UTF_8)
    } catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_INPUT) }

    private fun summary(o: JsonObject): SavedMemoryStorySummary {
        exact(o, "id", "title", "theme", "language", "revision", "cover_asset_id", "item_count", "chapter_count", "updated_at", "can_edit")
        val id = field(o, "id", 36); uuid(id)
        val title = field(o, "title", 160); val theme = field(o, "theme", 32).also(::theme)
        val language = field(o, "language", 2); check(language in setOf("zh", "en"))
        val revision = decimalString(o["revision"], positive = true)
        val cover = field(o, "cover_asset_id", 19); assetId(cover)
        val itemCount = integer(o["item_count"], 24); check(itemCount in 1..24)
        val chapterCount = integer(o["chapter_count"], 6); check(chapterCount in 1..6)
        val updated = long(o["updated_at"]); check(updated >= 0)
        return SavedMemoryStorySummary(id, title, theme, language, revision, cover, itemCount, chapterCount, updated, bool(o, "can_edit"))
    }

    private fun parseItem(o: JsonObject, library: String): MemoryStoryAsset {
        exact(o, "id", "kind", "width", "height", "duration_sec", "taken_at", "thumbnail_url", "date_hint", "evidence")
        val id = field(o, "id", 19); assetId(id)
        val kind = field(o, "kind", 8); check(kind in setOf("image", "video"))
        fun dimension(name: String): Int? = o[name].let { if (it == JsonNull) null else integer(it, 1_000_000).also { n -> check(n > 0) } }
        val width = dimension("width"); val height = dimension("height")
        val duration = o["duration_sec"].let { if (it == JsonNull) null else {
            val p = it as? JsonPrimitive ?: bad(); check(!p.isString)
            (p.doubleOrNull ?: bad()).also { n -> check(n.isFinite() && n in 0.0..1e9) }
        } }
        val taken = o["taken_at"].let { if (it == JsonNull) null else str(it, 64) }
        val thumbnail = field(o, "thumbnail_url", 2048)
        val base = okhttp3.HttpUrl.Builder().scheme("https").host("contract.invalid").build()
        val expected = base.newBuilder().addPathSegment("assets").addPathSegment(id).addPathSegment("thumbnail")
            .addQueryParameter("library", library).build()
        check(thumbnail.startsWith('/') && !thumbnail.startsWith("//") && '\\' !in thumbnail && base.resolve(thumbnail) == expected)
        val hint = o["date_hint"].let { if (it == JsonNull) null else {
            val h = obj(it ?: bad()); exact(h, "value", "source")
            DateHint(field(h, "value", 64), field(h, "source", 16))
        } }
        val evidence = array(o, "evidence", 3).map { parseEvidence(obj(it)) }
        check(evidence.map { it.id }.distinct().size == evidence.size)
        return MemoryStoryAsset(Asset(id, kind, width, height, duration, taken, thumbnail, hint), evidence)
    }

    private fun parseEvidence(o: JsonObject): MemoryStoryEvidence {
        val source = field(o, "source", 16)
        val evidenceId = field(o, "id", 64)
        return when {
            evidenceId.startsWith("family-") && source == "family" -> {
                exact(o, "id", "source", "title", "text", "revision")
                val id = evidenceId; check(id.matches(Regex("family-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")))
                val title = rawField(o, "title", 160, 512); val text = rawField(o, "text", 1800, 1800)
                val revision = integer(o["revision"]); check(revision > 0)
                MemoryStoryEvidence(id, source, title, text, revision)
            }
            evidenceId.startsWith("caption-") && source in setOf("family", "ai") -> {
                exact(o, "id", "source", "title", "text")
                val id = evidenceId; check(id.matches(Regex("caption-[1-9][0-9]{0,18}")) && id.removePrefix("caption-").toLongOrNull() != null)
                check(rawField(o, "title", 0, 0).isEmpty())
                val text = rawField(o, "text", 1800, 1800)
                MemoryStoryEvidence(id, source, "", text)
            }
            else -> bad()
        }
    }

    /** Existing family notes can contain CRLF and other controls; retain exact text, excluding NUL. */
    private fun rawField(o: JsonObject, name: String, maxCodePoints: Int, maxUtf8Bytes: Int): String {
        val p = o[name] as? JsonPrimitive ?: bad(); check(p.isString)
        val value = p.content
        check(value.indexOf('\u0000') < 0 && value.codePointCount(0, value.length) <= maxCodePoints)
        val bytes = try {
            Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(value)).remaining()
        } catch (_: Exception) { bad() }
        check(bytes <= maxUtf8Bytes)
        return value
    }

    private fun parseChapter(o: JsonObject, expectedNumber: Int): SavedMemoryStoryChapter {
        exact(o, "id", "title", "narration", "asset_ids", "evidence_ids")
        val id = field(o, "id", 10); check(id == "chapter-$expectedNumber")
        val title = field(o, "title", 160)
        val narration = field(o, "narration", 6000, allowNewline = true)
        check(narration.toByteArray(Charsets.UTF_8).size <= 6000)
        val assets = array(o, "asset_ids", 4).map { str(it, 19).also(::assetId) }
        check(assets.isNotEmpty() && assets.distinct().size == assets.size)
        val evidence = array(o, "evidence_ids", 12).map { str(it, 43) }
        check(evidence.distinct().size == evidence.size)
        return SavedMemoryStoryChapter(id, title, narration, assets, evidence)
    }

    private inline fun <T> guarded(block: () -> T): T = try { block() } catch (e: ApiFailure) { throw e } catch (_: Exception) { bad() }
}
