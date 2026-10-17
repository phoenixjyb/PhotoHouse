package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.util.concurrent.atomic.AtomicInteger

@OptIn(ExperimentalCoroutinesApi::class)
class BatchUploadRecoveryTest {
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))

    private data class Remote(
        val request: UploadSessionRequest,
        val id: String,
        var offset: Long = 0,
        var complete: Boolean = false,
    )

    private class Api : PhotoHouseApi {
        override val uploadEnabled = true
        override val protectedNativeV2Enabled = true
        val sessions = linkedMapOf<String, Remote>()
        val requests = mutableListOf<UploadSessionRequest>()
        val gets = mutableListOf<String>()
        val puts = mutableListOf<Pair<String, Long>>()
        val acceptedRanges = mutableListOf<Triple<String, Long, Long>>()
        val completions = mutableListOf<String>()
        var nextFailure: ApiFailure? = null
        var persistentFailure: ApiFailure? = null
        var loseFirstChunkReply = false
        var loseFirstCompletionReply = false
        var loseFirstCreateReply = false
        var blockChunk: CompletableDeferred<Unit>? = null
        var chunkEntered: CompletableDeferred<Unit>? = null

        override suspend fun createUploadSession(token: Bearer, request: UploadSessionRequest): UploadSession {
            requests += request
            val existing = sessions.values.firstOrNull { it.request.requestId == request.requestId }
            val remote = existing ?: Remote(request, request.requestId.takeLast(32).padStart(32, '0')).also {
                sessions[it.id] = it
            }
            if (loseFirstCreateReply) {
                loseFirstCreateReply = false
                throw ApiFailure(FailureKind.OFFLINE)
            }
            return wire(remote)
        }

        override suspend fun uploadSession(token: Bearer, uploadId: String): UploadSession {
            gets += uploadId
            return wire(sessions.getValue(uploadId))
        }

        override suspend fun uploadChunk(
            token: Bearer, uploadId: String, offset: Long, chunk: ByteArray, sha256: String,
        ): UploadSession {
            puts += uploadId to offset
            chunkEntered?.complete(Unit)
            blockChunk?.let { withContext(NonCancellable) { it.await() } }
            nextFailure?.let { nextFailure = null; throw it }
            persistentFailure?.let { throw it }
            val remote = sessions.getValue(uploadId)
            if (offset != remote.offset) throw ApiFailure(FailureKind.HTTP, 409)
            remote.offset += chunk.size
            acceptedRanges += Triple(uploadId, offset, remote.offset)
            if (loseFirstChunkReply) {
                loseFirstChunkReply = false
                throw ApiFailure(FailureKind.OFFLINE)
            }
            return wire(remote)
        }

        override suspend fun completeUploadSession(token: Bearer, uploadId: String): UploadSession {
            completions += uploadId
            val remote = sessions.getValue(uploadId)
            remote.complete = true
            if (loseFirstCompletionReply) {
                loseFirstCompletionReply = false
                throw ApiFailure(FailureKind.OFFLINE)
            }
            return wire(remote)
        }

        private fun wire(remote: Remote) = UploadSession(
            remote.id, remote.request.bytes, if (remote.complete) remote.request.bytes else remote.offset,
            4, if (remote.complete) "complete" else "uploading",
            if (remote.complete) "asset-${remote.request.requestId.takeLast(4)}" else null,
            remote.request.destinationLibraryId,
        )

        override suspend fun login(phone: String, password: String) = error("unused") as SessionToken
        override suspend fun register(phone: String, password: String, code: String) = error("unused") as SessionToken
        override suspend fun session(token: Bearer) = error("unused") as dev.photohouse.protocol.Session
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = error("unused") as dev.photohouse.protocol.Gallery
        override suspend fun detail(token: Bearer, library: String, assetId: String) = error("unused") as dev.photohouse.protocol.Detail
        override suspend fun captions(token: Bearer, library: String, assetId: String) = error("unused") as dev.photohouse.protocol.Captions
        override suspend fun thumbnail(token: Bearer, library: String, asset: dev.photohouse.protocol.Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = error("unused") as VideoChunk
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String) = byteArrayOf()
    }

    private fun source(
        name: String,
        bytes: ByteArray = byteArrayOf(1, 2, 3, 4, 5, 6, 7, 8),
        opens: AtomicInteger = AtomicInteger(),
    ) = BatchUploadSource(name, bytes.size.toLong(), UploadKind.IMAGE, {
        opens.incrementAndGet()
        ByteArrayInputStream(bytes)
    }, "content://$name")

    private fun queue(
        api: Api,
        scope: TestScope,
        sources: Map<String, BatchUploadSource>,
        valid: () -> Boolean = { true },
        persistence: InMemoryUploadQueuePersistence = InMemoryUploadQueuePersistence(),
    ) = BatchUploadQueue(api, scope, persistence, { record -> sources[record.filename] }, valid, { token },
        ioDispatcher = StandardTestDispatcher(scope.testScheduler)) to persistence

    private suspend fun awaitStatus(queue: BatchUploadQueue, localId: String, status: String): UploadQueueRecord =
        withTimeout(20_000) {
            queue.state.first { rows -> rows.firstOrNull { it.record.localId == localId }?.record?.status == status }
                .first { it.record.localId == localId }.record
        }

    @Test fun lostCreateReplyUsesSameRequestAndDoesNotCreateAnotherRemoteTransfer() = runTest {
        val api = Api().apply { loseFirstCreateReply = true }
        val item = source("one.jpg")
        val (queue, _) = queue(api, this, mapOf(item.filename to item))
        queue.attach("account")
        val id = queue.enqueue(listOf(item), "family-a").single()
        val original = queue.state.value.single().record
        queue.resume()
        awaitStatus(queue, id, "complete")
        assertEquals(2, api.requests.size)
        assertEquals(1, api.sessions.size)
        assertTrue(api.requests.all { it.requestId == original.requestId && it.batch == original.batch &&
            it.destinationLibraryId == original.destinationLibraryId })
        assertEquals(2, api.acceptedRanges.size)
    }

    @Test fun securityAndProtocolFailuresDoNotRetryOrAdvanceAnotherFile() = runTest {
        for (failure in listOf(ApiFailure(FailureKind.TLS), ApiFailure(FailureKind.INVALID_RESPONSE),
            ApiFailure(FailureKind.HTTP, 401), ApiFailure(FailureKind.HTTP, 403))) {
            val api = Api().apply { persistentFailure = failure }
            val first = source("first.jpg"); val second = source("second.jpg")
            val (queue, _) = queue(api, this, listOf(first, second).associateBy { it.filename })
            queue.attach("account")
            val ids = queue.enqueue(listOf(first, second))
            queue.resume()
            awaitStatus(queue, ids.first(), "failed")
            queue.activity.first { it == null }
            assertEquals(1, api.puts.size)
            assertEquals(1, api.requests.size)
            assertEquals("needs_hash", queue.state.value.last().record.status)
        }
    }

    @Test fun acceptedChunkWithLostReplyReconcilesOffsetWithoutResendingAcceptedBytes() = runTest {
        val api = Api().apply { loseFirstChunkReply = true }
        val originalSource = source("one.jpg")
        val (queue, _) = queue(api, this, mapOf(originalSource.filename to originalSource))
        queue.attach("account")
        val localId = queue.enqueue(listOf(originalSource), "family-a").single()
        val original = queue.state.value.single().record

        queue.resume()
        val complete = awaitStatus(queue, localId, "complete")

        assertEquals(2, api.acceptedRanges.size)
        assertEquals(listOf(0L, 4L), api.puts.map { it.second })
        assertEquals(listOf(4L, 8L), api.acceptedRanges.map { it.third })
        assertTrue(api.gets.isNotEmpty())
        assertEquals(complete.uploadId, api.gets.last())
        assertEquals(listOf(original.requestId), api.requests.map { it.requestId })
        assertTrue(api.requests.all { it.batch == original.batch && it.destinationLibraryId == "family-a" })
        assertEquals(8L, complete.offset)
    }

    @Test fun lostCompletionReplyReconcilesCompleteWithoutReopeningSourceOrFinalizingTwice() = runTest {
        val api = Api().apply { loseFirstCompletionReply = true }
        val opens = AtomicInteger()
        val originalSource = source("one.jpg", opens = opens)
        val (queue, _) = queue(api, this, mapOf(originalSource.filename to originalSource))
        queue.attach("account")
        val localId = queue.enqueue(listOf(originalSource)).single()

        queue.resume()
        val complete = awaitStatus(queue, localId, "complete")

        assertEquals(1, api.completions.size)
        assertEquals(1, api.gets.count { it == complete.uploadId })
        assertEquals(complete.offset, complete.bytes)
        assertEquals("asset-${complete.requestId.takeLast(4)}", complete.assetId)
        assertEquals(2, api.acceptedRanges.size)
        assertEquals("digest and initial transfer are the only source opens", 2, opens.get())
    }

    @Test fun badSourceFailsOnlyItsRowAndQueueContinuesToNextFile() = runTest {
        val api = Api()
        val first = source("unreadable.jpg").copy(open = { ByteArrayInputStream(byteArrayOf(1, 2)) })
        val second = source("good.jpg")
        val (queue, _) = queue(api, this, mapOf(first.filename to first, second.filename to second))
        queue.attach("account")
        val ids = queue.enqueue(listOf(first, second))

        queue.resume()
        val failed = awaitStatus(queue, ids[0], "failed")
        val complete = awaitStatus(queue, ids[1], "complete")

        assertEquals("upload:source", failed.error)
        assertEquals("complete", complete.status)
        assertEquals(listOf(ids[0], ids[1]), queue.state.value.map { it.record.localId })
        assertEquals(1, api.requests.size)
        assertEquals(second.filename, api.requests.single().filename)
    }

    @Test fun retryContinuesOnlyWithinSameBatchAndDoesNotResetCompletedRows() = runTest {
        val api = Api()
        val first = source("first.jpg")
        val second = source("second.jpg")
        val other = source("other.jpg")
        val (queue, _) = queue(api, this, listOf(first, second, other).associateBy { it.filename })
        queue.attach("account")
        val firstBatch = queue.enqueue(listOf(first, second))
        val otherBatch = queue.enqueue(listOf(other)).single()
        api.nextFailure = ApiFailure(FailureKind.INVALID_INPUT)

        queue.resume(firstBatch[0])
        awaitStatus(queue, firstBatch[0], "failed")
        val secondComplete = awaitStatus(queue, firstBatch[1], "complete")
        queue.activity.first { it == null }
        val otherRecord = queue.state.value.first { it.record.localId == otherBatch }.record
        assertEquals("needs_hash", otherRecord.status)

        api.nextFailure = ApiFailure(FailureKind.OFFLINE)
        queue.retryBatch(queue.state.value.first { it.record.localId == firstBatch[0] }.record.batch)
        val firstComplete = awaitStatus(queue, firstBatch[0], "complete")
        assertEquals("complete", awaitStatus(queue, firstBatch[1], "complete").status)
        assertEquals("needs_hash", queue.state.value.first { it.record.localId == otherBatch }.record.status)
        assertEquals("complete", firstComplete.status)
        assertEquals("complete", secondComplete.status)
    }

    @Test fun retryIsNoOpForCompletedOrCurrentlyActiveRow() = runTest {
        val api = Api()
        val gate = CompletableDeferred<Unit>()
        val entered = CompletableDeferred<Unit>()
        api.blockChunk = gate
        api.chunkEntered = entered
        val item = source("one.jpg")
        val (queue, _) = queue(api, this, mapOf(item.filename to item))
        queue.attach("account")
        val id = queue.enqueue(listOf(item)).single()
        queue.resume()
        entered.await()
        val requestsBefore = api.requests.size
        queue.retry(id)
        runCurrent()
        assertEquals(requestsBefore, api.requests.size)
        assertEquals("uploading", queue.state.value.single().record.status)
        gate.complete(Unit)
        val done = awaitStatus(queue, id, "complete")
        queue.activity.first { it == null }
        queue.retry(id)
        runCurrent()
        assertEquals("complete", done.status)
        assertEquals(1, api.requests.size)
    }

    @Test fun retryAttemptsAreBoundedAndRetryAfterOverThirtySecondsIsNotAutomatic() = runTest {
        val api = Api()
        val item = source("busy.jpg")
        val (queue, _) = queue(api, this, mapOf(item.filename to item))
        queue.attach("account")
        val id = queue.enqueue(listOf(item)).single()
        api.nextFailure = ApiFailure(FailureKind.HTTP, 429, retryAfterMillis = 31_000)

        queue.resume(id)
        val failed = awaitStatus(queue, id, "failed")
        queue.activity.first { it == null }
        assertEquals("upload:busy", failed.error)
        assertEquals(1, api.requests.size)
        assertEquals(1, api.puts.size)
        assertNull(queue.activity.value)
    }

    @Test fun retryBackoffUsesBoundedAttemptsAndHonorsRetryAfterFloor() = runTest {
        val api = Api().apply { persistentFailure = ApiFailure(FailureKind.HTTP, 503, retryAfterMillis = 3_000) }
        val item = source("busy.jpg")
        val (queue, _) = queue(api, this, mapOf(item.filename to item))
        queue.attach("account")
        val id = queue.enqueue(listOf(item)).single()

        queue.resume(id)
        val firstWait = withTimeout(20_000) {
            queue.activity.first { it?.phase == UploadQueuePhase.WAITING_RETRY && it?.retryAttempt == 1 }
        }
        assertEquals(3_000L, firstWait?.retryDelayMillis)
        advanceTimeBy(2_999)
        runCurrent()
        assertEquals(1, api.puts.size)
        advanceTimeBy(1)
        runCurrent()

        val secondWait = withTimeout(20_000) {
            queue.activity.first { it?.phase == UploadQueuePhase.WAITING_RETRY && it?.retryAttempt == 2 }
        }
        assertEquals(4_000L, secondWait?.retryDelayMillis)
        advanceTimeBy(4_000)
        runCurrent()
        val thirdWait = withTimeout(20_000) {
            queue.activity.first { it?.phase == UploadQueuePhase.WAITING_RETRY && it?.retryAttempt == 3 }
        }
        assertEquals(8_000L, thirdWait?.retryDelayMillis)
        advanceTimeBy(8_000)
        val failed = awaitStatus(queue, id, "failed")
        queue.activity.first { it == null }

        assertEquals("upload:server", failed.error)
        assertEquals(4, api.puts.size)
        assertEquals(1, api.requests.size)
    }

    @Test fun pauseDuringBackoffPreventsAnotherNetworkAttemptAndRestoresPaused() = runTest {
        val api = Api()
        val item = source("flaky.jpg")
        val (queue, persistence) = queue(api, this, mapOf(item.filename to item))
        queue.attach("account")
        val id = queue.enqueue(listOf(item)).single()
        api.nextFailure = ApiFailure(FailureKind.OFFLINE)

        queue.resume(id)
        val waiting = withTimeout(20_000) {
            queue.activity.first { it?.phase == UploadQueuePhase.WAITING_RETRY }
        }
        assertNotNull(waiting)
        queue.pause()
        advanceTimeBy(60_000)
        runCurrent()

        assertEquals(1, api.requests.size)
        assertEquals("paused", queue.state.value.single().record.status)
        val restored = BatchUploadQueue(api, this, persistence, { item }, { true }, { token })
        restored.attach("account")
        assertEquals("paused", restored.state.value.single().record.status)
        assertTrue("attach must not start a transfer", api.gets.isEmpty())
    }

    @Test fun accountDetachFencesLateChunkReplyAndCannotUpdateOtherAccountQueue() = runTest {
        val api = Api()
        val gate = CompletableDeferred<Unit>()
        val entered = CompletableDeferred<Unit>()
        api.blockChunk = gate
        api.chunkEntered = entered
        val item = source("one.jpg")
        val (queue, persistence) = queue(api, this, mapOf(item.filename to item))
        queue.attach("account-a")
        val id = queue.enqueue(listOf(item)).single()
        queue.resume(id)
        entered.await()

        queue.detach()
        queue.attach("account-b")
        gate.complete(Unit)
        advanceUntilIdle()

        assertTrue(queue.state.value.isEmpty())
        assertTrue(persistence.load("account-b").isEmpty())
        assertEquals("paused", persistence.load("account-a").single().status)
    }
}
