package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class PhoneDiscoveryStoreTest {
    private val person = PhoneChoice("51", "Reviewed person", 1, listOf("已确认的人物"))
    private val first = Asset("9223372036854775807", "image", 10, 10, null, null, "/assets/9223372036854775807/thumbnail?library=family")
    private val second = first.copy(id = "2", kind = "video", thumbnail_url = "/assets/2/thumbnail?library=family")
    private fun snapshot(library: String) = PhoneSnapshot(library, "b".repeat(64), "1", PhoneDiscoveryWire.fields, 51, 51,
        PhoneDiscoveryWire.fields.associateWith { PhoneCoverage(51, 0) }, "2026-01-01", "2026-12-31", listOf(person))
    private inner class FakeApi(override val discoveryEnabled: Boolean = true) : PhotoHouseApi {
        var facetReads = 0; var searches = 0; var galleryReads = 0; var originals = 0; var allowOriginals = false
        var placeQueries = mutableListOf<String>()
        var supportsPlaceQuery = true
        var placeGate: CompletableDeferred<Unit>? = null
        var searchGate: CompletableDeferred<Unit>? = null; var searchError: ApiFailure? = null
        var facetError: ApiFailure? = null; var sessionDenied = false
        var returnedKind = "image"
        var seenFilters: PhoneFilters? = null; var seenPage = 0; var seenFingerprint: String? = null
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer): Session {
            if (sessionDenied) throw ApiFailure(FailureKind.HTTP, 401)
            return Session("account", "+12025550123", listOf("family", "other").map { Membership(it, "approved", "viewer", 1, null, 0, true) })
        }
        override suspend fun logout(token: Bearer) {}
        override suspend fun acceptInvitation(token: Bearer, code: String) {}
        override suspend fun gallery(token: Bearer, library: String, page: Int): Gallery { galleryReads++; return Gallery(library, page, 50, 1, false, listOf(first)) }
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, allowOriginals, first.copy(id = assetId, kind = returnedKind))
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset) = byteArrayOf(1)
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray { originals++; return byteArrayOf(2) }
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = VideoChunk(start, 1, byteArrayOf(1))
        override suspend fun facets(token: Bearer, library: String, facet: PhoneFacet, page: Int, binding: String?): PhoneFacetPage {
            facetReads++; facetError?.let { throw it }
            return PhoneFacetPage(snapshot(library), facet, page, 50, 51, page == 1, if (page == 1) listOf(PhoneChoice("1", "First choice", 1)) else listOf(person))
        }
        override suspend fun placeFacets(token: Bearer, library: String, page: Int, query: String, binding: String?): PhoneFacetPage {
            if (!supportsPlaceQuery) return super<PhotoHouseApi>.placeFacets(token, library, page, query, binding)
            placeQueries += query
            placeGate?.let { withContext(NonCancellable) { it.await() } }
            return PhoneFacetPage(snapshot(library), PhoneFacet.PLACES, page, 50, 51, page == 1,
                if (page == 1) listOf(PhoneChoice("1", "北京", 1), PhoneChoice("2", "Beijing", 1)) else listOf(person))
        }
        override suspend fun search(token: Bearer, library: String, binding: String, filters: PhoneFilters, page: Int, fingerprint: String?): PhoneSearchPage {
            searches++; seenFilters = filters; seenPage = page; seenFingerprint = fingerprint
            searchGate?.let { withContext(NonCancellable) { it.await() } }; searchError?.let { throw it }
            return PhoneSearchPage(Gallery(library, page, 50, 51, false, if (page == 1) listOf(first) else listOf(second)), binding, "f".repeat(64), page == 1)
        }
    }
    private fun TestScope.signedIn(api: FakeApi): ConnectedStore {
        val store = ConnectedStore(api, backgroundScope) { testScheduler.currentTime }
        store.authenticate("+12025550123", "synthetic-password-only"); runCurrent()
        return store // Authentication now loads the preferred library itself.
    }
    @Test fun disabledBuildMakesNoDiscoveryRequests() = runTest {
        val api = FakeApi(false); val s = signedIn(api); s.openDiscovery(); runCurrent()
        assertNull(s.state.value.discovery); assertEquals(0, api.facetReads)
    }
    @Test fun legacyPlaceFacetAdapterRejectsQueryInsteadOfDroppingIt() = runTest {
        val api = FakeApi().apply { supportsPlaceQuery = false }
        val token = Bearer.from(api.login("+12025550123", "synthetic-password-only"))
        api.placeFacets(token, "family", 1, "")
        val failure = runCatching { api.placeFacets(token, "family", 1, "Beijing") }.exceptionOrNull()
        assertTrue(failure is ApiFailure)
        assertEquals(FailureKind.INVALID_INPUT, (failure as ApiFailure).kind)
        assertEquals(1, api.facetReads)
    }
    @Test fun placeQueryResetsToFirstPageRetainsSelectionsAndSuppressesOldResponse() = runTest {
        val api = FakeApi(); val s = signedIn(api); s.openDiscovery(); runCurrent()
        s.searchPlaces(); runCurrent()
        s.updateDiscoveryFilters(PhoneFilters(places = listOf(PhoneChoice("1", "北京", 1))))
        s.loadDiscoveryFacet(PhoneFacet.PLACES, 2); runCurrent()
        assertEquals(listOf("", ""), api.placeQueries)
        val gate = CompletableDeferred<Unit>(); api.placeGate = gate
        s.searchPlaces(); runCurrent()
        s.updatePlaceQuery("Beijing")
        assertEquals("Beijing", s.state.value.discovery!!.placeQuery)
        assertNull(s.state.value.discovery!!.facetPage)
        gate.complete(Unit); runCurrent()
        assertNull(s.state.value.discovery!!.facetPage)
        api.placeGate = null
        s.searchPlaces(); runCurrent()
        assertEquals(listOf("", "", "", "Beijing"), api.placeQueries)
        assertEquals(listOf("1"), s.state.value.discovery!!.filters.places.map { it.id })
        s.loadDiscoveryFacet(PhoneFacet.PLACES, 2); runCurrent()
        assertEquals("Beijing", api.placeQueries.last())
    }
    @Test fun laterFacetSelectionSurvivesPagingAndQueriesUseExplicitApply() = runTest {
        val api = FakeApi(); val s = signedIn(api); s.openDiscovery(); runCurrent()
        s.loadDiscoveryFacet(PhoneFacet.PEOPLE, 2); runCurrent()
        s.updateDiscoveryFilters(PhoneFilters(people = listOf(person), peopleAll = true, caption = "家庭"))
        s.loadDiscoveryFacet(PhoneFacet.TAGS); runCurrent()
        assertEquals(listOf(person), s.state.value.discovery!!.filters.people); assertEquals(0, api.searches)
        s.applyDiscovery(); runCurrent()
        assertEquals("家庭", api.seenFilters!!.caption); assertTrue(api.seenFilters!!.peopleAll)
        assertNull(api.seenFingerprint)
        s.navigatePage(2); runCurrent(); assertEquals(2, api.seenPage); assertEquals("f".repeat(64), api.seenFingerprint)
    }
    @Test fun invalidDatesAndUnknownSelectionsNeverReachTransport() = runTest {
        val api = FakeApi(); val s = signedIn(api); s.openDiscovery(); runCurrent()
        s.updateDiscoveryFilters(PhoneFilters(people = listOf(person.copy(id = "999"))))
        assertTrue(s.state.value.discovery!!.filters.people.isEmpty())
        s.updateDiscoveryFilters(PhoneFilters(from = "2026-02-30")); s.applyDiscovery(); runCurrent()
        assertTrue(s.state.value.discovery!!.inputInvalid); assertEquals(0, api.searches)
    }
    @Test fun resultMediaUsesFreshPermissionAndReturnsToSameQueryPage() = runTest {
        val api = FakeApi(); val s = signedIn(api); s.openDiscovery(); runCurrent()
        s.updateDiscoveryFilters(PhoneFilters(caption = "birthday")); s.applyDiscovery(); runCurrent(); s.navigatePage(2); runCurrent()
        s.openMedia(s.state.value.gallery!!.items.first()); runCurrent()
        assertFalse(s.state.value.viewingOriginal); assertNull(s.state.value.video); assertEquals(0, api.originals)
        s.backToPhotos(); runCurrent()
        assertEquals(2, s.state.value.gallery!!.page); assertEquals("birthday", api.seenFilters!!.caption); assertEquals(1, api.galleryReads)
        api.allowOriginals = true; api.returnedKind = "video"
        s.openMedia(s.state.value.gallery!!.items.first()); runCurrent(); assertNotNull(s.state.value.video)
        s.closeVideo(); s.backToPhotos(); runCurrent(); assertEquals(2, s.state.value.gallery!!.page)
    }
    @Test fun changedBindingClearsAllDependentStateAndDoesNotReplayQuery() = runTest {
        val api = FakeApi(); val s = signedIn(api); s.openDiscovery(); runCurrent()
        s.updateDiscoveryFilters(PhoneFilters(caption = "private words")); api.searchError = ApiFailure(FailureKind.HTTP, 409)
        s.applyDiscovery(); runCurrent()
        assertNull(s.state.value.gallery); assertTrue(s.state.value.discovery!!.changed)
        assertEquals("", s.state.value.discovery!!.filters.caption); assertNull(s.state.value.discovery!!.snapshot)
        assertEquals(1, api.searches); assertEquals(1, api.facetReads); assertFalse(s.canRetry())
        api.searchError = null; s.openDiscovery(); runCurrent(); assertEquals(1, api.searches)
    }
    @Test fun lateResultCannotSurviveLogoutBackgroundLibraryChangeOrCloseSearch() = runTest {
        for (action in listOf<(ConnectedStore) -> Unit>({ it.logout() }, { it.background() }, { it.selectLibrary("other") }, { it.loadPage(1) })) {
            val api = FakeApi(); val s = signedIn(api); s.openDiscovery(); runCurrent()
            val gate = CompletableDeferred<Unit>(); api.searchGate = gate; s.applyDiscovery(); runCurrent()
            action(s); runCurrent(); val generation = s.state.value.generation; gate.complete(Unit); runCurrent()
            assertEquals(generation, s.state.value.generation); assertNull(s.state.value.discovery)
            assertFalse(s.state.value.previews.keys.contains(Long.MAX_VALUE.toString()) && s.state.value.covered)
        }
    }
    @Test fun deniedSearchReconcilesSessionAndNeverRetainsQueryOrMedia() = runTest {
        val api = FakeApi(); val s = signedIn(api); s.openDiscovery(); runCurrent()
        api.sessionDenied = true; api.searchError = ApiFailure(FailureKind.HTTP, 401); s.applyDiscovery(); runCurrent()
        assertFalse(s.hasSession); assertNull(s.state.value.discovery); assertTrue(s.state.value.previews.isEmpty())
    }
    @Test fun busyRetryHonorsCooldownAndRequiresNewApply() = runTest {
        val api = FakeApi(); val s = signedIn(api); s.openDiscovery(); runCurrent()
        api.searchError = ApiFailure(FailureKind.HTTP, 429, 2000); s.applyDiscovery(); runCurrent()
        assertFalse(s.canRetry()); s.retry(); assertEquals(1, api.searches)
        advanceTimeBy(2000); api.searchError = null; s.retry(); runCurrent()
        assertEquals(1, api.searches); assertNotNull(s.state.value.discovery?.snapshot)
    }
    @Test fun forbiddenAndExpiryClearDiscoveryIncludingPendingResults() = runTest {
        val api = FakeApi(); val s = signedIn(api); s.openDiscovery(); runCurrent()
        api.searchError = ApiFailure(FailureKind.HTTP, 403); s.applyDiscovery(); runCurrent()
        assertNull(s.state.value.discovery); assertNull(s.state.value.gallery); assertFalse(s.canRetry())
        api.searchError = null; s.openDiscovery(); runCurrent()
        val gate = CompletableDeferred<Unit>(); api.searchGate = gate; s.applyDiscovery(); runCurrent()
        advanceTimeBy(86400001); runCurrent(); gate.complete(Unit); runCurrent()
        assertFalse(s.hasSession); assertNull(s.state.value.discovery); assertTrue(s.state.value.previews.isEmpty())
    }
}
