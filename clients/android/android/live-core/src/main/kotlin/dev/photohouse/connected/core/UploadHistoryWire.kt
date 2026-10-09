package dev.photohouse.connected.core

import kotlinx.serialization.json.*

/** Strict parser for the protected account-scoped upload history response. */
object UploadHistoryWire {
    private const val PAGE_SIZE = 10
    private const val MAX_BYTES = 16L * 1024 * 1024 * 1024
    private const val MAX_IMAGE_BYTES = 256L * 1024 * 1024
    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(ok: Boolean) { if (!ok) bad() }
    private fun JsonElement.obj(vararg keys: String): JsonObject =
        (this as? JsonObject ?: bad()).also { check(it.keys == keys.toSet()) }
    private fun JsonElement.int(low: Int, high: Int): Int {
        val p = this as? JsonPrimitive ?: bad()
        check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toLongOrNull()?.takeIf { it in low.toLong()..high.toLong() }?.toInt() ?: bad()
    }
    private fun JsonElement.long(low: Long, high: Long): Long {
        val p = this as? JsonPrimitive ?: bad()
        check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toLongOrNull()?.takeIf { it in low..high } ?: bad()
    }
    private fun JsonElement.str(max: Int): String {
        val p = this as? JsonPrimitive ?: bad(); check(p.isString)
        check(p.content.isNotEmpty() && p.content.codePointCount(0, p.content.length) <= max &&
            p.content.none { it < ' ' || it == '\u007f' })
        return p.content
    }
    private fun JsonElement.nullableLibrary(): String? = if (this == JsonNull) null else str(128).also { check(PhoneDiscoveryWire.validLibrary(it)) }

    fun parse(bytes: ByteArray, requestedPage: Int): UploadHistoryPage {
        if (requestedPage !in 1..100000 || bytes.size !in 1..64 * 1024) bad()
        return try {
            val root = DiscoveryJson.parse(bytes).obj("page", "page_size", "total", "items")
            val page = root.getValue("page").int(1, 100000)
            val pageSize = root.getValue("page_size").int(PAGE_SIZE, PAGE_SIZE)
            check(page == requestedPage)
            val total = root.getValue("total").int(0, Int.MAX_VALUE)
            val items = (root.getValue("items") as? JsonArray ?: bad()).also { check(it.size <= PAGE_SIZE) }.map { element ->
                val item = element.obj("asset_id", "created_at", "bytes", "kind", "state", "library_id")
                val state = item.getValue("state").str(32); check(state in setOf("awaiting_review", "available", "unavailable"))
                val library = item.getValue("library_id").nullableLibrary()
                check((state == "available") == (library != null))
                UploadHistoryItem(item.getValue("asset_id").str(19).also { check(PhoneDiscoveryWire.validId(it)) },
                    item.getValue("created_at").long(0, 253402300799),
                    item.getValue("bytes").long(1, MAX_BYTES).also { bytes -> check(item.getValue("kind").str(8).let { kind -> kind == "image" && bytes <= MAX_IMAGE_BYTES || kind == "video" }) },
                    item.getValue("kind").str(8), state, library)
            }
            check(items.map { it.assetId }.distinct().size == items.size)
            check(items.size.toLong() == minOf(PAGE_SIZE.toLong(), maxOf(0L, total.toLong() - (page - 1L) * PAGE_SIZE)))
            UploadHistoryPage(page, pageSize, total, items)
        } catch (e: ApiFailure) { throw e } catch (_: Exception) { bad() }
    }
}
