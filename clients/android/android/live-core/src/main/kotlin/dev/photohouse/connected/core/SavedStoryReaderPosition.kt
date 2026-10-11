package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.Collections
import java.util.UUID

/** A content-free pointer to one location in a saved grouped story. */
data class SavedStoryReaderPosition(
    val accountId: String,
    val libraryId: String,
    val storyId: String,
    val storyRevision: Long,
    val chapterId: String,
    val assetId: String,
)

/** App-local persistence contract. Implementations must encrypt records at rest. */
interface SavedStoryReaderPositionPersistence {
    fun load(accountId: String): List<SavedStoryReaderPosition>
    fun save(accountId: String, position: SavedStoryReaderPosition)
    fun remove(accountId: String, libraryId: String, storyId: String)
    fun clear(accountId: String)
}

/** Strict, account-bound serialization and bounded newest-first MRU operations. */
object SavedStoryReaderPositions {
    const val MAX_POSITIONS = 12
    const val MAX_RECORD_BYTES = 16 * 1024
    private const val VERSION = 1

    /** Validates the complete list and returns an immutable defensive copy. */
    fun validated(accountId: String, positions: List<SavedStoryReaderPosition>): List<SavedStoryReaderPosition> {
        require(validAccount(accountId))
        require(positions.size <= MAX_POSITIONS)
        val copy = positions.toList()
        require(copy.all { it.accountId == accountId && validPosition(it) })
        require(copy.map { it.libraryId to it.storyId }.distinct().size == copy.size)
        return Collections.unmodifiableList(copy)
    }

    /** Replaces this story's pointer and moves it to the front, evicting the oldest beyond 12. */
    fun upsert(
        accountId: String,
        positions: List<SavedStoryReaderPosition>,
        position: SavedStoryReaderPosition,
    ): List<SavedStoryReaderPosition> {
        val existing = validated(accountId, positions)
        require(position.accountId == accountId && validPosition(position))
        val next = listOf(position) + existing.filterNot {
            it.libraryId == position.libraryId && it.storyId == position.storyId
        }
        return validated(accountId, next.take(MAX_POSITIONS))
    }

    /** Removes only the selected story in this account and library. */
    fun without(
        accountId: String,
        positions: List<SavedStoryReaderPosition>,
        libraryId: String,
        storyId: String,
    ): List<SavedStoryReaderPosition> {
        val existing = validated(accountId, positions)
        require(PhoneDiscoveryWire.validLibrary(libraryId) && canonicalUuid(storyId))
        return validated(accountId, existing.filterNot { it.libraryId == libraryId && it.storyId == storyId })
    }

    /** Encodes only identifiers and revision metadata; content, credentials and endpoints are excluded. */
    fun encodeRecord(accountId: String, positions: List<SavedStoryReaderPosition>): ByteArray {
        val checked = validated(accountId, positions)
        val record = JsonObject(linkedMapOf(
            "version" to JsonPrimitive(VERSION),
            "account_id" to JsonPrimitive(accountId),
            "positions" to JsonArray(checked.map { position -> JsonObject(linkedMapOf(
                "library_id" to JsonPrimitive(position.libraryId),
                "story_id" to JsonPrimitive(position.storyId),
                "story_revision" to JsonPrimitive(position.storyRevision.toString()),
                "chapter_id" to JsonPrimitive(position.chapterId),
                "asset_id" to JsonPrimitive(position.assetId),
            )) }),
        ))
        val bytes = record.toString().toByteArray(Charsets.UTF_8)
        require(bytes.size <= MAX_RECORD_BYTES)
        return bytes
    }

    /** Rejects the whole record on any schema, scope, encoding, or entry validation failure. */
    fun decodeRecord(accountId: String, bytes: ByteArray): List<SavedStoryReaderPosition> {
        try {
            require(validAccount(accountId))
            require(bytes.size in 1..MAX_RECORD_BYTES)
            val root = DiscoveryJson.parse(bytes, limit = MAX_RECORD_BYTES, maxArrayItems = MAX_POSITIONS).jsonObject
            require(root.keys == setOf("version", "account_id", "positions"))
            require(root.getValue("version").jsonPrimitive.let { !it.isString && it.content == VERSION.toString() })
            val storedAccount = root.getValue("account_id").strictString(256)
            require(storedAccount == accountId && validAccount(storedAccount))
            val rawPositions = root.getValue("positions").jsonArray
            val parsed = rawPositions.map { raw ->
                val entry = raw.jsonObject
                require(entry.keys == setOf("library_id", "story_id", "story_revision", "chapter_id", "asset_id"))
                val library = entry.getValue("library_id").strictString(128)
                val story = entry.getValue("story_id").strictString(36)
                val revisionText = entry.getValue("story_revision").strictString(19)
                val revision = revisionText.takeIf { it.matches(Regex("[1-9][0-9]{0,18}")) }
                    ?.toLongOrNull() ?: throw IllegalArgumentException("Invalid story revision")
                SavedStoryReaderPosition(
                    accountId = accountId,
                    libraryId = library,
                    storyId = story,
                    storyRevision = revision,
                    chapterId = entry.getValue("chapter_id").strictString(9),
                    assetId = entry.getValue("asset_id").strictString(19),
                ).also { require(validPosition(it)) }
            }
            return validated(accountId, parsed)
        } catch (failure: ApiFailure) {
            throw failure
        } catch (_: Exception) {
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        }
    }

    private fun JsonElement.strictString(maxCodePoints: Int): String {
        val primitive = this as? JsonPrimitive ?: throw IllegalArgumentException("Expected string")
        require(primitive.isString)
        val value = primitive.content
        require(value.codePointCount(0, value.length) <= maxCodePoints)
        require(value.none { Character.isISOControl(it) })
        require(validUtf8(value))
        return value
    }

    private fun validPosition(value: SavedStoryReaderPosition): Boolean =
        validAccount(value.accountId) && PhoneDiscoveryWire.validLibrary(value.libraryId) && validUtf8(value.libraryId) &&
            canonicalUuid(value.storyId) && value.storyRevision in 1 until Long.MAX_VALUE &&
            value.chapterId in CHAPTER_IDS && PhoneDiscoveryWire.validId(value.assetId)

    private fun validAccount(value: String): Boolean = value.isNotBlank() &&
        value.codePointCount(0, value.length) <= 256 && value.none { Character.isISOControl(it) } && validUtf8(value)

    private fun validUtf8(value: String): Boolean = runCatching {
        Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value))
    }.isSuccess

    private fun canonicalUuid(value: String): Boolean = runCatching {
        UUID.fromString(value).toString() == value
    }.getOrDefault(false)

    private val CHAPTER_IDS = (1..6).map { "chapter-$it" }.toSet()
}
