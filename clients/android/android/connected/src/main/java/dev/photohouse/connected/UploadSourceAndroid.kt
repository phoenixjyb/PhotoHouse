package dev.photohouse.connected

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.provider.OpenableColumns
import android.provider.DocumentsContract
import dev.photohouse.connected.core.HttpsPhotoHouseApi
import dev.photohouse.connected.core.UploadNetwork
import dev.photohouse.connected.core.UploadSource
import dev.photohouse.connected.core.BatchUploadSource
import dev.photohouse.connected.core.UploadKind

/** Build a bounded source over an ephemeral SAF URI; no media bytes are copied to app storage. */
internal fun uploadSource(context: Context, uri: Uri): UploadSource? {
    if (uri.scheme != "content") return null
    val resolver = context.applicationContext.contentResolver
    val mime = resolver.getType(uri)?.substringBefore(';')?.lowercase() ?: return null
    val extension = when (mime) { "image/jpeg" -> "jpg"; "image/png" -> "png"; else -> return null }
    val bytes = resolver.query(uri, arrayOf(OpenableColumns.SIZE), null, null, null)?.use { cursor ->
        if (!cursor.moveToFirst() || cursor.isNull(0)) null else cursor.getLong(0)
    } ?: return null
    if (bytes !in 1..HttpsPhotoHouseApi.MAX_UPLOAD_BYTES) return null
    // Do not expose provider filenames or EXIF data. The backend treats this as advisory.
    return UploadSource("photo.$extension", bytes) { resolver.openInputStream(uri) ?: error("SAF stream unavailable") }
}

internal fun uploadNetwork(context: Context): UploadNetwork {
    val connectivity = context.getSystemService(ConnectivityManager::class.java)
    val network = connectivity?.activeNetwork ?: return UploadNetwork.UNKNOWN
    val capabilities = connectivity.getNetworkCapabilities(network) ?: return UploadNetwork.UNKNOWN
    if (!capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)) return UploadNetwork.UNKNOWN
    if (!capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) return UploadNetwork.UNKNOWN
    return if (capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)) UploadNetwork.UNMETERED else UploadNetwork.METERED
}

internal fun batchUploadSource(context: Context, uri: Uri): BatchUploadSource? {
    if (uri.scheme != "content") return null
    val resolver = context.applicationContext.contentResolver
    val mime = resolver.getType(uri)?.substringBefore(';')?.lowercase() ?: return null
    val kind = when (mime) { "image/jpeg", "image/png" -> UploadKind.IMAGE; "video/mp4", "video/quicktime" -> UploadKind.VIDEO; else -> return null }
    val bytes = resolver.query(uri, arrayOf(OpenableColumns.SIZE), null, null, null)?.use { c -> if (!c.moveToFirst() || c.isNull(0)) null else c.getLong(0) } ?: return null
    val max = if (kind == UploadKind.IMAGE) 256L * 1024 * 1024 else 16L * 1024 * 1024 * 1024
    if (bytes !in 1..max) return null
    val name = resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c -> if (c.moveToFirst()) c.getString(0) else null } ?: ("upload." + if (kind == UploadKind.IMAGE) "jpg" else "mp4")
    val safeName = name.take(200)
    if (safeName.isEmpty() || safeName == "." || safeName == ".." || safeName.any { it < ' ' || it == '\u007f' || it == '/' || it == '\\' }) return null
    return BatchUploadSource(safeName, bytes, kind, { resolver.openInputStream(uri) ?: error("SAF stream unavailable") }, uri.toString())
}

internal data class BatchTreeResult(val sources: List<BatchUploadSource>, val skipped: Int, val bytes: Long)

/** Enumerates only the selected local SAF tree; provider paths and folder names never reach the API. */
internal fun batchUploadTree(context: Context, tree: Uri, maxFiles: Int = 100, maxBytes: Long = 64L * 1024 * 1024 * 1024): BatchTreeResult {
    if (tree.scheme != "content") return BatchTreeResult(emptyList(), 1, 0)
    val resolver = context.applicationContext.contentResolver
    val root = DocumentsContract.buildChildDocumentsUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree))
    val seen = mutableSetOf<String>(); val sources = mutableListOf<BatchUploadSource>(); var skipped = 0; var bytes = 0L; var scanned = 0
    fun walk(children: Uri) {
        if (sources.size >= maxFiles || scanned >= 1000) return
        resolver.query(children, arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_MIME_TYPE, DocumentsContract.Document.COLUMN_SIZE), null, null, null)?.use { c ->
            val idCol = c.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_DOCUMENT_ID)
            val mimeCol = c.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_MIME_TYPE)
            val sizeCol = c.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_SIZE)
            while (c.moveToNext()) {
                if (++scanned > 1000) { skipped++; break }
                if (sources.size >= maxFiles) { skipped++; continue }
                val id = c.getString(idCol); if (!seen.add(id)) continue
                val mime = c.getString(mimeCol); if (mime == DocumentsContract.Document.MIME_TYPE_DIR) { walk(DocumentsContract.buildChildDocumentsUriUsingTree(tree, id)); continue }
                val size = if (c.isNull(sizeCol)) -1L else c.getLong(sizeCol)
                val uri = DocumentsContract.buildDocumentUriUsingTree(tree, id)
                val source = if (size > 0) batchUploadSource(context, uri) else null
                if (source == null || size > maxBytes - bytes) skipped++ else { sources += source; bytes += size }
            }
        }
    }
    walk(root)
    return BatchTreeResult(sources, skipped, bytes)
}
