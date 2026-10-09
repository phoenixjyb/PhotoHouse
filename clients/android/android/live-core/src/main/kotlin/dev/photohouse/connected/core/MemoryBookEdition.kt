package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.UUID

data class MemoryBookEditionCapabilities(val enabled: Boolean, val canSave: Boolean)
data class MemoryBookEditionChild(val id: String, val revision: String)
data class MemoryBookEditionChapter(val id: String, val narration: String, val sourceIds: List<String>)
data class MemoryBookEditionManuscript(
    val title: String,
    val chapters: List<MemoryBookEditionChapter>,
    val questions: List<String>,
    val needsReview: Boolean = true,
)
data class MemoryBookEditionProposal(
    val bookId: String,
    val revision: String,
    val jobId: String,
    val jobResultSha256: String,
    val sourceFingerprint: String,
    val contextProfile: String,
    val children: List<MemoryBookEditionChild>,
    val manuscript: MemoryBookEditionManuscript,
    val needsReview: Boolean,
)
data class MemoryBookEditionSaveRequest(
    val version: Int,
    val revision: String,
    val mutationId: String,
    val jobId: String,
    val jobResultSha256: String,
    val sourceFingerprint: String,
    val reviewed: Boolean,
    val children: List<MemoryBookEditionChild>,
    val manuscript: MemoryBookEditionManuscript,
)
enum class MemoryBookEditionState { CURRENT, SOURCE_CHANGED, SOURCE_INVALIDATED }
data class MemoryBookEditionReceipt(
    val id: String,
    val bookId: String,
    val bookRevision: String,
    val createdAt: Long,
    val state: MemoryBookEditionState,
    val mutationId: String,
)
data class MemoryBookEditionDetail(
    val receipt: MemoryBookEditionReceipt,
    val manuscript: MemoryBookEditionManuscript?,
)
data class MemoryBookEditionPage(
    val bookId: String,
    val page: Int,
    val hasMore: Boolean,
    val items: List<MemoryBookEditionDetail>,
)

/** Bounded exact-field wire checks plus deterministic request freezing for reviewed editions. */
object MemoryBookEditionWire {
    const val MAX_REQUEST_BYTES = 128 * 1024
    private const val MAX_RESPONSE_BYTES = MemoryCommunityResponseLimits.JSON_BYTES
    private const val MAX_CHILDREN = 24
    private const val MAX_CHAPTERS = 24
    private const val MAX_SOURCES = 96
    private const val MAX_TEXT_BYTES = 6000
    private const val MAX_MANUSCRIPT_TITLE_BYTES = 512
    private const val MAX_QUESTIONS = 6
    private const val MAX_QUESTION_BYTES = 512
    private const val MAX_SOURCE_ID_BYTES = 128
    private const val MAX_STORED_MANUSCRIPT_BYTES = 196608
    private const val MAX_MANUSCRIPT_BYTES = 64 * 1024
    private val safeId = Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    private val revisionPattern = Regex("[1-9][0-9]{0,18}")
    private val sha256Pattern = Regex("[0-9a-f]{64}")

    private fun invalid(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun input(ok: Boolean) { require(ok) { "Invalid reviewed memoir edition input" } }
    private fun check(ok: Boolean) { if (!ok) invalid() }

    private fun utf8(value: String): ByteArray = try {
        val encoded = Charsets.UTF_8.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .encode(CharBuffer.wrap(value))
        ByteArray(encoded.remaining()).also(encoded::get)
    } catch (_: Exception) {
        invalid()
    }

    private fun uuid(value: String): String = value.also {
        check(runCatching { UUID.fromString(it).toString() == it }.getOrDefault(false))
    }

    private fun canonicalUuid(value: String): Boolean =
        runCatching { UUID.fromString(value).toString() == value }.getOrDefault(false)

    private fun validRevision(value: String): Long {
        check(revisionPattern.matches(value))
        return value.toLongOrNull() ?: invalid()
    }

    private fun revision(value: JsonElement?): String = string(value, 19).also(::validRevision)

    private fun sha(value: JsonElement?): String = string(value, 64).also {
        check(sha256Pattern.matches(it))
    }

    private fun obj(value: JsonElement?, vararg keys: String): JsonObject =
        (value as? JsonObject ?: invalid()).also { check(it.keys == keys.toSet()) }

    private fun string(value: JsonElement?, maxBytes: Int, blank: Boolean = false): String {
        val primitive = value as? JsonPrimitive ?: invalid()
        check(primitive.isString)
        val text = primitive.content
        check(utf8(text).size <= maxBytes && (blank || text.isNotBlank()))
        check(text.none { it == '\u0000' || it.isISOControl() && it !in "\n\t" })
        return text
    }

    private fun bool(value: JsonElement?): Boolean {
        val primitive = value as? JsonPrimitive ?: invalid()
        check(!primitive.isString)
        return primitive.booleanOrNull ?: invalid()
    }

    private fun integer(value: JsonElement?, minimum: Long, maximum: Long): Long {
        val primitive = value as? JsonPrimitive ?: invalid()
        check(!primitive.isString && primitive.content.matches(Regex("0|[1-9][0-9]*")))
        return primitive.content.toLongOrNull()?.takeIf { it in minimum..maximum } ?: invalid()
    }

    private fun array(value: JsonElement?, maximum: Int): JsonArray =
        (value as? JsonArray ?: invalid()).also { check(it.size <= maximum) }

    private fun children(value: JsonElement?, expected: List<MemoryBookEditionChild>? = null): List<MemoryBookEditionChild> {
        val raw = array(value, MAX_CHILDREN)
        check(raw.isNotEmpty())
        val result = raw.map { item ->
            val child = obj(item, "id", "revision")
            MemoryBookEditionChild(uuid(string(child["id"], 36)), revision(child["revision"]))
        }
        check(result.map { it.id }.distinct().size == result.size)
        if (expected != null) check(result == expected)
        return result
    }

    private fun manuscript(
        value: JsonElement?, expectedChapterIds: List<String>, allowedSourceIds: Map<String, Set<String>>? = null,
    ): MemoryBookEditionManuscript {
        val root = obj(value, "version", "title", "chapters", "questions", "needs_review")
        check(integer(root["version"], 1, 1) == 1L)
        val title = string(root["title"], MAX_MANUSCRIPT_TITLE_BYTES)
        check(bool(root["needs_review"]))
        check(expectedChapterIds.size in 1..MAX_CHAPTERS)
        check(expectedChapterIds.distinct().size == expectedChapterIds.size)
        expectedChapterIds.forEach { check(safeId.matches(it) && utf8(it).size <= 128) }
        val rawChapters = array(root["chapters"], MAX_CHAPTERS)
        check(rawChapters.size == expectedChapterIds.size)
        val chapters = rawChapters.mapIndexed { index, raw ->
            val chapter = obj(raw, "id", "narration", "source_ids")
            val id = string(chapter["id"], 128)
            check(id == expectedChapterIds[index] && safeId.matches(id))
            val narration = string(chapter["narration"], MAX_TEXT_BYTES, blank = true)
            val refs = array(chapter["source_ids"], MAX_SOURCES).map { string(it, MAX_SOURCE_ID_BYTES) }
            check(refs.distinct().size == refs.size && refs.all(safeId::matches))
            if (allowedSourceIds != null) check(refs.all { it in (allowedSourceIds[id] ?: emptySet()) })
            check(narration.isBlank() || refs.isNotEmpty())
            MemoryBookEditionChapter(id, narration, refs)
        }
        val rawQuestions = array(root["questions"], MAX_QUESTIONS)
        val questions = rawQuestions.map { string(it, MAX_QUESTION_BYTES) }
        val result = MemoryBookEditionManuscript(title, chapters, questions, needsReview = true)
        val serialized = canonicalManuscript(result)
        check(utf8(serialized).size <= MAX_MANUSCRIPT_BYTES)
        val storedSize = serialized.sumOf { if (it.code > 0x7f) 6L else 1L }
        check(storedSize <= MAX_STORED_MANUSCRIPT_BYTES)
        return result
    }

    private fun canonicalManuscript(value: MemoryBookEditionManuscript): String = buildJsonObject {
        put("version", 1)
        put("title", value.title)
        put("chapters", JsonArray(value.chapters.map { chapter -> buildJsonObject {
            put("id", chapter.id); put("narration", chapter.narration)
            put("source_ids", JsonArray(chapter.sourceIds.map(::JsonPrimitive)))
        } }))
        put("questions", JsonArray(value.questions.map(::JsonPrimitive)))
        put("needs_review", true)
    }.toString()

    private fun expectedAllowed(proposal: MemoryBookEditionProposal): Map<String, Set<String>> =
        proposal.manuscript.chapters.associate { it.id to it.sourceIds.toSet() }

    private fun validateChapterOrder(childList: List<MemoryBookEditionChild>, ids: List<String>) {
        check(ids.size in 1..MAX_CHAPTERS && childList.isNotEmpty())
        var childIndex = 0
        var chapterIndex = 1
        ids.forEach { id ->
            if (!id.startsWith(childList[childIndex].id + "-chapter-")) {
                check(chapterIndex > 1)
                childIndex++
                chapterIndex = 1
                check(childIndex < childList.size)
            }
            check(id == "${childList[childIndex].id}-chapter-${chapterIndex++}" && chapterIndex <= 7)
        }
        check(childIndex == childList.lastIndex)
    }

    private fun validateProposalForSave(proposal: MemoryBookEditionProposal) {
        try {
            uuid(proposal.bookId); validRevision(proposal.revision); uuid(proposal.jobId)
            check(sha256Pattern.matches(proposal.jobResultSha256) && sha256Pattern.matches(proposal.sourceFingerprint))
            check(proposal.contextProfile in setOf("stories", "memoir_editorial_v1"))
            check(proposal.needsReview && proposal.manuscript.needsReview)
            val childList = children(JsonArray(proposal.children.map { child -> buildJsonObject {
                put("id", child.id); put("revision", child.revision)
            } }))
            val chapterIds = proposal.manuscript.chapters.map { it.id }
            validateChapterOrder(childList, chapterIds)
            manuscript(DiscoveryJson.parse(utf8(canonicalManuscript(proposal.manuscript)), MAX_REQUEST_BYTES, 256), chapterIds)
        } catch (_: ApiFailure) {
            throw IllegalArgumentException("Invalid reviewed memoir edition input")
        }
    }

    fun decodeCapabilities(bytes: ByteArray): MemoryBookEditionCapabilities = guarded(bytes) {
        val root = obj(DiscoveryJson.parse(bytes, MAX_RESPONSE_BYTES, 8), "version", "enabled", "can_save")
        check(integer(root["version"], 1, 1) == 1L)
        val enabled = bool(root["enabled"])
        val canSave = bool(root["can_save"])
        check(!canSave || enabled)
        MemoryBookEditionCapabilities(enabled, canSave)
    }

    fun decodeProposal(
        bytes: ByteArray, expectedBookId: String, expectedRevision: Long, expectedJobId: String,
        expectedChildren: List<MemoryBookEditionChild>, expectedChapterIds: List<String>,
    ): MemoryBookEditionProposal = guarded(bytes) {
        check(expectedRevision > 0 && expectedChildren.size in 1..MAX_CHILDREN)
        uuid(expectedBookId); uuid(expectedJobId)
        val root = obj(DiscoveryJson.parse(bytes, MAX_RESPONSE_BYTES, 128), "version", "book_id", "revision",
            "job_id", "job_result_sha256", "source_fingerprint", "context_profile", "children", "manuscript",
            "needs_review")
        check(integer(root["version"], 1, 1) == 1L)
        val bookId = uuid(string(root["book_id"], 36)); check(bookId == expectedBookId)
        val bookRevision = revision(root["revision"]); check(bookRevision.toLong() == expectedRevision)
        val jobId = uuid(string(root["job_id"], 36)); check(jobId == expectedJobId)
        val jobDigest = sha(root["job_result_sha256"])
        val fingerprint = sha(root["source_fingerprint"])
        val profile = string(root["context_profile"], 32)
        check(profile in setOf("stories", "memoir_editorial_v1"))
        val childList = children(root["children"], expectedChildren)
        validateChapterOrder(childList, expectedChapterIds)
        val manuscript = manuscript(root["manuscript"], expectedChapterIds)
        check(bool(root["needs_review"]))
        MemoryBookEditionProposal(bookId, bookRevision, jobId, jobDigest, fingerprint, profile,
            childList, manuscript, needsReview = true)
    }

    /** Produce one immutable exact body from a reviewed proposal. Never log the returned text. */
    fun encodeSaveRequest(
        proposal: MemoryBookEditionProposal,
        mutationId: String,
        reviewedManuscript: MemoryBookEditionManuscript = proposal.manuscript,
        reviewed: Boolean,
    ): String {
        input(reviewed && reviewedManuscript.needsReview)
        validateProposalForSave(proposal)
        input(canonicalUuid(mutationId) && proposal.needsReview && reviewedManuscript.needsReview)
        val allowed = expectedAllowed(proposal)
        val normalized = try {
            // Reuse the response validator for exact chapter order, citation bounds, text controls,
            // UTF-8 lengths, and stored-size constraints.
            val raw = utf8(canonicalManuscript(reviewedManuscript))
            val root = DiscoveryJson.parse(raw, MAX_REQUEST_BYTES, 256)
            manuscript(root, proposal.manuscript.chapters.map { it.id }, allowed).also { value ->
                check(value.questions == proposal.manuscript.questions)
                check(value.chapters.map { it.sourceIds } == proposal.manuscript.chapters.map { it.sourceIds })
            }
        } catch (_: ApiFailure) {
            throw IllegalArgumentException("Invalid reviewed memoir edition input")
        }
        val fields = buildJsonObject {
            put("version", 1)
            put("revision", proposal.revision)
            put("mutation_id", mutationId)
            put("job_id", proposal.jobId)
            put("job_result_sha256", proposal.jobResultSha256)
            put("source_fingerprint", proposal.sourceFingerprint)
            put("reviewed", true)
            put("children", JsonArray(proposal.children.map { child -> buildJsonObject {
                put("id", child.id); put("revision", child.revision)
            } }))
            put("manuscript", Json.parseToJsonElement(canonicalManuscript(normalized)))
        }.toString()
        input(utf8(fields).size <= MAX_REQUEST_BYTES)
        return fields
    }

    fun decodeSaveRequest(bytes: ByteArray, proposal: MemoryBookEditionProposal): MemoryBookEditionSaveRequest = guarded(bytes) {
        check(bytes.size in 1..MAX_REQUEST_BYTES)
        validateProposalForSave(proposal)
        val root = obj(DiscoveryJson.parse(bytes, MAX_REQUEST_BYTES, 256), "version", "revision", "mutation_id",
            "job_id", "job_result_sha256", "source_fingerprint", "reviewed", "children", "manuscript")
        check(integer(root["version"], 1, 1) == 1L)
        val bookRevision = revision(root["revision"]); check(bookRevision == proposal.revision)
        val mutationId = uuid(string(root["mutation_id"], 36))
        val jobId = uuid(string(root["job_id"], 36)); check(jobId == proposal.jobId)
        val jobDigest = sha(root["job_result_sha256"]); check(jobDigest == proposal.jobResultSha256)
        val fingerprint = sha(root["source_fingerprint"]); check(fingerprint == proposal.sourceFingerprint)
        check(bool(root["reviewed"]))
        val childList = children(root["children"], proposal.children)
        val normalized = manuscript(root["manuscript"], proposal.manuscript.chapters.map { it.id },
            expectedAllowed(proposal))
        MemoryBookEditionSaveRequest(1, bookRevision, mutationId, jobId, jobDigest,
            fingerprint, true, childList, normalized)
    }

    fun decodeReceipt(
        bytes: ByteArray, expectedBookId: String, expectedMutationId: String? = null,
        expectedBookRevision: Long? = null,
    ): MemoryBookEditionReceipt = guarded(bytes) {
        uuid(expectedBookId)
        val root = obj(DiscoveryJson.parse(bytes, MAX_RESPONSE_BYTES, 16), "version", "id", "book_id",
            "book_revision", "created_at", "state", "mutation_id")
        check(integer(root["version"], 1, 1) == 1L)
        val id = uuid(string(root["id"], 36))
        val bookId = uuid(string(root["book_id"], 36)); check(bookId == expectedBookId)
        val bookRevision = revision(root["book_revision"])
        if (expectedBookRevision != null) check(bookRevision.toLong() == expectedBookRevision)
        val createdAt = integer(root["created_at"], 0, 253402300799)
        val state = when (string(root["state"], 32)) {
            "current" -> MemoryBookEditionState.CURRENT
            "source_invalidated" -> MemoryBookEditionState.SOURCE_INVALIDATED
            else -> invalid()
        }
        val mutationId = uuid(string(root["mutation_id"], 36))
        if (expectedMutationId != null) check(mutationId == expectedMutationId)
        MemoryBookEditionReceipt(id, bookId, bookRevision, createdAt,
            state, mutationId)
    }

    fun decodeDetail(
        bytes: ByteArray, expectedBookId: String, expectedEditionId: String,
        currentBookRevision: Long, expectedChapterIds: List<String>,
    ): MemoryBookEditionDetail = guarded(bytes) {
        check(currentBookRevision > 0)
        uuid(expectedBookId); uuid(expectedEditionId)
        val root = obj(DiscoveryJson.parse(bytes, MAX_RESPONSE_BYTES, 256), "version", "id", "book_id",
            "book_revision", "created_at", "state", "mutation_id", "manuscript")
        check(integer(root["version"], 1, 1) == 1L)
        val id = uuid(string(root["id"], 36)); check(id == expectedEditionId)
        val bookId = uuid(string(root["book_id"], 36)); check(bookId == expectedBookId)
        val bookRevision = revision(root["book_revision"])
        val createdAt = integer(root["created_at"], 0, 253402300799)
        val state = when (string(root["state"], 32)) {
            "current" -> MemoryBookEditionState.CURRENT
            "source_changed" -> MemoryBookEditionState.SOURCE_CHANGED
            "source_invalidated" -> MemoryBookEditionState.SOURCE_INVALIDATED
            else -> invalid()
        }
        val mutationId = uuid(string(root["mutation_id"], 36))
        val manuscript = if (root["manuscript"] == JsonNull) null else
            manuscript(root["manuscript"], expectedChapterIds)
        when (state) {
            MemoryBookEditionState.CURRENT -> {
                check(bookRevision.toLong() == currentBookRevision && manuscript != null)
            }
            MemoryBookEditionState.SOURCE_CHANGED, MemoryBookEditionState.SOURCE_INVALIDATED ->
                check(manuscript == null)
        }
        MemoryBookEditionDetail(MemoryBookEditionReceipt(id, bookId, bookRevision, createdAt,
            state, mutationId), manuscript)
    }

    /** A saved reader has no private job or proposal. Still bind every chapter to the current ordered children. */
    fun decodeReadableDetail(
        bytes: ByteArray, expectedBookId: String, expectedEditionId: String,
        currentBookRevision: Long, currentChildren: List<MemoryBookEditionChild>,
    ): MemoryBookEditionDetail = guarded(bytes) {
        val root = DiscoveryJson.parse(bytes, MAX_RESPONSE_BYTES, 256) as? JsonObject ?: invalid()
        val chapterIds = if (root["manuscript"] == JsonNull) emptyList() else {
            val raw = root["manuscript"] as? JsonObject ?: invalid()
            val ids = array(raw["chapters"], MAX_CHAPTERS).map {
                string((it as? JsonObject ?: invalid())["id"], 128)
            }
            val childList = children(JsonArray(currentChildren.map { child -> buildJsonObject {
                put("id", child.id); put("revision", child.revision)
            } }))
            validateChapterOrder(childList, ids)
            ids
        }
        decodeDetail(bytes, expectedBookId, expectedEditionId, currentBookRevision, chapterIds)
    }

    fun decodePage(bytes: ByteArray, expectedBookId: String, expectedPage: Int): MemoryBookEditionPage = guarded(bytes) {
        uuid(expectedBookId); check(expectedPage in 1..100000)
        val root = obj(DiscoveryJson.parse(bytes, MAX_RESPONSE_BYTES, 128), "version", "book_id", "page",
            "page_size", "has_more", "items")
        check(integer(root["version"], 1, 1) == 1L)
        val bookId = uuid(string(root["book_id"], 36)); check(bookId == expectedBookId)
        check(integer(root["page"], 1, 100000).toInt() == expectedPage)
        check(integer(root["page_size"], 8, 8) == 8L)
        val hasMore = bool(root["has_more"])
        val rawItems = array(root["items"], 8)
        val items = rawItems.map { raw ->
            val item = obj(raw, "version", "id", "book_id", "book_revision", "created_at", "state",
                "mutation_id", "manuscript")
            check(item["manuscript"] == JsonNull)
            check(integer(item["version"], 1, 1) == 1L)
            val id = uuid(string(item["id"], 36))
            val itemBookId = uuid(string(item["book_id"], 36)); check(itemBookId == expectedBookId)
            val bookRevision = revision(item["book_revision"])
            val createdAt = integer(item["created_at"], 0, 253402300799)
            val state = when (string(item["state"], 32)) {
                "current" -> MemoryBookEditionState.CURRENT
                "source_changed" -> MemoryBookEditionState.SOURCE_CHANGED
                "source_invalidated" -> MemoryBookEditionState.SOURCE_INVALIDATED
                else -> invalid()
            }
            val mutationId = uuid(string(item["mutation_id"], 36))
            MemoryBookEditionDetail(MemoryBookEditionReceipt(id, itemBookId, bookRevision,
                createdAt, state, mutationId), manuscript = null)
        }
        check(items.map { it.receipt.id }.distinct().size == items.size)
        items.zipWithNext().forEach { (a, b) ->
            check(a.receipt.createdAt > b.receipt.createdAt ||
                a.receipt.createdAt == b.receipt.createdAt && a.receipt.id >= b.receipt.id)
        }
        MemoryBookEditionPage(bookId, expectedPage, hasMore, items)
    }

    private inline fun <T> guarded(bytes: ByteArray, block: () -> T): T {
        if (bytes.size !in 1..MAX_RESPONSE_BYTES) invalid()
        return try { block() } catch (failure: ApiFailure) { throw failure }
        catch (_: Exception) { invalid() }
    }

}
