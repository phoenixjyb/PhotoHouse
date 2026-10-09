package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.util.Base64
import java.util.UUID

data class MemoryCommunityCapabilities(
    val enabled: Boolean,
    val contributionsEnabled: Boolean,
    val generationEnabled: Boolean,
    val conversationRetentionDays: Int,
    val audioFormat: String,
    val maxAudioSeconds: Int,
    val maxTextBytes: Int,
    val originalRetention: String,
)

data class MemoryContribution(
    val id: String, val storyId: String, val authorId: String, val kind: String,
    val language: String, val byline: String, val sha256: String, val durationMs: Long?,
    val chapterId: String?, val baseStoryRevision: Long, val state: String, val createdAt: Long,
    val text: String?, val processingConsent: Boolean,
)
data class MemoryContributionPage(
    val storyId: String, val page: Int, val hasMore: Boolean, val canReview: Boolean,
    val canDelete: Boolean, val items: List<MemoryContribution>,
)
data class MemoryContributionReceipt(
    val contribution: MemoryContribution, val canReview: Boolean, val canDelete: Boolean,
)
data class MemoryContributionDerivation(
    val revision: Int, val state: String, val transcript: String?, val polishedText: String?,
    val tags: List<String>, val errorCode: String?, val createdAt: Long, val updatedAt: Long,
)
data class MemoryContributionDetail(val receipt: MemoryContributionReceipt, val derivation: MemoryContributionDerivation?)
data class MemoryContributionRequest(
    val kind: String, val text: String, val language: String, val byline: String,
    val consent: Boolean, val chapterId: String?, val revision: Long,
    val mutationId: String = UUID.randomUUID().toString(),
)
data class MemoryBookStorySummary(val id: String, val title: String, val revision: Long,
                                  val itemCount: Int, val coverAssetId: String)
data class MemoryBook(
    val id: String, val revision: Long, val canEdit: Boolean, val title: String,
    val introduction: String, val language: String, val stories: List<MemoryBookStorySummary>,
)
data class MemoryBookPage(
    val libraryId: String, val page: Int, val hasMore: Boolean, val canCreate: Boolean,
    val items: List<MemoryBook>,
)
data class MemoryBookMutation(
    val title: String, val language: String, val introduction: String,
    val storyIds: List<String>, val revision: Long,
    val mutationId: String = UUID.randomUUID().toString(),
)
data class MemoryConversation(
    val id: String, val targetType: String, val targetId: String, val expiresAt: Long,
)
data class MemoryConversationSummary(
    val id: String,
    val createdAt: Long,
    val expiresAt: Long,
    val firstMessagePreview: String? = null,
)
data class MemoryConversationPage(val items: List<MemoryConversationSummary>)
data class MemoryTurn(
    val id: String, val sequence: Int, val inputText: String, val replyText: String?,
    val replyKind: String?, val jobId: String?, val state: String?,
    val replySourceIds: List<String>? = null, val replyQuestions: List<String>? = null,
)
data class MemoryReplyContext(val sourceIds: List<String>, val questions: List<String>)

/** Prefer opt-in history metadata; use a job only for legacy turns with metadata absent. */
fun memoryReplyContext(turn: MemoryTurn, job: MemoryJob?, revision: Long): MemoryReplyContext? {
    if (turn.state != "ready" || turn.replyText.isNullOrBlank() || turn.replyKind == null) return null
    val sourceIds = turn.replySourceIds
    val questions = turn.replyQuestions
    if (sourceIds != null && questions != null) {
        return MemoryReplyContext(sourceIds, questions).takeIf(::validReplyContext)
    }
    if (sourceIds != null || questions != null || turn.jobId == null) return null
    if (job?.id != turn.jobId || job.kind != "chat" || job.state != "ready" || job.baseRevision != revision) return null
    val result = job.result ?: return null
    val context = runCatching {
        if (result["kind"]?.jsonPrimitive?.contentOrNull != turn.replyKind ||
            result["reply"]?.jsonPrimitive?.contentOrNull != turn.replyText) return null
        val ids = result["source_ids"]?.jsonArray?.map {
            it.jsonPrimitive.takeIf(JsonPrimitive::isString)?.content ?: return null
        } ?: return null
        val fallbackQuestions = result["questions"]?.jsonArray?.map {
            it.jsonPrimitive.takeIf(JsonPrimitive::isString)?.content ?: return null
        } ?: return null
        MemoryReplyContext(ids, fallbackQuestions)
    }.getOrNull() ?: return null
    return context.takeIf(::validReplyContext)
}

private fun validReplyContext(context: MemoryReplyContext): Boolean =
    context.sourceIds.size <= 96 && context.sourceIds.distinct().size == context.sourceIds.size &&
        context.sourceIds.all { it.matches(Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")) } &&
        context.questions.size <= 3 && context.questions.all { question ->
            question.isNotBlank() && runCatching { ProtectedMemoryCommunityWire.strictUtf8(question).size <= 512 }.getOrDefault(false) &&
                question.none { it == '\u0000' || it.isISOControl() && it !in "\n\t" }
        }
data class MemoryTurnPage(
    val conversationId: String, val expiresAt: Long, val page: Int, val hasMore: Boolean,
    val items: List<MemoryTurn>,
)
data class MemoryJob(
    val id: String, val kind: String, val state: String, val createdAt: Long,
    val updatedAt: Long, val expiresAt: Long, val errorCode: String?, val result: JsonObject?,
    val needsReview: Boolean, val baseRevision: Long,
)
data class MemoryConversationRequest(val id: String = UUID.randomUUID().toString(),
                                     val targetType: String, val targetId: String)
data class MemoryTurnRequest(val revision: Long, val text: String,
                              val mutationId: String = UUID.randomUUID().toString(),
                              val editorialContext: Boolean = false)
data class MemoryNarrativeRequest(val targetType: String, val targetId: String,
    val revision: Long, val instructions: String, val mutationId: String = UUID.randomUUID().toString(),
    val editorialContext: Boolean = false)

/** Strict versioned wire contract for /memory-community/v1. */
internal object MemoryCommunityResponseLimits {
    const val JSON_BYTES = 512 * 1024
    const val WAV_BYTES = 2 * 1024 * 1024
}

internal object ProtectedMemoryCommunityWire {
    private const val MAX_JSON = MemoryCommunityResponseLimits.JSON_BYTES
    private const val MAX_WAV = MemoryCommunityResponseLimits.WAV_BYTES
    private val languages = setOf("zh", "en", "mixed", "und")
    private val states = setOf("pending", "accepted", "declined")

    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(ok: Boolean) { if (!ok) bad() }
    private fun obj(v: JsonElement?, vararg keys: String): JsonObject =
        (v as? JsonObject ?: bad()).also { check(it.keys == keys.toSet()) }
    private fun str(v: JsonElement?, maxBytes: Int, blank: Boolean = false, newline: Boolean = false): String {
        val p = v as? JsonPrimitive ?: bad(); check(p.isString)
        val value = p.content
        val bytes = try { strictUtf8(value) } catch (_: Exception) { bad() }
        check(bytes.size <= maxBytes && (blank || value.isNotBlank()))
        check(value.none { it == '\u0000' || it.isISOControl() && !(newline && it in "\n\t") })
        return value
    }
    private fun int(v: JsonElement?, min: Int = 0, max: Int = Int.MAX_VALUE): Int {
        val p = v as? JsonPrimitive ?: bad(); check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toLongOrNull()?.takeIf { it in min.toLong()..max.toLong() }?.toInt() ?: bad()
    }
    private fun long(v: JsonElement?, min: Long = 0, max: Long = Long.MAX_VALUE): Long {
        val p = v as? JsonPrimitive ?: bad(); check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toLongOrNull()?.takeIf { it in min..max } ?: bad()
    }
    private fun decimal(v: JsonElement?, positive: Boolean = false): Long {
        val s = str(v, 19)
        check(s.matches(Regex(if (positive) "[1-9][0-9]{0,18}" else "0|[1-9][0-9]{0,18}")))
        return s.toLongOrNull() ?: bad()
    }
    private fun bool(v: JsonElement?): Boolean {
        val p = v as? JsonPrimitive ?: bad(); check(!p.isString)
        return p.booleanOrNull ?: bad()
    }
    private fun nullableString(v: JsonElement?, max: Int, blank: Boolean = true, newline: Boolean = false): String? =
        if (v == JsonNull) null else str(v, max, blank, newline)
    private fun uuid(value: String): String = value.also {
        check(runCatching { UUID.fromString(it).toString() == it }.getOrDefault(false))
    }
    private fun arr(v: JsonElement?, max: Int): JsonArray =
        (v as? JsonArray ?: bad()).also { check(it.size <= max) }
    private fun root(bytes: ByteArray): JsonObject = try {
        DiscoveryJson.parse(bytes, MAX_JSON, 512) as? JsonObject ?: bad()
    } catch (e: ApiFailure) { throw e } catch (_: Exception) { bad() }

    fun capabilities(bytes: ByteArray): MemoryCommunityCapabilities = guarded {
        val r = root(bytes); obj(r, "version", "enabled", "contributions_enabled", "generation_enabled",
            "conversation_retention_days", "audio_format", "max_audio_seconds", "max_text_bytes", "original_retention")
        check(int(r["version"], 1, 1) == 1)
        val retention = int(r["conversation_retention_days"], 30, 30)
        val format = str(r["audio_format"], 64).also { check(it == "wav_pcm16_mono_16000") }
        val seconds = int(r["max_audio_seconds"], 1, 30)
        val textBytes = int(r["max_text_bytes"], 1, 8192)
        val originalRetention = str(r["original_retention"], 64).also { check(it == "until_owner_deletes") }
        val enabled = bool(r["enabled"]); val contributions = bool(r["contributions_enabled"])
        val generation = bool(r["generation_enabled"])
        check((contributions.not() || enabled) && (generation.not() || enabled))
        MemoryCommunityCapabilities(enabled, contributions, generation, retention, format, seconds, textBytes, originalRetention)
    }

    private fun contribution(v: JsonElement?, receipt: Boolean = false): MemoryContributionReceipt {
        val common = setOf("id", "story_id", "author_id", "kind", "language", "byline", "sha256",
            "duration_ms", "chapter_id", "base_story_revision", "state", "created_at", "text", "processing_consent")
        val keys = common + if (receipt) setOf("version", "can_review", "can_delete") else emptySet()
        val r = obj(v, *keys.toTypedArray())
        if (receipt) check(int(r["version"], 1, 1) == 1)
        val id = uuid(str(r["id"], 36)); val storyId = uuid(str(r["story_id"], 36))
        val author = uuid(str(r["author_id"], 36)); val kind = str(r["kind"], 8).also { check(it in setOf("text", "audio")) }
        val language = str(r["language"], 8).also { check(it in languages) }
        val byline = str(r["byline"], 256, blank = true, newline = true)
        val sha = str(r["sha256"], 64).also { check(it.matches(Regex("[0-9a-f]{64}"))) }
        val duration = if (r["duration_ms"] == JsonNull) null else long(r["duration_ms"], 1, 30000)
        val chapter = nullableString(r["chapter_id"], 32)
        if (chapter != null) check(chapter.matches(Regex("chapter-[1-6]")))
        val baseRevision = decimal(r["base_story_revision"], positive = true)
        val state = str(r["state"], 16).also { check(it in states) }
        val created = long(r["created_at"], 0, 253402300799)
        val text = nullableString(r["text"], 8192, blank = kind == "audio", newline = true)
        val consent = bool(r["processing_consent"])
        check(if (kind == "text") text != null && duration == null else text == null && duration != null)
        val item = MemoryContribution(id, storyId, author, kind, language, byline, sha, duration,
            chapter, baseRevision, state, created, text, consent)
        return MemoryContributionReceipt(item, if (receipt) bool(r["can_review"]) else false,
            if (receipt) bool(r["can_delete"]) else false)
    }

    fun contributionPage(bytes: ByteArray, storyId: String, page: Int): MemoryContributionPage = guarded {
        val r = root(bytes); obj(r, "version", "story_id", "page", "page_size", "has_more", "can_review", "can_delete", "items")
        check(int(r["version"], 1, 1) == 1 && uuid(str(r["story_id"], 36)) == storyId)
        check(int(r["page"], 1, 100000) == page && int(r["page_size"], 16, 16) == 16)
        val items = arr(r["items"], 16).map { contribution(it).contribution }
        check(items.all { it.storyId == storyId } && items.map { it.id }.distinct().size == items.size)
        MemoryContributionPage(storyId, page, bool(r["has_more"]), bool(r["can_review"]), bool(r["can_delete"]), items)
    }

    fun contributionReceipt(bytes: ByteArray, expectedStory: String): MemoryContributionReceipt = guarded {
        contribution(root(bytes), true).also { check(it.contribution.storyId == expectedStory) }
    }

    fun contributionDetail(bytes: ByteArray, storyId: String, contributionId: String): MemoryContributionDetail = guarded {
        val r = root(bytes); val receiptKeys = setOf("version", "id", "story_id", "author_id", "kind", "language", "byline", "sha256",
            "duration_ms", "chapter_id", "base_story_revision", "state", "created_at", "text", "processing_consent", "can_review", "can_delete")
        obj(r, *(receiptKeys + "derivation").toTypedArray())
        val receipt = contribution(JsonObject(r.filterKeys { it != "derivation" }), true)
        check(receipt.contribution.storyId == storyId && receipt.contribution.id == contributionId)
        val derivation = if (r["derivation"] == JsonNull) null else {
            val d = obj(r["derivation"], "revision", "state", "transcript", "polished_text", "tags", "error_code", "created_at", "updated_at")
            val state = str(d["state"], 16).also { check(it in setOf("waiting", "running", "ready", "failed", "cancelled")) }
            val tags = arr(d["tags"], 24).map { str(it, 256) }
            check(tags.distinct().size == tags.size)
            MemoryContributionDerivation(int(d["revision"], 1), state,
                nullableString(d["transcript"], 8192, newline = true),
                nullableString(d["polished_text"], 8192, newline = true), tags,
                nullableString(d["error_code"], 128), long(d["created_at"]), long(d["updated_at"]))
        }
        MemoryContributionDetail(receipt, derivation)
    }

    fun textRequest(request: MemoryContributionRequest): String {
        require(request.kind == "text" && request.revision > 0 && request.language in languages)
        require(request.text.isNotBlank() && strictUtf8(request.text).size <= 8192 && safeText(request.text, allowNewline = true))
        require(strictUtf8(request.byline).size <= 256 && safeText(request.byline, allowNewline = true))
        request.chapterId?.let { require(it.matches(Regex("chapter-[1-6]"))) }
        requireCanonicalUuid(request.mutationId)
        return buildJsonObject {
            put("kind", "text"); put("text", request.text); put("language", request.language)
            put("byline", request.byline); put("consent", if (request.consent) "1" else "0")
            put("chapter_id", request.chapterId ?: ""); put("revision", request.revision.toString())
            put("mutation_id", request.mutationId)
        }.toString()
    }

    fun audioMetadata(request: MemoryContributionRequest, capabilities: MemoryCommunityCapabilities): String {
        require(capabilities.enabled && capabilities.contributionsEnabled && capabilities.maxAudioSeconds in 1..30)
        require(request.kind == "audio" && request.text.isEmpty() && request.revision > 0 && request.language in languages)
        require(strictUtf8(request.byline).size <= 256 && safeText(request.byline, allowNewline = true))
        request.chapterId?.let { require(it.matches(Regex("chapter-[1-6]"))) }
        requireCanonicalUuid(request.mutationId)
        val json = buildJsonObject {
            put("kind", "audio"); put("text", ""); put("language", request.language)
            put("byline", request.byline); put("consent", if (request.consent) "1" else "0")
            put("chapter_id", request.chapterId ?: ""); put("revision", request.revision.toString())
            put("mutation_id", request.mutationId)
        }.toString()
        val encoded = Base64.getEncoder().encodeToString(json.toByteArray(Charsets.UTF_8))
        require(encoded.length <= 4096)
        return encoded
    }

    fun validWav(bytes: ByteArray, maxSeconds: Int): Boolean {
        if (maxSeconds !in 1..30 || bytes.size !in 46..MAX_WAV || !ascii(bytes, 0, "RIFF") ||
            !ascii(bytes, 8, "WAVE") || u32(bytes, 4) != bytes.size - 8L) return false
        var offset = 12
        var formatSeen = false
        var dataSize = -1L
        while (offset + 8 <= bytes.size) {
            val chunkSize = u32(bytes, offset + 4)
            val content = offset + 8
            if (chunkSize > Int.MAX_VALUE || content.toLong() + chunkSize > bytes.size) return false
            when {
                ascii(bytes, offset, "fmt ") -> {
                    if (formatSeen || chunkSize < 16) return false
                    formatSeen = true
                    if (u16(bytes, content) != 1 || u16(bytes, content + 2) != 1 ||
                        u32(bytes, content + 4) != 16000L || u32(bytes, content + 8) != 32000L ||
                        u16(bytes, content + 12) != 2 || u16(bytes, content + 14) != 16) return false
                }
                ascii(bytes, offset, "data") -> {
                    if (dataSize >= 0) return false
                    dataSize = chunkSize
                }
            }
            offset = content + chunkSize.toInt() + (chunkSize.toInt() and 1)
        }
        if (offset != bytes.size || !formatSeen || dataSize <= 0 || dataSize % 2L != 0L ||
            dataSize / 32000.0 > maxSeconds) return false
        return true
    }

    fun bookPage(bytes: ByteArray, library: String, page: Int): MemoryBookPage = guarded {
        val r = root(bytes); obj(r, "version", "library_id", "page", "page_size", "has_more", "can_create", "items")
        check(int(r["version"], 1, 1) == 1 && str(r["library_id"], 256) == library)
        check(int(r["page"], 1, 100000) == page && int(r["page_size"], 8, 8) == 8)
        val books = arr(r["items"], 8).map { book(it) }
        check(books.map { it.id }.distinct().size == books.size)
        MemoryBookPage(library, page, bool(r["has_more"]), bool(r["can_create"]), books)
    }

    fun bookDetail(bytes: ByteArray, expectedId: String? = null, expectedRevision: Long = 1): MemoryBook = guarded {
        val parsed = book(root(bytes)); check((expectedId == null || parsed.id == expectedId) && parsed.revision >= expectedRevision); parsed
    }

    private fun book(v: JsonElement?): MemoryBook {
        val r = obj(v, "version", "type", "id", "revision", "can_edit", "title", "introduction", "language", "stories")
        check(int(r["version"], 1, 1) == 1 && str(r["type"], 16) == "memoir")
        val id = uuid(str(r["id"], 36)); val revision = decimal(r["revision"], true)
        val title = str(r["title"], 512); val intro = str(r["introduction"], 6000, blank = true, newline = true)
        val language = str(r["language"], 2).also { check(it in setOf("zh", "en")) }
        val stories = arr(r["stories"], 24).map { sv ->
            val s = obj(sv, "id", "title", "revision", "item_count", "cover_asset_id")
            MemoryBookStorySummary(uuid(str(s["id"], 36)), str(s["title"], 512),
                decimal(s["revision"], true), int(s["item_count"], 1, 24),
                str(s["cover_asset_id"], 19).also { check(PhoneDiscoveryWire.validId(it)) })
        }
        check(stories.isNotEmpty() && stories.map { it.id }.distinct().size == stories.size)
        return MemoryBook(id, revision, bool(r["can_edit"]), title, intro, language, stories)
    }

    fun bookRequest(request: MemoryBookMutation): String {
        require(request.title.isNotBlank() && strictUtf8(request.title).size <= 512 && safeText(request.title))
        require(strictUtf8(request.introduction).size <= 6000 && safeText(request.introduction, allowNewline = true))
        require(request.language in setOf("zh", "en") && request.storyIds.size in 1..24)
        request.storyIds.forEach(::requireCanonicalUuid); require(request.storyIds.distinct().size == request.storyIds.size)
        require(request.revision >= 0); requireCanonicalUuid(request.mutationId)
        return buildJsonObject {
            put("title", request.title); put("language", request.language); put("introduction", request.introduction)
            put("story_ids", request.storyIds.joinToString(",")); put("revision", request.revision.toString())
            put("mutation_id", request.mutationId)
        }.toString()
    }

    fun reviewRequest(accepted: Boolean, revision: Long): String {
        require(revision > 0)
        return buildJsonObject {
            put("state", if (accepted) "accepted" else "declined")
            put("revision", revision.toString())
        }.toString()
    }

    fun conversation(bytes: ByteArray, request: MemoryConversationRequest): MemoryConversation = guarded {
        val r = root(bytes); obj(r, "version", "id", "target_type", "target_id", "expires_at")
        check(int(r["version"], 1, 1) == 1)
        val parsed = MemoryConversation(uuid(str(r["id"], 36)), str(r["target_type"], 8),
            uuid(str(r["target_id"], 36)), long(r["expires_at"]))
        check(parsed.id == request.id && parsed.targetType == request.targetType && parsed.targetId == request.targetId &&
            parsed.targetType in setOf("story", "book"))
        parsed
    }

    fun conversationRequest(request: MemoryConversationRequest): String {
        require(request.targetType in setOf("story", "book")); requireCanonicalUuid(request.id)
        requireCanonicalUuid(request.targetId)
        return buildJsonObject {
            put("id", request.id); put("target_type", request.targetType); put("target_id", request.targetId)
        }.toString()
    }

    fun conversations(bytes: ByteArray): MemoryConversationPage = guarded {
        val r = root(bytes); obj(r, "version", "items"); check(int(r["version"], 1, 1) == 1)
        val rows = arr(r["items"], 8).map { v ->
            val row = v as? JsonObject ?: bad()
            val legacyKeys = setOf("id", "created_at", "expires_at")
            val previewKeys = legacyKeys + "first_message_preview"
            check(row.keys == legacyKeys || row.keys == previewKeys)
            val preview = if (row.keys == previewKeys) conversationPreview(row["first_message_preview"]) else null
            MemoryConversationSummary(uuid(str(row["id"], 36)), long(row["created_at"]), long(row["expires_at"]), preview)
        }
        check(rows.map { it.firstMessagePreview != null }.distinct().size <= 1)
        check(rows.map { it.id }.distinct().size == rows.size)
        MemoryConversationPage(rows)
    }

    private fun conversationPreview(value: JsonElement?): String {
        val preview = str(value, 320, blank = true)
        val points = preview.codePoints().toArray()
        check(points.size <= 80)
        var previousWhitespace = false
        points.forEachIndexed { index, codePoint ->
            val whitespace = Character.isWhitespace(codePoint) || Character.isSpaceChar(codePoint)
            if (whitespace) check(codePoint == ' '.code && index > 0 && index < points.lastIndex && !previousWhitespace)
            previousWhitespace = whitespace
        }
        return preview
    }

    fun turns(bytes: ByteArray, conversationId: String, page: Int): MemoryTurnPage = guarded {
        val r = root(bytes); obj(r, "version", "id", "expires_at", "page", "has_more", "items")
        check(int(r["version"], 1, 1) == 1 && uuid(str(r["id"], 36)) == conversationId)
        check(int(r["page"], 1, 100000) == page)
        val rows = arr(r["items"], 16).map { v ->
            val row = v as? JsonObject ?: bad()
            val legacyKeys = setOf("id", "sequence", "input_text", "reply_text", "reply_kind", "job_id", "state")
            val contextKeys = legacyKeys + setOf("reply_source_ids", "reply_questions")
            check(row.keys == legacyKeys || row.keys == contextKeys)
            val hasReplySourceIds = "reply_source_ids" in row
            val hasReplyQuestions = "reply_questions" in row
            check(hasReplySourceIds == hasReplyQuestions)
            val i = row
            val kind = nullableString(i["reply_kind"], 32)
            val state = nullableString(i["state"], 16)
            check(kind == null || kind in setOf("answer", "clarification", "proposal"))
            check(state == null || state in setOf("queued", "running", "ready", "failed", "cancelled", "stale"))
            val sourceIds = if (hasReplySourceIds) refs(i["reply_source_ids"], 96, opaqueIds = true) else null
            val followups = if (hasReplyQuestions) questions(i["reply_questions"], 3) else null
            MemoryTurn(uuid(str(i["id"], 36)), int(i["sequence"], 1, 128), str(i["input_text"], 4096, newline = true),
                nullableString(i["reply_text"], 4096, newline = true), kind,
                nullableString(i["job_id"], 36)?.also(::uuid), state, sourceIds, followups)
        }
        check(rows.map { it.sequence }.distinct().size == rows.size)
        MemoryTurnPage(conversationId, long(r["expires_at"]), page, bool(r["has_more"]), rows)
    }

    fun turnRequest(request: MemoryTurnRequest): String {
        require(request.revision > 0 && safeText(request.text, allowNewline = true) &&
            request.text.isNotBlank() && strictUtf8(request.text).size <= 4096)
        requireCanonicalUuid(request.mutationId)
        return buildJsonObject {
            put("revision", request.revision.toString()); put("mutation_id", request.mutationId); put("text", request.text)
        }.toString()
    }

    fun job(bytes: ByteArray, expectedId: String? = null): MemoryJob = guarded {
        val r = root(bytes); obj(r, "version", "id", "kind", "state", "created_at", "updated_at", "expires_at",
            "error_code", "result", "needs_review", "base_revision")
        check(int(r["version"], 1, 1) == 1)
        val id = uuid(str(r["id"], 36)); if (expectedId != null) check(id == expectedId)
        val kind = str(r["kind"], 16).also { check(it in setOf("narrative", "chat")) }
        val state = str(r["state"], 16).also { check(it in setOf("queued", "running", "ready", "failed", "cancelled", "stale")) }
        val result = if (r["result"] == JsonNull) null else r["result"] as? JsonObject ?: bad()
        check((state == "ready") == (result != null))
        result?.let { if (kind == "chat") companionResult(it) else narrativeResult(it) }
        MemoryJob(id, kind, state, long(r["created_at"]), long(r["updated_at"]), long(r["expires_at"]),
            nullableString(r["error_code"], 128), result, bool(r["needs_review"]).also { check(it) }, decimal(r["base_revision"], true))
    }

    private fun narrativeResult(r: JsonObject) {
        obj(r, "version", "title", "chapters", "questions", "needs_review")
        check(int(r["version"], 1, 1) == 1 && bool(r["needs_review"]))
        str(r["title"], 512)
        val chapters = arr(r["chapters"], 24)
        check(chapters.isNotEmpty())
        chapters.forEach { element ->
            val c = obj(element, "id", "narration", "source_ids")
            str(c["id"], 128)
            str(c["narration"], 6000, blank = true, newline = true)
            refs(c["source_ids"], 96)
        }
        questions(r["questions"], 6)
    }

    private fun companionResult(r: JsonObject) {
        obj(r, "version", "kind", "reply", "source_ids", "questions", "proposal")
        check(int(r["version"], 1, 1) == 1)
        val kind = str(r["kind"], 16).also { check(it in setOf("answer", "clarification", "proposal")) }
        str(r["reply"], 4000, newline = true)
        refs(r["source_ids"], 96)
        questions(r["questions"], 3)
        val proposal = r["proposal"]
        check((kind == "proposal") == (proposal != JsonNull))
        if (proposal != JsonNull) narrativeResult(proposal as? JsonObject ?: bad())
    }

    private fun refs(value: JsonElement?, maximum: Int, opaqueIds: Boolean = false): List<String> {
        val values = arr(value, maximum).map { str(it, 128) }
        check(values.distinct().size == values.size)
        if (opaqueIds) check(values.all { it.matches(Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")) })
        return values
    }

    private fun questions(value: JsonElement?, maximum: Int): List<String> =
        arr(value, maximum).map { str(it, 512, newline = true) }

    fun deleted(bytes: ByteArray, expectedId: String) = guarded {
        val r = root(bytes); obj(r, "deleted", "id")
        check(bool(r["deleted"]) && uuid(str(r["id"], 36)) == expectedId)
    }

    fun deletedConversation(bytes: ByteArray) = guarded {
        val r = root(bytes); obj(r, "version", "deleted")
        check(int(r["version"], 1, 1) == 1 && bool(r["deleted"]))
    }

    fun narrativeRequest(request: MemoryNarrativeRequest): String {
        require(request.targetType in setOf("story", "book")); requireCanonicalUuid(request.targetId)
        require(request.revision > 0 && safeText(request.instructions, allowNewline = true) && strictUtf8(request.instructions).size <= 4096)
        requireCanonicalUuid(request.mutationId)
        return buildJsonObject {
            put("target_type", request.targetType); put("target_id", request.targetId)
            put("revision", request.revision.toString()); put("mutation_id", request.mutationId); put("instructions", request.instructions)
        }.toString()
    }

    fun strictUtf8(value: String) = Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(value)).let { out ->
            ByteArray(out.remaining()).also(out::get)
        }
    private fun safeText(value: String, allowNewline: Boolean = false) =
        value.none { it == '\u0000' || it.isISOControl() && !(allowNewline && it in "\n\t") } && runCatching { strictUtf8(value) }.isSuccess
    private fun requireCanonicalUuid(value: String) { require(runCatching { UUID.fromString(value).toString() == value }.getOrDefault(false)) }
    private fun ascii(bytes: ByteArray, offset: Int, value: String) =
        offset + value.length <= bytes.size && value.indices.all { bytes[offset + it] == value[it].code.toByte() }
    private fun u16(bytes: ByteArray, offset: Int) = (bytes[offset].toInt() and 255) or ((bytes[offset + 1].toInt() and 255) shl 8)
    private fun u32(bytes: ByteArray, offset: Int): Long = u16(bytes, offset).toLong() or (u16(bytes, offset + 2).toLong() shl 16)
    private inline fun <T> guarded(block: () -> T): T = try { block() } catch (e: ApiFailure) { throw e } catch (_: Exception) { bad() }
}
