package dev.photohouse.connected.core

import kotlinx.serialization.json.*

/** Strict parser/encoder for resumable upload sessions. */
object UploadSessionWire {
    private const val MAX_IMAGE = 256L * 1024 * 1024
    private const val MAX_VIDEO = 16L * 1024 * 1024 * 1024
    private val BASE_FIELDS = setOf("upload_id", "bytes", "offset", "chunk_bytes", "state", "asset_id")
    private val OPTIONAL_FIELDS = setOf("destination_library_id", "approval_state", "library_id")
    private val LIBRARY_ID = Regex("[a-z0-9][a-z0-9_-]{2,63}")
    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun obj(e: JsonElement): JsonObject = (e as? JsonObject ?: bad()).also {
        if (!it.keys.containsAll(BASE_FIELDS) || (it.keys - BASE_FIELDS).any { key -> key !in OPTIONAL_FIELDS }) bad()
    }
    private fun text(o: JsonObject, key: String, regex: Regex): String = (o[key] as? JsonPrimitive)?.takeIf { it.isString }?.content?.also { if (!regex.matches(it)) bad() } ?: bad()
    private fun number(o: JsonObject, key: String, range: LongRange): Long {
        val p = o[key] as? JsonPrimitive ?: bad(); if (p.isString || !p.content.matches(Regex("0|[1-9][0-9]*"))) bad()
        return p.content.toLongOrNull()?.takeIf { it in range } ?: bad()
    }
    fun request(r: UploadSessionRequest): String {
        require(r.requestId.matches(Regex("[0-9a-f]{32}")) && r.batch.matches(Regex("[0-9a-f]{32}")))
        require(r.filename.isNotEmpty() && r.filename.length <= 200 && r.filename.none { it == '\u0000' || it == '\r' || it == '\n' })
        require(r.bytes in 1..if (r.kind == UploadKind.IMAGE) MAX_IMAGE else MAX_VIDEO)
        require(r.sha256.matches(Regex("[0-9a-f]{64}")))
        require(r.destinationLibraryId == null || r.destinationLibraryId.isNotBlank() &&
            r.destinationLibraryId.length <= 128 && r.destinationLibraryId.none(Char::isISOControl))
        return buildJsonObject {
            put("request_id", r.requestId); put("batch", r.batch); put("filename", r.filename); put("bytes", r.bytes)
            put("sha256", r.sha256); put("kind", if (r.kind == UploadKind.IMAGE) "image" else "video")
            r.destinationLibraryId?.let { put("destination_library_id", it) }
        }.toString()
    }
    fun parse(bytes: ByteArray): UploadSession = try {
        val o = obj(DiscoveryJson.parse(bytes, 16 * 1024))
        val id = text(o, "upload_id", Regex("[0-9a-f]{32}")); val size = number(o, "bytes", 1..MAX_VIDEO)
        val offset = number(o, "offset", 0..size); val chunk = number(o, "chunk_bytes", 4L * 1024 * 1024..4L * 1024 * 1024)
        val state = text(o, "state", Regex("uploading|complete|cancelled"))
        val asset = o["asset_id"].let { if (it == JsonNull) null else text(o, "asset_id", Regex("[1-9][0-9]{0,18}")) }
        if ((state == "complete") != (asset != null) || state == "cancelled" && asset != null || state == "complete" && offset != size) bad()
        val destination = if ("destination_library_id" in o) text(o, "destination_library_id", LIBRARY_ID) else null
        val hasApproval = "approval_state" in o
        val hasLibrary = "library_id" in o
        if (hasLibrary && !hasApproval) bad()
        val approval = if (hasApproval) {
            if (state != "complete" || destination == null) bad()
            text(o, "approval_state", Regex("automatic|manual|awaiting_review|unavailable"))
        } else null
        val library = if (hasLibrary) text(o, "library_id", LIBRARY_ID) else null
        when (approval) {
            "automatic", "manual" -> if (library != destination) bad()
            "awaiting_review", "unavailable" -> if (hasLibrary) bad()
        }
        UploadSession(id, size, offset, chunk.toInt(), state, asset, destination, approval, library)
    } catch (e: ApiFailure) { throw e } catch (_: Exception) { bad() }
}
