package dev.photohouse.connected.core

/** User-visible import state derived from the current upload queue and library access. */
enum class UploadImportStatus { RECEIVED, AWAITING_REVIEW, IN_LIBRARY, UNAVAILABLE }

/** Projects a history row using the caller's current account-scoped library access. */
fun uploadHistoryStatus(
    item: UploadHistoryItem,
    availableLibraries: Set<String>,
): UploadImportStatus {
    if (item.assetId.isBlank() || item.bytes <= 0 || (item.kind != "image" && item.kind != "video"))
        return UploadImportStatus.UNAVAILABLE

    return when (item.state) {
        "awaiting_review" -> if (item.libraryId == null) UploadImportStatus.AWAITING_REVIEW
            else UploadImportStatus.UNAVAILABLE
        "available" -> {
            val libraryId = item.libraryId
            if (libraryId != null && libraryId.isNotBlank() && libraryId in availableLibraries)
                UploadImportStatus.IN_LIBRARY
            else UploadImportStatus.UNAVAILABLE
        }
        else -> UploadImportStatus.UNAVAILABLE
    }
}

/**
 * Projects a completed local queue record against history from the current account and load.
 * A missing or unavailable history result means only that receipt is known locally.
 */
fun receivedUploadStatus(
    record: UploadQueueRecord,
    historyItems: List<UploadHistoryItem>,
    historyAvailable: Boolean,
    availableLibraries: Set<String>,
): UploadImportStatus? {
    if (record.status != "complete") return null

    val assetId = record.assetId ?: return UploadImportStatus.RECEIVED
    if (!historyAvailable) return UploadImportStatus.RECEIVED

    val matching = historyItems.firstOrNull {
        it.assetId == assetId && it.kind == record.kind.name.lowercase() && it.bytes == record.bytes
    } ?: return UploadImportStatus.RECEIVED

    if (matching.state == "available" && matching.libraryId != null &&
        record.destinationLibraryId != null && matching.libraryId != record.destinationLibraryId
    ) return UploadImportStatus.UNAVAILABLE

    return uploadHistoryStatus(matching, availableLibraries)
}

data class UploadTransferSummary(
    val total: Int,
    val uploading: Int,
    val waiting: Int,
    val failed: Int,
    val received: Int,
    val cancelled: Int,
    val transferredBytes: Long,
    val totalBytes: Long,
)

fun uploadQueueActivityMessage(activity: UploadQueueActivity, zh: Boolean): String = when (activity.phase) {
    UploadQueuePhase.HASHING -> if (zh) "正在读取并校验文件" else "Reading and checking the file"
    UploadQueuePhase.CHECKING -> if (zh) "正在核对服务器已接收的进度" else "Checking progress confirmed by the server"
    UploadQueuePhase.UPLOADING -> if (zh) "正在传输文件" else "Transferring the file"
    UploadQueuePhase.FINALIZING -> if (zh) "文件字节已传完，正在等待服务器确认接收" else "All file bytes sent; waiting for the server to confirm receipt"
    UploadQueuePhase.WAITING_RETRY -> {
        val seconds = (activity.retryDelayMillis.coerceIn(0, 30_000) + 999) / 1_000
        val attempt = activity.retryAttempt.coerceIn(1, 3)
        if (zh) "连接暂不可用，等待 $seconds 秒后自动恢复（$attempt/3），无需重复点击重试"
        else "Connection temporarily unavailable; retrying after $seconds seconds ($attempt/3). No need to tap Retry again."
    }
}

/** Summarizes queue metadata without reading source streams or treating optimistic bytes as committed. */
fun uploadTransferSummary(items: List<UploadQueueItem>): UploadTransferSummary {
    var uploading = 0
    var waiting = 0
    var failed = 0
    var received = 0
    var cancelled = 0
    var transferredBytes = 0L
    var totalBytes = 0L

    for (item in items) {
        val record = item.record
        when (record.status) {
            "uploading" -> uploading++
            "needs_hash", "queued", "paused", "cancelling" -> waiting++
            "failed" -> failed++
            "complete" -> received++
            "cancelled" -> cancelled++
        }

        if (record.status == "cancelled") continue
        val bytes = record.bytes.coerceAtLeast(0L)
        totalBytes = saturatingAdd(totalBytes, bytes)
        val committed = if (record.status == "complete") bytes
            else record.offset.coerceIn(0L, bytes)
        transferredBytes = saturatingAdd(transferredBytes, committed)
    }

    return UploadTransferSummary(
        total = items.size,
        uploading = uploading,
        waiting = waiting,
        failed = failed,
        received = received,
        cancelled = cancelled,
        transferredBytes = transferredBytes,
        totalBytes = totalBytes,
    )
}

private fun saturatingAdd(left: Long, right: Long): Long =
    if (Long.MAX_VALUE - left < right) Long.MAX_VALUE else left + right
