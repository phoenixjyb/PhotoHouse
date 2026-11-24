package dev.photohouse.connected

import dev.photohouse.connected.core.BatchUploadSource

internal data class BatchTreeResult(
    val sources: List<BatchUploadSource>,
    val skipped: Int,
    val bytes: Long,
    val persistedReadAccess: Boolean = true,
    val scanLimited: Boolean = false,
)

internal data class BatchTreeEntry(
    val id: String?,
    val mime: String?,
    val size: Long?,
    val name: String?,
    val directory: Boolean,
)

internal data class BatchTreePage(val entries: List<BatchTreeEntry>, val hasMore: Boolean)

/** Inventory the selected tree without holding a parent cursor while reading a child. */
internal fun inventoryBatchTree(
    root: String,
    maxFiles: Int,
    maxBytes: Long,
    readDirectory: (String, Int) -> BatchTreePage?,
    prepareSource: (BatchTreeEntry) -> BatchUploadSource?,
    checkActive: () -> Unit = {},
    maxRows: Int = 1000,
): BatchTreeResult {
    val directories = ArrayDeque<String>().apply { add(root) }
    val seen = mutableSetOf(root)
    val sources = mutableListOf<BatchUploadSource>()
    var skipped = 0
    var bytes = 0L
    var rows = 0
    var limited = false
    while (directories.isNotEmpty() && rows < maxRows && sources.size < maxFiles && bytes < maxBytes) {
        checkActive()
        val page = readDirectory(directories.removeFirst(), maxRows - rows)
        if (page == null) {
            skipped++
            continue
        }
        rows += page.entries.size
        limited = limited || page.hasMore
        for (entry in page.entries) {
            checkActive()
            val id = entry.id
            if (id.isNullOrBlank()) {
                skipped++
                continue
            }
            if (!seen.add(id)) continue
            if (sources.size == maxFiles || bytes == maxBytes) {
                limited = true
                break
            }
            if (entry.directory) {
                directories.add(id)
                continue
            }
            val source = prepareSource(entry)
            when {
                source == null || source.bytes <= 0L -> skipped++
                source.bytes > maxBytes - bytes -> limited = true
                else -> {
                    sources.add(source)
                    bytes += source.bytes
                }
            }
        }
    }
    checkActive()
    return BatchTreeResult(sources, skipped, bytes, scanLimited = limited || directories.isNotEmpty())
}
