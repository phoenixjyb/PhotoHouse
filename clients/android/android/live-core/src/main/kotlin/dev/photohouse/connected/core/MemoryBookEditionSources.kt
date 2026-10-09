package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.UUID

/** Optional edition-bound original reads; no unbound contribution/audio fallback. */
interface MemoryBookEditionSourceApi {
    suspend fun editionSources(token: Bearer, library: String, bookId: String, editionId: String, page: Int): ByteArray
    suspend fun editionSource(token: Bearer, library: String, bookId: String, editionId: String, sourceId: String): ByteArray
    suspend fun editionSourceAudio(token: Bearer, library: String, bookId: String, editionId: String, sourceId: String): ByteArray
}

enum class MemoryBookEditionSourceOrigin(val wire: String) {
    CONTRIBUTION_TEXT("contribution_text"), CONTRIBUTION_AUDIO("contribution_audio"),
    ASSET_NOTE("asset_note"), CAPTION("caption"), BOOK_INTRODUCTION("book_introduction"), STORY_CHAPTER("story_chapter"),
}

data class MemoryBookEditionSourceMetadata(
    val sourceId: String, val origin: MemoryBookEditionSourceOrigin, val kind: String, val assetId: String?,
)
data class MemoryBookEditionSourcePage(
    val bookId: String, val editionId: String, val bookRevision: Long, val state: MemoryBookEditionState,
    val page: Int, val hasMore: Boolean, val items: List<MemoryBookEditionSourceMetadata>,
)
data class MemoryBookEditionSourceMaterial(
    val metadata: MemoryBookEditionSourceMetadata, val storyId: String?, val byline: String?,
    val originalText: String?, val originalTruncated: Boolean, val transcript: String?,
    val transcriptTruncated: Boolean, val promptExcerpt: String, val audioAvailable: Boolean,
) { override fun toString() = "MemoryBookEditionSourceMaterial(content omitted)" }
data class MemoryBookEditionSourceDetail(
    val bookId: String, val editionId: String, val bookRevision: Long, val sourceId: String,
    val state: MemoryBookEditionState, val source: MemoryBookEditionSourceMaterial?,
) { override fun toString() = "MemoryBookEditionSourceDetail(content omitted)" }

/** Exact bounded wire validation establishes client structure; the server authorizes source truth. */
object MemoryBookEditionSourceWire {
    private val sourcePattern = Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    private val positive = Regex("[1-9][0-9]{0,18}")
    fun validSourceId(value: String) = sourcePattern.matches(value)
    private fun invalid(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(ok: Boolean) { if (!ok) invalid() }
    private fun obj(value: JsonElement?, vararg keys: String) = (value as? JsonObject ?: invalid()).also {
        check(it.keys == keys.toSet())
    }
    private fun text(value: JsonElement?, max: Int, blank: Boolean = false): String {
        val primitive = value as? JsonPrimitive ?: invalid()
        check(primitive.isString)
        val result = primitive.content
        val encoded = Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(result))
        check(encoded.remaining() <= max && (blank || result.isNotBlank()))
        check(result.none { it.isISOControl() && it !in "\n\t" })
        return result
    }
    private fun nullable(value: JsonElement?, max: Int): String? = if (value === JsonNull) null else text(value, max, blank = true)
    private fun bool(value: JsonElement?): Boolean {
        val p = value as? JsonPrimitive ?: invalid(); check(!p.isString)
        return p.booleanOrNull ?: invalid()
    }
    private fun number(value: JsonElement?, max: Long): Long {
        val p = value as? JsonPrimitive ?: invalid()
        check(!p.isString && positive.matches(p.content))
        return p.content.toLongOrNull()?.takeIf { it in 1..max } ?: invalid()
    }
    private fun revision(value: JsonElement?): Long = text(value,19).let {
        check(positive.matches(it)); it.toLongOrNull()?.takeIf { n -> n > 0 } ?: invalid()
    }
    private fun uuid(value: String): String = value.also { check(runCatching { UUID.fromString(it).toString() == it }.getOrDefault(false)) }
    private fun asset(value: JsonElement?): String? = nullable(value,19)?.also { check(positive.matches(it) && it.toLongOrNull() != null) }
    private fun state(value: JsonElement?) = when (text(value,24)) {
        "current" -> MemoryBookEditionState.CURRENT
        "source_changed" -> MemoryBookEditionState.SOURCE_CHANGED
        "source_invalidated" -> MemoryBookEditionState.SOURCE_INVALIDATED
        else -> invalid()
    }
    private fun identity(r: JsonObject, book: String, edition: String, rev: Long) {
        check(number(r["version"],1) == 1L && uuid(text(r["book_id"],36)) == book &&
            uuid(text(r["edition_id"],36)) == edition && revision(r["book_revision"]) == rev)
    }
    private fun metadata(id: String, originValue: JsonElement?, kindValue: JsonElement?, assetValue: JsonElement?): MemoryBookEditionSourceMetadata {
        check(validSourceId(id))
        val origin = MemoryBookEditionSourceOrigin.entries.find { it.wire == text(originValue,24) } ?: invalid()
        val kind = text(kindValue,16); val asset = asset(assetValue)
        when (origin) {
            MemoryBookEditionSourceOrigin.CONTRIBUTION_TEXT, MemoryBookEditionSourceOrigin.CONTRIBUTION_AUDIO -> {
                check(id.startsWith("contribution-")); uuid(id.removePrefix("contribution-"))
                check(asset == null && kind == if (origin == MemoryBookEditionSourceOrigin.CONTRIBUTION_TEXT) "family" else "transcript")
            }
            MemoryBookEditionSourceOrigin.ASSET_NOTE -> {
                check(id.startsWith("family-")); uuid(id.removePrefix("family-")); check(asset != null && kind == "family")
            }
            MemoryBookEditionSourceOrigin.CAPTION -> {
                check(id.startsWith("caption-")); val n = id.removePrefix("caption-")
                check(positive.matches(n) && n.toLongOrNull() != null && asset != null && kind in setOf("family","ai"))
            }
            MemoryBookEditionSourceOrigin.BOOK_INTRODUCTION -> {
                check(id.startsWith("editorial-book-")); uuid(id.removePrefix("editorial-book-")); check(asset == null && kind == "editorial")
            }
            MemoryBookEditionSourceOrigin.STORY_CHAPTER -> {
                check(id.startsWith("editorial-")); val suffix = id.removePrefix("editorial-")
                check(suffix.length == 46 && suffix.substring(36).matches(Regex("-chapter-[1-6]")))
                uuid(suffix.take(36)); check(asset == null && kind == "editorial")
            }
        }
        return MemoryBookEditionSourceMetadata(id,origin,kind,asset)
    }
    private inline fun <T> guarded(block: () -> T): T = try { block() } catch (e: ApiFailure) { throw e }
        catch (_: Exception) { invalid() }

    fun decodePage(bytes: ByteArray, book: String, edition: String, revision: Long, page: Int, children: List<String>): MemoryBookEditionSourcePage = guarded {
        val r = obj(DiscoveryJson.parse(bytes,MemoryCommunityResponseLimits.JSON_BYTES,128),
            "version","book_id","edition_id","book_revision","state","page","page_size","has_more","items")
        identity(r,book,edition,revision)
        check(number(r["page"],100000) == page.toLong() && number(r["page_size"],16) == 16L)
        val status = state(r["state"]); val more = bool(r["has_more"])
        val array = r["items"] as? JsonArray ?: invalid(); check(array.size <= 16)
        val items = array.map { raw ->
            val item = obj(raw,"source_id","origin","kind","asset_id")
            metadata(text(item["source_id"],128),item["origin"],item["kind"],item["asset_id"])
        }
        check(items.map { it.sourceId }.distinct().size == items.size && (!more || items.size == 16))
        check(!more || page < 6)
        check(items.isEmpty() || (page - 1L) * 16 + items.size <= 96)
        items.filter { it.origin == MemoryBookEditionSourceOrigin.STORY_CHAPTER }.forEach {
            check(it.sourceId.removePrefix("editorial-").take(36) in children)
        }
        if (status != MemoryBookEditionState.CURRENT) check(items.isEmpty() && !more)
        items.filter { it.origin == MemoryBookEditionSourceOrigin.BOOK_INTRODUCTION }.forEach {
            check(it.sourceId == "editorial-book-$book")
        }
        MemoryBookEditionSourcePage(book,edition,revision,status,page,more,items)
    }
    fun decodeDetail(bytes: ByteArray, book: String, edition: String, revision: Long, sourceId: String,
                     children: List<String>): MemoryBookEditionSourceDetail = guarded {
        val r = obj(DiscoveryJson.parse(bytes,MemoryCommunityResponseLimits.JSON_BYTES,64),
            "version","book_id","edition_id","book_revision","source_id","state","source")
        identity(r,book,edition,revision); check(text(r["source_id"],128) == sourceId && validSourceId(sourceId))
        val status = state(r["state"])
        val source = if (status != MemoryBookEditionState.CURRENT) { check(r["source"] === JsonNull); null } else {
            val s = obj(r["source"],"origin","kind","asset_id","story_id","byline","original_text","original_truncated",
                "transcript","transcript_truncated","prompt_excerpt","audio_available")
            val meta = metadata(sourceId,s["origin"],s["kind"],s["asset_id"])
            val story = nullable(s["story_id"],36)?.let(::uuid)
            val byline = nullable(s["byline"],256)
            val original = nullable(s["original_text"],8192); val originalCut = bool(s["original_truncated"])
            val transcript = nullable(s["transcript"],8192); val transcriptCut = bool(s["transcript_truncated"])
            val excerpt = text(s["prompt_excerpt"],8192,blank = true); val audio = bool(s["audio_available"])
            check(original != null || !originalCut); check(transcript != null || !transcriptCut)
            if (meta.origin in setOf(MemoryBookEditionSourceOrigin.CONTRIBUTION_TEXT,MemoryBookEditionSourceOrigin.CONTRIBUTION_AUDIO,
                    MemoryBookEditionSourceOrigin.STORY_CHAPTER)) check(story != null && story in children) else check(story == null)
            if (meta.origin == MemoryBookEditionSourceOrigin.CONTRIBUTION_AUDIO) check(original == null && transcript != null && audio)
            else check(original != null && transcript == null && !audio)
            if (meta.origin == MemoryBookEditionSourceOrigin.BOOK_INTRODUCTION) check(sourceId == "editorial-book-$book")
            if (meta.origin == MemoryBookEditionSourceOrigin.STORY_CHAPTER) {
                check(sourceId.startsWith("editorial-$story-chapter-")); check(byline == null)
            }
            MemoryBookEditionSourceMaterial(meta,story,byline,original,originalCut,transcript,transcriptCut,excerpt,audio)
        }
        MemoryBookEditionSourceDetail(book,edition,revision,sourceId,status,source)
    }
}
