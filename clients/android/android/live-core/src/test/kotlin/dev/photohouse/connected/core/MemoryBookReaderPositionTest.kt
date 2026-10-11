package dev.photohouse.connected.core

import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

class MemoryBookReaderPositionTest {
    private val account = "family-account"
    private val bookId = "66666666-6666-4666-8666-666666666666"
    private val storyId = "11111111-1111-4111-8111-111111111111"

    private fun position(
        account: String = this.account,
        library: String = "family",
        book: String = bookId,
        revision: Long = 2,
        story: String = storyId,
        storyRevision: Long = 3,
        chapter: String = "chapter-2",
        asset: String = "9",
    ) = MemoryBookReaderPosition(account, library, book, revision, story, storyRevision, chapter, asset)

    @Test fun codecRoundTripsContentFreeAccountBoundPositionsAndReturnsImmutableList() {
        val rows = listOf(position(), position(library = "other", book = UUID.randomUUID().toString(), asset = "10"))
        val encoded = MemoryBookReaderPositions.encodeRecord(account, rows)
        val json = encoded.toString(Charsets.UTF_8)
        assertFalse(json.contains("narration"))
        assertFalse(json.contains("token"))
        assertEquals(rows, MemoryBookReaderPositions.decodeRecord(account, encoded))
        try {
            (MemoryBookReaderPositions.decodeRecord(account, encoded) as MutableList).clear()
            fail("decoded positions must be immutable")
        } catch (_: UnsupportedOperationException) { }
        try {
            MemoryBookReaderPositions.decodeRecord("other-account", encoded)
            fail("record must be bound to its account")
        } catch (failure: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, failure.kind) }
    }

    @Test fun mruUpsertReplacesThisBookMovesItFirstAndCapsAtTwelve() {
        val rows = (1..MemoryBookReaderPositions.MAX_POSITIONS).map { index ->
            position(book = UUID.nameUUIDFromBytes("book-$index".toByteArray()).toString(), asset = index.toString())
        }
        val replacement = rows.last().copy(storyRevision = 4, chapterId = "chapter-1", assetId = "99")
        val updated = MemoryBookReaderPositions.upsert(account, rows, replacement)
        assertEquals(MemoryBookReaderPositions.MAX_POSITIONS, updated.size)
        assertEquals(replacement, updated.first())
        assertEquals(1, updated.count { it.libraryId == replacement.libraryId && it.bookId == replacement.bookId })
        assertEquals(rows.dropLast(1).last(), updated.last())
        assertEquals(11, MemoryBookReaderPositions.without(account, updated, replacement.libraryId, replacement.bookId).size)
    }

    @Test fun malformedDuplicateUnknownOversizedAndNoncanonicalRecordsRejectAsWhole() {
        val valid = MemoryBookReaderPositions.encodeRecord(account, listOf(position())).toString(Charsets.UTF_8)
        val encodedEntry = valid.substringAfter("\"positions\":[").substringBeforeLast("]")
        val variants = listOf(
            valid.replace("\"version\":1", "\"version\":2"),
            valid.replace("\"asset_id\":\"9\"", "\"asset_id\":\"09\""),
            valid.replace("\"chapter_id\":\"chapter-2\"", "\"chapter_id\":\"chapter-7\""),
            valid.replace("\"book_revision\":\"2\"", "\"book_revision\":\"${Long.MAX_VALUE}\""),
            valid.replace("\"positions\":[", "\"positions\":[{\"unknown\":true},"),
            valid.replace("\"positions\":[", "\"positions\":[$encodedEntry,$encodedEntry"),
            "{" + "x".repeat(MemoryBookReaderPositions.MAX_RECORD_BYTES) + "}",
        )
        variants.forEach { malformed ->
            try {
                MemoryBookReaderPositions.decodeRecord(account, malformed.toByteArray())
                fail("malformed record must be rejected")
            } catch (failure: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, failure.kind) }
        }
    }

    @Test fun invalidInputsIncludeControlCharactersAndUnpairedSurrogates() {
        listOf(
            position(account = "bad\u0085account"),
            position(account = "bad\uD800account"),
            position(book = "66666666666666666666666666666666"),
            position(story = "11111111-1111-4111-8111-111111111111 "),
            position(asset = "0"),
            position(library = ".."),
        ).forEach { invalid ->
            try {
                MemoryBookReaderPositions.validated(account, listOf(invalid))
                fail("invalid pointer should fail validation")
            } catch (_: IllegalArgumentException) { }
        }
    }
}
