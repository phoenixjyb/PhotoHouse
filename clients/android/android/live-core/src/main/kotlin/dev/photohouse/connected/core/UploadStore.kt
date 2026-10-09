package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.isActive
import java.util.UUID
import java.util.concurrent.atomic.AtomicLong

enum class UploadNetwork { UNMETERED, METERED, UNKNOWN }

sealed class UploadState {
    data object Idle : UploadState()
    data class AwaitingNetwork(val network: UploadNetwork) : UploadState()
    data class Uploading(val sent: Long, val total: Long) : UploadState()
    data class Succeeded(val receipt: UploadReceipt) : UploadState()
    data class Failed(val problem: LiveProblem, val retryAvailable: Boolean = true) : UploadState()
    data object Cancelled : UploadState()
}

/** One-at-a-time whole-file upload coordinator. It owns no bytes or disk cache. */
class UploadStore(
    private val api: PhotoHouseApi,
    private val token: Bearer,
    private val scope: CoroutineScope,
    private val valid: () -> Boolean,
    private val network: () -> UploadNetwork = { UploadNetwork.UNKNOWN },
    private val now: () -> Long = System::currentTimeMillis,
    private val onDenied: () -> Unit = {},
    destinationLibraryId: String? = null,
    private val destinationAllowed: (String) -> Boolean = { true },
) {
    var destinationLibraryId: String? = destinationLibraryId
        private set
    private val mutable = MutableStateFlow<UploadState>(UploadState.Idle)
    val state = mutable.asStateFlow()
    private var job: Job? = null
    private var pending: Pending? = null
    private var closed = false
    private val epoch = AtomicLong(0)

    private data class Pending(val source: UploadSource, val batch: String, val destinationLibraryId: String?)

    fun chooseDestination(libraryId: String): Boolean {
        if (closed || job?.isActive == true || !destinationAllowed(libraryId)) return false
        require(libraryId.isNotBlank() && libraryId.length <= 128 && libraryId.none(Char::isISOControl))
        destinationLibraryId = libraryId
        return true
    }

    fun start(source: UploadSource, batch: String = UUID.randomUUID().toString().replace("-", ""),
              network: UploadNetwork, allowMetered: Boolean = false,
              destinationLibraryId: String? = this.destinationLibraryId): Boolean {
        if (closed || !api.uploadEnabled || !api.protectedNativeV2Enabled || job?.isActive == true || !valid()) return false
        require(batch.matches(Regex("[0-9a-f]{32}")))
        require(destinationLibraryId == null || destinationLibraryId.isNotBlank() && destinationLibraryId.length <= 128 && destinationLibraryId.none(Char::isISOControl))
        if (destinationLibraryId != null && !destinationAllowed(destinationLibraryId)) return false
        if (network != UploadNetwork.UNMETERED && !allowMetered) {
            pending = Pending(source, batch, destinationLibraryId); mutable.value = UploadState.AwaitingNetwork(network); return true
        }
        pending = Pending(source, batch, destinationLibraryId)
        launchPending()
        return true
    }

    /** Explicit user action after reviewing the metered/unknown-network warning. */
    fun approveNetwork(): Boolean {
        if (closed || mutable.value !is UploadState.AwaitingNetwork || job?.isActive == true || !valid()) return false
        launchPending(); return true
    }

    /** Retry is always explicit; an interrupted request may already have created the receipt. */
    fun retry(): Boolean {
        val failed = mutable.value as? UploadState.Failed ?: return false
        if (closed || !failed.retryAvailable || failed.problem.retryAtMillis > now() || job?.isActive == true || !valid()) return false
        if (pending?.destinationLibraryId?.let { !destinationAllowed(it) } == true) return false
        val currentNetwork = network()
        if (currentNetwork != UploadNetwork.UNMETERED) {
            mutable.value = UploadState.AwaitingNetwork(currentNetwork)
            return true
        }
        launchPending(); return true
    }

    fun cancel() {
        epoch.incrementAndGet()
        job?.cancel()
        job = null
        pending = null
        mutable.value = UploadState.Cancelled
    }

    fun close() {
        closed = true
        epoch.incrementAndGet()
        job?.cancel()
        job = null
        pending = null
        mutable.value = UploadState.Idle
    }

    private fun launchPending() {
        val request = pending ?: return
        val attempt = epoch.incrementAndGet()
        job?.cancel()
        mutable.value = UploadState.Uploading(0, request.source.bytes)
        job = scope.launch {
            try {
                if (!valid()) throw ApiFailure(FailureKind.HTTP, 401)
                if (request.destinationLibraryId?.let { !destinationAllowed(it) } == true) {
                    epoch.incrementAndGet(); pending = null
                    mutable.value = UploadState.Failed(LiveProblem(Message.ACCESS_DENIED), retryAvailable = false)
                    return@launch
                }
                val receipt = api.uploadPhoto(token, request.source, request.batch, request.destinationLibraryId) { sent ->
                    scope.launch { if (isActive && attempt == epoch.get() && valid()) mutable.value = UploadState.Uploading(sent, request.source.bytes) }
                }
                if (attempt == epoch.get() && valid()) { epoch.incrementAndGet(); pending = null; mutable.value = UploadState.Succeeded(receipt) }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                    if (attempt == epoch.get() && valid()) {
                        epoch.incrementAndGet(); mutable.value = UploadState.Failed(problem(error), retryAvailable = retryable(error))
                        if (error is ApiFailure && error.status in setOf(401, 403)) onDenied()
                    }
                } finally {
                if (attempt == epoch.get()) job = null
            }
        }
    }

    private fun retryable(error: Exception) = error is ApiFailure && when (error.kind) {
        FailureKind.OFFLINE -> true
        FailureKind.HTTP -> error.status in setOf(408, 429, 500, 502, 503, 504)
        else -> false
    }

    private fun problem(error: Exception): LiveProblem = when (error) {
        is ApiFailure -> when (error.kind) {
            FailureKind.HTTP -> LiveProblem(if (error.status == 401 || error.status == 403) Message.ACCESS_DENIED else Message.UNAVAILABLE, retryAt(error.retryAfterMillis))
            FailureKind.OFFLINE -> LiveProblem(Message.UNAVAILABLE)
            FailureKind.TLS -> LiveProblem(Message.TLS_ERROR)
            FailureKind.TOO_LARGE -> LiveProblem(Message.TOO_LARGE)
            else -> LiveProblem(Message.INVALID_RESPONSE)
        }
        else -> LiveProblem(Message.UNAVAILABLE)
    }

    private fun retryAt(delay: Long): Long {
        val current = now()
        return current + delay.coerceIn(0, Long.MAX_VALUE - current)
    }
}
