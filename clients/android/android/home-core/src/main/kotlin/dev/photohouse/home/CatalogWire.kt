package dev.photohouse.home

import kotlinx.serialization.json.*

/** Frozen home-catalog v2. Strict keys and bounded UTF-8 parsing; no permissive v1 fallback. */
object CatalogWire {
    const val ORIGINAL_MAX_BYTES = 64 * 1024 * 1024
    const val VIDEO_MAX_BYTES = 34359738368L
    const val READ_BYTES = 262144
    private fun bad(): Nothing = throw HomeFailure(HomeError.INVALID)
    private fun check(ok: Boolean) { if (!ok) bad() }
    private fun JsonElement.obj(vararg keys: String): JsonObject {
        val o = this as? JsonObject ?: bad(); check(o.keys == keys.toSet()); return o
    }
    private fun JsonElement.number(low: Long = 1, high: Long = Int.MAX_VALUE.toLong()): Long {
        val p = this as? JsonPrimitive ?: bad()
        check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toLongOrNull()?.takeIf { it in low..high } ?: bad()
    }
    private fun JsonElement.str(max: Int): String {
        val p = this as? JsonPrimitive ?: bad(); check(p.isString)
        check(p.content.toByteArray().size <= max && p.content.none { it < ' ' && it != '\n' && it != '\t' })
        return p.content
    }
    private fun JsonElement.bool(): Boolean {
        val p = this as? JsonPrimitive ?: bad(); check(!p.isString); return p.booleanOrNull ?: bad()
    }
    private fun JsonElement.hash(): String = str(64).also { check(it.matches(Regex("[0-9a-f]{64}"))) }
    private fun JsonElement.reason(): MediaUnavailable {
        val o = obj("state", "reason"); check(o.getValue("state").str(20) == "unavailable")
        return when (o.getValue("reason").str(32)) {
            "not_prepared" -> MediaUnavailable.NOT_PREPARED
            "source_missing" -> MediaUnavailable.SOURCE_MISSING
            "unsupported" -> MediaUnavailable.UNSUPPORTED
            "preparation_failed" -> MediaUnavailable.PREPARATION_FAILED
            else -> bad()
        }
    }
    fun previewPath(id: Int, variant: Variant, revision: Int, version: Int = 2) = "/home/v$version/assets/$id/preview?variant=${variant.wire}&revision=$revision"
    fun videoPath(id: Int, revision: Int, version: Int = 2) = "/home/v$version/assets/$id/video?revision=$revision"
    fun feed(bytes: ByteArray, page: Int, requestedRevision: Int? = null, version: Int = 2, selection: BrowseSelection? = null): HomeFeed = try {
        check(version in 2..3)
        check(page in 1..100000 && (page == 1 || requestedRevision != null))
        check(selection == null || version == 3)
        val keys = arrayOf("version", "revision", "library", "page", "page_size", "total", "has_more", "items")
        val o = HomeWire.parse(bytes).obj(*(if (selection == null) keys else keys + "browse"))
        val counts = selection?.let {
            val b = o.getValue("browse").obj("version", "availability", "order", "media", "ready_total", "matching_total")
            check(b.getValue("version").number() == 1L)
            check(b.getValue("availability").str(16) == it.availability.wire && b.getValue("order").str(16) == it.order.wire && b.getValue("media").str(16) == it.media.wire)
            BrowseCounts(b.getValue("ready_total").number(0, 100000).toInt(), b.getValue("matching_total").number(0, 100000).toInt()).also { c -> check(c.ready <= c.matching) }
        }
        check(o.getValue("version").number() == version.toLong())
        val revision = o.getValue("revision").number().toInt()
        check(requestedRevision == null || revision == requestedRevision)
        check(o.getValue("page").number() == page.toLong() && o.getValue("page_size").number() == 50L)
        val total = o.getValue("total").number(0, 100000).toInt()
        val more = o.getValue("has_more").bool(); check(more == (page * 50 < total))
        val library = o.getValue("library").obj("id", "title")
        val id = library.getValue("id").str(64); check(id.matches(Regex("[a-z0-9-]{1,64}")))
        val items = (o.getValue("items") as? JsonArray ?: bad()).map { element ->
            val keys = arrayOf("id", "kind", "label", "width", "height", "previews", "video", "originals_allowed")
            val a = element.obj(*(if (version == 3) keys + "original" else keys))
            val originalsAllowed = a.getValue("originals_allowed").bool()
            if (version == 2) check(!originalsAllowed)
            for (dimension in listOf("width", "height")) a.getValue(dimension).let { if (it != JsonNull) it.number(1, 1000000) }
            val assetId = a.getValue("id").number().toInt()
            val kind = when (a.getValue("kind").str(16)) {
                "photo" -> AssetKind.PHOTO; "video" -> AssetKind.VIDEO; "unsupported" -> AssetKind.UNSUPPORTED; else -> bad()
            }
            val previews = a.getValue("previews").obj("grid", "display")
            fun preview(v: Variant): Pair<Preview?, MediaUnavailable?> {
                val raw = previews.getValue(v.wire); val p = raw as? JsonObject ?: bad()
                if (p["state"] == JsonPrimitive("unavailable")) return null to raw.reason()
                if (version == 3 && p["state"] == JsonPrimitive("on_demand")) {
                    p.obj("state", "url"); check(kind == AssetKind.PHOTO)
                    val url = p.getValue("url").str(160); check(url == previewPath(assetId, v, revision, version))
                    return Preview(0, 0, v.bytes, "", url, onDemand = true) to null
                }
                p.obj("state", "width", "height", "bytes", "sha256", "url")
                check(p.getValue("state").str(20) == "ready")
                val w = p.getValue("width").number(1, v.edge.toLong()).toInt()
                val h = p.getValue("height").number(1, v.edge.toLong()).toInt(); check(w.toLong() * h <= v.pixels)
                val url = p.getValue("url").str(160); check(url == previewPath(assetId, v, revision, version))
                return Preview(w, h, p.getValue("bytes").number(1, v.bytes.toLong()).toInt(), p.getValue("sha256").hash(), url) to null
            }
            val grid = preview(Variant.GRID); val display = preview(Variant.DISPLAY)
            var video: HomeVideo? = null; var unavailable: MediaUnavailable? = null
            val raw = a.getValue("video")
            if (kind != AssetKind.VIDEO) check(raw == JsonNull)
            else {
                val v = raw as? JsonObject ?: bad()
                if (v["state"] == JsonPrimitive("unavailable")) unavailable = v.reason()
                else {
                    val direct = version == 3 && v["state"] == JsonPrimitive("direct")
                    val keys = arrayOf("state", "mime", "video_codec", "audio_codec", "width", "height", "duration_ms", "bytes", "url")
                    v.obj(*(if (direct) keys else keys + "sha256"))
                    check(!direct || originalsAllowed)
                    check((direct || v.getValue("state").str(20) == "ready") && v.getValue("mime").str(32) == "video/mp4" && v.getValue("video_codec").str(8) == "h264")
                    val audio = v.getValue("audio_codec").let { if (it == JsonNull) null else it.str(8).also { codec -> check(codec == "aac") } }
                    val w = v.getValue("width").number(1, 1920).toInt(); val h = v.getValue("height").number(1, 1920).toInt(); check(w.toLong() * h <= 2073600)
                    val url = v.getValue("url").str(160); check(url == videoPath(assetId, revision, version))
                    video = HomeVideo(w, h, v.getValue("duration_ms").number(1, 86400000).toInt(), v.getValue("bytes").number(1, VIDEO_MAX_BYTES), if (direct) "" else v.getValue("sha256").hash(), url, audio, direct)
                }
            }
            val original = if (version == 3 && a["original"] != JsonNull) {
                check(originalsAllowed && kind == AssetKind.PHOTO)
                val o = a.getValue("original").obj("mime", "bytes", "width", "height", "url")
                val mime = o.getValue("mime").str(32); check(mime in listOf("image/jpeg", "image/png"))
                val w = o.getValue("width").number(1, 32768).toInt(); val h = o.getValue("height").number(1, 32768).toInt()
                check(w.toLong() * h <= 256_000_000)
                val url = o.getValue("url").str(160); check(url == "/home/v3/assets/$assetId/original?revision=$revision")
                HomeOriginal(mime, o.getValue("bytes").number(1, ORIGINAL_MAX_BYTES.toLong()).toInt(), w, h, url)
            } else null
            if (version == 3) check(originalsAllowed == (original != null || video?.direct == true))
            HomeAsset(assetId, a.getValue("label").str(256), grid.first, display.first, kind, video, grid.second, display.second, unavailable, original)
        }
        check(items.size == minOf(50, maxOf(0, total - (page - 1) * 50)))
        check(items.map { it.id }.distinct().size == items.size)
        if (selection != null && counts != null) {
            check(total == if (selection.availability == Availability.READY) counts.ready else counts.matching)
            check(items.all { selection.media == BrowseMedia.ALL || it.kind == if (selection.media == BrowseMedia.PHOTOS) AssetKind.PHOTO else AssetKind.VIDEO })
            check(selection.availability != Availability.READY || items.all { it.deliveryReady() })
            val visibleReady = items.count { it.deliveryReady() }
            check(visibleReady <= counts.ready)
            if (selection.availability == Availability.ALL) {
                check(items.size - visibleReady <= counts.matching - counts.ready)
                if (selection.order == BrowseOrder.READY_FIRST) check(items.withIndex().all { (index, asset) ->
                    asset.deliveryReady() == ((page - 1) * 50 + index < counts.ready)
                })
            }
        }
        check(items.zipWithNext().all { (a, b) ->
            if (selection?.order == BrowseOrder.READY_FIRST && a.deliveryReady() != b.deliveryReady()) a.deliveryReady()
            else a.id > b.id
        })
        HomeFeed(revision, id, library.getValue("title").str(256), page, 50, total, more, items, version = version, browseCounts = counts)
    } catch (e: HomeFailure) { throw e } catch (_: Exception) { bad() }
}
