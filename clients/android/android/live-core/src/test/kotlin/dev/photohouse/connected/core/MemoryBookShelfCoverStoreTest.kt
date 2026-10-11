package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withContext
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MemoryBookShelfCoverStoreTest {
    private val firstBook = "11111111-1111-4111-8111-111111111111"
    private val secondBook = "22222222-2222-4222-8222-222222222222"
    private fun token(seed: Char = 'a') = Bearer.from(SessionToken(86400, seed.toString().repeat(43), "Bearer"))
    private fun jpeg(marker: Byte = 1) = byteArrayOf(0xff.toByte(), 0xd8.toByte(), 0xff.toByte(), marker, 0xff.toByte(), 0xd9.toByte())
    private fun entry(book: String = firstBook, asset: String = "17") = MemoryBookShelfCoverEntry(book, asset)
    private fun binding(
        account: String = "account-a", credential: Bearer = token(), generation: Long = 1,
        library: String = "family-a", shelf: Long = 10, entries: List<MemoryBookShelfCoverEntry> = listOf(entry()),
    ) = MemoryBookShelfCoverScope(account, credential, generation, library, shelf, entries)

    private object MissingThumbnail

    private data class Call(val token: Bearer, val library: String, val asset: Asset)

    private inner class Api : PhotoHouseApi {
        val calls = mutableListOf<Call>()
        val results = ArrayDeque<Any>()
        var gate: CompletableDeferred<Unit>? = null
        var gateAssetId: String? = null
        var gateBytes: ByteArray? = null
        var gateFailure: Exception? = null

        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? {
            calls += Call(token, library, asset)
            val wait = gate
            if (wait != null && (gateAssetId == null || gateAssetId == asset.id)) {
                withContext(NonCancellable) { wait.await() }
                gateFailure?.let { throw it }
                gateBytes?.let { return it }
            }
            val result = if (results.isEmpty()) jpeg() else results.removeFirst()
            if (result === MissingThumbnail) return null
            if (result is Exception) throw result
            return result as ByteArray
        }

        override suspend fun login(phone: String, password: String) = SessionToken(86400, "a".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("account-a", "+12025550123", emptyList())
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 1, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String) = error("covers must not read detail")
        override suspend fun captions(token: Bearer, library: String, assetId: String) = error("covers must not read captions")
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = error("covers must not read video")
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String) = error("covers must not read originals")
    }

    @Test fun constructionIsInertAndExplicitLoadUsesOnlyScopedThumbnailAssetsSequentially() = runTest {
        val current = binding(entries = listOf(entry(firstBook, "17"), entry(secondBook, "17")))
        val api = Api(); val store = MemoryBookShelfCoverStore(api, this, { current })
        assertTrue(api.calls.isEmpty())
        assertTrue(store.load()); runCurrent()
        assertEquals(2, api.calls.size)
        assertTrue(api.calls.all { it.library == "family-a" && it.token === current.credential })
        assertEquals(listOf("17", "17"), api.calls.map { it.asset.id })
        assertEquals("image", api.calls.first().asset.kind)
        assertEquals("/assets/17/thumbnail?library=family-a", api.calls.first().asset.thumbnail_url)
        assertEquals(setOf(firstBook, secondBook), store.state.value.images.keys)
        assertNotSame(store.state.value.images[firstBook], store.state.value.images[secondBook])
        assertTrue(store.state.value.unavailableBookIds.isEmpty())
        assertFalse(store.state.value.busy)
    }

    @Test fun invalidAndOversizedResponsesBecomePerBookUnavailableAndAreWiped() = runTest {
        val oversized = ByteArray(512 * 1024 + 1).also { it[0] = 0xff.toByte(); it[1] = 0xd8.toByte(); it[2] = 0xff.toByte() }
        val malformed = byteArrayOf(1, 2, 3, 4)
        val api = Api().apply { results.add(oversized); results.add(malformed); results.add(MissingThumbnail) }
        val current = binding(entries = listOf(entry(firstBook, "1"), entry(secondBook, "2"), entry("33333333-3333-4333-8333-333333333333", "3")))
        val store = MemoryBookShelfCoverStore(api, this, { current })
        store.load(); runCurrent()
        assertEquals(3, api.calls.size)
        assertTrue(oversized.all { it == 0.toByte() }); assertTrue(malformed.all { it == 0.toByte() })
        assertTrue(store.state.value.images.isEmpty())
        assertEquals(current.entries.map { it.bookId }.toSet(), store.state.value.unavailableBookIds)
    }

    @Test fun retryKeepsReadyCoverAndFetchesOnlyUnavailableIds() = runTest {
        val api = Api().apply { results.add(jpeg(1)); results.add(MissingThumbnail) }
        val current = binding(entries = listOf(entry(firstBook, "1"), entry(secondBook, "2")))
        val store = MemoryBookShelfCoverStore(api, this, { current })
        store.load(); runCurrent()
        val ready = store.state.value.images.getValue(firstBook)
        assertTrue(store.state.value.unavailableBookIds.contains(secondBook))
        api.results.add(jpeg(2))
        assertTrue(store.retryUnavailable()); runCurrent()
        assertEquals(listOf("1", "2", "2"), api.calls.map { it.asset.id })
        assertSame(ready, store.state.value.images[firstBook])
        assertTrue(ready.any { it != 0.toByte() })
        assertEquals(setOf(firstBook, secondBook), store.state.value.images.keys)
        assertTrue(store.state.value.unavailableBookIds.isEmpty())
    }

    @Test fun closeWipesPublishedBytesAndLateNoncooperativeResponse() = runTest {
        val current = binding(); val api = Api(); val store = MemoryBookShelfCoverStore(api, this, { current })
        store.load(); runCurrent()
        val published = store.state.value.images.getValue(firstBook)
        assertTrue(published.any { it != 0.toByte() })
        store.close()
        assertTrue(published.all { it == 0.toByte() })
        assertNull(store.state.value.accountId)

        val late = jpeg(9); api.gate = CompletableDeferred(); api.gateBytes = late
        assertTrue(store.load()); runCurrent()
        store.close(); api.gate!!.complete(Unit); runCurrent()
        assertTrue(late.all { it == 0.toByte() })
        assertTrue(store.state.value.images.isEmpty())
    }

    @Test fun closeWipesAlreadyStagedBytesAndCannotPublishAfterBlockedLaterResponse() = runTest {
        val first = jpeg(3); val late = jpeg(4)
        val api = Api().apply {
            results.add(first)
            gate = CompletableDeferred(); gateAssetId = "2"; gateBytes = late
        }
        val current = binding(entries = listOf(entry(firstBook, "1"), entry(secondBook, "2")))
        val store = MemoryBookShelfCoverStore(api, this, { current })
        store.load(); runCurrent()
        assertEquals(listOf("1", "2"), api.calls.map { it.asset.id })
        assertTrue(first.any { it != 0.toByte() })
        store.close()
        assertTrue(first.all { it == 0.toByte() })
        api.gate!!.complete(Unit); runCurrent()
        assertTrue(late.all { it == 0.toByte() })
        assertTrue(store.state.value.images.isEmpty())
        assertNull(store.state.value.accountId)
    }

    @Test fun retryWhileInitialLoadIsBusyDoesNotCancelOrClearThatLoad() = runTest {
        val late = jpeg(5)
        val api = Api().apply { gate = CompletableDeferred(); gateBytes = late }
        val current = binding()
        val store = MemoryBookShelfCoverStore(api, this, { current })
        assertTrue(store.load()); runCurrent()
        assertTrue(store.state.value.busy)
        assertFalse(store.retryUnavailable())
        assertTrue(store.state.value.busy)
        assertEquals(1, api.calls.size)
        api.gate!!.complete(Unit); runCurrent()
        assertEquals(setOf(firstBook), store.state.value.images.keys)
        assertTrue(store.state.value.images.getValue(firstBook).any { it != 0.toByte() })
        assertFalse(store.state.value.busy)
    }

    @Test fun retryAfterScopeMismatchClosesAndWipesThePreviousShelf() = runTest {
        var current = binding()
        val api = Api(); val store = MemoryBookShelfCoverStore(api, this, { current })
        store.load(); runCurrent()
        val ready = store.state.value.images.getValue(firstBook)
        current = current.copy(library = "family-b")
        assertFalse(store.retryUnavailable())
        assertTrue(ready.all { it == 0.toByte() })
        assertNull(store.state.value.accountId)
        assertTrue(store.state.value.images.isEmpty())
    }

    @Test fun accountCredentialLibraryAndShelfReplacementWipesOldBuffersBeforeReload() = runTest {
        var current = binding()
        val api = Api(); val store = MemoryBookShelfCoverStore(api, this, { current })
        store.load(); runCurrent()
        val old = store.state.value.images.getValue(firstBook)
        current = current.copy(accountId = "account-b")
        assertTrue(store.load()); assertTrue(old.all { it == 0.toByte() }); runCurrent()
        val second = store.state.value.images.getValue(firstBook)
        current = current.copy(credential = token('b'))
        assertTrue(store.load()); assertTrue(second.all { it == 0.toByte() }); runCurrent()
        val third = store.state.value.images.getValue(firstBook)
        current = current.copy(library = "family-b")
        assertTrue(store.load()); assertTrue(third.all { it == 0.toByte() }); runCurrent()
        val fourth = store.state.value.images.getValue(firstBook)
        current = current.copy(shelfScopeId = current.shelfScopeId + 1)
        assertTrue(store.load()); assertTrue(fourth.all { it == 0.toByte() }); runCurrent()
        assertEquals(5, api.calls.size)
        assertEquals("family-b", store.state.value.library)
        assertEquals(current.shelfScopeId, store.state.value.shelfScopeId)
    }

    @Test fun scopeChangeDuringReadDropsLateBytesAndStaleDenialIsInert() = runTest {
        var current = binding(); val denied = mutableListOf<String>()
        val api = Api().apply { gate = CompletableDeferred(); gateBytes = jpeg(8) }
        val store = MemoryBookShelfCoverStore(api, this, { current }, { denied += current.accountId })
        store.load(); runCurrent()
        val late = api.gateBytes!!
        current = current.copy(accountId = "replacement")
        api.gate!!.complete(Unit); runCurrent()
        assertTrue(late.all { it == 0.toByte() })
        assertTrue(denied.isEmpty())
        assertTrue(store.state.value.images.isEmpty())

        api.gate = CompletableDeferred(); api.gateBytes = null; api.gateFailure = ApiFailure(FailureKind.HTTP, 403)
        store.load(); runCurrent()
        val denialGate = api.gate!!
        current = current.copy(accountId = "newer-account")
        denialGate.complete(Unit); runCurrent()
        assertNull(store.state.value.accountId)
        assertTrue(denied.isEmpty())
    }

    @Test fun currentDenialWipesAllBuffersAndCallsOwnerOnce() = runTest {
        val current = binding(entries = listOf(entry(firstBook, "1"), entry(secondBook, "2")))
        val first = jpeg()
        val api = Api().apply { results.add(first); results.add(ApiFailure(FailureKind.HTTP, 401)) }
        var denied = 0
        val store = MemoryBookShelfCoverStore(api, this, { current }) { denied++ }
        store.load(); runCurrent()
        assertEquals(1, denied)
        assertTrue(store.state.value.images.isEmpty())
        assertNull(store.state.value.accountId)
        assertFalse(store.state.value.busy)
        assertTrue(first.all { it == 0.toByte() })
    }

    @Test fun boundedInputsAndConcurrentDuplicateLoadsAreRejected() = runTest {
        val tooMany = binding(entries = (1..9).map { entry(uuid(it), it.toString()) })
        val invalid = MemoryBookShelfCoverStore(Api(), this, { tooMany })
        assertFalse(invalid.load()); assertTrue(invalid.state.value.images.isEmpty())

        val malformed = binding(entries = listOf(entry("not-a-uuid", "1")))
        val invalidId = MemoryBookShelfCoverStore(Api(), this, { malformed })
        assertFalse(invalidId.load())

        val api = Api().apply { gate = CompletableDeferred(); gateBytes = jpeg() }
        val current = binding(); val store = MemoryBookShelfCoverStore(api, this, { current })
        assertTrue(store.load()); runCurrent()
        assertFalse(store.load()); assertFalse(store.retryUnavailable())
        assertEquals(1, api.calls.size)
        store.close(); api.gate!!.complete(Unit); runCurrent()
    }

    @Test fun orderedEntryChangeInvalidatesThePreviousSnapshot() = runTest {
        var current = binding(entries = listOf(entry(firstBook, "1"), entry(secondBook, "2")))
        val api = Api(); val store = MemoryBookShelfCoverStore(api, this, { current })
        store.load(); runCurrent()
        val first = store.state.value.images.getValue(firstBook)
        val second = store.state.value.images.getValue(secondBook)
        current = current.copy(entries = current.entries.reversed())
        assertTrue(store.load())
        assertTrue(first.all { it == 0.toByte() }); assertTrue(second.all { it == 0.toByte() })
        runCurrent()
        assertEquals(listOf("1", "2", "2", "1"), api.calls.map { it.asset.id })
        assertEquals(setOf(firstBook, secondBook), store.state.value.images.keys)
    }

    private fun uuid(n: Int) = "%08x-0000-4000-8000-000000000000".format(n)
}
