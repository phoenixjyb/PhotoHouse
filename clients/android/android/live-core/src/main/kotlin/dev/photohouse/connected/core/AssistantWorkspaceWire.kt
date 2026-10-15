package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.time.Instant
import java.time.OffsetDateTime
import java.util.UUID

/** Strict JSON grammar for the optional private assistant workspace. */
object AssistantWorkspaceWire {
    const val RESPONSE_LIMIT = 256 * 1024
    private const val REVISION_MAX = Long.MAX_VALUE - 1
    private const val SAVED_MEMORY_RESPONSE_LIMIT = 240 * 1024
    private const val SAVED_MEMORY_READER_ENVELOPE_LIMIT = 1024 * 1024
    private const val SAVED_MEMORY_STORY_LIMIT = 256 * 1024
    private const val SAVED_MEMORY_BOOK_LIMIT = 512 * 1024
    private val ERROR_CODES = setOf("assistant_unavailable", "context_changed", "request_cancelled", "access_denied",
        "invalid_request", "storage_unavailable", "turn_interrupted")
    private val CARD_TYPES = setOf("media", "album", "story", "memoir", "timeline", "unavailable")
    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(ok: Boolean) { if (!ok) bad() }
    private inline fun <T> guarded(block: () -> T): T = try { block() } catch (e: ApiFailure) { throw e } catch (_: Exception) { bad() }
    private fun JsonElement.obj(required: Set<String>, optional: Set<String> = emptySet()): JsonObject =
        (this as? JsonObject ?: bad()).also { check(it.keys.containsAll(required) && it.keys.all { key -> key in required || key in optional }) }
    private fun JsonElement.str(max: Int): String {
        val p = this as? JsonPrimitive ?: bad(); check(p.isString)
        check(p.content.codePointCount(0, p.content.length) <= max && p.content.none { it < ' ' && it !in "\n\t" })
        strictUtf8(p.content)
        return p.content
    }
    private fun JsonElement.bool(): Boolean {
        val p = this as? JsonPrimitive ?: bad()
        check(!p.isString && p.content in setOf("true", "false"))
        return p.booleanOrNull ?: bad()
    }
    private fun JsonElement.integer(max: Long = REVISION_MAX): Long {
        val p = this as? JsonPrimitive ?: bad(); check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toLongOrNull()?.takeIf { it <= max } ?: bad()
    }
    private fun JsonElement.count(max: Int): Int = integer(max.toLong()).toInt()
    private fun JsonElement.array(max: Int): JsonArray = (this as? JsonArray ?: bad()).also { check(it.size <= max) }
    private fun nullableString(e: JsonElement, max: Int): String? = if (e == JsonNull) null else e.str(max)
    private fun validDate(value: String): String {
        check(value.length <= 64 && (runCatching { Instant.parse(value) }.isSuccess || runCatching { OffsetDateTime.parse(value) }.isSuccess))
        return value
    }
    fun validUuid4(value: String): Boolean = value.matches(Regex("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"))
    private fun uuid(e: JsonElement): String = e.str(36).also { check(validUuid4(it)) }
    private fun strictUtf8(value: String): ByteArray = try {
        val buffer = Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value))
        ByteArray(buffer.remaining()).also(buffer::get)
    } catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_INPUT) }

    private fun memoryText(value: JsonElement?, maxCodePoints: Int, maxBytes: Int, multiline: Boolean = false): String {
        val p = value as? JsonPrimitive ?: bad(); check(p.isString)
        val text = p.content
        check(text.codePointCount(0, text.length) <= maxCodePoints)
        var offset = 0
        while (offset < text.length) {
            val cp = text.codePointAt(offset)
            val allowedWhitespace = multiline && (cp == '\n'.code || cp == '\t'.code)
            val allowedJoiner = cp == 0x200c || cp == 0x200d
            val type = Character.getType(cp)
            val forbidden = type == Character.CONTROL.toInt() || type == Character.FORMAT.toInt() ||
                type == Character.SURROGATE.toInt() || type == Character.PRIVATE_USE.toInt() ||
                type == Character.UNASSIGNED.toInt()
            check(allowedWhitespace || allowedJoiner || !forbidden)
            offset += Character.charCount(cp)
        }
        check(text.isNotBlank())
        val bytes = strictUtf8(text)
        try { check(bytes.size <= maxBytes) } finally { bytes.fill(0) }
        return text
    }

    private fun memoryReference(value: JsonElement): AssistantSavedMemoryReference {
        val o = value.obj(setOf("kind", "id", "revision", "source_revision"))
        val kind = o.getValue("kind").str(16); check(kind in setOf("story", "memoir"))
        val id = uuid(o.getValue("id"))
        val revision = o.getValue("revision").str(19)
        check(revision.matches(Regex("[1-9][0-9]{0,18}")) && revision.toLongOrNull()?.let { it <= REVISION_MAX } == true)
        val digest = o.getValue("source_revision").str(64); check(digest.matches(Regex("[0-9a-f]{64}")))
        return AssistantSavedMemoryReference(kind, id, revision, digest)
    }

    private fun savedMemoryResult(raw: JsonObject, library: String, acceptSavedMemoryActions: Boolean): AssistantTurn {
        val o = raw.obj(setOf("version", "kind", "reply", "context", "filters", "items", "total", "has_more", "effect", "memory_cards"),
            if (acceptSavedMemoryActions) setOf("memory_action") else emptySet())
        check(o.getValue("version").count(1) == 1)
        val kind = o.getValue("kind").str(32)
        val reply = memoryText(o["reply"], 4000, 8192)
        check(o["filters"] == JsonNull && o.getValue("items").array(0).isEmpty() && o["effect"] == JsonNull)
        val total = o.getValue("total").count(256)
        val hasMore = o.getValue("has_more").bool()
        val cardValues = o.getValue("memory_cards").array(12)
        if (kind == "clarification") {
            check(o["context"] == JsonNull && total == 0 && !hasMore && cardValues.isEmpty() && "memory_action" !in o)
            return AssistantTurn(kind, reply, null, null, emptyList(), 0, false, null)
        }
        check(kind == "memory_cards")
        val context = o.getValue("context").obj(setOf("kind", "library_id", "source_revision", "references"))
        check(context.getValue("kind").str(32) == "saved_memory" && context.getValue("library_id").str(256) == library)
        val contextDigest = context.getValue("source_revision").str(64)
        check(contextDigest.matches(Regex("[0-9a-f]{64}")))
        val refs = context.getValue("references").array(12).map(::memoryReference)
        check(refs.size == cardValues.size && cardValues.size == minOf(total, 12) && hasMore == (total > cardValues.size))
        val cards = cardValues.mapIndexed { index, value ->
            val c = value.obj(setOf("kind", "id", "revision", "source_revision", "title", "excerpt"))
            val binding = memoryReference(JsonObject(mapOf("kind" to c.getValue("kind"), "id" to c.getValue("id"),
                "revision" to c.getValue("revision"), "source_revision" to c.getValue("source_revision"))))
            check(binding == refs[index])
            AssistantSavedMemoryCard(binding.kind, binding.id, binding.revision, binding.sourceRevision,
                memoryText(c["title"], 640, 640), memoryText(c["excerpt"], 240, 960, multiline = true))
        }
        check(cards.map { it.kind to it.id }.distinct().size == cards.size)
        val memoryAction = o["memory_action"]?.let { value ->
            val action = value.obj(setOf("type", "ordinal"))
            val type = action.getValue("type").str(16)
            val ordinal = action.getValue("ordinal").count(11)
            check(type in setOf("open", "read_opening") && cards.isNotEmpty() && ordinal in cards.indices)
            AssistantSavedMemoryAction(type, ordinal)
        }
        return AssistantTurn(kind, reply, null, null, emptyList(), total, hasMore, null,
            memoryCards = cards, savedMemoryContext = AssistantSavedMemoryContext(library, contextDigest, refs),
            memoryAction = memoryAction)
    }

    private fun parseThread(value: JsonElement, library: String, includeLabel: Boolean = false): AssistantWorkspaceThreadSummary {
        val optional = buildSet { add("exchange_count"); if (includeLabel) add("label") }
        val o = value.obj(setOf("thread_id", "library_id", "created_at", "updated_at", "expires_at", "revision"), optional)
        val threadId = uuid(o.getValue("thread_id")); check(o.getValue("library_id").str(128) == library && PhoneDiscoveryWire.validLibrary(library))
        val revision = o.getValue("revision").integer()
        val count = o["exchange_count"]?.count(100000) ?: 0
        val label = o["label"]?.let { element ->
            if (element == JsonNull) null else element.str(64).also { value ->
                var offset = 0
                while (offset < value.length) {
                    val codePoint = value.codePointAt(offset)
                    check(!Character.isISOControl(codePoint))
                    offset += Character.charCount(codePoint)
                }
            }
        }
        return AssistantWorkspaceThreadSummary(threadId, library, validDate(o.getValue("created_at").str(64)),
            validDate(o.getValue("updated_at").str(64)), validDate(o.getValue("expires_at").str(64)), revision, count, label)
    }

    fun capabilities(bytes: ByteArray): AssistantWorkspaceCapabilities = guarded {
        check(bytes.size in 1..4096)
        val o = DiscoveryJson.parse(bytes).obj(setOf("version", "available", "threads", "preferences", "preferences_applied", "server_owned_turns"),
            setOf("applied_preferences", "history_paging", "thread_labels", "reply_speech", "search"))
        check(o.getValue("version").count(1) == 1)
        val applied = o["applied_preferences"]?.array(4)?.map { it.str(32) } ?: emptyList()
        check(applied.distinct().size == applied.size && applied.all { it == "locale" })
        val appliedFlag = o.getValue("preferences_applied").bool()
        val hasSearch = "search" in o
        val searchPerspectiveLabel = if (hasSearch) {
            val value = o.getValue("search")
            check(o.getValue("available").bool() && o.getValue("threads").bool() && o.getValue("server_owned_turns").bool())
            val presentation = value.obj(setOf("version", "date_basis", "perspective"))
            check(presentation.getValue("version").count(2) == 2)
            check(presentation.getValue("date_basis").str(16) == "capture")
            val perspective = presentation.getValue("perspective")
            val label = if (perspective == JsonNull) null else perspective.obj(setOf("label"))
                .getValue("label").let { memoryText(it, 512, 512) }
            label
        } else null
        AssistantWorkspaceCapabilities(1, o.getValue("available").bool(), o.getValue("threads").bool(),
            o.getValue("preferences").bool(), appliedFlag, o.getValue("server_owned_turns").bool(), applied.toSet(),
            o["history_paging"]?.bool() ?: false, o["thread_labels"]?.bool() ?: false,
            o["reply_speech"]?.bool() ?: false, if (hasSearch) 2 else 1,
            if (hasSearch) "capture" else null, searchPerspectiveLabel)
    }

    fun savedMemoryReaderCapabilities(bytes: ByteArray): SavedMemoryReaderCapabilities = guarded {
        check(bytes.size in 1..4096)
        val o = DiscoveryJson.parse(bytes).obj(setOf("version", "available"))
        check(o.getValue("version").count(1) == 1)
        SavedMemoryReaderCapabilities(1, o.getValue("available").bool())
    }

    fun savedMemoryReader(bytes: ByteArray, library: String): SavedMemoryReaderPayload = guarded {
        check(bytes.size in 1..SAVED_MEMORY_READER_ENVELOPE_LIMIT &&
            PhoneDiscoveryWire.validLibrary(library))
        val o = DiscoveryJson.parse(bytes, SAVED_MEMORY_READER_ENVELOPE_LIMIT, 12000)
            .obj(setOf("version", "kind", "reader"))
        check(o.getValue("version").count(1) == 1)
        val kind = o.getValue("kind").str(16); check(kind in setOf("story", "memoir"))
        val readerBytes = o.getValue("reader").toString().toByteArray(Charsets.UTF_8)
        try {
            when (kind) {
                "story" -> {
                    check(readerBytes.size in 1..SAVED_MEMORY_STORY_LIMIT)
                    val reader = DiscoveryJson.parse(readerBytes, SAVED_MEMORY_STORY_LIMIT, 1200) as? JsonObject ?: bad()
                    val id = reader["id"]?.let { (it as? JsonPrimitive)?.content } ?: bad()
                    check(AssistantWorkspaceWire.validUuid4(id))
                    val story = ProtectedMemoryStoriesWire.detail(readerBytes, library, id, 1)
                    SavedMemoryReaderPayload.Story(story)
                }
                "memoir" -> {
                    check(readerBytes.size in 1..SAVED_MEMORY_BOOK_LIMIT)
                    val memoir = ProtectedMemoryCommunityWire.bookDetail(readerBytes)
                    SavedMemoryReaderPayload.Memoir(memoir)
                }
                else -> bad()
            }
        } finally { readerBytes.fill(0) }
    }

    fun threadList(bytes: ByteArray, library: String, includeLabels: Boolean = false): AssistantWorkspaceThreadList = guarded {
        check(bytes.size in 1..RESPONSE_LIMIT && PhoneDiscoveryWire.validLibrary(library))
        val o = DiscoveryJson.parse(bytes).obj(setOf("version", "threads"))
        check(o.getValue("version").count(1) == 1)
        val items = o.getValue("threads").array(100).map { parseThread(it, library, includeLabels) }
        check(items.map { it.threadId }.distinct().size == items.size)
        AssistantWorkspaceThreadList(1, items)
    }

    fun createdThread(bytes: ByteArray, library: String, expectedId: String): AssistantWorkspaceCreatedThread = guarded {
        check(bytes.size in 1..RESPONSE_LIMIT && PhoneDiscoveryWire.validLibrary(library) && validUuid4(expectedId))
        val o = DiscoveryJson.parse(bytes).obj(setOf("version", "thread")); check(o.getValue("version").count(1) == 1)
        val thread = parseThread(o.getValue("thread"), library); check(thread.threadId == expectedId)
        AssistantWorkspaceCreatedThread(1, thread)
    }

    private fun parseExchange(value: JsonElement): AssistantWorkspaceExchange {
        val o = value.obj(setOf("exchange_id", "revision", "created_at", "expires_at", "input_text", "reply", "cards", "receipt_count"), setOf("request_id"))
        val cards = o.getValue("cards").array(32).map { item ->
            val c = item.obj(setOf("type", "count", "actionable"))
            val type = c.getValue("type").str(32); check(type in CARD_TYPES)
            val actionable = c.getValue("actionable").bool(); check(!actionable)
            AssistantWorkspaceCardCount(type, c.getValue("count").count(100000), actionable)
        }
        check(cards.map { it.type }.distinct().size == cards.size)
        val requestId = o["request_id"]?.let(::uuid)
        val input = o.getValue("input_text").str(1024)
        val reply = o.getValue("reply").str(8192)
        check(input.toByteArray(Charsets.UTF_8).size <= 1024 && reply.toByteArray(Charsets.UTF_8).size <= 8192)
        return AssistantWorkspaceExchange(uuid(o.getValue("exchange_id")), o.getValue("revision").integer(),
            validDate(o.getValue("created_at").str(64)), validDate(o.getValue("expires_at").str(64)),
            input, reply, cards,
            o.getValue("receipt_count").count(100000), requestId)
    }

    fun threadDetail(bytes: ByteArray, library: String, expectedThreadId: String): AssistantWorkspaceThreadDetail = guarded {
        check(bytes.size in 1..RESPONSE_LIMIT && PhoneDiscoveryWire.validLibrary(library) && validUuid4(expectedThreadId))
        val o = DiscoveryJson.parse(bytes).obj(setOf("version", "thread", "exchanges"), setOf("latest_request_id", "has_older_exchanges"))
        check(o.getValue("version").count(1) == 1)
        val thread = parseThread(o.getValue("thread"), library); check(thread.threadId == expectedThreadId)
        val exchanges = o.getValue("exchanges").array(200).map(::parseExchange)
        check(exchanges.zipWithNext().all { (a, b) -> a.revision < b.revision } && exchanges.all { it.revision <= thread.revision })
        val latest = o["latest_request_id"]?.let { nullableString(it, 36)?.also { id -> check(validUuid4(id)) } }
        val older = o["has_older_exchanges"]?.bool() ?: false
        AssistantWorkspaceThreadDetail(1, thread, exchanges, latest, older)
    }

    fun historyPage(bytes: ByteArray, library: String, expectedThreadId: String,
                    expectedBeforeRevision: Long, expectedSnapshotRevision: Long): AssistantWorkspaceHistoryPage = guarded {
        check(bytes.size in 1..RESPONSE_LIMIT && PhoneDiscoveryWire.validLibrary(library) && validUuid4(expectedThreadId))
        check(expectedBeforeRevision in 1..REVISION_MAX && expectedSnapshotRevision in 0..REVISION_MAX &&
            expectedBeforeRevision <= expectedSnapshotRevision)
        val o = DiscoveryJson.parse(bytes, RESPONSE_LIMIT).obj(setOf("version", "thread_id", "snapshot_revision", "before_revision",
            "exchanges", "has_older_exchanges", "next_before_revision"))
        check(o.getValue("version").count(1) == 1)
        check(uuid(o.getValue("thread_id")) == expectedThreadId)
        val snapshot = o.getValue("snapshot_revision").integer()
        val before = o.getValue("before_revision").integer()
        check(snapshot == expectedSnapshotRevision && before == expectedBeforeRevision && before <= snapshot)
        val exchanges = o.getValue("exchanges").array(20).map(::parseExchange)
        check(exchanges.zipWithNext().all { (a, b) -> a.revision < b.revision })
        check(exchanges.all { it.revision > 0 && it.revision < before && it.revision <= snapshot })
        check(exchanges.map { it.exchangeId }.distinct().size == exchanges.size)
        check(exchanges.mapNotNull { it.requestId }.distinct().size == exchanges.count { it.requestId != null })
        val hasOlder = o.getValue("has_older_exchanges").bool()
        val next = if (o.getValue("next_before_revision") == JsonNull) null else o.getValue("next_before_revision").integer()
        if (hasOlder) {
            val cursor = next ?: bad()
            check(exchanges.isNotEmpty() && cursor == exchanges.first().revision && cursor > 0 && cursor < before)
        } else check(next == null)
        AssistantWorkspaceHistoryPage(1, expectedThreadId, snapshot, before, exchanges, hasOlder, next)
    }

    fun preferences(bytes: ByteArray): AssistantWorkspacePreferences = guarded {
        check(bytes.size in 1..4096)
        val o = DiscoveryJson.parse(bytes).obj(setOf("version", "locale", "reply_length", "voice_pace", "revision"))
        check(o.getValue("version").count(1) == 1)
        val locale = nullableString(o.getValue("locale"), 8); check(locale == null || locale in setOf("zh", "en"))
        val length = nullableString(o.getValue("reply_length"), 16); check(length == null || length in setOf("brief", "standard"))
        val pace = nullableString(o.getValue("voice_pace"), 16); check(pace == null || pace in setOf("slow", "normal"))
        AssistantWorkspacePreferences(1, locale, length, pace, o.getValue("revision").integer())
    }

    fun deletedThread(bytes: ByteArray, expectedThreadId: String): AssistantWorkspaceDeletedThread = guarded {
        check(bytes.size in 1..4096 && validUuid4(expectedThreadId))
        val o = DiscoveryJson.parse(bytes).obj(setOf("thread_id", "deleted"))
        val id = uuid(o.getValue("thread_id")); check(id == expectedThreadId)
        val deleted = o.getValue("deleted").bool(); check(deleted)
        AssistantWorkspaceDeletedThread(id, true)
    }

    fun createThreadRequest(library: String, clientThreadId: String): String {
        if (!PhoneDiscoveryWire.validLibrary(library) || !validUuid4(clientThreadId)) throw ApiFailure(FailureKind.INVALID_INPUT)
        return buildJsonObject { put("library_id", library); put("thread_id", clientThreadId) }.toString()
    }
    fun deleteThreadRequest(library: String, expectedRevision: Long): String {
        if (!PhoneDiscoveryWire.validLibrary(library) || expectedRevision !in 0..REVISION_MAX) throw ApiFailure(FailureKind.INVALID_INPUT)
        return buildJsonObject { put("library_id", library); put("expected_revision", expectedRevision) }.toString()
    }
    fun preferencesRequest(library: String, expectedRevision: Long,
                           updates: Map<AssistantWorkspacePreference, String?>): String {
        if (!PhoneDiscoveryWire.validLibrary(library) || expectedRevision !in 0..REVISION_MAX || updates.isEmpty() ||
            updates.any { (key, value) -> value != null && when (key) {
                AssistantWorkspacePreference.LOCALE -> value !in setOf("zh", "en")
                AssistantWorkspacePreference.REPLY_LENGTH -> value !in setOf("brief", "standard")
                AssistantWorkspacePreference.VOICE_PACE -> value !in setOf("slow", "normal")
            } }) throw ApiFailure(FailureKind.INVALID_INPUT)
        return buildJsonObject {
            put("library_id", library)
            put("expected_revision", expectedRevision)
            updates.forEach { (key, value) -> put(when (key) {
                AssistantWorkspacePreference.LOCALE -> "locale"
                AssistantWorkspacePreference.REPLY_LENGTH -> "reply_length"
                AssistantWorkspacePreference.VOICE_PACE -> "voice_pace"
            }, value) }
        }.toString()
    }
    fun resetPreferencesRequest(library: String, expectedRevision: Long): String {
        if (!PhoneDiscoveryWire.validLibrary(library) || expectedRevision !in 0..REVISION_MAX) throw ApiFailure(FailureKind.INVALID_INPUT)
        return buildJsonObject { put("library_id", library); put("expected_revision", expectedRevision) }.toString()
    }
    fun replySpeechRequest(library: String, expectedRevision: Long,
                           turnId: String, speechRequestId: String): String {
        if (!PhoneDiscoveryWire.validLibrary(library) || expectedRevision !in 0..REVISION_MAX ||
            !validUuid4(turnId) || !validUuid4(speechRequestId) || turnId == speechRequestId) {
            throw ApiFailure(FailureKind.INVALID_INPUT)
        }
        return buildJsonObject {
            put("library_id", library)
            put("expected_revision", expectedRevision)
        }.toString()
    }

    /** Exact request body for one explicit saved-memory source segment. */
    fun savedMemorySegmentSpeechRequest(library: String, expectedRevision: Long,
                                        turnId: String, segment: Int, speechRequestId: String): String {
        if (!PhoneDiscoveryWire.validLibrary(library) || expectedRevision !in 0..REVISION_MAX ||
            !validUuid4(turnId) || segment !in 0..127 || !validUuid4(speechRequestId) || turnId == speechRequestId) {
            throw ApiFailure(FailureKind.INVALID_INPUT)
        }
        return buildJsonObject {
            put("library_id", library)
            put("expected_revision", expectedRevision)
        }.toString()
    }

    /** Apply the shared WAV envelope check plus the private Windows TTS duration contract. */
    fun replySpeechAudio(bytes: ByteArray): ByteArray = guarded {
        AssistantWire.speechAudio(bytes)
        check(bytes.size >= 44 && readAscii(bytes, 0, 4) == "RIFF" && readAscii(bytes, 8, 4) == "WAVE")
        check(readU32(bytes, 4) + 8L == bytes.size.toLong())
        var offset = 12
        var formatSeen = false
        var dataSeen = false
        var blockAlign = 0L
        var sampleRate = 0L
        var frames = 0L
        while (offset < bytes.size) {
            check(offset <= bytes.size - 8)
            val chunk = readAscii(bytes, offset, 4)
            val size = readU32(bytes, offset + 4)
            val contentStart = offset + 8L
            val contentEnd = contentStart + size
            check(contentEnd <= bytes.size.toLong())
            when (chunk) {
                "fmt " -> {
                    check(!formatSeen && size >= 16)
                    val encoding = readU16(bytes, contentStart.toInt())
                    val channels = readU16(bytes, contentStart.toInt() + 2)
                    sampleRate = readU32(bytes, contentStart.toInt() + 4)
                    val byteRate = readU32(bytes, contentStart.toInt() + 8)
                    blockAlign = readU16(bytes, contentStart.toInt() + 12).toLong()
                    val bits = readU16(bytes, contentStart.toInt() + 14)
                    check(encoding == 1 && channels in 1..2 && sampleRate in 8_000..48_000 &&
                        bits in setOf(8, 16, 24, 32))
                    check(blockAlign == channels.toLong() * (bits / 8) &&
                        byteRate == sampleRate * blockAlign)
                    formatSeen = true
                }
                "data" -> {
                    check(!dataSeen && size > 0)
                    frames = size
                    dataSeen = true
                }
            }
            offset = (contentEnd + (size and 1L)).toInt()
            check(offset <= bytes.size)
        }
        check(offset == bytes.size && formatSeen && dataSeen && blockAlign > 0 && frames % blockAlign == 0L)
        check(frames / blockAlign <= sampleRate * 30L)
        bytes
    }

    private fun readAscii(bytes: ByteArray, offset: Int, length: Int): String =
        String(bytes, offset, length, Charsets.US_ASCII)
    private fun readU16(bytes: ByteArray, offset: Int): Int =
        (bytes[offset].toInt() and 0xff) or ((bytes[offset + 1].toInt() and 0xff) shl 8)
    private fun readU32(bytes: ByteArray, offset: Int): Long =
        (bytes[offset].toLong() and 0xff) or ((bytes[offset + 1].toLong() and 0xff) shl 8) or
            ((bytes[offset + 2].toLong() and 0xff) shl 16) or ((bytes[offset + 3].toLong() and 0xff) shl 24)

    fun turnRequest(library: String, requestId: String, expectedRevision: Long, text: String,
                    acceptSavedMemoryCards: Boolean = false,
                    memoryParent: AssistantSavedMemoryParent? = null,
                    acceptSavedMemoryActions: Boolean = false): String {
        if (!PhoneDiscoveryWire.validLibrary(library) || !validUuid4(requestId) || expectedRevision !in 0..REVISION_MAX) throw ApiFailure(FailureKind.INVALID_INPUT)
        if (acceptSavedMemoryActions && !acceptSavedMemoryCards || memoryParent != null && (!acceptSavedMemoryCards || !validUuid4(memoryParent.requestId) ||
                memoryParent.revision !in 1..REVISION_MAX))
            throw ApiFailure(FailureKind.INVALID_INPUT)
        val textBytes = strictUtf8(text)
        if (text.isBlank() || textBytes.size !in 1..1024 || text.any { (it < ' ' && it !in "\n\t") || it == '\u007f' })
            throw ApiFailure(FailureKind.INVALID_INPUT)
        return buildJsonObject {
            put("library_id", library); put("request_id", requestId); put("expected_revision", expectedRevision); put("text", text)
            if (acceptSavedMemoryCards) put("accepts", buildJsonArray {
                add("saved_memory_cards_v1")
                if (acceptSavedMemoryActions) add("saved_memory_actions_v1")
            })
            memoryParent?.let { parent -> put("memory_parent", buildJsonObject {
                put("request_id", parent.requestId); put("revision", parent.revision)
            }) }
        }
            .toString().also { if (it.toByteArray(Charsets.UTF_8).size > 20 * 1024) throw ApiFailure(FailureKind.INVALID_INPUT) }
    }

    private fun validateResult(bytes: ByteArray, library: String, recovered: Boolean,
                               acceptSavedMemoryCards: Boolean, acceptSavedMemoryActions: Boolean,
                               searchVersion: Int): AssistantTurn {
        val raw = DiscoveryJson.parse(bytes, RESPONSE_LIMIT) as? JsonObject ?: bad()
        if (raw["version"] == JsonPrimitive(2)) {
            check(searchVersion == 2)
            return validateV2Result(bytes, library, recovered)
        }
        check(searchVersion in 1..2)
        if ("memory_cards" in raw || raw["kind"]?.let { (it as? JsonPrimitive)?.content } == "memory_cards") {
            check(bytes.size in 1..SAVED_MEMORY_RESPONSE_LIMIT && acceptSavedMemoryCards && !recovered)
            return savedMemoryResult(raw, library, acceptSavedMemoryActions)
        }
        check(searchVersion != 2 || recovered)
        val result = AssistantWire.response(bytes, library)
        val json = DiscoveryJson.parse(bytes, RESPONSE_LIMIT) as? JsonObject ?: bad()
        val context = json.getValue("context").let { if (it == JsonNull) null else it as? JsonObject ?: bad() }
        if (context != null) {
            val contextV2 = "search_version" in context
            check(!contextV2)
            val ctx = context.obj(setOf("library_id", "binding", "fingerprint", "filters", "visible_ids", "total"))
            check(ctx.getValue("library_id").str(128) == library)
            check(ctx.getValue("binding").str(64).matches(Regex("[0-9a-f]{64}")))
            check(ctx.getValue("fingerprint").str(64).matches(Regex("[0-9a-f]{64}")))
            val filters = ctx.getValue("filters") as? JsonObject ?: bad()
            validateFilters(filters)
            check(filters.toString().toByteArray(Charsets.UTF_8).size <= 16 * 1024)
            check(json.getValue("filters") == ctx.getValue("filters"))
            val ids = ctx.getValue("visible_ids").array(20).map { e -> e.str(19).also { check(PhoneDiscoveryWire.validId(it)) } }
            check(ids.distinct().size == ids.size && ids == result.items.map { it.id })
            check(ctx.getValue("total").integer(100000).toInt() == result.total)
        } else {
            check(result.total == 0 && result.items.isEmpty() && result.filters == null && result.effect == null && !result.hasMore)
        }
        if (recovered) check(result.kind != "open" && result.effect == null)
        return result
    }

    /** Validate the persisted form emitted by PhoneFilters.json without display metadata. */
    private fun validateFilters(filters: JsonObject, searchVersion: Int = 1) {
        check(filters.keys.all { it in PhoneDiscoveryWire.fields || searchVersion == 2 && it == "text" })
        fun selected(e: JsonElement, withMatch: Boolean) {
            if (withMatch) {
                val group = e.obj(setOf("ids", "match"))
                val match = group.getValue("match").str(8); check(match in setOf("all", "any"))
                ids(group.getValue("ids"))
            } else ids(e)
        }
        filters["people"]?.let { selected(it, true) }
        filters["tags"]?.let { selected(it, true) }
        filters["locations"]?.let { selected(it, false) }
        filters["media"]?.let { e ->
            val values = e.array(3).map { it.str(8) }
            check(values.isNotEmpty() && values.distinct().size == values.size && values.all { it in setOf("image", "video", "other") })
        }
        filters["date"]?.let { e ->
            val dates = e.obj(setOf("from", "to"))
            val from = filterDate(dates.getValue("from")); val to = filterDate(dates.getValue("to"))
            check((from != null || to != null) && (from == null || to == null || from <= to))
        }
        filters["caption"]?.let { e ->
            val caption = e.str(512)
            check(caption.isNotBlank() && caption.toByteArray(Charsets.UTF_8).size <= 512)
        }
        filters["text"]?.let { e ->
            check(searchVersion == 2)
            memoryText(e, 512, 512)
        }
        check(filters.toString().toByteArray(Charsets.UTF_8).size <= 16 * 1024)
        val phoneFields = JsonObject(filters.filterKeys { it != "text" })
        check(phoneFilters(phoneFields).json() == phoneFields)
    }

    private fun selectedFilterIds(filters: JsonObject?, key: String): List<String> {
        if (filters == null) return emptyList()
        return when (key) {
            "locations" -> filters[key]?.array(20)?.map { it.str(19) } ?: emptyList()
            else -> filters[key]?.obj(setOf("ids", "match"))?.getValue("ids")?.array(20)?.map { it.str(19) }
                ?: emptyList()
        }
    }

    private fun searchInterpretation(value: JsonElement, filters: JsonObject?): AssistantSearchInterpretation {
        val o = value.obj(setOf("date_basis", "people", "tags", "locations", "perspective"))
        check(o.getValue("date_basis").str(16) == "capture")
        fun selections(key: String): List<AssistantSearchFacetSelection> {
            val selected = selectedFilterIds(filters, key)
            val values = o.getValue(key).array(20).map { item ->
                val facet = item.obj(setOf("id", "label"))
                val id = facet.getValue("id").str(19).also { check(PhoneDiscoveryWire.validId(it)) }
                val label = memoryText(facet.getValue("label"), 512, 512)
                AssistantSearchFacetSelection(id, label)
            }
            check(values.map { it.id } == selected && values.map { it.id }.distinct().size == values.size)
            return values
        }
        val perspectiveValue = o.getValue("perspective")
        val perspective = if (perspectiveValue == JsonNull) null else {
            val p = perspectiveValue.obj(setOf("label"))
            val label = memoryText(p.getValue("label"), 512, 512)
            AssistantSearchPerspective(label)
        }
        return AssistantSearchInterpretation("capture", selections("people"), selections("tags"),
            selections("locations"), perspective)
    }

    private fun reason(value: JsonElement): AssistantMatchReason {
        val source = (value as? JsonObject)?.get("source")?.str(32) ?: bad()
        return when (source) {
            "photo_memory" -> {
                val o = value.obj(setOf("source", "source_id", "revision"))
                val id = o.getValue("source_id").str(128)
                check(id.isNotEmpty() && strictUtf8(id).size <= 128)
                check(o.getValue("revision").integer() > 0)
                AssistantMatchReason.PhotoMemory(id)
            }
            "edited_caption", "generated_caption" -> {
                val o = value.obj(setOf("source", "source_id", "revision"))
                val id = o.getValue("source_id").str(19)
                check(PhoneDiscoveryWire.validId(id))
                val digest = o.getValue("revision").str(64)
                check(digest.matches(Regex("[0-9a-f]{64}")))
                AssistantMatchReason.Caption(source == "generated_caption", id)
            }
            "reviewed_person" -> {
                val o = value.obj(setOf("source", "source_id"))
                val id = o.getValue("source_id").str(19)
                check(PhoneDiscoveryWire.validId(id))
                AssistantMatchReason.ReviewedPerson(id)
            }
            "capture_date" -> {
                val o = value.obj(setOf("source", "value"))
                val date = o.getValue("value").str(10)
                check(date.matches(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}")) && runCatching { java.time.LocalDate.parse(date) }.isSuccess)
                AssistantMatchReason.CaptureDate(date)
            }
            else -> bad()
        }
    }

    private fun validateV2Result(bytes: ByteArray, library: String, recovered: Boolean): AssistantTurn {
        val raw = DiscoveryJson.parse(bytes, RESPONSE_LIMIT).obj(
            setOf("version", "kind", "reply", "context", "filters", "items", "total", "has_more", "effect", "interpretation"))
        check(raw.getValue("version").count(2) == 2)
        val context = raw.getValue("context").let { if (it == JsonNull) null else
            it.obj(setOf("library_id", "binding", "fingerprint", "filters", "visible_ids", "total", "search_version")) }
        val filters = raw.getValue("filters").let { if (it == JsonNull) null else it as? JsonObject ?: bad() }
        if (context != null) {
            check(context.getValue("library_id").str(128) == library && context.getValue("search_version").count(2) == 2)
            check(context.getValue("binding").str(64).matches(Regex("[0-9a-f]{64}")))
            check(context.getValue("fingerprint").str(64).matches(Regex("[0-9a-f]{64}")))
            check(filters != null && context.getValue("filters") == filters)
            validateFilters(filters!!, 2)
        } else check(filters == null)
        val interpretation = searchInterpretation(raw.getValue("interpretation"), filters)
        val rawItems = raw.getValue("items").array(20)
        val reasons = linkedMapOf<String, List<AssistantMatchReason>>()
        val strippedItems = rawItems.map { item ->
            val asset = item as? JsonObject ?: bad()
            val legacyKeys = setOf("id", "kind", "width", "height", "duration_sec", "taken_at", "thumbnail_url")
            check(asset.keys == legacyKeys || asset.keys == legacyKeys + "date_hint" ||
                asset.keys == legacyKeys + "match_reasons" || asset.keys == legacyKeys + setOf("date_hint", "match_reasons"))
            val id = asset.getValue("id").str(19).also { check(PhoneDiscoveryWire.validId(it)) }
            asset["match_reasons"]?.let { value ->
                val parsed = value.array(64).map(::reason)
                check(parsed.isNotEmpty() && id !in reasons)
                reasons[id] = parsed
            }
            JsonObject(asset.filterKeys { it != "match_reasons" })
        }
        val legacy = JsonObject(raw.filterKeys { it != "interpretation" } + ("version" to JsonPrimitive(1)) +
            ("items" to JsonArray(strippedItems)))
        val turn = AssistantWire.response(legacy.toString().toByteArray(Charsets.UTF_8), library)
        if (context != null) {
            val ids = context.getValue("visible_ids").array(20).map { it.str(19).also { id -> check(PhoneDiscoveryWire.validId(id)) } }
            check(ids.distinct().size == ids.size && ids == turn.items.map { it.id })
            check(context.getValue("total").integer(100000).toInt() == turn.total)
            check(turn.filters == filters && turn.total == raw.getValue("total").count(100000))
        } else check(turn.total == 0 && turn.items.isEmpty() && turn.filters == null && turn.effect == null && !turn.hasMore)
        if (recovered) check(turn.kind != "open" && turn.effect == null)
        return turn.copy(searchVersion = 2, searchInterpretation = interpretation, matchReasons = reasons)
    }

    private fun phoneFilters(filters: JsonObject): PhoneFilters {
        fun selections(key: String): Pair<List<PhoneChoice>, Boolean> {
            val element = filters[key] ?: return emptyList<PhoneChoice>() to false
            val group = element.obj(setOf("ids", "match"))
            val ids = group.getValue("ids").array(20).map { it.str(19).also { id -> check(PhoneDiscoveryWire.validId(id)) } }
            val match = group.getValue("match").str(8)
            check(match in setOf("any", "all"))
            return ids.map { PhoneChoice(it, "", 0) } to (match == "all")
        }
        val (people, peopleAll) = selections("people")
        val (tags, tagsAll) = selections("tags")
        val places = filters["locations"]?.array(20)?.map { it.str(19).also { id -> check(PhoneDiscoveryWire.validId(id)) } }
            ?: emptyList()
        val media = filters["media"]?.array(3)?.map { it.str(8) }?.toSet() ?: emptySet()
        val date = filters["date"]?.let { e ->
            val o = e.obj(setOf("from", "to"))
            (filterDate(o.getValue("from")).orEmpty()) to (filterDate(o.getValue("to")).orEmpty())
        } ?: ("" to "")
        val caption = filters["caption"]?.str(512) ?: ""
        return PhoneFilters(people, peopleAll, tags, tagsAll, places.map { PhoneChoice(it, "", 0) }, media.toSet(), date.first, date.second, caption)
    }

    private fun ids(value: JsonElement) {
        val parsed = value.array(20).map { it.str(19).also { id -> check(PhoneDiscoveryWire.validId(id)) } }
        check(parsed.isNotEmpty() && parsed.distinct().size == parsed.size)
    }

    private fun filterDate(e: JsonElement): String? = if (e == JsonNull) null else e.str(10).also {
        check(it.matches(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}")) && runCatching { java.time.LocalDate.parse(it) }.isSuccess)
    }

    fun turn(bytes: ByteArray, library: String, threadId: String, requestId: String,
             fromGet: Boolean, acceptSavedMemoryCards: Boolean = false,
             acceptSavedMemoryActions: Boolean = false,
             searchVersion: Int = 1): AssistantWorkspaceTurn = guarded {
        check(bytes.size in 1..RESPONSE_LIMIT && PhoneDiscoveryWire.validLibrary(library) && validUuid4(threadId) && validUuid4(requestId))
        val o = DiscoveryJson.parse(bytes, RESPONSE_LIMIT).obj(setOf("version", "thread_id", "request_id", "status", "revision", "recovered", "error", "result"))
        check(o.getValue("version").count(1) == 1)
        check(uuid(o.getValue("thread_id")) == threadId && uuid(o.getValue("request_id")) == requestId)
        val status = when (o.getValue("status").str(16)) {
            "pending" -> AssistantWorkspaceRequestStatus.PENDING
            "completed" -> AssistantWorkspaceRequestStatus.COMPLETED
            "failed" -> AssistantWorkspaceRequestStatus.FAILED
            "interrupted" -> AssistantWorkspaceRequestStatus.INTERRUPTED
            else -> bad()
        }
        val revision = o.getValue("revision").integer()
        val recovered = o.getValue("recovered").bool()
        check(!fromGet || recovered)
        val error = nullableString(o.getValue("error"), 64)
        val rawResult = o.getValue("result")
        check(if (status == AssistantWorkspaceRequestStatus.COMPLETED) rawResult != JsonNull && error == null
              else rawResult == JsonNull)
        check(if (status == AssistantWorkspaceRequestStatus.FAILED || status == AssistantWorkspaceRequestStatus.INTERRUPTED)
            error in ERROR_CODES else error == null)
        val result = if (rawResult == JsonNull) null else validateResult(rawResult.toString().toByteArray(Charsets.UTF_8), library, recovered,
            acceptSavedMemoryCards, acceptSavedMemoryActions, searchVersion)
        AssistantWorkspaceTurn(1, threadId, requestId, status, revision, recovered, error, result)
    }
}
