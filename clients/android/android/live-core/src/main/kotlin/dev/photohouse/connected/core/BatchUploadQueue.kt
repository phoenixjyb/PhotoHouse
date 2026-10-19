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

enum class UploadQueuePhase { HASHING, CHECKING, UPLOADING, FINALIZING, WAITING_RETRY }
/** Ephemeral activity for an explicitly started run; never restored as permission to start network work. */
data class UploadQueueActivity(
    val localId: String, val phase: UploadQueuePhase,
    val retryAttempt: Int = 0, val maxRetries: Int = 3, val retryDelayMillis: Long = 0,
)

enum class BatchUploadEnqueueIssue {
    EMPTY_SELECTION,
    QUEUE_LIMIT,
    INVALID_SOURCE,
    BATCH_TOO_LARGE,
    DESTINATION_UNAVAILABLE,
    ACCOUNT_UNAVAILABLE,
}

class BatchUploadEnqueueRejected(val issue: BatchUploadEnqueueIssue) :
    IllegalArgumentException("Batch upload rejected: $issue")

/** One active file at a time. Restoring the queue never starts a network request. */
class BatchUploadQueue(
    private val api: PhotoHouseApi, private val scope: CoroutineScope,
    private val persistence: UploadQueuePersistence, private val source: (UploadQueueRecord) -> BatchUploadSource?,
    private val valid: () -> Boolean, private val token: () -> Bearer,
    private val destinationAllowed: (String) -> Boolean = { true },
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO,
) {
    private val mutable = MutableStateFlow<List<UploadQueueItem>>(emptyList())
    val state = mutable.asStateFlow()
    private val mutableActivity = MutableStateFlow<UploadQueueActivity?>(null)
    val activity = mutableActivity.asStateFlow()
    @Volatile private var account: String? = null
    @Volatile private var epoch = 0L
    private var job: Job? = null
    /** Observed on the owner's dispatcher; a notification owner must stop when this becomes false. */
    val running: Boolean get() = job?.isActive == true

    fun attach(accountId: String) {
        pause(); account = accountId
        val loaded = persistence.load(accountId).take(100)
        val restored = loaded.map { record ->
            if (record.status == "uploading") record.copy(status = "paused") else record
        }
        mutable.value = restored.map { UploadQueueItem(it) }
        if (restored != loaded) persistence.save(accountId, restored)
    }
    fun detach() { pause(); account = null; mutable.value = emptyList() }
    fun enqueueIssue(items: List<BatchUploadSource>, destinationLibraryId: String? = null): BatchUploadEnqueueIssue? {
        if (account == null) return BatchUploadEnqueueIssue.ACCOUNT_UNAVAILABLE
        if (destinationLibraryId != null && !destinationAllowed(destinationLibraryId))
            return BatchUploadEnqueueIssue.DESTINATION_UNAVAILABLE
        if (items.isEmpty()) return BatchUploadEnqueueIssue.EMPTY_SELECTION

        val activeCount = mutable.value.count { it.record.status !in setOf("complete", "cancelled") }
        if (items.size > 100 || activeCount + items.size > 100) return BatchUploadEnqueueIssue.QUEUE_LIMIT

        var totalBytes = 0L
        for (item in items) {
            val maxBytes = when (item.kind) {
                UploadKind.IMAGE -> MAX_IMAGE
                UploadKind.VIDEO -> MAX_VIDEO
            }
            if (item.bytes !in 1L..maxBytes || !validName(item.filename))
                return BatchUploadEnqueueIssue.INVALID_SOURCE
            if (item.bytes > MAX_BATCH - totalBytes) return BatchUploadEnqueueIssue.BATCH_TOO_LARGE
            totalBytes += item.bytes
        }
        return null
    }
    fun enqueue(items: List<BatchUploadSource>, destinationLibraryId: String? = null): List<String> {
        val issue = enqueueIssue(items, destinationLibraryId)
        if (issue != null) throw BatchUploadEnqueueRejected(issue)
        val accountId = account ?: throw BatchUploadEnqueueRejected(BatchUploadEnqueueIssue.ACCOUNT_UNAVAILABLE)
        val records = mutable.value.map { it.record }.filterNot { it.status in setOf("complete", "cancelled") }.toMutableList()
        val batchId = hex(); val ids = mutableListOf<String>()
        items.forEach { item ->
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
        if (first.status !in READY) return
        epoch++; val run = epoch; var activeId = target
        job = scope.launch {
            try { processQueue(first, run, if (localId == null) null else first.batch) { activeId = it } }
            catch (_: CancellationException) { if (epoch == run) update(activeId) { it.copy(status = "paused") } }
            catch (error: Exception) { if (epoch == run) update(activeId) { it.copy(status = "failed", error = uploadFailureCode(error)) } }
            finally { if (epoch == run) { job = null; mutableActivity.value = null } }
        }
    }
    fun pause() {
        epoch++; job?.cancel(); job = null
        mutableActivity.value = null
        mutable.value = mutable.value.map { if (it.record.status == "uploading") it.copy(record = it.record.copy(status = "paused")) else it }
        persistCurrent()
    }
    fun cancel(localId: String) {
        val record = mutable.value.firstOrNull { it.record.localId == localId }?.record ?: return
        if (record.status in setOf("complete", "cancelled", "cancelling")) return
        pause(); val run = epoch
        val accountAtCancel = account ?: return
        val bearer = runCatching { token() }.getOrNull()
        if (record.uploadId == null) { update(localId) { it.copy(status = "cancelled") }; return }
        if (bearer == null || !valid()) { update(localId) { it.copy(status = "failed", error = "Cancellation needs a connection") }; return }
        update(localId) { it.copy(status = "cancelling") }
        scope.launch {
            val confirmed = runCatching { api.cancelUploadSession(bearer, record.uploadId) }.getOrNull()
            if (epoch == run && account == accountAtCancel && bearer === runCatching { token() }.getOrNull()) {
                if (confirmed?.state == "cancelled" && confirmed.uploadId == record.uploadId && confirmed.bytes == record.bytes &&
                    confirmed.destinationLibraryId == record.destinationLibraryId)
                    update(localId) { it.copy(status = "cancelled", error = null) }
                else update(localId) { it.copy(status = "failed", error = "Cancellation could not be confirmed") }
            }
        }
    }
    fun retry(localId: String) {
        if (job?.isActive == true || account == null || !valid()) return
        if (mutable.value.none { it.record.localId == localId && it.record.status == "failed" }) return
        update(localId) { it.copy(status = "queued", error = null) }
        resume(localId)
    }

    /** One explicit action retries interrupted members of this batch, retaining all identities. */
    fun retryBatch(batch: String) {
        val accountId = account ?: return
        if (job?.isActive == true || !valid()) return
        val records = mutable.value.map { it.record }
        if (records.none { it.batch == batch && it.status == "failed" }) return
        persist(accountId, records.map {
            if (it.batch == batch && it.status == "failed") it.copy(status = "queued", error = null) else it
        })
        val target = mutable.value.firstOrNull { it.record.batch == batch && it.record.status in READY } ?: return
        resume(target.record.localId)
    }

    private suspend fun processQueue(first: UploadQueueRecord, run: Long, batch: String?, onActive: (String) -> Unit) {
        var current: UploadQueueRecord? = first
        while (current != null) {
            ensure(run)
            val record = current
            onActive(record.localId)
            try { processWithRecovery(record.localId, run) }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) {
                ensure(run)
                update(record.localId) { it.copy(status = "failed", error = uploadFailureCode(error)) }
                // A missing/invalid file must not block the remaining files. Connection,
                // access and protocol failures affect the run; do not hammer every row.
                if (!fileSpecificFailure(error)) return
            }
            current = mutable.value.map { it.record }.firstOrNull { it.status in READY && (batch == null || it.batch == batch) }
        }
    }
    private suspend fun processWithRecovery(localId: String, run: Long) {
        var retries = 0
        while (true) {
            ensure(run)
            val record = mutable.value.first { it.record.localId == localId }.record.copy(status = "uploading", error = null)
            replace(record)
            try { process(record, run); return }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) {
                ensure(run)
                val wait = recoveryDelay(error, retries) ?: throw error
                retries++
                mutableActivity.value = UploadQueueActivity(localId, UploadQueuePhase.WAITING_RETRY,
                    retryAttempt = retries, retryDelayMillis = wait)
                delay(wait)
                ensure(run)
                // Re-enter with the latest persisted uploadId/offset. GET reconciles
                // ambiguous chunk/completion writes; create reuses the same requestId.
            }
        }
    }
    private fun recoveryDelay(error: Exception, retries: Int): Long? {
        if (retries >= 3 || error !is ApiFailure) return null
        val transient = error.kind == FailureKind.OFFLINE || error.kind == FailureKind.HTTP &&
            error.status in setOf(408, 429, 500, 502, 503, 504)
        if (!transient || error.retryAfterMillis > 30_000) return null
        return maxOf(2_000L shl retries, error.retryAfterMillis.coerceAtLeast(0))
    }
    private fun fileSpecificFailure(error: Exception) = when (error) {
        is ApiFailure -> error.kind in setOf(FailureKind.INVALID_INPUT, FailureKind.TOO_LARGE) ||
            error.kind == FailureKind.HTTP && error.status in setOf(400, 413, 415, 422)
        is java.io.IOException, is SecurityException -> true
        else -> false
    }
    private fun phase(record: UploadQueueRecord, run: Long, phase: UploadQueuePhase) {
        ensure(run)
        mutableActivity.value = UploadQueueActivity(record.localId, phase)
    }
    private suspend fun process(initial: UploadQueueRecord, run: Long) {
        var record = initial
        val destinationLibraryId = record.destinationLibraryId
        if (destinationLibraryId != null && !destinationAllowed(destinationLibraryId)) throw ApiFailure(FailureKind.HTTP, 403)
        phase(record, run, UploadQueuePhase.CHECKING)
        var session = record.uploadId?.let { api.uploadSession(token(), it) }
        ensure(run)
        if (session != null) {
            requireDestination(session, record)
            require(session.uploadId == record.uploadId && session.bytes == record.bytes)
            if (session.state == "complete") {
                replace(record.copy(offset = session.bytes, status = "complete", error = null, assetId = session.assetId)); return
            }
            require(session.state == "uploading")
            record = record.copy(offset = session.offset, status = "uploading", error = null)
            replace(record)
        }
        // All bytes may already be committed after a lost final reply. Confirm
        // completion without reopening a source the provider may no longer expose.
        if (session != null && session.offset == record.bytes) {
            finish(record, session, run); return
        }
        phase(record, run, UploadQueuePhase.HASHING)
        val item = withContext(ioDispatcher) { source(record) } ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        ensure(run)
        if (item.bytes != record.bytes || item.kind != record.kind || item.filename != record.filename)
            throw ApiFailure(FailureKind.INVALID_INPUT)
        if (record.sha256.isEmpty()) {
            record = record.copy(sha256 = withContext(ioDispatcher) { digest(item, run) })
            ensure(run); replace(record)
        }
        if (session == null) session = api.createUploadSession(token(), UploadSessionRequest(record.requestId, record.batch,
            record.filename, record.bytes, record.sha256, record.kind, record.destinationLibraryId))
        ensure(run)
        requireDestination(session, record)
        require(session.uploadId == (record.uploadId ?: session.uploadId) && session.bytes == record.bytes)
        if (session.state == "complete") { replace(record.copy(uploadId = session.uploadId, offset = session.bytes, status = "complete", error = null, assetId = session.assetId)); return }
        require(session.state == "uploading")
        record = record.copy(uploadId = session.uploadId, offset = session.offset, status = "uploading", error = null)
        replace(record)
        phase(record, run, UploadQueuePhase.UPLOADING)
        session = uploadChunks(item, session, record, token(), run)
        ensure(run)
        finish(record, session, run)
    }
    private suspend fun finish(record: UploadQueueRecord, session: UploadSession, run: Long) {
        phase(record, run, UploadQueuePhase.FINALIZING)
        val completed = api.completeUploadSession(token(), session.uploadId)
        ensure(run)
        requireDestination(completed, record)
        require(completed.uploadId == record.uploadId && completed.bytes == record.bytes && completed.offset == record.bytes && completed.state == "complete")
        replace(record.copy(offset = completed.bytes, status = "complete", error = null, assetId = completed.assetId))
    }
    private suspend fun uploadChunks(item: BatchUploadSource, start: UploadSession, initial: UploadQueueRecord, bearer: Bearer, run: Long): UploadSession = withContext(ioDispatcher) {
        var session = start; var record = initial; var conflicts = 0
        var stream: InputStream = item.open()
        fun skipTo(offset: Long) {
            var skipped = 0L
            while (skipped < offset) {
                ensure(run)
                val count = stream.skip(offset - skipped)
                if (count > 0) skipped += count
                else if (stream.read() >= 0) skipped++ else throw ApiFailure(FailureKind.INVALID_INPUT)
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
                    if (count <= 0) throw ApiFailure(FailureKind.INVALID_INPUT)
                    read += count
                }
                session = try { api.uploadChunk(bearer, session.uploadId, offset, chunk, sha(chunk)) }
                catch (failure: ApiFailure) {
                    if (failure.status != 409 || ++conflicts > 3) throw failure
                    val confirmed = api.uploadSession(bearer, session.uploadId)
                    ensure(run)
                    requireDestination(confirmed, record)
                    require(confirmed.uploadId == record.uploadId && confirmed.bytes == record.bytes && confirmed.state == "uploading")
                    stream.close(); stream = item.open(); skipTo(confirmed.offset)
                    session = confirmed; continue
                }
                ensure(run)
                requireDestination(session, record)
                require(session.uploadId == record.uploadId && session.bytes == record.bytes && session.offset > offset && session.offset <= record.bytes)
                record = record.copy(offset = session.offset); replace(record)
            }
            session
        } finally { stream.close() }
    }
    private fun requireDestination(session: UploadSession, record: UploadQueueRecord) {
        if (session.destinationLibraryId != record.destinationLibraryId)
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
    }
    private fun digest(item: BatchUploadSource, run: Long): String {
        val hash = MessageDigest.getInstance("SHA-256"); var total = 0L
        item.open().use { input ->
            val block = ByteArray(64 * 1024)
            while (true) {
                ensure(run); val count = input.read(block)
                if (count < 0) break
                if (count == 0) throw ApiFailure(FailureKind.INVALID_INPUT)
                total += count
                if (total > item.bytes) throw ApiFailure(FailureKind.INVALID_INPUT)
                hash.update(block, 0, count)
            }
        }
        ensure(run); if (total != item.bytes) throw ApiFailure(FailureKind.INVALID_INPUT)
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
