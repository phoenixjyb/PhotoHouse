package dev.photohouse.home

import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import org.junit.Test
import org.junit.Assert.*

@OptIn(ExperimentalCoroutinesApi::class)
class DiscoveryControllerTest {
    private val options = DiscoveryOptions(setOf(DiscoveryField.PEOPLE), people = listOf(DiscoveryChoice("1", "Sample person")))
    private val snapshot = DiscoverySnapshot(7, 1, "synthetic", "Synthetic", options)
    private class Api(private val fail: HomeError? = null) : HomeApi {
        override val catalogVersion = 2
        override val retryRevisionChanges = false
        var reads = 0
        override suspend fun feed(page: Int): HomeFeed {
            reads++; fail?.let { throw HomeFailure(it) }
            return HomeFeed(1, "synthetic", "Synthetic", page, 50, 0, false, emptyList(), 2)
        }
        override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray? = error("Unexpected media")
    }
    @Test fun explicitApplyCreatesIsolatedResultsAndClearRevalidatesBrowse() = runTest {
        val base = Api(); val browse = HomeStore(base, backgroundScope); browse.foreground(); runCurrent()
        val queries = mutableListOf<DiscoveryDraft>()
        val controller = DiscoveryController(object : DiscoveryGateway {
            override suspend fun load() = snapshot
            override suspend fun more(snapshot: DiscoverySnapshot, field: DiscoveryField) = snapshot
            override fun results(snapshot: DiscoverySnapshot, draft: DiscoveryDraft): HomeApi { queries += draft; return Api() }
        }, browse, backgroundScope)
        controller.open(); runCurrent(); assertTrue(queries.isEmpty())
        controller.search(DiscoveryDraft(people = setOf("1"))); runCurrent()
        assertEquals(1, queries.size); assertNotNull(controller.state.value.results?.state?.value?.feed)
        val old = controller.state.value.results!!
        controller.clearResults(); runCurrent(); assertNull(controller.state.value.results)
        assertTrue(old.state.value.covered); assertEquals(2, base.reads)
    }
    @Test fun staleMetadataAfterBackgroundCannotRestorePeopleOrSearch() = runTest {
        val browse = HomeStore(Api(), backgroundScope)
        val controller = DiscoveryController(object : DiscoveryGateway {
            override suspend fun load(): DiscoverySnapshot { withContext(NonCancellable) { delay(100) }; return snapshot }
            override suspend fun more(snapshot: DiscoverySnapshot, field: DiscoveryField) = snapshot
            override fun results(snapshot: DiscoverySnapshot, draft: DiscoveryDraft): HomeApi = error("No search")
        }, browse, backgroundScope)
        controller.open(); runCurrent(); controller.background(); advanceTimeBy(101); runCurrent()
        assertEquals(DiscoveryState(), controller.state.value)
        controller.search(DiscoveryDraft(people = setOf("1"))); assertNull(controller.state.value.results)
    }
    @Test fun unknownSelectionDoesNotReachGatewayAndDenialClearsBothStores() = runTest {
        val browse = HomeStore(Api(), backgroundScope); browse.foreground(); runCurrent()
        var queries = 0
        val controller = DiscoveryController(object : DiscoveryGateway {
            override suspend fun load() = snapshot
            override suspend fun more(snapshot: DiscoverySnapshot, field: DiscoveryField) = snapshot
            override fun results(snapshot: DiscoverySnapshot, draft: DiscoveryDraft): HomeApi { queries++; return Api(HomeError.DENIED) }
        }, browse, backgroundScope)
        controller.open(); runCurrent(); controller.search(DiscoveryDraft(people = setOf("not-an-id")))
        assertEquals(0, queries)
        controller.search(DiscoveryDraft(people = setOf("1"))); runCurrent()
        assertEquals(HomeError.DENIED, controller.state.value.results!!.state.value.problem)
        controller.invalidateResults(HomeError.DENIED)
        assertNull(controller.state.value.snapshot); assertNull(controller.state.value.query)
        assertNull(browse.state.value.feed); assertEquals(HomeError.DENIED, browse.state.value.problem)
    }
    @Test fun changedSearchSnapshotDoesNotAutomaticallyRetryOldRevision() = runTest {
        val api = Api(HomeError.CHANGED); val result = HomeStore(api, backgroundScope, jitter = { 0.0 })
        result.foreground(); runCurrent(); advanceTimeBy(61000); runCurrent()
        assertEquals(1, api.reads); assertNull(result.state.value.feed); assertEquals(HomeError.CHANGED, result.state.value.problem)
    }
    @Test fun retryAfterSurvivesEditorCloseAndBackground() = runTest {
        val browse = HomeStore(Api(), backgroundScope); var calls = 0
        val controller = DiscoveryController(object : DiscoveryGateway {
            override suspend fun load(): DiscoverySnapshot { calls++; throw HomeFailure(HomeError.BUSY, 5000) }
            override suspend fun more(snapshot: DiscoverySnapshot, field: DiscoveryField) = snapshot
            override fun results(snapshot: DiscoverySnapshot, draft: DiscoveryDraft): HomeApi = error("No search")
        }, browse, backgroundScope, now = { testScheduler.currentTime })
        controller.open(); runCurrent(); controller.background(); controller.open(); runCurrent()
        assertEquals(1, calls); assertEquals(HomeError.BUSY, controller.state.value.problem)
        advanceTimeBy(5000); controller.open(); runCurrent(); assertEquals(2, calls)
    }
    @Test fun editRetainsLaterFacetPagesOnlyWhileVerifiedBindingMatches() = runTest {
        val browse = HomeStore(Api(), backgroundScope); var binding = "a".repeat(64)
        val first = snapshot.copy(binding = binding, nextPages = mapOf(DiscoveryField.PEOPLE to 2),
            facetTotals = mapOf(DiscoveryField.PEOPLE to 2), facetLastIds = mapOf(DiscoveryField.PEOPLE to 1))
        val gateway = object : DiscoveryGateway {
            override suspend fun load() = first.copy(binding = binding)
            override suspend fun more(snapshot: DiscoverySnapshot, field: DiscoveryField) = snapshot.copy(
                options = options.copy(people = options.people + DiscoveryChoice("2", "Later sample")),
                nextPages = emptyMap(), facetLastIds = mapOf(DiscoveryField.PEOPLE to 2))
            override fun results(snapshot: DiscoverySnapshot, draft: DiscoveryDraft) = Api()
        }
        val controller = DiscoveryController(gateway, browse, backgroundScope)
        controller.open(); runCurrent(); controller.more(DiscoveryField.PEOPLE); runCurrent()
        val query = DiscoveryDraft(people = setOf("2"))
        controller.search(query); runCurrent(); controller.open(); runCurrent()
        assertNull(query.issue(controller.state.value.snapshot!!.options))
        assertTrue(controller.state.value.snapshot!!.nextPages.isEmpty())
        binding = "b".repeat(64); controller.open(); runCurrent()
        assertEquals(DraftIssue.UNKNOWN_CHOICE, query.issue(controller.state.value.snapshot!!.options))
    }
    @Test fun lateTagQueryAfterBackgroundCannotRestoreLabels() = runTest {
        val browse=HomeStore(Api(),backgroundScope)
        val controller=DiscoveryController(object:DiscoveryGateway {
            override suspend fun load()=snapshot.copy(tagQuery="")
            override suspend fun more(snapshot:DiscoverySnapshot,field:DiscoveryField)=snapshot
            override suspend fun findTags(snapshot:DiscoverySnapshot,query:String,selected:Set<String>):DiscoverySnapshot {
                withContext(NonCancellable) { delay(100) }
                return snapshot.copy(tagQuery=query)
            }
            override fun results(snapshot:DiscoverySnapshot,draft:DiscoveryDraft):HomeApi=error("No search")
        },browse,backgroundScope)
        controller.open();runCurrent();controller.findTags("湖",emptySet());runCurrent()
        controller.background();advanceTimeBy(101);runCurrent()
        assertEquals(DiscoveryState(),controller.state.value)
    }

    @Test fun lateCalendarAfterBackgroundCannotRestoreCovers() = runTest {
        val browse=HomeStore(Api(),backgroundScope)
        val controller=DiscoveryController(object:DiscoveryGateway {
            override val calendarEnabled=true
            override suspend fun load()=snapshot
            override suspend fun more(snapshot:DiscoverySnapshot,field:DiscoveryField)=snapshot
            override suspend fun calendar(snapshot:DiscoverySnapshot,request:CalendarRequest):CalendarPage {
                withContext(NonCancellable) {delay(100)}
                return CalendarPage(request,0,false,0,0,emptyList())
            }
            override fun calendarCovers(snapshot:DiscoverySnapshot,page:CalendarPage):HomeApi=error("No late cover store")
            override fun results(snapshot:DiscoverySnapshot,draft:DiscoveryDraft):HomeApi=error("No search")
        },browse,backgroundScope)
        controller.open();runCurrent();controller.calendar();runCurrent();controller.background()
        advanceTimeBy(101);runCurrent();assertEquals(DiscoveryState(),controller.state.value)
    }
    @Test fun calendarCoverDenialClearsMetadataAndBrowse() = runTest {
        val browse=HomeStore(Api(),backgroundScope);browse.foreground();runCurrent()
        val controller=DiscoveryController(object:DiscoveryGateway {
            override val calendarEnabled=true
            override suspend fun load()=snapshot
            override suspend fun more(snapshot:DiscoverySnapshot,field:DiscoveryField)=snapshot
            override suspend fun calendar(snapshot:DiscoverySnapshot,request:CalendarRequest)=CalendarPage(request,0,false,0,0,emptyList())
            override fun calendarCovers(snapshot:DiscoverySnapshot,page:CalendarPage)=Api(HomeError.DENIED)
            override fun results(snapshot:DiscoverySnapshot,draft:DiscoveryDraft):HomeApi=error("No search")
        },browse,backgroundScope)
        controller.open();runCurrent();controller.calendar();runCurrent()
        assertNull(controller.state.value.snapshot);assertEquals(HomeError.DENIED,controller.state.value.problem)
        assertNull(browse.state.value.feed)
    }

}
