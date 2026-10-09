package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import dev.photohouse.protocol.Gallery
import kotlinx.serialization.json.*
import okhttp3.HttpUrl.Companion.toHttpUrl

data class FamilyTagChoice(val name: String, val assetCount: Int)
data class FamilyTagsPage(val libraryId: String, val page: Int, val pageSize: Int, val total: Int,
    val items: List<FamilyTagChoice>)

/** Strict wire handling for the protected family-authored note tag endpoints. */
object FamilyTagsWire {
    const val PAGE_SIZE = 25
    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(ok: Boolean) { if (!ok) bad() }

    fun validQuery(value: String) = validText(value, allowEmpty = true)
    fun validTag(value: String) = validText(value, allowEmpty = false)
    private fun validText(value: String, allowEmpty: Boolean): Boolean = runCatching {
        val encoded = Charsets.UTF_8.newEncoder().onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
            .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(value))
        require(value.codePointCount(0, value.length) <= 128 && encoded.remaining() <= 512 && (allowEmpty || value.isNotBlank()))
        require(value.none { it < ' ' || it == '\u007f' })
    }.isSuccess

    private fun JsonElement.obj(vararg keys: String): JsonObject = (this as? JsonObject ?: bad()).also { check(it.keys == keys.toSet()) }
    private fun JsonElement.string(maxBytes: Int, maxCodePoints: Int = Int.MAX_VALUE, allowEmpty: Boolean = false): String {
        val p = this as? JsonPrimitive ?: bad(); check(p.isString)
        val value = p.content
        val encoded = runCatching { Charsets.UTF_8.newEncoder().onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
            .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(value)).remaining() }.getOrNull()
        check(encoded != null && encoded <= maxBytes && value.codePointCount(0, value.length) <= maxCodePoints)
        check(value.none { it < ' ' || it == '\u007f' } && (allowEmpty || value.isNotBlank()))
        return value
    }
    private fun JsonElement.int(low: Int = 0, high: Int = Int.MAX_VALUE): Int {
        val p = this as? JsonPrimitive ?: bad()
        check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toIntOrNull()?.takeIf { it in low..high } ?: bad()
    }
    private fun JsonElement.bool(): Boolean {
        val p = this as? JsonPrimitive ?: bad(); check(!p.isString)
        return p.booleanOrNull ?: bad()
    }
    private fun JsonElement.array(max: Int): JsonArray = (this as? JsonArray ?: bad()).also { check(it.size <= max) }
    private fun page(o: JsonObject, requestedPage: Int, total: Int, count: Int) {
        check(o.getValue("page").int(1, 100000) == requestedPage)
        check(o.getValue("page_size").int(1, PAGE_SIZE) == PAGE_SIZE)
        check(o.getValue("total").int() == total)
        val expected = minOf(PAGE_SIZE, maxOf(0, total - (requestedPage - 1) * PAGE_SIZE))
        check(count == expected)
    }

    fun catalog(bytes: ByteArray, library: String, requestedPage: Int): FamilyTagsPage = try {
        check(PhoneDiscoveryWire.validLibrary(library) && requestedPage in 1..100000)
        val o = DiscoveryJson.parse(bytes).obj("library_id", "page", "page_size", "total", "items")
        check(o.getValue("library_id").string(128) == library)
        val total = o.getValue("total").int()
        val items = o.getValue("items").array(PAGE_SIZE).map { element ->
            val item = element.obj("name", "asset_count")
            FamilyTagChoice(item.getValue("name").string(512, 128), item.getValue("asset_count").int(1))
        }
        check(items.map { it.name }.distinct().size == items.size)
        page(o, requestedPage, total, items.size)
        FamilyTagsPage(library, requestedPage, PAGE_SIZE, total, items)
    } catch (e: ApiFailure) { throw e } catch (_: Exception) { bad() }

    fun assetsRequest(tag: String, requestedPage: Int): String {
        require(validTag(tag) && requestedPage in 1..100000)
        return buildJsonObject { put("tag", tag); put("page", requestedPage) }.toString()
            .also { require(it.toByteArray(Charsets.UTF_8).size <= 1024) }
    }

    fun assets(bytes: ByteArray, library: String, tag: String, requestedPage: Int): Gallery = try {
        check(PhoneDiscoveryWire.validLibrary(library) && validTag(tag) && requestedPage in 1..100000)
        val o = DiscoveryJson.parse(bytes).obj("library_id", "tag", "page", "page_size", "total", "originals_allowed", "items")
        check(o.getValue("library_id").string(128) == library)
        check(o.getValue("tag").string(512, 128) == tag)
        val total = o.getValue("total").int()
        val items = o.getValue("items").array(PAGE_SIZE).map { element ->
            val item = element.obj("id", "kind", "width", "height", "duration_sec", "taken_at", "thumbnail_url")
            val id = item.getValue("id").string(19)
            check(id.matches(Regex("[1-9][0-9]{0,18}")) && id.toLongOrNull() != null)
            val kind = item.getValue("kind").string(8); check(kind in setOf("image", "video", "other"))
            fun dimension(key: String): Int? = item.getValue(key).let { if (it == JsonNull) null else it.int(1, 1000000) }
            val duration = item.getValue("duration_sec").let { value ->
                if (value == JsonNull) null else {
                    val p = value as? JsonPrimitive ?: bad(); check(!p.isString)
                    (p.doubleOrNull ?: bad()).also { check(it.isFinite() && it in 0.0..1e9) }
                }
            }
            val taken = item.getValue("taken_at").let { if (it == JsonNull) null else it.string(64) }
            val thumbnail = item.getValue("thumbnail_url").string(2048)
            val base = "https://contract.invalid/".toHttpUrl()
            val expected = base.newBuilder().addPathSegment("assets").addPathSegment(id).addPathSegment("thumbnail")
                .addQueryParameter("library", library).build()
            check(thumbnail.startsWith('/') && !thumbnail.startsWith("//") && '\\' !in thumbnail && base.resolve(thumbnail) == expected)
            Asset(id, kind, dimension("width"), dimension("height"), duration, taken, thumbnail)
        }
        check(items.map { it.id }.distinct().size == items.size)
        page(o, requestedPage, total, items.size)
        Gallery(library, requestedPage, PAGE_SIZE, total.toLong(), o.getValue("originals_allowed").bool(), items)
    } catch (e: ApiFailure) { throw e } catch (_: Exception) { bad() }
}
