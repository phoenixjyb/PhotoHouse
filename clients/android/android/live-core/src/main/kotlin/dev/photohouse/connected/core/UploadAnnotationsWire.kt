package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import java.nio.charset.CodingErrorAction
import java.util.UUID
import java.security.MessageDigest

/** Exact c4 text annotation request and bounded response parsing. */
internal object UploadAnnotationsWire {
    private val requestKeys = setOf("batch", "asset_id", "language", "consent", "mutation_id", "text")
    private val itemKeys = setOf("id", "scope", "asset_id", "batch", "library_id", "author_id", "kind",
        "original_text", "audio_url", "mime", "duration_ms", "sha256", "language",
        "local_processing_consent", "created_at", "derivation", "tags")
    private val derivationKeys = setOf("revision", "state", "transcript", "polished_text", "provider", "model", "error_code")
    private val tagKeys = setOf("tag", "status", "revision")

    fun request(value: UploadTextAnnotationRequest): String {
        require(value.batch.matches(Regex("[0-9a-f]{32}")))
        require(value.assetId.isEmpty() || validAssetId(value.assetId))
        require(value.language in setOf("en", "zh", "mixed", "und"))
        require(value.consent in setOf("yes", "no"))
        require(runCatching { UUID.fromString(value.mutationId).toString() == value.mutationId }.getOrDefault(false))
        val encoded = strictUtf8(value.text)
        require(encoded.size <= MAX_TEXT_BYTES)
        val json = buildJsonObject {
            put("batch", value.batch); put("asset_id", value.assetId); put("language", value.language)
            put("consent", value.consent); put("mutation_id", value.mutationId); put("text", value.text)
        }
        check(json.keys == requestKeys)
        return json.toString()
    }

    data class AudioInfo(val durationMs: Long, val sha256: String)

    fun audioInfo(value: UploadAudioAnnotationRequest): AudioInfo {
        require(value.batch.matches(Regex("[0-9a-f]{32}")))
        require(value.assetId.isEmpty() || validAssetId(value.assetId))
        require(value.language in setOf("en", "zh", "mixed", "und") && value.consent in setOf("yes", "no"))
        require(runCatching { UUID.fromString(value.mutationId).toString() == value.mutationId }.getOrDefault(false))
        val wav = value.wav
        require(wav.size in 44..MAX_AUDIO_BYTES && ascii(wav, 0, "RIFF") && ascii(wav, 8, "WAVE"))
        require(u32(wav, 4) == wav.size.toLong() - 8)
        var offset = 12L
        var rate = 0L
        var dataBytes = -1L
        var formatSeen = false
        while (offset + 8 <= wav.size) {
            val at = offset.toInt()
            val size = u32(wav, at + 4)
            val end = offset + 8 + size
            require(end <= wav.size)
            when {
                ascii(wav, at, "fmt ") -> {
                    require(!formatSeen && size >= 16)
                    formatSeen = true
                    rate = u32(wav, at + 12)
                    require(u16(wav, at + 8) == 1 && u16(wav, at + 10) == 1 &&
                        rate in setOf(16000L, 48000L) && u32(wav, at + 16) == rate * 2 &&
                        u16(wav, at + 20) == 2 && u16(wav, at + 22) == 16)
                }
                ascii(wav, at, "data") -> { require(dataBytes < 0); dataBytes = size }
            }
            offset = end + (size and 1L)
        }
        require(offset == wav.size.toLong() && formatSeen && dataBytes > 0 && dataBytes % 2L == 0L)
        val frames = dataBytes / 2
        require(frames in rate / 2..rate * 60)
        val sha = MessageDigest.getInstance("SHA-256").digest(wav).joinToString("") { "%02x".format(it) }
        return AudioInfo(frames * 1000 / rate, sha)
    }

    private fun ascii(bytes: ByteArray, at: Int, text: String): Boolean =
        at >= 0 && at + text.length <= bytes.size && text.indices.all { bytes[at + it].toInt() == text[it].code }
    private fun u16(bytes: ByteArray, at: Int): Int = (bytes[at].toInt() and 255) or ((bytes[at + 1].toInt() and 255) shl 8)
    private fun u32(bytes: ByteArray, at: Int): Long = u16(bytes, at).toLong() or (u16(bytes, at + 2).toLong() shl 16)

    fun parseItem(bytes: ByteArray): UploadAnnotation = try {
        val root = DiscoveryJson.parse(bytes, ANNOTATION_ITEM_LIMIT).jsonObject
        require(root.keys == itemKeys)
        parseAnnotation(root)
    } catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_RESPONSE) }

    fun parsePage(bytes: ByteArray, requestedLibrary: String, requestedAsset: String, requestedPage: Int): UploadAnnotationPage = try {
        val root = DiscoveryJson.parse(bytes, ANNOTATION_PAGE_LIMIT).jsonObject
        require(root.keys == setOf("library_id", "asset_id", "batch", "page", "page_size", "total", "items"))
        val library = root.string("library_id")
        val asset = root.string("asset_id")
        val batch = root.string("batch").also { require(it.matches(Regex("[0-9a-f]{32}"))) }
        val page = root.integer("page").toIntExact()
        val pageSize = root.integer("page_size").toIntExact()
        val total = root.integer("total").toIntExact()
        require(library == requestedLibrary && asset == requestedAsset && page == requestedPage && pageSize == 20 && total >= 0)
        val items = root.getValue("items").jsonArray.map { parseAnnotation(it.jsonObject) }
        require(items.size <= 20 && total >= items.size && items.all {
            it.libraryId == library && it.batch == batch && (it.assetId.isEmpty() || it.assetId == asset)
        })
        UploadAnnotationPage(library, asset, batch, page, pageSize, total, items)
    } catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_RESPONSE) }

    private fun parseAnnotation(root: JsonObject): UploadAnnotation {
        require(root.keys == itemKeys)
        val d = root.getValue("derivation").jsonObject
        require(d.keys == derivationKeys)
        val tags = root.getValue("tags").jsonArray.map {
            val tag = it.jsonObject; require(tag.keys == tagKeys)
            UploadAnnotationTag(tag.string("tag"), tag.string("status"), tag.integer("revision").toIntExact())
        }
        val assetId = root.nullableString("asset_id") ?: ""
        val batch = root.string("batch")
        val kind = root.string("kind")
        val language = root.string("language")
        val consent = root.string("local_processing_consent")
        val original = root.nullableString("original_text")
        require(assetId.isEmpty() || validAssetId(assetId))
        require(batch.matches(Regex("[0-9a-f]{32}")) && kind in setOf("text", "audio"))
        require(root.string("scope") == if (assetId.isEmpty()) "folder" else "item")
        require(language in setOf("en", "zh", "mixed", "und") && consent in setOf("yes", "no"))
        require(if (kind == "text") original != null && original.isNotBlank() && strictUtf8(original).size <= MAX_TEXT_BYTES
            else original == null)
        val sha = root.nullableString("sha256")
        require(sha == null || sha.matches(Regex("[0-9a-f]{64}")))
        val duration = root.nullableInteger("duration_ms")
        require(duration == null || duration >= 0)
        val derivationRevision = d.integer("revision").toIntExact()
        require(derivationRevision >= 0 && d.string("state").isNotBlank())
        return UploadAnnotation(
            root.string("id"), root.string("scope"), assetId, batch, root.string("library_id"),
            root.string("author_id"), kind, original, root.nullableString("audio_url"),
            root.nullableString("mime"), duration, sha,
            language, consent, root.integer("created_at").also { require(it >= 0) },
            UploadAnnotationDerivation(derivationRevision, d.string("state"), d.nullableString("transcript"),
                d.nullableString("polished_text"), d.nullableString("provider"), d.nullableString("model"), d.nullableString("error_code")), tags)
    }

    private fun JsonObject.string(key: String) = getValue(key).jsonPrimitive.content.also { require(getValue(key).jsonPrimitive.isString) }
    private fun JsonObject.nullableString(key: String): String? = getValue(key).let { if (it == JsonNull) null else it.jsonPrimitive.content.also { _ -> require(it.jsonPrimitive.isString) } }
    private fun JsonObject.integer(key: String) = getValue(key).jsonPrimitive.content.toLong().also { require(!getValue(key).jsonPrimitive.isString) }
    private fun JsonObject.nullableInteger(key: String): Long? = getValue(key).let { if (it == JsonNull) null else it.jsonPrimitive.content.toLong().also { _ -> require(!it.jsonPrimitive.isString) } }
    private fun Long.toIntExact(): Int = Math.toIntExact(this)
    private fun validAssetId(value: String) = value.matches(Regex("[1-9][0-9]{0,18}")) && value.toLongOrNull() != null
    private fun strictUtf8(value: String) = Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(value)).let { buffer ->
            ByteArray(buffer.remaining()).also { buffer.get(it) }
        }

    const val MAX_TEXT_BYTES = 16 * 1024
    const val MAX_AUDIO_BYTES = 2 * 1024 * 1024
    const val ANNOTATION_ITEM_LIMIT = 128 * 1024
    const val ANNOTATION_PAGE_LIMIT = 4 * 1024 * 1024
}
