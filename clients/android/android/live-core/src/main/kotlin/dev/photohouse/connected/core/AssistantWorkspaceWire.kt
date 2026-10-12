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
            setOf("applied_preferences", "history_paging", "thread_labels"))
        check(o.getValue("version").count(1) == 1)
        val applied = o["applied_preferences"]?.array(4)?.map { it.str(32) } ?: emptyList()
        check(applied.distinct().size == applied.size && applied.all { it == "locale" })
        val appliedFlag = o.getValue("preferences_applied").bool()
        AssistantWorkspaceCapabilities(1, o.getValue("available").bool(), o.getValue("threads").bool(),
            o.getValue("preferences").bool(), appliedFlag, o.getValue("server_owned_turns").bool(), applied.toSet(),
            o["history_paging"]?.bool() ?: false, o["thread_labels"]?.bool() ?: false)
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
    fun turnRequest(library: String, requestId: String, expectedRevision: Long, text: String): String {
        if (!PhoneDiscoveryWire.validLibrary(library) || !validUuid4(requestId) || expectedRevision !in 0..REVISION_MAX) throw ApiFailure(FailureKind.INVALID_INPUT)
        val textBytes = strictUtf8(text)
        if (text.isBlank() || textBytes.size !in 1..1024 || text.any { (it < ' ' && it !in "\n\t") || it == '\u007f' })
            throw ApiFailure(FailureKind.INVALID_INPUT)
        return buildJsonObject { put("library_id", library); put("request_id", requestId); put("expected_revision", expectedRevision); put("text", text) }
            .toString().also { if (it.toByteArray(Charsets.UTF_8).size > 20 * 1024) throw ApiFailure(FailureKind.INVALID_INPUT) }
    }

    private fun validateResult(bytes: ByteArray, library: String, recovered: Boolean): AssistantTurn {
        val result = AssistantWire.response(bytes, library)
        val json = DiscoveryJson.parse(bytes, RESPONSE_LIMIT) as? JsonObject ?: bad()
        val context = json.getValue("context").let { if (it == JsonNull) null else it as? JsonObject ?: bad() }
        if (context != null) {
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
    private fun validateFilters(filters: JsonObject) {
        check(filters.keys.all { it in PhoneDiscoveryWire.fields })
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
        check(filters.toString().toByteArray(Charsets.UTF_8).size <= 16 * 1024)
        check(phoneFilters(filters).json() == filters)
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
             fromGet: Boolean): AssistantWorkspaceTurn = guarded {
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
        val result = if (rawResult == JsonNull) null else validateResult(rawResult.toString().toByteArray(Charsets.UTF_8), library, recovered)
        AssistantWorkspaceTurn(1, threadId, requestId, status, revision, recovered, error, result)
    }
}
