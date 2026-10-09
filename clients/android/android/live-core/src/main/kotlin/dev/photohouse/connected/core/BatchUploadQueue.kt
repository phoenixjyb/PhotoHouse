package dev.photohouse.connected.core

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.io.InputStream
import java.security.MessageDigest
import java.util.UUID

/** Metadata only. The original bytes remain with the selected SAF provider. */
data class UploadQueueRecord(
    val localId: String, val requestId: String, val batch: String, val filename: String, val locator: String?,
    val bytes: Long, val kind: UploadKind, val sha256: String, val uploadId: String? = null,
    val offset: Long = 0, val status: String = "queued", val error: String? = null,
    val destinationLibraryId: String? = null,
    val assetId: String? = null,
)
interface UploadQueuePersistence {
    fun load(account: String): List<UploadQueueRecord>
    fun save(account: String, records: List<UploadQueueRecord>)
    fun clear(account: String) = save(account, emptyList())
}
class InMemoryUploadQueuePersistence : UploadQueuePersistence {
    private val data = mutableMapOf<String, List<UploadQueueRecord>>()
    override fun load(account: String) = data[account].orEmpty()
    override fun save(account: String, records: List<UploadQueueRecord>) { data[account] = records }
}
data class UploadQueueItem(val record: UploadQueueRecord, val sent: Long = record.offset)

/** One active file at a time. Restoring the queue never starts a network request. */
class BatchUploadQueue(
    private val api: PhotoHouseApi, private val scope: CoroutineScope,
    private val persistence: UploadQueuePersistence, private val source: (UploadQueueRecord) -> BatchUploadSource?,
    private val valid: () -> Boolean, private val token: () -> Bearer,
    private val destinationAllowed: (String) -> Boolean = { true },
) {
    private val mutable = MutableStateFlow<List<UploadQueueItem>>(emptyList())
    val state = mutable.asStateFlow()
    @Volatile private var account: String? = null
    @Volatile private var epoch = 0L
    private var job: Job? = null

    fun attach(accountId: String) {
        pause(); account = accountId
        mutable.value = persistence.load(accountId).take(100).map { UploadQueueItem(it) }
    }
    fun detach() { pause(); account = null; mutable.value = emptyList() }
    fun enqueue(items: List<BatchUploadSource>, destinationLibraryId: String? = null): List<String> {
        val accountId = account ?: return emptyList()
        require(destinationLibraryId == null || destinationAllowed(destinationLibraryId))
        val records = mutable.value.map { it.record }.filterNot { it.status in setOf("complete", "cancelled") }.toMutableList()
        require(items.isNotEmpty() && items.size <= 100 && records.size + items.size <= 100)
        require(items.all { it.bytes in 1L..(if (it.kind == UploadKind.IMAGE) MAX_IMAGE else MAX_VIDEO) })
        require(items.fold(0L) { sum, item -> sum + item.bytes } <= MAX_BATCH)
        val batchId = hex(); val ids = mutableListOf<String>()
        items.forEach { item ->
            require(validName(item.filename))
            val id = hex(); ids += id
            records += UploadQueueRecord(id, hex(), batchId, item.filename, item.locator, item.bytes, item.kind, "",
                status = "needs_hash", destinationLibraryId = destinationLibraryId)
        }
        persist(accountId, records)
        return ids
    }
    fun resume(localId: String? = null) {
        if (job?.isActive == true || account == null || !valid()) return
        val target = localId ?: mutable.value.firstOrNull { it.record.status in READY }?.record?.localId ?: return
        val first = mutable.value.firstOrNull { it.record.localId == target }?.record ?: return
        if (first.status in setOf("complete", "cancelled", "cancelling")) return
        epoch++; val run = epoch; var activeId = target
        job = scope.launch {
            try { processQueue(first, run, localId == null) { activeId = it } }
            catch (_: CancellationException) { if (epoch == run) update(activeId) { it.copy(status = "paused") } }
            catch (error: Exception) { if (epoch == run) update(activeId) { it.copy(status = "failed", error = error.message ?: "Upload failed") } }
            finally { if (epoch == run) job = null }
        }
    }
    fun pause() {
        epoch++; job?.cancel(); job = null
        mutable.value = mutable.value.map { if (it.record.status == "uploading") it.copy(record = it.record.copy(status = "paused")) else it }
        persistCurrent()
    }
    fun cancel(localId: String) {
        val record = mutable.value.firstOrNull { it.record.localId == localId }?.record ?: return
        if (record.status in setOf("complete", "cancelled", "cancelling")) return
        epoch++; val run = epoch; job?.cancel(); job = null
        val accountAtCancel = account ?: return
        val bearer = runCatching { token() }.getOrNull()
        if (record.uploadId == null) { update(localId) { it.copy(status = "cancelled") }; return }
        if (bearer == null || !valid()) { update(localId) { it.copy(status = "failed", error = "Cancellation needs a connection") }; return }
        update(localId) { it.copy(status = "cancelling") }
        scope.launch {
            val confirmed = runCatching { api.cancelUploadSession(bearer, record.uploadId) }.getOrNull()
            if (epoch == run && account == accountAtCancel && bearer === runCatching { token() }.getOrNull()) {
                if (confirmed?.state == "cancelled" && confirmed.uploadId == record.uploadId && confirmed.bytes == record.bytes)
                    update(localId) { it.copy(status = "cancelled", error = null) }
                else update(localId) { it.copy(status = "failed", error = "Cancellation could not be confirmed") }
            }
        }
    }
    fun retry(localId: String) { update(localId) { it.copy(status = "queued", error = null) }; resume(localId) }

    private suspend fun processQueue(first: UploadQueueRecord, run: Long, all: Boolean, onActive: (String) -> Unit) {
        var current: UploadQueueRecord? = first
        while (current != null) {
            onActive(current.localId); process(current, run)
            current = if (all) mutable.value.map { it.record }.firstOrNull { it.status in READY } else null
        }
    }
    private suspend fun process(initial: UploadQueueRecord, run: Long) {
        var record = initial
        val destinationLibraryId = record.destinationLibraryId
        require(destinationLibraryId == null || destinationAllowed(destinationLibraryId))
        var session = record.uploadId?.let { api.uploadSession(token(), it) }
        ensure(run)
        if (session != null) {
            require(session.uploadId == record.uploadId && session.bytes == record.bytes)
            if (session.state == "complete") {
                replace(record.copy(offset = session.bytes, status = "complete", error = null, assetId = session.assetId)); return
            }
            require(session.state == "uploading")
        }
        val item = withContext(Dispatchers.IO) { source(record) } ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        ensure(run)
        require(item.bytes == record.bytes && item.kind == record.kind && item.filename == record.filename)
        if (record.sha256.isEmpty()) {
            record = record.copy(sha256 = withContext(Dispatchers.IO) { digest(item, run) })
            ensure(run); replace(record)
        }
        if (session == null) session = api.createUploadSession(token(), UploadSessionRequest(record.requestId, record.batch,
            record.filename, record.bytes, record.sha256, record.kind, record.destinationLibraryId))
        ensure(run)
        require(session.uploadId == (record.uploadId ?: session.uploadId) && session.bytes == record.bytes)
        if (session.state == "complete") { replace(record.copy(uploadId = session.uploadId, offset = session.bytes, status = "complete", error = null, assetId = session.assetId)); return }
        require(session.state == "uploading")
        record = record.copy(uploadId = session.uploadId, offset = session.offset, status = "uploading", error = null)
        replace(record)
        session = uploadChunks(item, session, record, token(), run)
        ensure(run)
        val completed = api.completeUploadSession(token(), session.uploadId)
        ensure(run)
        require(completed.uploadId == record.uploadId && completed.bytes == record.bytes && completed.offset == record.bytes && completed.state == "complete")
        replace(record.copy(offset = completed.bytes, status = "complete", error = null, assetId = completed.assetId))
    }
    private suspend fun uploadChunks(item: BatchUploadSource, start: UploadSession, initial: UploadQueueRecord, bearer: Bearer, run: Long): UploadSession = withContext(Dispatchers.IO) {
        var session = start; var record = initial; var conflicts = 0
        var stream: InputStream = item.open()
        fun skipTo(offset: Long) {
            var skipped = 0L
            while (skipped < offset) {
                ensure(run)
                val count = stream.skip(offset - skipped)
                if (count > 0) skipped += count
                else if (stream.read() >= 0) skipped++ else error("source ended")
            }
        }
        try {
            skipTo(session.offset)
            while (session.offset < session.bytes) {
                ensure(run)
                require(session.chunkBytes in 1..4 * 1024 * 1024)
                val offset = session.offset
                val chunk = ByteArray(minOf(session.chunkBytes.toLong(), session.bytes - offset).toInt())
                var read = 0
                while (read < chunk.size) {
                    ensure(run)
                    val count = stream.read(chunk, read, chunk.size - read)
                    if (count <= 0) error("source ended")
                    read += count
                }
                session = try { api.uploadChunk(bearer, session.uploadId, offset, chunk, sha(chunk)) }
                catch (failure: ApiFailure) {
                    if (failure.status != 409 || ++conflicts > 3) throw failure
                    val confirmed = api.uploadSession(bearer, session.uploadId)
                    ensure(run)
                    require(confirmed.uploadId == record.uploadId && confirmed.bytes == record.bytes && confirmed.state == "uploading")
                    stream.close(); stream = item.open(); skipTo(confirmed.offset)
                    session = confirmed; continue
                }
                ensure(run)
                require(session.uploadId == record.uploadId && session.bytes == record.bytes && session.offset > offset && session.offset <= record.bytes)
                record = record.copy(offset = session.offset); replace(record)
            }
            session
        } finally { stream.close() }
    }
    private fun digest(item: BatchUploadSource, run: Long): String {
        val hash = MessageDigest.getInstance("SHA-256"); var total = 0L
        item.open().use { input ->
            val block = ByteArray(64 * 1024)
            while (true) {
                ensure(run); val count = input.read(block)
                if (count < 0) break
                if (count == 0) error("source did not advance")
                total += count
                if (total > item.bytes) error("source exceeded declared length")
                hash.update(block, 0, count)
            }
        }
        ensure(run); if (total != item.bytes) error("source length changed")
        return hash.digest().joinToString("") { "%02x".format(it) }
    }
    private fun ensure(run: Long) { if (run != epoch || !valid()) throw CancellationException("Upload no longer active") }
    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    private fun replace(record: UploadQueueRecord) { mutable.value = mutable.value.map { if (it.record.localId == record.localId) UploadQueueItem(record) else it }; persistCurrent() }
    private fun update(id: String, f: (UploadQueueRecord) -> UploadQueueRecord) { mutable.value = mutable.value.map { if (it.record.localId == id) UploadQueueItem(f(it.record)) else it }; persistCurrent() }
    private fun persist(accountId: String, records: List<UploadQueueRecord>) { persistence.save(accountId, records); mutable.value = records.map { UploadQueueItem(it) } }
    private fun persistCurrent() { account?.let { persistence.save(it, mutable.value.map { item -> item.record }) } }
    private fun validName(value: String) = value.isNotEmpty() && value.length <= 200 && value != "." && value != ".." && value.none { it < ' ' || it == '\u007f' || it == '/' || it == '\\' }
    private fun hex() = UUID.randomUUID().toString().replace("-", "")
    private companion object {
        const val MAX_IMAGE = 256L * 1024 * 1024
        const val MAX_VIDEO = 16L * 1024 * 1024 * 1024
        const val MAX_BATCH = 64L * 1024 * 1024 * 1024
        val READY = setOf("queued", "needs_hash", "paused")
    }
}
