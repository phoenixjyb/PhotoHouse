package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class SavedStoryReaderPositionTest {
    private val account = "family-account"

    private fun position(
        index: Int,
        library: String = "family-a",
        revision: Long = 1,
        chapter: Int = 1,
        assetId: String = (index + 1).toString(),
    ) = SavedStoryReaderPosition(
        accountId = account,
        libraryId = library,
        storyId = "00000000-0000-0000-0000-${index.toString().padStart(12, '0')}",
        storyRevision = revision,
        chapterId = "chapter-$chapter",
        assetId = assetId,
    )

    private fun invalidRecord(bytes: ByteArray, expectedAccount: String = account) {
        try {
            SavedStoryReaderPositions.decodeRecord(expectedAccount, bytes)
            fail("Invalid reader-position record accepted")
        } catch (failure: ApiFailure) {
            assertEquals(FailureKind.INVALID_RESPONSE, failure.kind)
        }
    }

    @Test fun validationChecksScopeCanonicalIdsAndBounds() {
        assertEquals(listOf(position(1)), SavedStoryReaderPositions.validated(account, listOf(position(1))))
        for (bad in listOf(
            position(1).copy(accountId = "other"),
            position(1).copy(accountId = "x".repeat(257)),
            position(1).copy(accountId = "bad\u0085account"),
            position(1).copy(accountId = "bad\uD800account"),
            position(1).copy(libraryId = ".."),
            position(1).copy(storyId = "00000000-0000-0000-0000-00000000000A"),
            position(1).copy(storyRevision = 0),
            position(1).copy(storyRevision = Long.MAX_VALUE),
            position(1).copy(chapterId = "chapter-7"),
            position(1).copy(assetId = "01"),
        )) assertTrue(runCatching { SavedStoryReaderPositions.validated(account, listOf(bad)) }.isFailure)
        assertTrue(runCatching { SavedStoryReaderPositions.validated(account, listOf(position(1), position(1))) }.isFailure)
        assertTrue(runCatching { SavedStoryReaderPositions.validated(account, (1..13).map(::position)) }.isFailure)
    }

    @Test fun upsertIsNewestFirstDeterministicAndCappedAtTwelve() {
        val initial = (1..12).map(::position)
        val moved = position(4, revision = 8, chapter = 3, assetId = "99")
        val reordered = SavedStoryReaderPositions.upsert(account, initial, moved)
        assertEquals(moved, reordered.first())
        assertEquals(12, reordered.size)
        assertEquals(initial.filterNot { it.storyId == moved.storyId }, reordered.drop(1))

        val capped = SavedStoryReaderPositions.upsert(account, initial, position(13))
        assertEquals(position(13), capped.first())
        assertEquals(initial.take(11), capped.drop(1))
        assertEquals(initial, SavedStoryReaderPositions.validated(account, initial))
        assertNotSame(initial, SavedStoryReaderPositions.validated(account, initial))
    }

    @Test fun withoutIsScopedToAccountAndLibraryStoryPair() {
        val first = position(1)
        val otherLibrary = position(1, library = "family-b")
        val third = position(2)
        assertEquals(listOf(otherLibrary, third), SavedStoryReaderPositions.without(account, listOf(first, otherLibrary, third), "family-a", first.storyId))
        assertTrue(runCatching {
            SavedStoryReaderPositions.without(account, listOf(first), "family-a", "not-a-uuid")
        }.isFailure)
    }

    @Test fun recordRoundTripsExactMetadataWithoutAddingContentFields() {
        val positions = listOf(position(2, revision = Long.MAX_VALUE - 1, chapter = 6, assetId = Long.MAX_VALUE.toString()), position(1))
        val encoded = SavedStoryReaderPositions.encodeRecord(account, positions)
        assertTrue(encoded.size <= SavedStoryReaderPositions.MAX_RECORD_BYTES)
        assertEquals(positions, SavedStoryReaderPositions.decodeRecord(account, encoded))
        val root = Json.parseToJsonElement(encoded.toString(Charsets.UTF_8)).jsonObject
        assertEquals(setOf("version", "account_id", "positions"), root.keys)
        assertEquals(setOf("library_id", "story_id", "story_revision", "chapter_id", "asset_id"),
            root.getValue("positions").jsonArray.first().jsonObject.keys)
        val text = encoded.toString(Charsets.UTF_8)
        for (excluded in listOf("title", "narration", "content", "token", "endpoint")) assertFalse(text.contains(excluded))
    }

    @Test fun wrongAccountUnknownSchemaExtraDuplicateAndMalformedEntriesRejectWholeRecord() {
        val good = SavedStoryReaderPositions.encodeRecord(account, listOf(position(1))).toString(Charsets.UTF_8)
        invalidRecord(good.toByteArray(), "different-account")
        invalidRecord(good.replace("\"version\":1", "\"version\":2").toByteArray())
        invalidRecord(good.replace("\"account_id\":", "\"extra\":true,\"account_id\":").toByteArray())
        invalidRecord(good.replaceFirst("{", "{\"version\":1,").toByteArray())
        invalidRecord(good.replace("\"asset_id\":\"2\"", "\"asset_id\":\"02\"").toByteArray())
        invalidRecord(good.replace("\"chapter_id\":\"chapter-1\"", "\"chapter_id\":\"chapter-8\"").toByteArray())
        invalidRecord((good.dropLast(1) + ",\"unexpected\":true}").toByteArray())
        invalidRecord(byteArrayOf(0xc3.toByte(), 0x28))
    }

    @Test fun recordRejectsOversizeAndDuplicateStoryPointersAsAWhole() {
        invalidRecord(ByteArray(SavedStoryReaderPositions.MAX_RECORD_BYTES + 1) { ' '.code.toByte() })
        val duplicateStory = listOf(position(1, assetId = "2"), position(1, assetId = "3"))
        assertTrue(runCatching { SavedStoryReaderPositions.encodeRecord(account, duplicateStory) }.isFailure)
        val valid = SavedStoryReaderPositions.encodeRecord(account, listOf(position(1))).toString(Charsets.UTF_8)
        // Construct duplicate entry directly to avoid depending on codec map ordering.
        val entry = Json.parseToJsonElement(valid).jsonObject.getValue("positions").jsonArray.single()
        val duplicateJson = JsonObject(linkedMapOf(
            "version" to JsonPrimitive(1), "account_id" to JsonPrimitive(account),
            "positions" to JsonArray(listOf(entry, entry)),
        )).toString()
        invalidRecord(duplicateJson.toByteArray())
    }
}
