package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AssistantSceneWorkspaceStoreTest {
    private val token = Bearer.from(SessionToken(86400, "A".repeat(43), "Bearer"))
    private val tid = "11111111-1111-4111-8111-111111111111"
    private val rid = "22222222-2222-4222-8222-222222222222"
    private val query = "孩子 beside a blue bridge 放风筝"
    private fun scope(library: String = "family-a", generation: Long = 1) = AssistantWorkspaceScope("fictional", token, library, generation, true)
    private val caps = AssistantWorkspaceCapabilities(1, true, true, true, true, true, searchVersion = 3)
    private val filters = buildJsonObject {
        put("media", buildJsonArray { add("image") })
        put("people", buildJsonObject { put("ids", buildJsonArray { add("301") }); put("match", "any") })
        put("date", buildJsonObject { put("from", "2032-09-01"); put("to", "2032-09-30") })
    }
    private val original = buildJsonObject {
        put("library_id", "family-a"); put("binding", "a".repeat(64)); put("fingerprint", "b".repeat(64))
        put("filters", filters); put("visible_ids", JsonArray(emptyList())); put("total", 0); put("search_version", 3)
    }
    private fun thread(revision: Long) = AssistantWorkspaceThreadSummary(tid, "family-a", "2032-09-01T00:00:00Z", "2032-09-01T00:00:00Z", "2032-10-01T00:00:00Z", revision)
    private fun detail(revision: Long = 1, latest: String? = rid) = AssistantWorkspaceThreadDetail(1, thread(revision), emptyList(), latest)
    private fun ordinary(kind: String = "results") = AssistantTurn(kind, "Found", original, filters, emptyList(), 0, false, null,
        searchVersion = 3, searchInterpretation = AssistantSearchInterpretation("capture", listOf(AssistantSearchFacetSelection("301", "Sample Child")), emptyList(), emptyList(), null))
    private fun scene(text: String = query) = ordinary().copy(context = buildJsonObject {
        original.forEach { (key,value) -> put(key,value) };put("search_version", 4)
        put("scene", buildJsonObject { put("version",1);put("query",text);put("scope",original);put("scores", JsonArray(emptyList())) })
    }, searchVersion = 4, sceneRanking = AssistantSceneRanking(text, emptyMap(), 0))
    private fun turn(result: AssistantTurn, recovered: Boolean = true, revision: Long = if (result.searchVersion == 4) 2 else 1) =
        AssistantWorkspaceTurn(1, tid, rid, AssistantWorkspaceRequestStatus.COMPLETED, revision, recovered, null, result)
    private inner class Api : AssistantWorkspaceApi {
        override val assistantWorkspaceEnabled = true
        var savedText: String? = null
        var revision = 1L
        var sceneAvailable = true
        var gets = mutableListOf<Int>()
        var scenePosts = 0
        var normalPosts = 0
        var submitted: Triple<Long,String,String>? = null
        var reading: suspend (Int) -> AssistantWorkspaceTurn = { turn(ordinary()) }
        var posting: suspend () -> AssistantWorkspaceTurn = { revision = 2; turn(scene(), false) }
        override suspend fun capabilities(token: Bearer, library: String) = caps
        override suspend fun sceneSearchCapabilities(token: Bearer, library: String) = AssistantSceneSearchCapabilities(1, sceneAvailable)
        override suspend fun readThread(token: Bearer, library: String, threadId: String) = detail(revision).let { current ->
            savedText?.let { text -> current.copy(exchanges=listOf(AssistantWorkspaceExchange(tid, revision,
                "2032-09-01T00:00:00Z", "2032-10-01T00:00:00Z", text, "Saved reply", emptyList(), 0, rid))) } ?: current
        }
        override suspend fun getTurn(token: Bearer, library: String, threadId: String, requestId: String, searchVersion: Int): AssistantWorkspaceTurn {
            gets.add(searchVersion); return reading(searchVersion)
        }
        override suspend fun submitSceneTurn(token: Bearer, library: String, threadId: String, requestId: String, expectedRevision: Long, text: String): AssistantWorkspaceTurn {
            scenePosts++;submitted=Triple(expectedRevision,text,requestId);return posting()
        }
        override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String, expectedRevision: Long, text: String,
            parentRequestId: String?, acceptSavedMemoryCards: Boolean, memoryParent: AssistantSavedMemoryParent?, acceptSavedMemoryActions: Boolean, searchVersion: Int): AssistantWorkspaceTurn {
            normalPosts++;revision=expectedRevision+1;return turn(ordinary(),false,revision)
        }
    }
    @Test fun explicitSceneReservesExactScopeAndPreservesOrdinaryDraft() = runTest {
        val api=Api();val store=AssistantWorkspaceStore(api,backgroundScope,{scope()},{rid})
        store.refreshCapabilities();runCurrent();store.refreshSceneSearchCapabilities();runCurrent();store.openThread(tid);runCurrent()
        assertTrue(store.state.value.sceneReady);store.setDraft("unsent hard conditions");store.setSceneDraft(query)
        assertTrue(store.sendSceneTurn());assertTrue(store.state.value.pendingTurn!!.scene);assertNull(store.state.value.currentTurn);assertFalse(store.state.value.sceneReady)
        runCurrent();assertEquals(Triple(1L,query,rid),api.submitted);assertEquals(1,api.scenePosts);assertEquals(0,api.normalPosts)
        assertEquals("unsent hard conditions",store.state.value.draft);assertEquals("",store.state.value.sceneDraft);assertEquals(4,store.state.value.currentTurn!!.result!!.searchVersion)
        assertTrue(store.state.value.sceneReady)
    }
    @Test fun lostSceneKeepsV4AcrossCapabilityLossAndOnlyRecoversWithGet() = runTest {
        val api=Api();val store=AssistantWorkspaceStore(api,backgroundScope,{scope()},{rid})
        store.refreshCapabilities();runCurrent();store.refreshSceneSearchCapabilities();runCurrent();store.openThread(tid);runCurrent()
        api.posting={throw ApiFailure(FailureKind.OFFLINE)};api.reading={throw ApiFailure(FailureKind.OFFLINE)}
        store.setSceneDraft(query);store.sendSceneTurn();runCurrent();assertEquals(4,store.state.value.pendingTurn!!.searchVersion)
        api.sceneAvailable=false;store.refreshCapabilities();runCurrent();store.refreshSceneSearchCapabilities();runCurrent()
        api.revision=2;api.reading={turn(scene())};store.recoverPendingTurn();runCurrent()
        assertEquals(4,api.gets.last());assertEquals(1,api.scenePosts);assertNull(store.state.value.pendingTurn);assertEquals(4,store.state.value.currentTurn!!.result!!.searchVersion)
    }
    @Test fun newOrdinaryDraftAndEditedSceneDraftSurviveRecovery() = runTest {
        val api=Api();val store=AssistantWorkspaceStore(api,backgroundScope,{scope()},{rid})
        store.refreshCapabilities();runCurrent();store.refreshSceneSearchCapabilities();runCurrent();store.openThread(tid);runCurrent()
        api.posting={throw ApiFailure(FailureKind.OFFLINE)};api.reading={throw ApiFailure(FailureKind.OFFLINE)}
        store.setDraft("ordinary");store.setSceneDraft(query);store.sendSceneTurn();runCurrent();store.setSceneDraft("new scene")
        api.revision=2;api.reading={turn(scene())};store.recoverPendingTurn();runCurrent()
        assertEquals("ordinary",store.state.value.draft);assertEquals("new scene",store.state.value.sceneDraft)
    }
    @Test fun unresolvedAndUnsupportedScopeNeverSubmitsScene() = runTest {
        for (result in listOf(ordinary("clarification"),ordinary("open"),ordinary().copy(searchVersion=1),
            ordinary().copy(filters=buildJsonObject { put("media",buildJsonArray { add("video") }) }),
            ordinary().copy(filters=buildJsonObject { put("descriptive",buildJsonObject {}) }))) {
            val api=Api();api.reading={turn(result)};val store=AssistantWorkspaceStore(api,backgroundScope,{scope()},{rid})
            store.refreshCapabilities();runCurrent();store.refreshSceneSearchCapabilities();runCurrent();store.openThread(tid);runCurrent();store.setSceneDraft(query)
            assertFalse(store.state.value.sceneReady);assertFalse(store.sendSceneTurn());assertEquals(0,api.scenePosts);store.close()
        }
    }
    @Test fun malformedSceneInputDoesNotAllocateRequestOrSend() = runTest {
        var allocations=0;val api=Api();val store=AssistantWorkspaceStore(api,backgroundScope,{scope()},{allocations++;rid})
        store.refreshCapabilities();runCurrent();store.refreshSceneSearchCapabilities();runCurrent();store.openThread(tid);runCurrent()
        for(text in listOf("", "a\nb", "a\tb", "中".repeat(171), "\uD800")) {store.setSceneDraft(text);assertFalse(store.sendSceneTurn())}
        assertEquals(0,allocations);assertEquals(0,api.scenePosts)
    }
    @Test fun definitiveRefusalDoesNotStrandUnacceptedRequest() = runTest {
        for(status in listOf(400,409)) {
            val api=Api();val store=AssistantWorkspaceStore(api,backgroundScope,{scope()},{rid})
            store.refreshCapabilities();runCurrent();store.refreshSceneSearchCapabilities();runCurrent();store.openThread(tid);runCurrent()
            val before=api.gets.size;api.posting={throw ApiFailure(FailureKind.HTTP,status)};store.setSceneDraft(query);store.sendSceneTurn();runCurrent()
            assertNull(store.state.value.pendingTurn);assertFalse(store.state.value.uncertain);assertNull(store.state.value.currentTurn)
            assertEquals(query,store.state.value.sceneDraft);assertTrue(store.state.value.historyRefreshRequired);assertEquals(before,api.gets.size)
            store.openThread(tid);runCurrent();store.setDraft("find photos");assertTrue(store.sendTurn());runCurrent();assertEquals(1,api.normalPosts);store.close()
        }
    }
    @Test fun reopenV4AndFailedSourceReadNeverLeaveOldCardsOrPendingMarker() = runTest {
        val api=Api();api.revision=2;api.reading={turn(scene())};val store=AssistantWorkspaceStore(api,backgroundScope,{scope()},{rid})
        store.refreshCapabilities();runCurrent();store.refreshSceneSearchCapabilities();runCurrent();store.openThread(tid);runCurrent()
        assertEquals(4,api.gets.last());assertEquals(4,store.state.value.currentTurn!!.result!!.searchVersion)
        api.reading={throw ApiFailure(FailureKind.HTTP,503)};store.openThread(tid);runCurrent()
        assertNull(store.state.value.currentTurn);assertNull(store.state.value.pendingTurn);assertFalse(store.state.value.uncertain);assertFalse(store.state.value.sceneReady)
    }
    @Test fun lateCompletionAfterLibraryChangeCannotRestorePrivateContent() = runTest {
        var current=scope();val gate=CompletableDeferred<AssistantWorkspaceTurn>();val api=Api()
        api.posting={withContext(NonCancellable){gate.await()}}
        val store=AssistantWorkspaceStore(api,backgroundScope,{current},{rid})
        store.refreshCapabilities();runCurrent();store.refreshSceneSearchCapabilities();runCurrent();store.openThread(tid);runCurrent()
        store.setDraft("private ordinary");store.setSceneDraft(query);store.sendSceneTurn();runCurrent()
        current=scope("other",2);store.onScopeChanged();gate.complete(turn(scene(),false));runCurrent()
        assertNull(store.state.value.currentTurn);assertEquals("",store.state.value.sceneDraft);assertEquals("",store.state.value.draft);assertFalse(store.state.value.sceneSearchAvailable)
    }
    @Test fun changedQueryScopeOrRevisionCannotBeAcceptedAsFreshSceneResult() = runTest {
        for (variant in 0..2) {
            val api=Api();val store=AssistantWorkspaceStore(api,backgroundScope,{scope()},{rid})
            store.refreshCapabilities();runCurrent();store.refreshSceneSearchCapabilities();runCurrent();store.openThread(tid);runCurrent()
            api.posting={val result=if(variant==0)scene("different") else scene();val modified=if(variant==1)result.copy(context=buildJsonObject {
                result.context!!.forEach{(k,v)->put(k,v)};put("scene",buildJsonObject{put("scope",JsonObject(emptyMap()))})
            }) else result;turn(modified,false,if(variant==2)9 else 2)}
            store.setSceneDraft(query);store.sendSceneTurn();runCurrent();assertNull(store.state.value.currentTurn)
            assertEquals(AssistantWorkspaceError.INVALID_RESPONSE,store.state.value.error);assertNotNull(store.state.value.pendingTurn);store.close()
        }
    }
    @Test fun savedSceneQueryMustMatchKnownOriginalHistoryText() = runTest {
        val api=Api();api.revision=2;api.savedText=query;api.reading={turn(scene("different query"))}
        val store=AssistantWorkspaceStore(api,backgroundScope,{scope()},{rid})
        store.refreshCapabilities();runCurrent();store.refreshSceneSearchCapabilities();runCurrent();store.openThread(tid);runCurrent()
        assertNull(store.state.value.currentTurn);assertEquals(AssistantWorkspaceError.INVALID_RESPONSE,store.state.value.error)
    }
    @Test fun unavailableFeatureDoesNotBlindlyNegotiateV4OnOlderServerHistory() = runTest {
        val api=Api();api.sceneAvailable=false;api.revision=2;api.reading={throw ApiFailure(FailureKind.HTTP,409)}
        val store=AssistantWorkspaceStore(api,backgroundScope,{scope()},{rid})
        store.refreshCapabilities();runCurrent();store.refreshSceneSearchCapabilities();runCurrent();store.openThread(tid);runCurrent()
        assertEquals(3,api.gets.last());assertNull(store.state.value.currentTurn);assertNull(store.state.value.pendingTurn)
        assertTrue(store.state.value.continuationEnabled)
    }
    @Test fun absentSceneCapabilityLeavesOrdinarySearchUsable() = runTest {
        val api=Api();api.sceneAvailable=false;val store=AssistantWorkspaceStore(api,backgroundScope,{scope()},{rid})
        store.refreshCapabilities();runCurrent();store.refreshSceneSearchCapabilities();runCurrent();store.openThread(tid);runCurrent();store.setSceneDraft(query)
        assertFalse(store.sendSceneTurn());store.setDraft("find photos");assertTrue(store.sendTurn());runCurrent();assertEquals(1,api.normalPosts)
    }
}
