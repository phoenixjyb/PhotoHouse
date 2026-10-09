package dev.photohouse.fixture.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class FixtureTest {
    private fun text(name: String) = javaClass.classLoader!!.getResource(name)!!.readText()
    private val fixtures get() = Contract.fixtures(text("fixtures.json"))
    private fun case(id: String) = fixtures.cases.single { it.id == id }
    private class HarnessRepository(val cases: Map<String, FixtureCase>, val resources: Map<String, String>) : FixtureRepository {
        val calls = mutableListOf<String>()
        var delayedCase: String? = null
        val entered = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        var override: Pair<String, FixtureCase>? = null
        override suspend fun response(caseId: String): FixtureCase {
            calls += caseId
            if (caseId == delayedCase) {
                entered.complete(Unit)
                // Intentionally emulate a callback source that ignores cancellation.
                withContext(NonCancellable) { release.await() }
            }
            return override?.takeIf { it.first == caseId }?.second ?: cases.getValue(caseId)
        }
        override fun thumbnail(path: String): ByteArray? {
            calls += "image:$path"
            return resources[path]?.let { javaClass.classLoader!!.getResource(it)!!.readBytes() }
        }
    }
    private fun repo() = HarnessRepository(fixtures.cases.associateBy { it.id }, Contract.scenarios(text("client-scenarios.json")).thumbnail_resources)
    private suspend fun settle() { repeat(8) { yield() } }
    private suspend fun approved(store: PhotoHouseStore) { store.signIn(); settle(); store.selectLibrary("family-a"); settle() }
    private fun privateEmpty(store: PhotoHouseStore) {
        assertNull(store.state.value.gallery); assertNull(store.state.value.detail)
        assertNull(store.state.value.captions); assertEquals(0, store.cacheEntries)
    }

    @Test fun parsesEveryFrozenJsonSuccessAndRetainsWireTypes() {
        for (response in fixtures.cases.filter { it.status in 200..299 && it.body != null }) {
            when (response.operation_id) {
                "login", "registerInvited" -> assertEquals(86400L, Contract.body<SessionToken>(response).expires_in)
                "session" -> Contract.body<Session>(response)
                "gallery" -> Contract.body<Gallery>(response)
                "detail" -> Contract.body<Detail>(response)
                "captions" -> Contract.body<Captions>(response)
                "logout", "acceptInvitation" -> assertTrue(Contract.body<Ok>(response).ok)
                else -> error("Uncovered JSON success")
            }
        }
        assertEquals(38, fixtures.cases.size)
        assertEquals((1..10).map { "APP-%02d".format(it) }, Contract.scenarios(text("client-scenarios.json")).scenarios.map { it.id })
        assertEquals(20260000001L, Contract.body<Session>(case("approved").copy(body = Contract.json.parseToJsonElement(case("approved").body.toString().replace("\"revision\":1", "\"revision\":20260000001")))).memberships[0].revision)
        val large = Contract.json.decodeFromString<Asset>(Contract.body<Detail>(case("detail")).asset.let { kotlinx.serialization.json.Json.encodeToString(Asset.serializer(), it) }.replace("\"101\"", "\"9223372036854775807\""))
        assertEquals("9223372036854775807", large.id)
        assertEquals("2026-01-01", large.taken_at)
        assertEquals("2026-01-01 00:00:00", Contract.body<Captions>(case("captions-bilingual")).items[0].created_at)
        assertTrue(Contract.passwordLengthValid("😀".repeat(15)))
        assertFalse(Contract.passwordLengthValid("😀".repeat(14)))
        assertFalse(Contract.passwordLengthValid("😀".repeat(129)))
    }

    @Test fun app01InvitedRegistrationGrantsOnlyInvitedLibrary() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this)
        store.signIn(invited = true); settle()
        assertEquals(listOf("invited-registration", "invited-viewer"), repo.calls)
        assertEquals(listOf("family-a"), store.state.value.session!!.memberships.map { it.library_id })
        assertEquals("viewer", store.state.value.session!!.memberships.single().role)
        store.selectLibrary("family-a"); settle(); assertEquals(2, store.state.value.gallery!!.items.size)
    }
    @Test fun app02InvalidInvitationStaysSignedOut() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this)
        store.signIn(invited = true, invalidInvitation = true); settle()
        assertEquals(listOf("invalid-invitation"), repo.calls)
        assertNull(store.state.value.session); assertFalse(store.hasToken); privateEmpty(store)
        assertEquals(Notice.INVALID_INVITATION, store.state.value.problem!!.notice)
        store.selectLibrary("family-a"); settle(); assertEquals(1, repo.calls.size)
    }
    @Test fun app03AllUnavailableMembershipsDenyGalleryAndMedia() = runBlocking {
        for (profile in listOf("requested", "rejected", "revoked", "membership-expired", "no-memberships")) {
            val repo = repo(); val store = PhotoHouseStore(repo, this)
            store.signIn(profile = profile); settle(); store.selectLibrary("family-a"); settle()
            store.loadGallery(); settle()
            assertEquals(listOf("login", profile), repo.calls); privateEmpty(store)
        }
        val repo = repo()
        repo.override = "approved" to case("approved").copy(body = Contract.json.parseToJsonElement(case("approved").body.toString().replace("\"available\":true", "\"available\":false")))
        val store = PhotoHouseStore(repo, this); approved(store)
        assertEquals(listOf("login", "approved"), repo.calls)
    }
    @Test fun app04ApprovedGalleryDetailAndLiteralCaptions() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this); approved(store)
        assertEquals(2, store.cacheEntries)
        store.openAsset(store.state.value.gallery!!.items.single { it.id == "101" }); settle()
        assertEquals("Synthetic hillside. 合成山景。", store.state.value.captions!!.items.single().text)
        assertEquals("2026-01-01", store.state.value.detail!!.asset.taken_at)
        assertFalse(store.state.value.detail!!.originals_allowed)
    }
    @Test fun app05MissingPreviewNeverFallsBackAndVideoHasNoPlayer() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this); approved(store)
        store.loadGallery(missingPreview = true); settle()
        assertEquals(0, store.cacheEntries); assertEquals(2, store.state.value.gallery!!.items.size)
        store.openAsset(store.state.value.gallery!!.items.first()); settle()
        assertEquals("video", store.state.value.detail!!.asset.kind)
        assertFalse(store.state.value.detail!!.originals_allowed)
        assertTrue(repo.calls.none { it.contains("original") || it.contains("media?") })
        assertEquals(401, case("missing-original-permission").status)
    }
    @Test fun app06LateOldLibraryResponseIsDropped() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this)
        store.signIn(profile = "two-libraries"); settle()
        repo.delayedCase = "gallery"
        store.selectLibrary("family-a"); repo.entered.await()
        val generation = store.state.value.generation
        store.selectLibrary("family-b"); assertTrue(store.state.value.generation > generation)
        privateEmpty(store); repo.release.complete(Unit); settle()
        assertEquals("family-b", store.state.value.library); privateEmpty(store)
        assertTrue(repo.calls.none { it.startsWith("image:") })
    }
    @Test fun app07LogoutClearsImmediatelyEvenWithLateDataAndFailure() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this); approved(store)
        repo.delayedCase = "detail"
        store.openAsset(store.state.value.gallery!!.items.last()); repo.entered.await()
        store.logout(serverUnavailable = true)
        assertFalse(store.hasToken); assertNull(store.state.value.session); assertNull(store.state.value.library); privateEmpty(store)
        repo.release.complete(Unit); settle()
        privateEmpty(store); assertEquals(Notice.LOCAL_LOGOUT, store.state.value.problem!!.notice)
        assertFalse(store.hasToken)
    }
    @Test fun app07LateLoginCannotRestoreCredentialsAfterLogout() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this)
        repo.delayedCase = "approved"; store.signIn(); repo.entered.await()
        store.logout(); repo.release.complete(Unit); settle()
        assertNull(store.state.value.session); assertFalse(store.hasToken)
    }
    @Test fun app08ObjectDenialChecksSessionExactlyOnceWithoutSigningOutValidAccount() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this); approved(store)
        repo.calls.clear()
        store.openAsset(store.state.value.gallery!!.items.first(), denied = true); settle()
        assertEquals(listOf("foreign-asset", "approved"), repo.calls)
        assertTrue(store.hasToken); assertNotNull(store.state.value.session); privateEmpty(store)
        store.selectLibrary("family-a"); settle(); repo.calls.clear()
        store.openAsset(store.state.value.gallery!!.items.first(), denied = true, recheck = "expired"); settle()
        assertEquals(listOf("foreign-asset", "expired"), repo.calls)
        assertFalse(store.hasToken); assertNull(store.state.value.session); privateEmpty(store)
    }
    @Test fun app08UnavailableSessionCheckCoversWithoutClaimingRevocation() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this); approved(store)
        store.openAsset(store.state.value.gallery!!.items.first(), denied = true, recheck = "unavailable"); settle()
        assertTrue(store.hasToken); assertTrue(store.state.value.covered); privateEmpty(store)
        assertEquals(Notice.UNAVAILABLE, store.state.value.problem!!.notice)
    }
    @Test fun app09BackgroundClearsPrivateStateAndWaitsForRevalidation() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this); approved(store)
        store.background(); assertTrue(store.state.value.covered); assertNull(store.state.value.session); privateEmpty(store)
        repo.delayedCase = "approved"
        store.foreground(); repo.entered.await()
        assertTrue(store.state.value.covered); privateEmpty(store)
        repo.release.complete(Unit); settle()
        assertFalse(store.state.value.covered); assertNotNull(store.state.value.session); privateEmpty(store)
        store.background(); store.foreground("expired"); settle()
        assertFalse(store.hasToken); assertNull(store.state.value.session)
        val cold = PhotoHouseStore(repo, this)
        assertFalse(cold.hasToken); assertNull(cold.state.value.session); privateEmpty(cold)
    }
    @Test fun app09RevalidationCannotUncoverAfterAnotherBackground() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this); approved(store)
        store.background(); repo.delayedCase = "approved"; store.foreground(); repo.entered.await()
        store.background(); repo.release.complete(Unit); settle()
        assertTrue(store.state.value.covered); assertNull(store.state.value.session); privateEmpty(store)
    }
    @Test fun coveredNavigationCannotBypassRevalidation() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this); approved(store)
        store.background(); repo.calls.clear()
        store.libraries(); store.selectLibrary("family-a"); store.loadGallery(); store.acceptDemoInvitation(); settle()
        assertTrue(store.state.value.covered); assertNull(store.state.value.session); privateEmpty(store)
        assertTrue(repo.calls.isEmpty())
    }
    @Test fun sessionExpiryStopsForegroundReadsBeforeCallingRepository() = runBlocking {
        var now = 0L; val repo = repo(); val store = PhotoHouseStore(repo, this) { now }; approved(store)
        repo.calls.clear(); now = 86400000; store.loadGallery(); settle()
        assertFalse(store.hasToken); privateEmpty(store); assertTrue(repo.calls.isEmpty())
    }
    @Test fun app09TwentyFourHourExpiryLocksOnForeground() = runBlocking {
        var now = 0L; val repo = repo(); val store = PhotoHouseStore(repo, this) { now }; approved(store)
        store.background(); now = 86400000; store.foreground(); settle()
        assertFalse(store.hasToken); assertEquals(Notice.EXPIRED, store.state.value.problem!!.notice)
    }
    @Test fun app10EmptyCaptionsAndMarkupRemainLiteralAndSeparateFromUiLanguage() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this); approved(store)
        val asset = store.state.value.gallery!!.items.first()
        store.openAsset(asset); settle()
        assertEquals("<script>synthetic text only</script>", store.state.value.captions!!.items.single().text)
        store.openAsset(asset, missingCaptions = true); settle(); assertTrue(store.state.value.captions!!.items.isEmpty())
        store.loadGallery("empty-page"); settle(); assertTrue(store.state.value.gallery!!.items.isEmpty()); assertNull(store.state.value.problem)
    }
    @Test fun app10RateLimitCooldownAndUnavailableRetryDoNotLoop() = runBlocking {
        var now = 0L; val repo = repo(); val store = PhotoHouseStore(repo, this) { now }
        store.signIn(admission = "rate-limited"); settle()
        assertEquals(listOf("rate-limited"), repo.calls); assertFalse(store.canRetry())
        store.retry(); settle(); assertEquals(1, repo.calls.size)
        now = 5000; assertTrue(store.canRetry()); store.retry(); settle(); assertTrue(store.hasToken)
        store.logout(); settle(); store.signIn(profile = "unavailable"); settle()
        assertFalse(store.hasToken); assertEquals(Notice.UNAVAILABLE, store.state.value.problem!!.notice)
        store.retry(); settle(); assertTrue(store.hasToken)
        assertEquals(10000L, PhotoHouseStore.retryDelayMillis("10"))
        assertEquals(86400000L, PhotoHouseStore.retryDelayMillis("9999999"))
        assertEquals(10000L, PhotoHouseStore.retryDelayMillis("Thu, 01 Jan 1970 00:00:10 GMT", 0))
    }
    @Test fun rejectsWrongLibraryResponsesAndNeverLoadsTheirMedia() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this)
        store.signIn(); settle()
        repo.override = "gallery" to case("gallery").copy(body = Contract.json.parseToJsonElement(case("gallery").body.toString().replace("family-a", "family-b")))
        store.selectLibrary("family-a"); settle()
        privateEmpty(store); assertEquals(Notice.INVALID_RESPONSE, store.state.value.problem!!.notice)
        assertTrue(repo.calls.none { it.startsWith("image:") })
    }
    @Test fun closedBoundaryDoesNotTryLegacyOrRetry() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this)
        store.signIn(); settle(); repo.calls.clear()
        repo.override = "gallery" to case("foreign-asset").copy(status = 403)
        store.selectLibrary("family-a"); settle()
        assertEquals(listOf("gallery"), repo.calls); assertFalse(store.canRetry()); privateEmpty(store)
        assertEquals(Notice.CLOSED, store.state.value.problem!!.notice)
    }
    @Test fun acceptedInvitationRefetchesOnlyOwnSession() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this)
        store.signIn(); settle(); repo.calls.clear()
        store.acceptDemoInvitation(); settle()
        assertEquals(listOf("accept-second-library", "two-libraries"), repo.calls)
        assertEquals(2, store.state.value.session!!.memberships.size); privateEmpty(store)
    }
    @Test fun duplicateIdsAreDeduplicatedOnRefresh() = runBlocking {
        val repo = repo(); val store = PhotoHouseStore(repo, this)
        store.signIn(); settle()
        val gallery = Contract.body<Gallery>(case("gallery"))
        repo.override = "gallery" to case("gallery").copy(body = Contract.json.parseToJsonElement(Contract.json.encodeToString(Gallery.serializer(), gallery.copy(items = gallery.items + gallery.items))))
        store.selectLibrary("family-a"); settle(); assertEquals(2, store.state.value.gallery!!.items.size)
        store.loadGallery(); settle(); assertEquals(2, store.state.value.gallery!!.items.size)
    }
}
