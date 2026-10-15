package dev.photohouse.connected.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.UUID

/** The only scope that can read, replace or delete one device-local story draft. */
data class StoryDraftScope(val accountId: String, val libraryId: String)

data class StoryDraftChapter(
    val id: String,
    val title: String,
    val titleAuthored: Boolean,
    val narration: String,
    val narrationAuthored: Boolean,
    val assetIds: List<String>,
    val sourceIds: List<String>,
)

/** Exact create request journal for an explicitly saved draft whose response may be unknown. */
data class StoryDraftPendingSave(
    val body: String,
    val mutationId: String,
    val sourceReview: Boolean,
    val assetIds: List<String>,
)

/**
 * A bounded, user-authored local draft. It intentionally excludes server preview objects,
 * credentials, media bytes, generated source prose, and dictation state.
 */
data class StoryDraftRecord(
    val scope: StoryDraftScope,
    val recordId: String,
    val revision: Long,
    val createdAtEpochMillis: Long,
    val updatedAtEpochMillis: Long,
    val selectionRevision: String,
    val selectedAssetIds: List<String>,
    val theme: String,
    val language: String,
    val title: String,
    val titleAuthored: Boolean,
    val chapters: List<StoryDraftChapter>,
    val sourceReviewEnabled: Boolean,
    val guideMode: Boolean,
    val guideStep: String?,
    val pendingSave: StoryDraftPendingSave? = null,
)

/** Persistence implementations encrypt at rest and must implement compare-and-swap revisions. */
interface StoryDraftPersistence {
    /** Returns null only when the scoped slot is absent. Corrupt or unreadable data must throw. */
    fun load(scope: StoryDraftScope): StoryDraftRecord?

    /** expectedRevision=null creates only into an empty slot; otherwise replaces that exact revision. */
    fun write(record: StoryDraftRecord, expectedRevision: Long?, expectedRecordId: String? = null): StoryDraftRecord

    /** Deletes only if the slot still has expectedRevision. */
    fun delete(scope: StoryDraftScope, expectedRecordId: String, expectedRevision: Long): Boolean

    /** Stable identity for an unreadable slot, used only by the explicit corrupt-record delete action. */
    fun unreadableFingerprint(scope: StoryDraftScope): String?

    /** Deletes only if the same slot still has the observed fingerprint and remains unreadable. */
    fun deleteUnreadable(scope: StoryDraftScope, expectedFingerprint: String): Boolean

    /** Number of occupied slots across the configured origin. Corrupt files count as occupied. */
    fun occupiedSlots(): Int
}

class StoryDraftStorageException(message: String, cause: Throwable? = null) : IllegalStateException(message, cause)

/** Strict content codec shared by persistence implementations and JVM tests. */
object StoryDraftRecordCodec {
    const val VERSION = 1
    const val MAX_RECORD_BYTES = 128 * 1024
    const val MAX_SLOTS = 20
    private const val MAX_CHAPTERS = 6
    private const val MAX_ASSETS = 24
    private const val MAX_SOURCES_PER_CHAPTER = 12
    private const val MAX_BODY_BYTES = 64 * 1024

    fun validate(record: StoryDraftRecord) {
        require(validAccount(record.scope.accountId))
        require(PhoneDiscoveryWire.validLibrary(record.scope.libraryId))
        require(runCatching { UUID.fromString(record.recordId).toString() == record.recordId }.getOrDefault(false))
        require(record.revision > 0 && record.createdAtEpochMillis > 0 && record.updatedAtEpochMillis >= record.createdAtEpochMillis)
        require(record.selectionRevision.matches(Regex("[0-9a-f]{64}")))
        require(record.selectedAssetIds.size in 1..MAX_ASSETS && record.selectedAssetIds.distinct().size == record.selectedAssetIds.size)
        record.selectedAssetIds.forEach(::validateAssetId)
        require(record.theme in SAVED_MEMORY_STORY_THEMES && record.language in setOf("zh", "en"))
        validateText(record.title, 160, 640, allowNewline = false, allowBlank = true)
        require(record.titleAuthored || record.title.isEmpty())
        require(record.chapters.size in 1..MAX_CHAPTERS)
        require(record.chapters.map { it.id } == (1..record.chapters.size).map { "chapter-$it" })
        require(record.chapters.flatMap { it.assetIds } == record.selectedAssetIds)
        record.chapters.forEach { chapter ->
            require(chapter.assetIds.size in 1..4)
            chapter.assetIds.forEach(::validateAssetId)
            validateText(chapter.title, 160, 640, allowNewline = false, allowBlank = true)
            validateText(chapter.narration, Int.MAX_VALUE, 6000, allowNewline = true, allowBlank = true)
            require(chapter.titleAuthored || chapter.title.isEmpty())
            require(chapter.narrationAuthored || chapter.narration.isEmpty())
            require(chapter.sourceIds.size <= MAX_SOURCES_PER_CHAPTER && chapter.sourceIds.distinct().size == chapter.sourceIds.size)
            chapter.sourceIds.forEach { require(it.matches(Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,127}"))) }
        }
        require(record.sourceReviewEnabled || record.chapters.all { it.sourceIds.isEmpty() })
        require(record.guideStep == null || record.guideStep in setOf("FRAMES", "WORDS", "REVIEW"))
        record.pendingSave?.let { pending ->
            require(record.sourceReviewEnabled == pending.sourceReview)
            require(pending.assetIds == record.selectedAssetIds)
            require(pending.body.toByteArray(Charsets.UTF_8).size <= MAX_BODY_BYTES)
            require(runCatching { UUID.fromString(pending.mutationId).toString() == pending.mutationId }.getOrDefault(false))
            require(pending.body.contains("\"mutation_id\":\"${pending.mutationId}\""))
        }
        require(encodeUnchecked(record).toByteArray(Charsets.UTF_8).size <= MAX_RECORD_BYTES)
    }

    fun encode(record: StoryDraftRecord): ByteArray {
        validate(record)
        return encodeUnchecked(record).toByteArray(Charsets.UTF_8).also { require(it.size <= MAX_RECORD_BYTES) }
    }

    fun decode(scope: StoryDraftScope, bytes: ByteArray): StoryDraftRecord {
        try {
            require(bytes.size in 1..MAX_RECORD_BYTES)
            val root = DiscoveryJson.parse(bytes, MAX_RECORD_BYTES, 256).jsonObject
            require(root.keys == setOf("version", "account_id", "library_id", "record_id", "revision", "created_at", "updated_at",
                "selection_revision", "selected_asset_ids", "theme", "language", "title", "title_authored", "chapters", "source_review", "guide_mode", "guide_step", "pending_save"))
            require(root.getValue("version").strictLong() == VERSION.toLong())
            require(root.string("account_id", 256) == scope.accountId)
            require(root.string("library_id", 128) == scope.libraryId)
            val pendingRaw = root["pending_save"]
            val pending = if (pendingRaw == null || pendingRaw == JsonNull) null else pendingRaw.jsonObject.let { value ->
                require(value.keys == setOf("body", "mutation_id", "source_review", "asset_ids"))
                StoryDraftPendingSave(value.string("body", MAX_BODY_BYTES), value.string("mutation_id", 36),
                    value.bool("source_review"), value.array("asset_ids", MAX_ASSETS).map { it.strictString(20) })
            }
            val record = StoryDraftRecord(
                scope = scope,
                recordId = root.string("record_id", 36),
                revision = root.longString("revision"),
                createdAtEpochMillis = root.longString("created_at"),
                updatedAtEpochMillis = root.longString("updated_at"),
                selectionRevision = root.string("selection_revision", 64),
                selectedAssetIds = root.array("selected_asset_ids", MAX_ASSETS).map { it.strictString(20) },
                theme = root.string("theme", 32), language = root.string("language", 2),
                title = root.string("title", 640), titleAuthored = root.bool("title_authored"),
                chapters = root.array("chapters", MAX_CHAPTERS).map { raw ->
                    val chapter = raw.jsonObject
                    require(chapter.keys == setOf("id", "title", "title_authored", "narration", "narration_authored", "asset_ids", "source_ids"))
                    StoryDraftChapter(chapter.string("id", 16), chapter.string("title", 640), chapter.bool("title_authored"),
                        chapter.string("narration", 6000), chapter.bool("narration_authored"), chapter.array("asset_ids", 4).map { it.strictString(20) },
                        chapter.array("source_ids", MAX_SOURCES_PER_CHAPTER).map { it.strictString(128) })
                },
                sourceReviewEnabled = root.bool("source_review"), guideMode = root.bool("guide_mode"),
                guideStep = root.nullableString("guide_step", 16), pendingSave = pending,
            )
            validate(record)
            return record
        } catch (failure: Exception) {
            if (failure is StoryDraftStorageException) throw failure
            throw StoryDraftStorageException("Saved story draft is unreadable", failure)
        }
    }

    private fun encodeUnchecked(record: StoryDraftRecord): String {
        val chapters = JsonArray(record.chapters.map { chapter -> JsonObject(linkedMapOf(
            "id" to JsonPrimitive(chapter.id), "title" to JsonPrimitive(chapter.title),
            "title_authored" to JsonPrimitive(chapter.titleAuthored),
            "narration" to JsonPrimitive(chapter.narration), "narration_authored" to JsonPrimitive(chapter.narrationAuthored),
            "asset_ids" to JsonArray(chapter.assetIds.map(::JsonPrimitive)),
            "source_ids" to JsonArray(chapter.sourceIds.map(::JsonPrimitive)),
        )) })
        val pending = record.pendingSave?.let { value -> JsonObject(linkedMapOf(
            "body" to JsonPrimitive(value.body), "mutation_id" to JsonPrimitive(value.mutationId),
            "source_review" to JsonPrimitive(value.sourceReview),
            "asset_ids" to JsonArray(value.assetIds.map(::JsonPrimitive)),
        )) } ?: JsonNull
        return JsonObject(linkedMapOf(
            "version" to JsonPrimitive(VERSION), "account_id" to JsonPrimitive(record.scope.accountId),
            "library_id" to JsonPrimitive(record.scope.libraryId), "record_id" to JsonPrimitive(record.recordId),
            "revision" to JsonPrimitive(record.revision.toString()), "created_at" to JsonPrimitive(record.createdAtEpochMillis.toString()),
            "updated_at" to JsonPrimitive(record.updatedAtEpochMillis.toString()),
            "selection_revision" to JsonPrimitive(record.selectionRevision),
            "selected_asset_ids" to JsonArray(record.selectedAssetIds.map(::JsonPrimitive)),
            "theme" to JsonPrimitive(record.theme), "language" to JsonPrimitive(record.language), "title" to JsonPrimitive(record.title),
            "title_authored" to JsonPrimitive(record.titleAuthored),
            "chapters" to chapters, "source_review" to JsonPrimitive(record.sourceReviewEnabled),
            "guide_mode" to JsonPrimitive(record.guideMode), "guide_step" to (record.guideStep?.let(::JsonPrimitive) ?: JsonNull),
            "pending_save" to pending,
        )).toString()
    }

    private fun validAccount(value: String): Boolean = value.isNotBlank() && value.codePointCount(0, value.length) <= 256 &&
        value.none(Character::isISOControl) && runCatching {
            Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value))
        }.isSuccess

    private fun validateAssetId(value: String) { require(value.matches(Regex("[1-9][0-9]{0,18}")) && value.toLongOrNull()?.toString() == value) }

    private fun validateText(value: String, maxCodePoints: Int, maxBytes: Int, allowNewline: Boolean, allowBlank: Boolean) {
        require(value.codePointCount(0, value.length) <= maxCodePoints)
        val bytes = Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value)).remaining()
        require(bytes <= maxBytes && (allowBlank || value.isNotBlank()) &&
            value.none { it == '\u0000' || it.isISOControl() && !(allowNewline && it in "\n\t") })
    }

    private fun JsonObject.string(key: String, maxBytes: Int) = getValue(key).strictString(maxBytes)
    private fun JsonObject.longString(key: String): Long = getValue(key).strictString(19).let {
        require(it.matches(Regex("[1-9][0-9]{0,18}"))); it.toLong()
    }
    private fun JsonObject.bool(key: String): Boolean = getValue(key).let {
        require(it is JsonPrimitive && !it.isString); it.booleanOrNull ?: error("Invalid boolean")
    }
    private fun JsonObject.nullableString(key: String, maxBytes: Int): String? = getValue(key).let {
        if (it == JsonNull) null else it.strictString(maxBytes)
    }
    private fun JsonObject.array(key: String, max: Int) = getValue(key).strictArray(max)
    private fun JsonElement.strictString(maxBytes: Int): String {
        val primitive = this as? JsonPrimitive ?: error("Expected string")
        require(primitive.isString)
        return primitive.content.also { value ->
            require(value.toByteArray(Charsets.UTF_8).size <= maxBytes && !value.any(Character::isISOControl))
        }
    }
    private fun JsonElement.strictArray(max: Int): List<JsonElement> = jsonArray.also { require(it.size <= max) }
    private fun JsonElement.strictLong(): Long = jsonPrimitive.let { require(!it.isString); it.content.toLong() }
}
