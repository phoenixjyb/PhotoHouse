package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import dev.photohouse.protocol.Captions
import dev.photohouse.protocol.Detail
import dev.photohouse.protocol.Gallery
import dev.photohouse.protocol.Membership
import dev.photohouse.protocol.Session
import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class RememberedSessionStoreTest {
    private val token = "TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT"
    private val session = Session("account-a", "+12025550123", listOf(Membership("family", "approved", "viewer", 1, null, 0, true)))

    @Test fun recreatedStoreRestoresWithoutLoginAndReauthorizesBeforeUncovering() = runTest {
        val api = FakeApi().apply {
            currentSession = session.copy(memberships = listOf(
                session.memberships.single().copy(library_id = "alpha"), session.memberships.single()))
        }
        val storage = FakeStorage(RememberedSession(token, 0, DAY))
        val first = store(api, storage)
        first.authenticate(phone, password)
        runCurrent()
        assertEquals(1, api.logins)
        assertEquals(1, storage.saves)

        val gate = CompletableDeferred<Unit>()
        api.sessionGate = gate
        val recreated = store(api, storage)
        recreated.restoreSession()
        runCurrent()
        assertTrue(recreated.state.value.covered)
        assertTrue(recreated.state.value.busy)
        assertNull(recreated.state.value.session)
        assertEquals(1, api.logins)
        gate.complete(Unit)
        runCurrent()
        assertFalse(recreated.state.value.covered)
        assertEquals(api.currentSession, recreated.state.value.session)
        assertEquals("family", recreated.state.value.library)
        assertEquals("family", recreated.state.value.gallery?.library_id)
        assertEquals(2, api.sessionReads)
    }

    @Test fun restoreOfflineExposesRetryAndRetryReauthorizes() = runTest {
        val api = FakeApi().apply { sessionError = ApiFailure(FailureKind.OFFLINE) }
        val storage = FakeStorage(RememberedSession(token, 0, DAY))
        val store = store(api, storage)
        store.restoreSession()
        runCurrent()
        assertEquals(Message.NETWORK_UNAVAILABLE, store.state.value.problem?.message)
        assertTrue(store.state.value.covered)
        assertTrue(store.canRetry())
        api.sessionError = null
        store.retry()
        runCurrent()
        assertFalse(store.state.value.covered)
        assertEquals(session, store.state.value.session)
        assertEquals(2, api.sessionReads)
    }

    @Test fun expiredFutureAndInvalidDiskCredentialsAreClearedWithoutNetwork() = runTest {
        val cases = listOf(
            RememberedSession(token, -1, DAY - 1),
            RememberedSession(token, 1, DAY + 1),
            RememberedSession("!".repeat(43), 0, DAY),
        )
        for (saved in cases) {
            val api = FakeApi()
            val storage = FakeStorage(saved)
            val store = store(api, storage)
            store.restoreSession()
            runCurrent()
            assertEquals(0, api.sessionReads)
            assertEquals(1, storage.clears)
            assertNull(store.state.value.session)
            assertFalse(store.hasSession)
        }
    }

    @Test fun restoreDoesNotPersistIdentityAndUnavailableMembershipStaysDenied() = runTest {
        val unavailable = session.copy(memberships = listOf(Membership("family", "approved", "viewer", 1, null, 0, false)))
        val api = FakeApi().apply { currentSession = unavailable }
        val storage = FakeStorage(RememberedSession(token, 0, DAY))
        val store = store(api, storage)
        store.restoreSession()
        runCurrent()
        assertEquals(unavailable, store.state.value.session)
        assertNull(storage.identity)
        store.selectLibrary("family")
        runCurrent()
        assertEquals(Message.ACCESS_DENIED, store.state.value.problem?.message)
    }

    @Test fun server401ExpiresAndClearsRememberedCredential() = runTest {
        val api = FakeApi().apply { sessionError = ApiFailure(FailureKind.HTTP, 401) }
        val storage = FakeStorage(RememberedSession(token, 0, DAY))
        val store = store(api, storage)
        store.restoreSession()
        runCurrent()
        assertEquals(Message.SESSION_ENDED, store.state.value.problem?.message)
        assertEquals(1, storage.clears)
        assertFalse(store.hasSession)
    }

    @Test fun logoutDuringRestorePreventsLateReauthorizationState() = runTest {
        val gate = CompletableDeferred<Unit>()
        val api = FakeApi().apply { sessionGate = gate }
        val storage = FakeStorage(RememberedSession(token, 0, DAY))
        val store = store(api, storage)
        store.restoreSession()
        runCurrent()
        store.logout()
        gate.complete(Unit)
        runCurrent()
        assertNull(store.state.value.session)
        assertFalse(store.hasSession)
        assertEquals(1, storage.clears)
        assertEquals(0, storage.saves)
    }

    @Test fun rememberFalseDoesNotWriteAndStorageFailureLeavesSessionUsable() = runTest {
        val api = FakeApi()
        val storage = FakeStorage(null)
        val store = store(api, storage)
        store.authenticate(phone, password, remember = false)
        runCurrent()
        assertEquals(0, storage.saves)
        assertEquals(session, store.state.value.session)

        val failing = FakeStorage(null).apply { saveFailure = true }
        val second = store(api, failing)
        second.authenticate(phone, password)
        runCurrent()
        assertEquals(Message.SESSION_STORAGE_UNAVAILABLE, second.state.value.problem?.message)
        assertEquals(session, second.state.value.session)

        val loadFailing = FakeStorage(RememberedSession(token, 0, DAY)).apply { loadFailure = true }
        val restored = store(api, loadFailing)
        restored.restoreSession()
        runCurrent()
        assertEquals(Message.SESSION_STORAGE_UNAVAILABLE, restored.state.value.problem?.message)
        assertFalse(restored.hasSession)
    }

    private fun TestScope.store(api: FakeApi, storage: FakeStorage) =
        ConnectedStore(api, backgroundScope, storage) { testScheduler.currentTime }

    private class FakeStorage(var value: RememberedSession?) : SessionPersistence {
        var saves = 0
        var clears = 0
        var saveFailure = false
        var loadFailure = false
        var identity: Session? = null
        override fun load(): RememberedSession? {
            if (loadFailure) throw IllegalStateException("synthetic storage failure")
            return value
        }
        override fun save(value: RememberedSession) {
            if (saveFailure) throw IllegalStateException("synthetic storage failure")
            saves++
            this.value = value
        }
        override fun clear() { clears++; value = null; identity = null }
    }

    private class FakeApi : PhotoHouseApi {
        var currentSession = Session("account-a", "+12025550123", listOf(Membership("family", "approved", "viewer", 1, null, 0, true)))
        var sessionError: Exception? = null
        var sessionGate: CompletableDeferred<Unit>? = null
        var sessionReads = 0
        var logins = 0
        override suspend fun login(phone: String, password: String): SessionToken {
            logins++
            return SessionToken(86400, "TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT", "Bearer")
        }
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer): Session {
            sessionReads++
            sessionGate?.await()
            sessionError?.let { throw it }
            return currentSession
        }
        override suspend fun acceptInvitation(token: Bearer, code: String) {}
        override suspend fun logout(token: Bearer) {}
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 1, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, Asset(assetId, "image", 1, 1, null, null, "/synthetic"))
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = VideoChunk(start, 0, ByteArray(0))
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray = byteArrayOf(1)
    }

    private companion object {
        const val DAY = 86_400_000L
        const val phone = "+12025550123"
        const val password = "synthetic-password-only"
    }
}
