package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.Collections

data class ProtectedLibraryAlbum(
    val id: String,
    val title: String,
    val titleZh: String,
    val description: String,
    val theme: String,
    val assetIds: List<String>,
    val coverAssetId: String,
    val revision: String,
    val needsReview: Boolean,
)

data class ProtectedLibraryAlbumPage(
    val libraryId: String,
    val page: Int,
    val total: Long,
    val pageSize: Int,
    val canManage: Boolean,
    val items: List<ProtectedLibraryAlbum>,
)

/** Strict reader for the existing protected `/library-albums` response. */
internal object ProtectedLibraryAlbumsWire {
    private val themes = setOf("birthday", "trip", "growing_up", "grandparents", "year_in_review", "seasonal", "custom")

    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(value: Boolean) { if (!value) bad() }
    private fun obj(value: JsonElement?): JsonObject = value as? JsonObject ?: bad()
    private fun array(value: JsonElement?, max: Int): JsonArray = (value as? JsonArray)?.also { check(it.size <= max) } ?: bad()
    private fun integer(value: JsonElement?, max: Int): Int {
        val p = value as? JsonPrimitive ?: bad()
        check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toIntOrNull()?.takeIf { it <= max } ?: bad()
    }
    private fun long(value: JsonElement?): Long {
        val p = value as? JsonPrimitive ?: bad()
        check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toLongOrNull() ?: bad()
    }
    private fun bool(value: JsonElement?): Boolean {
        val p = value as? JsonPrimitive ?: bad()
        check(!p.isString)
        return p.booleanOrNull ?: bad()
    }
    private fun string(value: JsonElement?, maxCodePoints: Int, maxUtf8Bytes: Int,
                       allowBlank: Boolean = true, allowLineBreaks: Boolean = false): String {
        val p = value as? JsonPrimitive ?: bad()
        check(p.isString)
        val text = p.content
        check(text.codePointCount(0, text.length) <= maxCodePoints)
        check(allowBlank || text.isNotBlank())
        check(text.none { it.isISOControl() && !(allowLineBreaks && it in "\n\t") })
        val bytes = try {
            Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(text)).remaining()
        } catch (_: Exception) { bad() }
        check(bytes <= maxUtf8Bytes)
        return text
    }
    private fun canonicalAssetId(text: String) {
        check(text.matches(Regex("[1-9][0-9]{0,18}")) && text.toLongOrNull() != null)
    }
    private fun exact(o: JsonObject, vararg keys: String) { check(o.keys == keys.toSet()) }

    fun decodePage(bytes: ByteArray, expectedLibrary: String, expectedPage: Int): ProtectedLibraryAlbumPage = try {
        check(bytes.size <= 256 * 1024 && expectedPage in 1..100000 && PhoneDiscoveryWire.validLibrary(expectedLibrary))
        val root = obj(DiscoveryJson.parse(bytes, 256 * 1024, 1000))
        exact(root, "items", "page", "total", "page_size", "can_manage")
        check(integer(root["page"], 100000) == expectedPage)
        check(integer(root["page_size"], 10) == 10)
        val total = long(root["total"])
        val rows = array(root["items"], 10).map(::album)
        check(rows.map { it.id }.distinct().size == rows.size)
        ProtectedLibraryAlbumPage(expectedLibrary, expectedPage, total, 10, bool(root["can_manage"]),
            Collections.unmodifiableList(ArrayList(rows)))
    } catch (failure: ApiFailure) { throw failure }
    catch (_: Exception) { bad() }

    private fun album(value: JsonElement): ProtectedLibraryAlbum {
        val row = obj(value)
        exact(row, "id", "title", "title_zh", "description", "theme", "asset_ids", "cover_asset_id", "revision", "needs_review")
        val id = string(row["id"], 19, 19, allowBlank = false)
        canonicalAssetId(id)
        val title = string(row["title"], 160, 640, allowBlank = false, allowLineBreaks = true)
        val titleZh = string(row["title_zh"], 160, 640, allowLineBreaks = true)
        val description = string(row["description"], 1000, 4000, allowLineBreaks = true)
        val theme = string(row["theme"], 32, 32, allowBlank = false)
        check(theme in themes)
        val assets = array(row["asset_ids"], 60).map { value ->
            string(value, 19, 19, allowBlank = false).also(::canonicalAssetId)
        }
        check(assets.distinct().size == assets.size)
        val cover = string(row["cover_asset_id"], 19, 19)
        if (cover.isEmpty()) check(assets.isEmpty()) else {
            canonicalAssetId(cover)
            check(cover in assets)
        }
        val revision = string(row["revision"], 64, 64, allowBlank = false)
        check(revision.matches(Regex("[0-9a-f]{64}")))
        return ProtectedLibraryAlbum(id, title, titleZh, description, theme,
            Collections.unmodifiableList(ArrayList(assets)), cover, revision, bool(row["needs_review"]))
    }
}
