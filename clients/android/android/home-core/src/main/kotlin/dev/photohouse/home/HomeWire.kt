package dev.photohouse.home

import kotlinx.serialization.json.*
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.security.MessageDigest

object HomeLimits {
    const val JSON = 524288
    const val DISPLAY_BYTES = 12582912
    const val DISPLAY_PIXELS = 8847360
}
enum class Variant(val wire: String, val edge: Int, val pixels: Int, val bytes: Int) {
    GRID("grid", 512, 262144, 2097152), DISPLAY("display", 4096, HomeLimits.DISPLAY_PIXELS, HomeLimits.DISPLAY_BYTES)
}
data class Preview(val width: Int, val height: Int, val bytes: Int, val sha256: String, val url: String, val onDemand: Boolean = false)
enum class AssetKind { PHOTO, VIDEO, UNSUPPORTED }
enum class MediaUnavailable { NOT_PREPARED, SOURCE_MISSING, UNSUPPORTED, PREPARATION_FAILED }
data class HomeVideo(val width: Int, val height: Int, val durationMillis: Int, val bytes: Long,
                     val sha256: String, val url: String, val audioCodec: String?, val direct: Boolean = false)
data class HomeOriginal(val mime: String, val bytes: Int, val width: Int, val height: Int, val url: String)
data class HomeAsset(val id: Int, val caption: String, val grid: Preview?, val display: Preview?,
                     val kind: AssetKind = AssetKind.PHOTO, val video: HomeVideo? = null,
                     val gridUnavailable: MediaUnavailable? = null, val displayUnavailable: MediaUnavailable? = null,
                     val videoUnavailable: MediaUnavailable? = null, val original: HomeOriginal? = null) {
    fun preview(variant: Variant) = if (variant == Variant.GRID) grid else display
}
data class HomeFeed(val revision: Int, val id: String, val title: String, val page: Int,
                    val pageSize: Int, val total: Int, val hasMore: Boolean, val items: List<HomeAsset>, val version: Int = 1, val browseCounts: BrowseCounts? = null)
enum class HomeError { INVALID, DENIED, CHANGED, BUSY, UNAVAILABLE, OFFLINE, TLS }
class HomeFailure(val kind: HomeError, val retryAfterMillis: Long = 0) : Exception(kind.name)
interface HomeApi {
    val browseEnabled: Boolean get() = false
    suspend fun feed(page: Int, revision: Int?, selection: BrowseSelection): HomeFeed {
        if (selection != BrowseSelection()) throw HomeFailure(HomeError.INVALID)
        return feed(page, revision)
    }
    val catalogVersion: Int get() = 1
    suspend fun collections(): HomeCollections = throw HomeFailure(HomeError.INVALID)
    val retryRevisionChanges: Boolean get() = true
    suspend fun feed(page: Int, revision: Int?): HomeFeed = feed(page)
    fun video(asset: HomeAsset, revision: Int, failed: (Exception) -> Unit): HomeVideoSource = throw HomeFailure(HomeError.INVALID)
    suspend fun original(asset: HomeAsset, revision: Int): ByteArray = throw HomeFailure(HomeError.INVALID)
    suspend fun feed(page: Int): HomeFeed
    suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray?
}

object HomeWire {
    private fun bad(): Nothing = throw HomeFailure(HomeError.INVALID)
    private fun check(ok: Boolean) { if (!ok) bad() }
    private fun JsonElement.obj(vararg keys: String): JsonObject {
        val o = this as? JsonObject ?: bad(); check(o.keys == keys.toSet()); return o
    }
    private fun JsonElement.int(low: Int = 1, high: Int = Int.MAX_VALUE): Int {
        val p = this as? JsonPrimitive ?: bad()
        check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toIntOrNull()?.takeIf { it in low..high } ?: bad()
    }
    private fun JsonElement.str(max: Int): String {
        val p = this as? JsonPrimitive ?: bad(); check(p.isString)
        check(p.content.toByteArray().size <= max && p.content.none { it < ' ' && it != '\n' && it != '\t' })
        return p.content
    }
    private fun JsonElement.bool(): Boolean {
        val p = this as? JsonPrimitive ?: bad(); check(!p.isString)
        return p.booleanOrNull ?: bad()
    }
    /** Small bounded JSON reader: rejects duplicate keys, deep nesting and invalid UTF-8. */
    internal fun parse(bytes: ByteArray): JsonElement {
        check(bytes.size in 1..HomeLimits.JSON)
        val s = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString()
        var i = 0
        fun ws() { while (i < s.length && s[i] in " \t\r\n") i++ }
        fun string(): JsonPrimitive {
            val start = i++; var escaped = false
            while (i < s.length) {
                val c = s[i++]
                if (!escaped && c == '"') {
                    val p = Json.parseToJsonElement(s.substring(start, i)) as JsonPrimitive
                    // JSON escapes may encode lone UTF-16 surrogates; never replace them silently.
                    Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(p.content))
                    return p
                }
                if (!escaped && c == '\\') escaped = true else escaped = false
            }
            bad()
        }
        fun value(depth: Int): JsonElement {
            check(depth <= 8); ws(); check(i < s.length)
            if (s[i] == '"') return string()
            if (s[i] == '{') {
                i++; ws(); val map = linkedMapOf<String, JsonElement>()
                if (i < s.length && s[i] == '}') { i++; return JsonObject(map) }
                while (true) {
                    ws(); check(i < s.length && s[i] == '"'); val key = string().content
                    check(key !in map); ws(); check(i < s.length && s[i++] == ':'); map[key] = value(depth + 1)
                    ws(); check(i < s.length); if (s[i] == '}') { i++; break }; check(s[i++] == ',')
                }
                return JsonObject(map)
            }
            if (s[i] == '[') {
                i++; ws(); val list = mutableListOf<JsonElement>()
                if (i < s.length && s[i] == ']') { i++; return JsonArray(list) }
                while (true) {
                    check(list.size < 100); list += value(depth + 1); ws(); check(i < s.length)
                    if (s[i] == ']') { i++; break }; check(s[i++] == ',')
                }
                return JsonArray(list)
            }
            val start = i
            while (i < s.length && s[i] !in ",]} \t\r\n") i++
            check(i > start); return Json.parseToJsonElement(s.substring(start, i))
        }
        val result = value(0); ws(); check(i == s.length); return result
    }
    fun feed(bytes: ByteArray, page: Int): HomeFeed = try {
        check(page in 1..2000)
        val o = parse(bytes).obj("version", "revision", "feed", "page", "page_size", "total", "has_more", "items")
        check(o.getValue("version").int() == 1)
        val revision = o.getValue("revision").int()
        check(o.getValue("page").int() == page && o.getValue("page_size").int() == 50)
        val total = o.getValue("total").int(0, 2000)
        val more = o.getValue("has_more").bool(); check(more == (page * 50 < total))
        val feed = o.getValue("feed").obj("id", "title")
        val id = feed.getValue("id").str(64); check(id.matches(Regex("[a-z0-9-]{1,64}")))
        val items = (o.getValue("items") as? JsonArray ?: bad()).map { element ->
            val a = element.obj("id", "caption", "previews", "originals_allowed")
            check(!a.getValue("originals_allowed").bool())
            val assetId = a.getValue("id").int(); val previews = a.getValue("previews").obj("grid", "display")
            fun preview(v: Variant): Preview {
                val p = previews.getValue(v.wire).obj("width", "height", "bytes", "sha256", "url")
                val w = p.getValue("width").int(1, v.edge); val h = p.getValue("height").int(1, v.edge)
                check(w.toLong() * h <= v.pixels)
                val hash = p.getValue("sha256").str(64); check(hash.matches(Regex("[0-9a-f]{64}")))
                val url = p.getValue("url").str(160); check(url == path(assetId, v, revision))
                return Preview(w, h, p.getValue("bytes").int(1, v.bytes), hash, url)
            }
            HomeAsset(assetId, a.getValue("caption").str(1024), preview(Variant.GRID), preview(Variant.DISPLAY))
        }
        check(items.size == minOf(50, maxOf(0, total - (page - 1) * 50)))
        check(items.map { it.id }.toSet().size == items.size)
        HomeFeed(revision, id, feed.getValue("title").str(256), page, 50, total, more, items)
    } catch (e: HomeFailure) { throw e } catch (_: Exception) { bad() }

    fun collections(bytes: ByteArray): HomeCollections = try {
        val o = parse(bytes).obj("version", "revision", "collections")
        check(o.getValue("version").int() == 1)
        val revision = o.getValue("revision").int()
        val entries = (o.getValue("collections") as? JsonArray ?: bad()).map { element ->
            val c = element.obj("id", "title", "media_count", "photo_count", "video_count")
            val id = c.getValue("id").str(64); check(id.matches(Regex("[a-z0-9-]{1,64}")))
            val title = c.getValue("title").str(256); check(title.isNotBlank())
            val media = c.getValue("media_count").int(0, 100000)
            val photos = c.getValue("photo_count").int(0, 100000)
            val videos = c.getValue("video_count").int(0, 100000)
            check(media >= photos + videos)
            HomeCollection(id, title, media, photos, videos)
        }
        check(entries.size <= 100 && entries.map { it.id }.distinct().size == entries.size)
        HomeCollections(revision, entries)
    } catch (e: HomeFailure) { throw e } catch (_: Exception) { bad() }

    fun path(id: Int, variant: Variant, revision: Int): String {
        require(id > 0 && revision > 0)
        return "/home/v1/assets/$id/preview?variant=${variant.wire}&revision=$revision"
    }
    fun verifyPreview(bytes: ByteArray, meta: Preview, variant: Variant) {
        check(meta.width in 1..variant.edge && meta.height in 1..variant.edge && meta.width.toLong() * meta.height <= variant.pixels)
        check(meta.bytes in 1..variant.bytes && bytes.size == meta.bytes)
        check(MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) } == meta.sha256)
        check(jpegDimensions(bytes) == Pair(meta.width, meta.height))
    }
    /** Mirrors the frozen prepared JPEG framing policy; Android still checks actual decoding. */
    fun jpegDimensions(data: ByteArray): Pair<Int, Int> {
        fun at(i: Int) = data.getOrNull(i)?.toInt()?.and(255) ?: bad()
        fun word(i: Int) = (at(i) shl 8) + at(i + 1)
        check(at(0) == 255 && at(1) == 216)
        var pos = 2; var dimensions: Pair<Int, Int>? = null; var scanning = false
        while (pos < data.size) {
            if (scanning) { while (pos < data.size && at(pos) != 255) pos++ }
            check(at(pos) == 255); while (pos < data.size && at(pos) == 255) pos++
            val marker = at(pos++)
            if (scanning && (marker == 0 || marker in 208..215)) continue
            if (marker == 217) { check(pos == data.size && scanning); return dimensions ?: bad() }
            check(!scanning && marker in listOf(192, 196, 219, 221, 224, 218))
            val length = word(pos); check(length >= 2 && pos + length <= data.size)
            val start = pos + 2; val count = length - 2
            if (marker == 192) {
                check(dimensions == null && count >= 6 && at(start) == 8 && at(start + 5) in listOf(1, 3) && count == 6 + 3 * at(start + 5))
                dimensions = word(start + 3) to word(start + 1)
            }
            if (marker == 224) check(count == 14 && data.copyOfRange(start, start + 5).contentEquals(byteArrayOf(74,70,73,70,0)) && at(start + 12) == 0 && at(start + 13) == 0)
            if (marker == 218) { check(dimensions != null); scanning = true }
            pos += length
        }
        bad()
    }
}
