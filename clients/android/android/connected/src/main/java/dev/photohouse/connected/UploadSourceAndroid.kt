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

private fun batchUploadMetadata(
    context: Context, uri: Uri, mime: String?, bytes: Long, name: String?,
): BatchUploadSource? {
    val kind = when (mime?.substringBefore(';')?.lowercase()) {
        "image/jpeg", "image/png" -> UploadKind.IMAGE
        "video/mp4", "video/quicktime" -> UploadKind.VIDEO
        else -> return null
    }
    val max = if (kind == UploadKind.IMAGE) 256L * 1024 * 1024 else 16L * 1024 * 1024 * 1024
    if (bytes !in 1..max) return null
    val safeName = (name ?: if (kind == UploadKind.IMAGE) "upload.jpg" else "upload.mp4").take(200)
    if (safeName.isEmpty() || safeName == "." || safeName == ".." ||
        safeName.any { it < ' ' || it == '\u007f' || it == '/' || it == '\\' }) return null
    val resolver = context.applicationContext.contentResolver
    return BatchUploadSource(safeName, bytes, kind,
        { resolver.openInputStream(uri) ?: error("SAF stream unavailable") }, uri.toString())
}

internal fun batchUploadSource(context: Context, uri: Uri): BatchUploadSource? {
    if (uri.scheme != "content") return null
    val resolver = context.applicationContext.contentResolver
    val mime = resolver.getType(uri) ?: return null
    return resolver.query(uri, arrayOf(OpenableColumns.SIZE, OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        if (!cursor.moveToFirst()) return@use null
        val size = cursor.getColumnIndex(OpenableColumns.SIZE)
        if (size < 0 || cursor.isNull(size)) return@use null
        val name = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        batchUploadMetadata(context, uri, mime, cursor.getLong(size),
            if (name < 0) null else cursor.getString(name))
    }
}

internal data class BatchTreeRequest(
    val treeUri: Uri, val account: String, val destination: String?, val requirePersistedRead: Boolean,
)

internal fun hasPersistedTreeReadGrant(context: Context, tree: Uri): Boolean {
    if (tree.scheme != "content" || !DocumentsContract.isTreeUri(tree)) return false
    return runCatching {
        context.applicationContext.contentResolver.persistedUriPermissions.any {
            it.uri == tree && it.isReadPermission
        }
    }.getOrDefault(false)
}

/** Read only the selected SAF tree. Keep all media streams deferred until upload. */
internal fun batchUploadTree(
    context: Context, tree: Uri, maxFiles: Int = 100,
    maxBytes: Long = 64L * 1024 * 1024 * 1024, checkActive: () -> Unit = {},
): BatchTreeResult {
    if (tree.scheme != "content" || !DocumentsContract.isTreeUri(tree)) {
        return BatchTreeResult(emptyList(), 1, 0)
    }
    val resolver = context.applicationContext.contentResolver
    val idColumn = DocumentsContract.Document.COLUMN_DOCUMENT_ID
    val mimeColumn = DocumentsContract.Document.COLUMN_MIME_TYPE
    val sizeColumn = DocumentsContract.Document.COLUMN_SIZE
    val nameColumn = DocumentsContract.Document.COLUMN_DISPLAY_NAME
    return inventoryBatchTree(DocumentsContract.getTreeDocumentId(tree), maxFiles, maxBytes,
        readDirectory = { directory, remaining ->
            val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, directory)
            resolver.query(children, arrayOf(idColumn, mimeColumn, sizeColumn, nameColumn), null, null, null)?.use { cursor ->
                val id = cursor.getColumnIndexOrThrow(idColumn)
                val mime = cursor.getColumnIndex(mimeColumn)
                val size = cursor.getColumnIndex(sizeColumn)
                val name = cursor.getColumnIndex(nameColumn)
                val entries = mutableListOf<BatchTreeEntry>()
                while (entries.size < remaining && cursor.moveToNext()) {
                    checkActive()
                    val type = if (mime < 0) null else cursor.getString(mime)
                    entries.add(BatchTreeEntry(cursor.getString(id), type,
                        if (size < 0 || cursor.isNull(size)) null else cursor.getLong(size),
                        if (name < 0) null else cursor.getString(name),
                        type == DocumentsContract.Document.MIME_TYPE_DIR))
                }
                BatchTreePage(entries, entries.size == remaining && cursor.moveToNext())
            }
        },
        prepareSource = { entry ->
            val uri = DocumentsContract.buildDocumentUriUsingTree(tree, requireNotNull(entry.id))
            val size = entry.size
            if (size == null || entry.mime == null || entry.name == null) batchUploadSource(context, uri)
            else batchUploadMetadata(context, uri, entry.mime, size, entry.name)
        },
        checkActive = checkActive)
}
