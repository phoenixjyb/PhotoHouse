package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream

class UploadStoreTest {
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
    private val batch = "0123456789abcdef0123456789abcdef"

    private class Api : PhotoHouseApi {
        override val protectedNativeV2Enabled = true
        override val uploadEnabled = true
        var calls = 0
        var failure: Exception? = null
        var gate: CompletableDeferred<Unit>? = null
        val progress = mutableListOf<(Long) -> Unit>()
        var destinations = mutableListOf<String?>()
        override suspend fun uploadPhoto(token: Bearer, source: UploadSource, batch: String, destinationLibraryId: String?, onProgress: (Long) -> Unit): UploadReceipt {
            calls++; progress += onProgress
            destinations += destinationLibraryId
            gate?.let { withContext(NonCancellable) { it.await() } }
            failure?.let { throw it }; onProgress(source.bytes)
            return UploadReceipt("7", null, "member", batch, "image", 1, 1, "a".repeat(64), source.bytes, 5)
        }
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun session(token: Bearer) = Session("a", "+12025550123", emptyList())
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 1, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String) = error("unused")
        override suspend fun captions(token: Bearer, library: String, assetId: String) = error("unused")
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset) = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = VideoChunk(start, 1, byteArrayOf())
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String) = byteArrayOf()
    }

    @Test fun meteredUploadWaitsForExplicitApprovalAndReceiptIsQueuedOnly() = runTest {
        val api = Api(); val store = UploadStore(api, token, this, { true })
        val source = UploadSource("private-name.jpg", 2) { ByteArrayInputStream(byteArrayOf(1, 2)) }
        assertTrue(store.start(source, batch, UploadNetwork.METERED))
        assertEquals(UploadState.AwaitingNetwork(UploadNetwork.METERED), store.state.value)
        assertEquals(0, api.calls)
        assertTrue(store.approveNetwork()); advanceUntilIdle()
        val state = store.state.value as UploadState.Succeeded
        assertEquals("7", state.receipt.assetId); assertEquals(5, state.receipt.tasksEnqueued)
    }

    @Test fun explicitDestinationSurvivesMeteredApprovalAndRetry() = runTest {
        val api = Api().apply { failure = ApiFailure(FailureKind.HTTP, 503) }
        val store = UploadStore(api, token, this, { true }, { UploadNetwork.UNMETERED }, destinationLibraryId = null)
        val source = UploadSource("photo.jpg", 2) { ByteArrayInputStream(byteArrayOf(1, 2)) }
        assertTrue(store.start(source, batch, UploadNetwork.METERED, destinationLibraryId = "family-a"))
        assertTrue(store.approveNetwork()); advanceUntilIdle()
        assertEquals("family-a", api.destinations.single())
        assertTrue((store.state.value as UploadState.Failed).retryAvailable)
        api.failure = null; assertTrue(store.retry()); advanceUntilIdle()
        assertEquals(listOf("family-a", "family-a"), api.destinations)
    }

    @Test fun destinationRejectionIsNotRetriedWithoutTarget() = runTest {
        val api = Api().apply { failure = ApiFailure(FailureKind.HTTP, 422) }
        val store = UploadStore(api, token, this, { true }, { UploadNetwork.UNMETERED })
        val source = UploadSource("photo.jpg", 2) { ByteArrayInputStream(byteArrayOf(1, 2)) }
        assertTrue(store.start(source, batch, UploadNetwork.UNMETERED, destinationLibraryId = "family-a"))
        advanceUntilIdle()
        assertFalse((store.state.value as UploadState.Failed).retryAvailable)
        assertFalse(store.retry())
        assertEquals(listOf("family-a"), api.destinations)
    }

    @Test fun invalidScopePreventsStartAndCancelClearsPending() = runTest {
        var active = false; val api = Api(); val store = UploadStore(api, token, this, { active })
        assertFalse(store.start(UploadSource("x.jpg", 1) { ByteArrayInputStream(byteArrayOf(1)) }, batch, UploadNetwork.UNMETERED))
        store.cancel(); assertEquals(UploadState.Cancelled, store.state.value)
    }

    @Test fun accessDeniedDoesNotOfferRetry() = runTest {
        val api = Api().apply { failure = ApiFailure(FailureKind.HTTP, 403) }
        var denied = 0
        val store = UploadStore(api, token, this, { true }, { UploadNetwork.UNMETERED }, onDenied = { denied++ })
        assertTrue(store.start(UploadSource("photo.jpg", 1) { ByteArrayInputStream(byteArrayOf(1)) }, batch, UploadNetwork.UNMETERED))
        advanceUntilIdle()
        val failed = store.state.value as UploadState.Failed
        assertFalse(failed.retryAvailable)
        assertFalse(store.retry())
        assertEquals(1, denied)
    }
    @Test fun cancelledAttemptCannotOverwriteReplacementOrResurrectClosedState() = runTest {
        val api = Api(); val oldGate = CompletableDeferred<Unit>(); api.gate = oldGate
        val store = UploadStore(api, token, this, { true })
        val source = UploadSource("photo.jpg", 10) { ByteArrayInputStream(ByteArray(10)) }
        store.start(source, batch, UploadNetwork.UNMETERED); runCurrent()
        store.cancel()
        val newGate = CompletableDeferred<Unit>(); api.gate = newGate
        store.start(source, batch, UploadNetwork.UNMETERED); runCurrent()
        api.progress.first()(9); oldGate.complete(Unit); runCurrent()
        assertEquals(UploadState.Uploading(0,10), store.state.value)
        assertFalse(store.start(source, batch, UploadNetwork.UNMETERED))
        newGate.complete(Unit); runCurrent()
        assertTrue(store.state.value is UploadState.Succeeded)
        store.close(); api.progress.last()(10); runCurrent()
        assertEquals(UploadState.Idle, store.state.value)
        assertFalse(store.start(source,batch,UploadNetwork.UNMETERED))
    }

    @Test fun cooldownAndChangedNetworkRequireNewExplicitConsent() = runTest {
        var now = 1000L
        val api = Api().apply { failure = ApiFailure(FailureKind.HTTP,429,5000) }
        val store = UploadStore(api,token,this,{true},{UploadNetwork.METERED},{now})
        val source = UploadSource("photo.jpg",1){ ByteArrayInputStream(byteArrayOf(1)) }
        store.start(source,batch,UploadNetwork.UNMETERED); runCurrent()
        assertEquals(6000L,(store.state.value as UploadState.Failed).problem.retryAtMillis)
        assertFalse(store.retry()); now=6000
        assertTrue(store.retry()); assertEquals(UploadState.AwaitingNetwork(UploadNetwork.METERED),store.state.value)
        assertEquals(1,api.calls)
        api.failure=null; store.approveNetwork(); runCurrent()
        assertTrue(store.state.value is UploadState.Succeeded)
    }
}
