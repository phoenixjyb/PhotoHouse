package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import dev.photohouse.protocol.DateHint
import kotlinx.serialization.json.*
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction

data class ProtectedStoryWorkspaceDraft(
    val libraryId: String,
    val selectionRevision: String,
    val title: String,
    val theme: String,
    val language: String,
    val items: List<MemoryStoryAsset>,
    val chapters: List<SavedMemoryStoryChapter>,
    val questions: List<String>,
)

data class ProtectedStoryWorkspaceTitleCapabilities(
    val enabled: Boolean,
    val maxSuggestions: Int,
)

data class ProtectedStoryWorkspaceChapterInput(val id: String, val narration: String)
data class ProtectedStoryWorkspaceTitle(val text: String, val sourceIds: List<String>)

/** Wire-only draft foundation. It neither persists drafts nor invokes transport or a model. */
internal object ProtectedStoryWorkspaceWire {
    const val MAX_PREVIEW_REQUEST_BYTES = 4096
    const val MAX_TITLE_REQUEST_BYTES = 64 * 1024
    private const val MAX_RESPONSE_BYTES = 256 * 1024
    private const val MAX_ASSETS = 24
    private const val MAX_CHAPTERS = 6
    private const val MAX_ASSETS_PER_CHAPTER = 4
    private const val MAX_EVIDENCE_PER_ASSET = 3
    private const val MAX_EVIDENCE_PER_CHAPTER = 12
    private const val MAX_TITLE_CODE_POINTS = 160
    private const val MAX_TITLE_BYTES = 640
    private const val MAX_NARRATION_BYTES = 6000
    private const val MAX_QUESTIONS = 3
    private const val MAX_QUESTION_CODE_POINTS = 1000

    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun input(ok: Boolean) { require(ok) { "Invalid story workspace input" } }
    private fun check(ok: Boolean) { if (!ok) bad() }

    private fun utf8(value: String): ByteArray = try {
        Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value))
            .let { ByteArray(it.remaining()).also(it::get) }
    } catch (_: Exception) { bad() }

    private fun obj(value: JsonElement?): JsonObject = value as? JsonObject ?: bad()
    private fun exact(value: JsonObject, vararg keys: String) { check(value.keys == keys.toSet()) }
    private fun array(value: JsonElement?, max: Int): JsonArray = (value as? JsonArray)
        ?.also { check(it.size <= max) } ?: bad()

    private fun string(value: JsonElement?, maxCodePoints: Int, maxBytes: Int, allowNewline: Boolean = false,
                       blank: Boolean = false): String {
        val primitive = value as? JsonPrimitive ?: bad()
        check(primitive.isString)
        val text = primitive.content
        check(text.codePointCount(0, text.length) <= maxCodePoints)
        val encoded = utf8(text)
        check(encoded.size <= maxBytes)
        check(text.none { it == '\u0000' || it.isISOControl() && !(allowNewline && it in "\n\t") })
        check(blank || text.isNotBlank())
        return text
    }

    private fun bool(value: JsonElement?): Boolean {
        val primitive = value as? JsonPrimitive ?: bad()
        check(!primitive.isString)
        return primitive.booleanOrNull ?: bad()
    }

    private fun integer(value: JsonElement?, minimum: Int = 0, maximum: Int = Int.MAX_VALUE): Int {
        val primitive = value as? JsonPrimitive ?: bad()
        check(!primitive.isString && primitive.content.matches(Regex("0|[1-9][0-9]*")))
        return primitive.content.toIntOrNull()?.takeIf { it in minimum..maximum } ?: bad()
    }

    private fun long(value: JsonElement?): Long {
        val primitive = value as? JsonPrimitive ?: bad()
        check(!primitive.isString && primitive.content.matches(Regex("0|[1-9][0-9]*")))
        return primitive.content.toLongOrNull() ?: bad()
    }

    private fun assetId(value: String): String = value.also {
        check(it.matches(Regex("[1-9][0-9]{0,18}")) && it.toLongOrNull()?.toString() == it)
    }

    private fun validSelectionRevision(value: String): Boolean = value.matches(Regex("[0-9a-f]{64}"))

    private fun validateSelection(assetIds: List<String>) {
        input(assetIds.size in 1..MAX_ASSETS && assetIds.distinct().size == assetIds.size)
        assetIds.forEach { input(it.matches(Regex("[1-9][0-9]{0,18}")) && it.toLongOrNull()?.toString() == it) }
    }

    private fun inputText(value: String, maxCodePoints: Int, maxBytes: Int, allowNewline: Boolean = false,
                          blank: Boolean = false) {
        input(value.codePointCount(0, value.length) <= maxCodePoints)
        val bytes = try {
            Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value)).remaining()
        } catch (_: Exception) { throw IllegalArgumentException("Invalid story workspace input") }
        input(bytes <= maxBytes && value.none { it == '\u0000' || it.isISOControl() && !(allowNewline && it in "\n\t") })
        input(blank || value.isNotBlank())
    }

    fun encodePreviewRequest(assetIds: List<String>, theme: String, language: String, title: String): String = guardedInput {
        validateSelection(assetIds)
        input(theme in SAVED_MEMORY_STORY_THEMES && language in setOf("zh", "en"))
        inputText(title, MAX_TITLE_CODE_POINTS, MAX_TITLE_BYTES, blank = true)
        buildJsonObject {
            put("asset_ids", assetIds.joinToString(",")); put("theme", theme); put("language", language); put("title", title)
        }.toString().also { input(utf8(it).size <= MAX_PREVIEW_REQUEST_BYTES) }
    }

    fun decodePreview(
        bytes: ByteArray,
        expectedLibrary: String,
        expectedAssetIds: List<String>,
        expectedTheme: String? = null,
        expectedLanguage: String? = null,
    ): ProtectedStoryWorkspaceDraft = guarded {
        validateSelection(expectedAssetIds)
        check(PhoneDiscoveryWire.validLibrary(expectedLibrary))
        val root = obj(DiscoveryJson.parse(bytes, MAX_RESPONSE_BYTES, 1200))
        exact(root, "version", "library_id", "selection_revision", "state", "saved", "title", "theme", "language", "generator", "needs_review", "items", "chapters", "questions")
        check(integer(root["version"], 1, 1) == 1)
        check(string(root["library_id"], 256, 256) == expectedLibrary)
        val selectionRevision = string(root["selection_revision"], 64, 64)
        check(validSelectionRevision(selectionRevision))
        check(string(root["state"], 16, 16) == "draft" && !bool(root["saved"]))
        val title = string(root["title"], MAX_TITLE_CODE_POINTS, MAX_TITLE_BYTES, blank = true)
        val theme = string(root["theme"], 32, 32).also { check(it in SAVED_MEMORY_STORY_THEMES) }
        val language = string(root["language"], 2, 2).also { check(it in setOf("zh", "en")) }
        check(expectedTheme == null || theme == expectedTheme)
        check(expectedLanguage == null || language == expectedLanguage)
        check(string(root["generator"], 32, 32) == "evidence_outline" && bool(root["needs_review"]))
        val items = array(root["items"], MAX_ASSETS).map { parseItem(obj(it), expectedLibrary) }
        check(items.isNotEmpty() && items.map { it.asset.id } == expectedAssetIds)
        check(items.flatMap { it.evidence }.map { it.id }.distinct().size == items.sumOf { it.evidence.size })
        val chapters = array(root["chapters"], MAX_CHAPTERS).mapIndexed { index, raw -> parseChapter(obj(raw), index + 1) }
        check(chapters.isNotEmpty() && chapters.map { it.id }.distinct().size == chapters.size)
        check(chapters.map { it.assetIds } == expectedAssetIds.chunked(MAX_ASSETS_PER_CHAPTER))
        val evidenceByAsset = items.associate { it.asset.id to it.evidence.map { evidence -> evidence.id }.toSet() }
        chapters.forEach { chapter ->
            val eligibleEvidence = chapter.assetIds.flatMap { evidenceByAsset[it] ?: emptySet() }.toSet()
            check(chapter.evidenceIds.all { it in eligibleEvidence })
        }
        val questions = array(root["questions"], MAX_QUESTIONS).map {
            string(it, MAX_QUESTION_CODE_POINTS, 4000, allowNewline = true).also { question -> check(question.isNotBlank()) }
        }
        ProtectedStoryWorkspaceDraft(expectedLibrary, selectionRevision, title, theme, language, items, chapters, questions)
    }

    fun decodeTitleCapabilities(bytes: ByteArray): ProtectedStoryWorkspaceTitleCapabilities = guarded {
        val root = obj(DiscoveryJson.parse(bytes, 16 * 1024, 32))
        exact(root, "version", "enabled", "max_suggestions", "needs_review")
        check(integer(root["version"], 1, 1) == 1 && bool(root["needs_review"]))
        val max = integer(root["max_suggestions"], 3, 3)
        val enabled = bool(root["enabled"])
        ProtectedStoryWorkspaceTitleCapabilities(enabled, max)
    }

    fun encodeTitleRequest(
        assetIds: List<String>, theme: String, language: String, selectionRevision: String,
        chapters: List<ProtectedStoryWorkspaceChapterInput>,
    ): String = guardedInput {
        validateSelection(assetIds)
        input(theme in SAVED_MEMORY_STORY_THEMES && language in setOf("zh", "en"))
        input(validSelectionRevision(selectionRevision))
        input(chapters.size == (assetIds.size + MAX_ASSETS_PER_CHAPTER - 1) / MAX_ASSETS_PER_CHAPTER)
        input(chapters.size in 1..MAX_CHAPTERS && chapters.map { it.id } == (1..chapters.size).map { "chapter-$it" })
        chapters.forEach { inputText(it.narration, Int.MAX_VALUE, MAX_NARRATION_BYTES, allowNewline = true, blank = true) }
        val chapterJson = JsonArray(chapters.map { chapter -> buildJsonObject {
            put("id", chapter.id); put("narration", chapter.narration)
        } }).toString()
        buildJsonObject {
            put("asset_ids", assetIds.joinToString(",")); put("theme", theme); put("language", language)
            put("selection_revision", selectionRevision); put("chapters", chapterJson)
        }.toString().also { input(utf8(it).size <= MAX_TITLE_REQUEST_BYTES) }
    }

    fun decodeTitles(bytes: ByteArray, draft: ProtectedStoryWorkspaceDraft): List<ProtectedStoryWorkspaceTitle> = guarded {
        check(validSelectionRevision(draft.selectionRevision))
        val root = obj(DiscoveryJson.parse(bytes, MAX_RESPONSE_BYTES, 128))
        exact(root, "version", "selection_revision", "titles", "needs_review")
        check(integer(root["version"], 1, 1) == 1)
        check(string(root["selection_revision"], 64, 64) == draft.selectionRevision)
        check(bool(root["needs_review"]))
        val known = draft.items.flatMap { item -> item.evidence.filter { it.text.isNotBlank() }.map { it.id } }.toMutableSet()
        draft.chapters.filter { it.narration.isNotBlank() }.forEach { known += "draft-${it.id}" }
        val titles = array(root["titles"], 3).map { raw ->
            val title = obj(raw); exact(title, "text", "source_ids")
            val text = string(title["text"], MAX_TITLE_CODE_POINTS, MAX_TITLE_BYTES).also { value ->
                check(value.isNotBlank() && value.none { it == '\n' || it == '\r' || it == '\u2028' || it == '\u2029' })
            }
            val sourceIds = array(title["source_ids"], MAX_ASSETS * MAX_EVIDENCE_PER_ASSET + MAX_CHAPTERS).map { string(it, 64, 64) }
            check(sourceIds.isNotEmpty() && sourceIds.distinct().size == sourceIds.size && sourceIds.all { it in known })
            ProtectedStoryWorkspaceTitle(text, sourceIds)
        }
        check(titles.map { it.text }.distinct().size == titles.size)
        titles
    }

    private fun parseItem(o: JsonObject, library: String): MemoryStoryAsset {
        exact(o, "id", "kind", "width", "height", "duration_sec", "taken_at", "thumbnail_url", "date_hint", "evidence")
        val id = string(o["id"], 19, 19).also(::assetId)
        val kind = string(o["kind"], 8, 8).also { check(it in setOf("image", "video")) }
        fun dimension(name: String): Int? = o[name].let { if (it == JsonNull) null else integer(it, 1, 1_000_000) }
        val width = dimension("width"); val height = dimension("height")
        val duration = o["duration_sec"].let { if (it == JsonNull) null else {
            val p = it as? JsonPrimitive ?: bad(); check(!p.isString)
            (p.doubleOrNull ?: bad()).also { number -> check(number.isFinite() && number in 0.0..1e9) }
        } }
        val takenAt = o["taken_at"].let { if (it == JsonNull) null else string(it, 64, 256) }
        val thumbnail = string(o["thumbnail_url"], 2048, 2048)
        val base = okhttp3.HttpUrl.Builder().scheme("https").host("contract.invalid").build()
        val expected = base.newBuilder().addPathSegment("assets").addPathSegment(id).addPathSegment("thumbnail")
            .addQueryParameter("library", library).build()
        check(thumbnail.startsWith('/') && !thumbnail.startsWith("//") && '\\' !in thumbnail && base.resolve(thumbnail) == expected)
        val dateHint = o["date_hint"].let { if (it == JsonNull) null else {
            val hint = obj(it); exact(hint, "value", "source")
            DateHint(string(hint["value"], 64, 256), string(hint["source"], 16, 64).also { check(it in setOf("filename", "received")) })
        } }
        val evidence = array(o["evidence"], MAX_EVIDENCE_PER_ASSET).map { parseEvidence(obj(it)) }
        check(evidence.map { it.id }.distinct().size == evidence.size)
        return MemoryStoryAsset(Asset(id, kind, width, height, duration, takenAt, thumbnail, dateHint), evidence)
    }

    private fun parseEvidence(o: JsonObject): MemoryStoryEvidence {
        val source = string(o["source"], 16, 64)
        val id = string(o["id"], 64, 64)
        return when {
            id.startsWith("family-") && source == "family" -> {
                exact(o, "id", "source", "title", "text", "revision")
                check(id.matches(Regex("family-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")))
                val title = rawText(o["title"], 160, 512)
                val text = rawText(o["text"], 1800, 1800)
                val revision = integer(o["revision"], 1)
                MemoryStoryEvidence(id, source, title, text, revision)
            }
            id.startsWith("caption-") && source in setOf("family", "ai") -> {
                exact(o, "id", "source", "title", "text")
                check(id.matches(Regex("caption-[1-9][0-9]{0,18}") ) && id.removePrefix("caption-").toLongOrNull() != null)
                check(rawText(o["title"], 0, 0).isEmpty())
                MemoryStoryEvidence(id, source, "", rawText(o["text"], 1800, 1800))
            }
            else -> bad()
        }
    }

    private fun rawText(value: JsonElement?, maxCodePoints: Int, maxBytes: Int): String {
        val primitive = value as? JsonPrimitive ?: bad(); check(primitive.isString)
        val text = primitive.content
        check('\u0000' !in text && text.codePointCount(0, text.length) <= maxCodePoints && utf8(text).size <= maxBytes)
        return text
    }

    private fun parseChapter(o: JsonObject, number: Int): SavedMemoryStoryChapter {
        exact(o, "id", "title", "narration", "asset_ids", "evidence_ids")
        val id = string(o["id"], 10, 10).also { check(it == "chapter-$number") }
        val title = string(o["title"], MAX_TITLE_CODE_POINTS, MAX_TITLE_BYTES, blank = true)
        val narration = string(o["narration"], 6000, MAX_NARRATION_BYTES, allowNewline = true, blank = true)
        val assetIds = array(o["asset_ids"], MAX_ASSETS_PER_CHAPTER).map { string(it, 19, 19).also(::assetId) }
        check(assetIds.isNotEmpty() && assetIds.distinct().size == assetIds.size)
        val evidenceIds = array(o["evidence_ids"], MAX_EVIDENCE_PER_CHAPTER).map { string(it, 64, 64) }
        check(evidenceIds.distinct().size == evidenceIds.size)
        return SavedMemoryStoryChapter(id, title, narration, assetIds, evidenceIds)
    }

    private inline fun <T> guarded(block: () -> T): T = try { block() }
        catch (e: ApiFailure) { throw e }
        catch (_: Exception) { bad() }

    private inline fun <T> guardedInput(block: () -> T): T = try { block() }
        catch (e: ApiFailure) { throw e }
        catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_INPUT) }
}
