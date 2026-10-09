package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import dev.photohouse.protocol.DateHint
import kotlinx.serialization.json.*
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction

data class AssistantCapabilities(val enabled: Boolean, val text: Boolean, val transcribe: Boolean, val speech: Boolean, val maxAudioSeconds: Int)
data class AssistantEffect(val type: String, val assetId: String)
data class AssistantTurn(
    val kind: String,
    val reply: String,
    val context: JsonObject?,
    val filters: JsonObject?,
    val items: List<Asset>,
    val total: Int,
    val hasMore: Boolean,
    val effect: AssistantEffect?, val receipt: AssistantRequestReceipt? = null,
)
data class AssistantTranscript(
    val text: String, val language: String, val receipt: AssistantRequestReceipt? = null,
    /** Client-local UI identity; never serialized or accepted as server correlation. */
    val localRequestId: String = "",
)
data class AssistantRequestReceipt(val requestId: String, val tracking: String, val status: String?)
data class AssistantSpeechResult(val bytes: ByteArray, val receipt: AssistantRequestReceipt)
data class AssistantReceipt(
    val requestId: String, val operation: String, val parentRequestId: String?, val status: String,
    val createdAt: String, val updatedAt: String, val expiresAt: String, val httpStatus: Int?,
    val errorCode: String?, val inputText: String?, val recognizedText: String?, val resultKind: String?,
    val resultTotal: Int?, val clientOutcome: String?,
)

/** Strict, bounded parsing for the protected phone assistant envelope. */
object AssistantWire {
    private const val RESPONSE_LIMIT = 256 * 1024
    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(ok: Boolean) { if (!ok) bad() }
    private inline fun <T> guarded(block: () -> T): T = try { block() } catch (e: ApiFailure) { throw e } catch (_: Exception) { bad() }
    private fun JsonElement.obj(vararg keys: String): JsonObject = (this as? JsonObject ?: bad()).also { check(it.keys == keys.toSet()) }
    private fun JsonElement.str(max: Int): String {
        val p = this as? JsonPrimitive ?: bad(); check(p.isString)
        check(p.content.codePointCount(0, p.content.length) <= max && p.content.none { it < ' ' && it !in "\n\t" })
        return p.content
    }
    private fun JsonElement.bool(): Boolean = (this as? JsonPrimitive)?.booleanOrNull ?: bad()
    private fun JsonElement.int(max: Int): Int {
        val p = this as? JsonPrimitive ?: bad(); check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toIntOrNull()?.takeIf { it in 0..max } ?: bad()
    }
    private fun JsonElement.optionalObject(): JsonObject? = if (this == JsonNull) null else this as? JsonObject ?: bad()
    private fun contextSize(value: JsonObject?) {
        if (value != null) check(value.toString().toByteArray(Charsets.UTF_8).size <= 16 * 1024)
    }

    fun validRequestId(value: String): Boolean = value.matches(Regex("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"))
    fun requestReceipt(headers: Map<String, String>, sentId: String): AssistantRequestReceipt {
        if (!validRequestId(sentId)) throw ApiFailure(FailureKind.INVALID_INPUT)
        val tracking = headers["X-PhotoHouse-Tracking"] ?: return AssistantRequestReceipt(sentId, "unknown", null)
        if (tracking !in setOf("enabled", "disabled")) bad()
        val id = headers["X-PhotoHouse-Request-Id"]
        val status = headers["X-PhotoHouse-Receipt-Status"]
        if (tracking == "disabled") {
            if (id != null || status != null) bad()
        } else {
            if (id != sentId || !validRequestId(id)) bad()
            if (status !in setOf("received", "succeeded", "failed", "interrupted")) bad()
        }
        return AssistantRequestReceipt(sentId, tracking, status)
    }
    fun receipt(bytes: ByteArray, expectedId: String): AssistantReceipt = guarded {
        check(bytes.size in 1..16 * 1024 && validRequestId(expectedId))
        val o = DiscoveryJson.parse(bytes).obj("version", "request_id", "operation", "parent_request_id", "status", "created_at", "updated_at", "expires_at", "http_status", "error_code", "input_text", "recognized_text", "result_kind", "result_total", "client_outcome")
        check(o.getValue("version").int(1) == 1)
        fun nullableString(key: String, max: Int): String? = o.getValue(key).let { if (it == JsonNull) null else it.str(max) }
        val id = o.getValue("request_id").str(36); check(id == expectedId && validRequestId(id))
        val operation = o.getValue("operation").str(16); check(operation in setOf("transcribe", "turn", "speech"))
        val parent = nullableString("parent_request_id", 36); check(parent == null || validRequestId(parent))
        val status = o.getValue("status").str(16); check(status in setOf("received", "succeeded", "failed", "interrupted"))
        val http = o.getValue("http_status").let { if (it == JsonNull) null else it.int(599) }
        check(http == null || http in 100..599)
        check(status != "received" || http == null)
        check(status !in setOf("succeeded", "failed") || http != null)
        val resultTotal = o.getValue("result_total").let { if (it == JsonNull) null else it.int(100000) }
        val resultKind = nullableString("result_kind", 24); check(resultKind == null || resultKind in setOf("results", "open", "clarification", "unsupported"))
        val outcome = nullableString("client_outcome", 24); check(outcome == null || outcome in setOf("displayed", "open_requested", "failed", "cancelled"))
        val created = o.getValue("created_at").str(64); val updated = o.getValue("updated_at").str(64); val expires = o.getValue("expires_at").str(64)
        check(listOf(created, updated, expires).all { it.endsWith("Z") && runCatching { java.time.Instant.parse(it) }.isSuccess })
        AssistantReceipt(id, operation, parent, status, created, updated, expires, http,
            nullableString("error_code", 64), nullableString("input_text", 1024), nullableString("recognized_text", 4096), resultKind, resultTotal, outcome)
    }

    fun request(library: String, text: String, context: JsonObject?): String {
        if (!PhoneDiscoveryWire.validLibrary(library)) throw ApiFailure(FailureKind.INVALID_INPUT)
        val encoder = Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
        val bytes = runCatching { encoder.encode(CharBuffer.wrap(text)).remaining() }.getOrElse { throw ApiFailure(FailureKind.INVALID_INPUT) }
        if (text.isBlank() || bytes > 1024 || text.any { it == '\u0000' || it == '\r' }) throw ApiFailure(FailureKind.INVALID_INPUT)
        if (context != null && context.toString().toByteArray(Charsets.UTF_8).size > 16 * 1024) throw ApiFailure(FailureKind.INVALID_INPUT)
        return buildJsonObject {
            put("library_id", library); put("text", text)
            put("context", context ?: JsonNull)
        }.toString().also { require(it.toByteArray(Charsets.UTF_8).size <= 20 * 1024) }
    }

    fun speechRequest(library: String, context: JsonObject?, language: String): String {
        if (!PhoneDiscoveryWire.validLibrary(library) || language !in setOf("zh", "en")) throw ApiFailure(FailureKind.INVALID_INPUT)
        if (context == null || context.toString().toByteArray(Charsets.UTF_8).size > 16 * 1024) throw ApiFailure(FailureKind.INVALID_INPUT)
        return buildJsonObject { put("library_id", library); put("context", context); put("language", language) }.toString()
    }

    fun speechAudio(bytes: ByteArray): ByteArray {
        if (bytes.size !in 46..(2 * 1024 * 1024) || !bytes.copyOfRange(0, 4).contentEquals("RIFF".toByteArray()) ||
            !bytes.copyOfRange(8, 12).contentEquals("WAVE".toByteArray())) throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return bytes
    }

    fun capabilities(bytes: ByteArray): AssistantCapabilities = guarded {
        check(bytes.size in 1..4096)
        val o = DiscoveryJson.parse(bytes).obj("version", "enabled", "text", "transcribe", "speech", "max_audio_seconds")
        check(o.getValue("version").int(1) == 1)
        AssistantCapabilities(o.getValue("enabled").bool(), o.getValue("text").bool(), o.getValue("transcribe").bool(),
            o.getValue("speech").bool(), o.getValue("max_audio_seconds").int(30))
            .also { check((it.transcribe == (it.maxAudioSeconds > 0)) && (!it.text || it.enabled) && (!it.speech || it.enabled)) }
    }

    fun transcript(bytes: ByteArray): AssistantTranscript = guarded {
        check(bytes.size in 1..8192)
        val o = DiscoveryJson.parse(bytes).obj("version", "text", "language")
        check(o.getValue("version").int(1) == 1)
        val text = o.getValue("text").str(2048)
        val language = o.getValue("language").str(16)
        check(language in setOf("zh", "en", "mixed", "unknown"))
        AssistantTranscript(text, language)
    }

    fun response(bytes: ByteArray, library: String): AssistantTurn = guarded {
        check(bytes.size in 1..RESPONSE_LIMIT && PhoneDiscoveryWire.validLibrary(library))
        val o = DiscoveryJson.parse(bytes).obj("version", "kind", "reply", "context", "filters", "items", "total", "has_more", "effect")
        check(o.getValue("version").int(1) == 1)
        val kind = o.getValue("kind").str(24); check(kind in setOf("results", "open", "clarification", "unsupported"))
        val reply = o.getValue("reply").str(2000)
        val context = o.getValue("context").optionalObject(); contextSize(context)
        val filters = o.getValue("filters").optionalObject()
        val total = o.getValue("total").int(100000)
        val hasMore = o.getValue("has_more").bool()
        val rawItems = o.getValue("items") as? JsonArray ?: bad()
        check(rawItems.size <= 20 && rawItems.size <= total)
        val items = rawItems.map { parseAsset(it, library) }
        check(items.map { it.id }.distinct().size == items.size)
        check(items.size == minOf(20, total) && hasMore == (total > items.size))
        val effect = if (o.getValue("effect") == JsonNull) null else {
            val e = o.getValue("effect").obj("type", "asset_id")
            val type = e.getValue("type").str(32); check(type == "open_asset")
            AssistantEffect(type, e.getValue("asset_id").str(19).also { check(PhoneDiscoveryWire.validId(it)) })
        }
        check((kind == "open") == (effect != null))
        if (kind == "open") check(items.any { it.id == effect?.assetId })
        AssistantTurn(kind, reply, context, filters, items, total, hasMore, effect)
    }

    private fun parseAsset(value: JsonElement, library: String): Asset {
        val o = value as? JsonObject ?: bad()
        check(o.keys == setOf("id", "kind", "width", "height", "duration_sec", "taken_at", "thumbnail_url", "date_hint"))
        val id = o.getValue("id").str(19).also { check(PhoneDiscoveryWire.validId(it)) }
        val kind = o.getValue("kind").str(8).also { check(it in setOf("image", "video", "other")) }
        fun dimension(key: String): Int? = o.getValue(key).let { if (it == JsonNull) null else it.int(1_000_000).also { n -> check(n > 0) } }
        val duration = o.getValue("duration_sec").let { if (it == JsonNull) null else {
            val p = it as? JsonPrimitive ?: bad(); check(!p.isString)
            (p.doubleOrNull ?: bad()).also { n -> check(n.isFinite() && n in 0.0..1e9) }
        } }
        val taken = o.getValue("taken_at").let { if (it == JsonNull) null else it.str(64) }
        val thumbnail = o.getValue("thumbnail_url").str(2048)
        val base = okhttp3.HttpUrl.Builder().scheme("https").host("contract.invalid").build()
        val expected = base.newBuilder().addPathSegment("assets").addPathSegment(id).addPathSegment("thumbnail")
            .addQueryParameter("library", library).build()
        check(thumbnail.startsWith('/') && !thumbnail.startsWith("//") && '\\' !in thumbnail && base.resolve(thumbnail) == expected)
        val hint = o.getValue("date_hint").let { if (it == JsonNull) null else {
            val h = it.obj("value", "source")
            DateHint(h.getValue("value").str(64), h.getValue("source").str(16))
        } }
        return Asset(id, kind, dimension("width"), dimension("height"), duration, taken, thumbnail, hint)
    }
}
