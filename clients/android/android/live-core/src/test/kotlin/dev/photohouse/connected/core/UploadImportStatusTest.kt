package dev.photohouse.connected.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class UploadImportStatusTest {
    private fun history(
        assetId: String = "asset-1",
        bytes: Long = 100,
        kind: String = "image",
        state: String = "available",
        libraryId: String? = "family-a",
    ) = UploadHistoryItem(assetId, 1, bytes, kind, state, libraryId)

    private fun record(
        status: String = "complete",
        bytes: Long = 100,
        offset: Long = bytes,
        kind: UploadKind = UploadKind.IMAGE,
        assetId: String? = "asset-1",
        destination: String? = "family-a",
    ) = UploadQueueRecord(
        localId = "local-1", requestId = "request-1", batch = "batch-1", filename = "photo.jpg",
        locator = null, bytes = bytes, kind = kind, sha256 = "", offset = offset, status = status,
        destinationLibraryId = destination, assetId = assetId,
    )

    @Test fun historyProjectionDistinguishesManualReviewAndCurrentLibraryAccess() {
        assertEquals(UploadImportStatus.AWAITING_REVIEW,
            uploadHistoryStatus(history(state = "awaiting_review", libraryId = null), emptySet()))
        assertEquals(UploadImportStatus.IN_LIBRARY,
            uploadHistoryStatus(history(), setOf("family-a")))
        assertEquals(UploadImportStatus.UNAVAILABLE,
            uploadHistoryStatus(history(), setOf("family-b")))
        assertEquals(UploadImportStatus.UNAVAILABLE,
            uploadHistoryStatus(history(state = "unavailable", libraryId = null), setOf("family-a")))
        assertEquals(UploadImportStatus.UNAVAILABLE,
            uploadHistoryStatus(history(state = "mystery"), setOf("family-a")))
        assertEquals(UploadImportStatus.UNAVAILABLE,
            uploadHistoryStatus(history(state = "awaiting_review", libraryId = "family-a"), setOf("family-a")))
        assertEquals(UploadImportStatus.UNAVAILABLE,
            uploadHistoryStatus(history(bytes = 0), setOf("family-a")))
    }

    @Test fun completedQueueUsesOnlyCurrentExactHistoryAndReportsReceiptWhenUnavailable() {
        val row = history()
        assertEquals(UploadImportStatus.RECEIVED,
            receivedUploadStatus(record(), emptyList(), historyAvailable = false, availableLibraries = setOf("family-a")))
        assertEquals(UploadImportStatus.RECEIVED,
            receivedUploadStatus(record(), listOf(row), historyAvailable = false, availableLibraries = setOf("family-a")))
        assertEquals(UploadImportStatus.RECEIVED,
            receivedUploadStatus(record(), emptyList(), historyAvailable = true, availableLibraries = setOf("family-a")))
        assertEquals(UploadImportStatus.RECEIVED,
            receivedUploadStatus(record(), listOf(row.copy(bytes = 99)), true, setOf("family-a")))
        assertEquals(UploadImportStatus.RECEIVED,
            receivedUploadStatus(record(), listOf(row.copy(kind = "video")), true, setOf("family-a")))
        assertEquals(UploadImportStatus.IN_LIBRARY,
            receivedUploadStatus(record(), listOf(row), true, setOf("family-a")))
        assertEquals(UploadImportStatus.UNAVAILABLE,
            receivedUploadStatus(record(destination = "family-b"), listOf(row), true, setOf("family-a")))
        assertEquals(UploadImportStatus.UNAVAILABLE,
            receivedUploadStatus(record(), listOf(row), true, setOf("family-b")))
        assertEquals(UploadImportStatus.AWAITING_REVIEW,
            receivedUploadStatus(record(destination = null), listOf(row.copy(state = "awaiting_review", libraryId = null)), true, emptySet()))
        assertNull(receivedUploadStatus(record(status = "uploading"), listOf(row), true, setOf("family-a")))
        assertNull(receivedUploadStatus(record(status = "failed"), listOf(row), true, setOf("family-a")))
    }

    @Test fun transferSummaryUsesCommittedOffsetsAndExcludesCancelledDenominator() {
        val items = listOf(
            UploadQueueItem(record(status = "paused", bytes = 10, offset = 4), sent = 9),
            UploadQueueItem(record(status = "failed", bytes = 20, offset = 6), sent = 18),
            UploadQueueItem(record(status = "complete", bytes = 30, offset = 2)),
            UploadQueueItem(record(status = "cancelled", bytes = 40, offset = 35)),
            UploadQueueItem(record(status = "needs_hash", bytes = -5, offset = 8)),
        )

        assertEquals(
            UploadTransferSummary(
                total = 5, uploading = 0, waiting = 2, failed = 1, received = 1, cancelled = 1,
                transferredBytes = 40, totalBytes = 60,
            ),
            uploadTransferSummary(items),
        )
    }

    @Test fun transferSummarySaturatesLongSumsAndCountsWaitingStates() {
        val statuses = listOf("needs_hash", "queued", "paused", "cancelling", "uploading")
            .map { status -> UploadQueueItem(record(status, Long.MAX_VALUE, offset = Long.MAX_VALUE), sent = 0) }
        val summary = uploadTransferSummary(statuses)

        assertEquals(5, summary.total)
        assertEquals(1, summary.uploading)
        assertEquals(4, summary.waiting)
        assertEquals(Long.MAX_VALUE, summary.totalBytes)
        assertEquals(Long.MAX_VALUE, summary.transferredBytes)
    }
}
