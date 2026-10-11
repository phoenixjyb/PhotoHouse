package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.Collections
import java.util.UUID

/** Content-free location in one exact child story inside one exact memoir revision. */
data class MemoryBookReaderPosition(
    val accountId: String,
    val libraryId: String,
    val bookId: String,
    val bookRevision: Long,
    val storyId: String,
    val storyRevision: Long,
    val chapterId: String,
    val assetId: String,
)

/** App-local persistence contract. Implementations encrypt records at rest. */
interface MemoryBookReaderPositionPersistence {
    fun load(accountId: String): List<MemoryBookReaderPosition>
    fun save(accountId: String, position: MemoryBookReaderPosition)
    fun remove(accountId: String, libraryId: String, bookId: String)
    fun clear(accountId: String)
}

/** Strict account-bound record codec and deterministic newest-first MRU operations. */
object MemoryBookReaderPositions {
    const val MAX_POSITIONS = 12
    const val MAX_RECORD_BYTES = 16 * 1024
    private const val VERSION = 1
    private val chapterIds = (1..6).map { "chapter-$it" }.toSet()

    fun validated(accountId: String, positions: List<MemoryBookReaderPosition>): List<MemoryBookReaderPosition> {
        require(validAccount(accountId))
        require(positions.size <= MAX_POSITIONS)
        val copy = positions.toList()
        require(copy.all { it.accountId == accountId && validPosition(it) })
        require(copy.map { it.libraryId to it.bookId }.distinct().size == copy.size)
        return Collections.unmodifiableList(copy)
    }

    fun upsert(
        accountId: String,
        positions: List<MemoryBookReaderPosition>,
        position: MemoryBookReaderPosition,
    ): List<MemoryBookReaderPosition> {
        val existing = validated(accountId, positions)
        require(position.accountId == accountId && validPosition(position))
        val next = listOf(position) + existing.filterNot {
            it.libraryId == position.libraryId && it.bookId == position.bookId
        }
        return validated(accountId, next.take(MAX_POSITIONS))
    }

    fun without(
        accountId: String,
        positions: List<MemoryBookReaderPosition>,
        libraryId: String,
        bookId: String,
    ): List<MemoryBookReaderPosition> {
        val existing = validated(accountId, positions)
        require(PhoneDiscoveryWire.validLibrary(libraryId) && validUtf8(libraryId) && canonicalUuid(bookId))
        return validated(accountId, existing.filterNot { it.libraryId == libraryId && it.bookId == bookId })
    }

    /** Encodes only identifiers and revision metadata; no memoir prose or credentials. */
    fun encodeRecord(accountId: String, positions: List<MemoryBookReaderPosition>): ByteArray {
        val checked = validated(accountId, positions)
        val record = JsonObject(linkedMapOf(
            "version" to JsonPrimitive(VERSION),
            "account_id" to JsonPrimitive(accountId),
            "positions" to JsonArray(checked.map { position -> JsonObject(linkedMapOf(
                "library_id" to JsonPrimitive(position.libraryId),
                "book_id" to JsonPrimitive(position.bookId),
                "book_revision" to JsonPrimitive(position.bookRevision.toString()),
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

    /** Rejects the complete record on any schema, scope, encoding or entry validation failure. */
    fun decodeRecord(accountId: String, bytes: ByteArray): List<MemoryBookReaderPosition> {
        try {
            require(validAccount(accountId))
            require(bytes.size in 1..MAX_RECORD_BYTES)
            val root = DiscoveryJson.parse(bytes, limit = MAX_RECORD_BYTES, maxArrayItems = MAX_POSITIONS).jsonObject
            require(root.keys == setOf("version", "account_id", "positions"))
            require(root.getValue("version").jsonPrimitive.let { !it.isString && it.content == VERSION.toString() })
            val storedAccount = root.getValue("account_id").strictString(256)
            require(storedAccount == accountId && validAccount(storedAccount))
            val parsed = root.getValue("positions").jsonArray.map { raw ->
                val entry = raw.jsonObject
                require(entry.keys == setOf(
                    "library_id", "book_id", "book_revision", "story_id", "story_revision", "chapter_id", "asset_id",
                ))
                MemoryBookReaderPosition(
                    accountId = accountId,
                    libraryId = entry.getValue("library_id").strictString(128),
                    bookId = entry.getValue("book_id").strictString(36),
                    bookRevision = entry.getValue("book_revision").strictRevision(),
                    storyId = entry.getValue("story_id").strictString(36),
                    storyRevision = entry.getValue("story_revision").strictRevision(),
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

    private fun JsonElement.strictRevision(): Long = strictString(19)
        .takeIf { it.matches(Regex("[1-9][0-9]{0,18}")) }
        ?.toLongOrNull()?.takeIf { it < Long.MAX_VALUE }
        ?: throw IllegalArgumentException("Invalid revision")

    private fun JsonElement.strictString(maxCodePoints: Int): String {
        val primitive = this as? JsonPrimitive ?: throw IllegalArgumentException("Expected string")
        require(primitive.isString)
        val value = primitive.content
        require(value.codePointCount(0, value.length) <= maxCodePoints)
        require(value.none { Character.isISOControl(it) })
        require(validUtf8(value))
        return value
    }

    private fun validPosition(value: MemoryBookReaderPosition): Boolean =
        validAccount(value.accountId) && PhoneDiscoveryWire.validLibrary(value.libraryId) && validUtf8(value.libraryId) &&
            canonicalUuid(value.bookId) && value.bookRevision in 1 until Long.MAX_VALUE &&
            canonicalUuid(value.storyId) && value.storyRevision in 1 until Long.MAX_VALUE &&
            value.chapterId in chapterIds && PhoneDiscoveryWire.validId(value.assetId)

    private fun validAccount(value: String): Boolean = value.isNotBlank() &&
        value.codePointCount(0, value.length) <= 256 && value.none { Character.isISOControl(it) } && validUtf8(value)

    private fun validUtf8(value: String): Boolean = runCatching {
        Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value))
    }.isSuccess

    private fun canonicalUuid(value: String): Boolean = runCatching {
        UUID.fromString(value).toString() == value
    }.getOrDefault(false)
}
