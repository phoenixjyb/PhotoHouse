package dev.photohouse.connected.core

import org.junit.Assert.*
import org.junit.Test

class StoryDraftRecordCodecTest {
    private val scope = StoryDraftScope("family-account", "family-a")

    private fun record(pending: StoryDraftPendingSave? = null) = StoryDraftRecord(
        scope = scope,
        recordId = "11111111-1111-4111-8111-111111111111",
        revision = 3,
        createdAtEpochMillis = 100,
        updatedAtEpochMillis = 200,
        selectionRevision = "a".repeat(64),
        selectedAssetIds = listOf("1", "2"),
        theme = "everyday",
        language = "zh",
        title = "",
        titleAuthored = false,
        chapters = listOf(
            StoryDraftChapter("chapter-1", "", false, "family words 一家人的回忆", true,
                listOf("1", "2"), listOf("caption-1")),
        ),
        sourceReviewEnabled = true,
        guideMode = true,
        guideStep = "WORDS",
        pendingSave = pending,
    )

    @Test fun roundTripKeepsOnlyScopedAuthoredDraftFields() {
        val original = record()
        val encoded = StoryDraftRecordCodec.encode(original)
        assertTrue(encoded.size <= StoryDraftRecordCodec.MAX_RECORD_BYTES)
        assertEquals(original, StoryDraftRecordCodec.decode(scope, encoded))
        val serialized = encoded.decodeToString()
        assertFalse(serialized.contains("caption prose"))
        assertFalse(serialized.contains("thumbnail"))
        assertFalse(serialized.contains("Bearer"))
    }

    @Test fun pendingRequestBodyAndMutationIdSurviveByteForByte() {
        val id = "55555555-5555-4555-8555-555555555555"
        val body = "{\"mutation_id\":\"$id\",\"title\":\"literal \\\"quote\\\" and 漢字\"}"
        val original = record(StoryDraftPendingSave(body, id, sourceReview = true, assetIds = listOf("1", "2")))
        val decoded = StoryDraftRecordCodec.decode(scope, StoryDraftRecordCodec.encode(original))
        assertEquals(body, decoded.pendingSave?.body)
        assertEquals(id, decoded.pendingSave?.mutationId)
    }

    @Test fun rejectsCrossScopeAndUnmarkedServerPreviewText() {
        val encoded = StoryDraftRecordCodec.encode(record())
        assertThrows(StoryDraftStorageException::class.java) {
            StoryDraftRecordCodec.decode(StoryDraftScope("other-account", "family-a"), encoded)
        }
        assertThrows(IllegalArgumentException::class.java) {
            StoryDraftRecordCodec.validate(record().copy(title = "generated preview", titleAuthored = false))
        }
    }

    @Test fun rejectsSourceIdsOutsideExplicitSourceReview() {
        assertThrows(IllegalArgumentException::class.java) {
            StoryDraftRecordCodec.validate(record().copy(sourceReviewEnabled = false))
        }
    }
}
