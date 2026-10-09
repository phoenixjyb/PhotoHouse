package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.delay
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream

@OptIn(ExperimentalCoroutinesApi::class)
class BatchUploadQueueTest {
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
    private class Api : PhotoHouseApi {
        override val uploadEnabled = true; override val protectedNativeV2Enabled = true
        var offset = 0L; var queried = 0; var chunks = 0; var conflict = true; var cancelled = 0; var remoteComplete = false
        val sessionRequests = mutableListOf<UploadSessionRequest>()
        override suspend fun createUploadSession(token: Bearer, request: UploadSessionRequest): UploadSession {
            sessionRequests += request
            return UploadSession("a".repeat(32), request.bytes, offset, 4 * 1024 * 1024, "uploading", null)
        }
        override suspend fun uploadSession(token: Bearer, uploadId: String): UploadSession { queried++; return UploadSession(uploadId, 8, if (remoteComplete) 8 else offset, 4 * 1024 * 1024, if (remoteComplete) "complete" else "uploading", if (remoteComplete) "901" else null) }
        override suspend fun uploadChunk(token: Bearer, uploadId: String, offset: Long, chunk: ByteArray, sha256: String): UploadSession {
            chunks++; if (conflict) { conflict = false; throw ApiFailure(FailureKind.HTTP, 409) }; this.offset = offset + chunk.size; return UploadSession(uploadId, 8, this.offset, 4 * 1024 * 1024, "uploading", null)
        }
        override suspend fun completeUploadSession(token: Bearer, uploadId: String) = UploadSession(uploadId, 8, 8, 4 * 1024 * 1024, "complete", "901")
        override suspend fun cancelUploadSession(token: Bearer, uploadId: String) = UploadSession(uploadId, 8, offset, 4 * 1024 * 1024, "cancelled", null).also { cancelled++ }
        override suspend fun login(phone: String, password: String) = error("unused") as dev.photohouse.protocol.SessionToken
        override suspend fun register(phone: String, password: String, code: String) = error("unused") as dev.photohouse.protocol.SessionToken
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
    private fun source() = BatchUploadSource("a.mp4", 8, UploadKind.VIDEO, { ByteArrayInputStream(ByteArray(8) { 7 }) }, "content://a")
    @Test fun hashesStreamsResyncs409AndCompletes() = runBlocking {
        val api = Api(); val persistence = InMemoryUploadQueuePersistence(); val map = mapOf("content://a" to source())
        val queue = BatchUploadQueue(api, CoroutineScope(Dispatchers.Default), persistence, { it.locator?.let(map::get) }, { true }, { token }); queue.attach("account-a")
        val id = queue.enqueue(listOf(source()), "family-a").single(); queue.resume(id); delay(250)
        assertEquals("complete", queue.state.value.single().record.status); assertEquals(1, api.queried); assertEquals(2, api.chunks)
        assertEquals("901", queue.state.value.single().record.assetId)
        assertEquals("family-a", api.sessionRequests.single().destinationLibraryId)
        assertEquals("family-a", persistence.load("account-a").single().destinationLibraryId)
    }
    @Test fun restartIsScopedAndDoesNotAutoResume() = runTest {
        val persistence = InMemoryUploadQueuePersistence(); val api = Api(); val source = source(); val resolver = { r: UploadQueueRecord -> if (r.locator == source.locator) source else null }
        val first = BatchUploadQueue(api, this, persistence, resolver, { true }, { token }); first.attach("a"); first.enqueue(listOf(source()), "family-a"); first.pause()
        val second = BatchUploadQueue(api, this, persistence, resolver, { true }, { token }); second.attach("a"); assertEquals("needs_hash", second.state.value.single().record.status); assertTrue(second.state.value.isNotEmpty())
        assertEquals("family-a", second.state.value.single().record.destinationLibraryId)
        val other = BatchUploadQueue(api, this, persistence, resolver, { true }, { token }); other.attach("b"); assertTrue(other.state.value.isEmpty())
    }
    @Test fun expiryOrCancelStopsQueueWithoutLateProgress() = runTest {
        val persistence = InMemoryUploadQueuePersistence(); val api = Api(); var valid = true; val source = source(); val q = BatchUploadQueue(api, this, persistence, { source }, { valid }, { token }); q.attach("a"); val id = q.enqueue(listOf(source())).single(); valid = false; q.resume(id); advanceUntilIdle(); assertNotEquals("complete", q.state.value.single().record.status)
    }
    @Test fun lostCompletionReplyReconcilesWithoutOpeningOriginalAgain() = runBlocking {
        val api = Api().apply { remoteComplete = true }
        val memory = InMemoryUploadQueuePersistence()
        memory.save("account-a", listOf(UploadQueueRecord("local", "1".repeat(32), "2".repeat(32), "missing.mp4", "content://missing", 8, UploadKind.VIDEO, "0".repeat(64), "a".repeat(32), 8, "paused")))
        val queue = BatchUploadQueue(api, CoroutineScope(Dispatchers.Default), memory, { error("Media must not be opened") }, { true }, { token })
        queue.attach("account-a"); queue.resume("local"); delay(150)
        assertEquals("complete", queue.state.value.single().record.status)
        assertEquals(1, api.queried)
    }
    @Test fun failureInSecondFileDoesNotMarkCompletedFirstFileAsFailed() = runBlocking {
        val api = Api().apply { conflict = false }; val first = source(); val second = first.copy(filename = "missing.mp4", locator = "content://missing")
        val queue = BatchUploadQueue(api, CoroutineScope(Dispatchers.Default), InMemoryUploadQueuePersistence(),
            { if (it.filename == first.filename) first else null }, { true }, { token })
        queue.attach("account-a"); queue.enqueue(listOf(first, second)); queue.resume(); delay(250)
        assertEquals(listOf("complete", "failed"), queue.state.value.map { it.record.status })
        assertEquals(queue.state.value[0].record.batch, queue.state.value[1].record.batch)
    }
}
