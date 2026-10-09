package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ProtectedStoryStoreTest {
    private val asset = Asset("1", "image", 256, 256, null, null, "/assets/1/thumbnail?library=family")
    private inner class Api : PhotoHouseApi {
        override var protectedNativeV2Enabled = true
        override var assistantEnabled = false
        var dictationGate: CompletableDeferred<Unit>? = null
        var dictationError: Exception? = null
        var transcriptions = 0
        var turns = 0
        override suspend fun assistantCapabilities(token: Bearer, library: String) = AssistantCapabilities(true, true, true, false, 30)
        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray, requestId: String): AssistantTranscript {
            transcriptions++
            dictationGate?.let { withContext(NonCancellable) { it.await() } }
            dictationError?.let { throw it }
            return AssistantTranscript("那天我们一起种花。", "zh", AssistantRequestReceipt(requestId, "enabled", "succeeded"))
        }
        override suspend fun assistantTurn(token: Bearer, library: String, text: String, context: kotlinx.serialization.json.JsonObject?): AssistantTurn {
            turns++
            error("Dictation must never send a command")
        }
        var available = true
        var sessionDisplayName: String? = null
        var storyByline = "A family member"
        var sessionError: Exception? = null
        var storyError: Exception? = null
        var gate: CompletableDeferred<Unit>? = null
        val reads = mutableListOf<Int>()
        var wrongScope = false
        var canCreate = false
        var editEnabled = false
        var saveGate: CompletableDeferred<Unit>? = null
        var saveError: Exception? = null
        val savedMutations = mutableListOf<StoryMutation>()
        var savedStoryText = "server returned text"
        var currentStory: ProtectedStory? = null
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone,password)
        override suspend fun session(token: Bearer): Session {
            sessionError?.let { throw it }
            return Session("synthetic-account", "+12025550123", listOf(Membership("family", "approved", "viewer", 1, null, 0, available)), sessionDisplayName)
        }
        override suspend fun acceptInvitation(token: Bearer, code: String) {}
        override suspend fun logout(token: Bearer) {}
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library,page,50,1,false,listOf(asset))
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library,false,asset.copy(id=assetId))
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library,assetId,false,emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk = error("unused")
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray = error("unused")
        override suspend fun stories(token: Bearer, library: String, assetId: String, page: Int): ProtectedStoryPage {
            reads += page
            gate?.let { withContext(NonCancellable) { it.await() } }
            storyError?.let { throw it }
            val story = ProtectedStory("10000000-0000-0000-0000-000000000001",assetId,"Title","家人的原文 <b>literal</b>","mixed",storyByline,"synthetic-account",1,100,100,editEnabled,false)
            currentStory = story
            return ProtectedStoryPage(if(wrongScope) "foreign" else library, assetId, page, canCreate, page==1,
                if(page==1) listOf(story) else emptyList())
        }
        override suspend fun saveStory(token: Bearer, library: String, mutation: StoryMutation): ProtectedStory {
            saveGate?.let { withContext(NonCancellable) { it.await() } }
            saveError?.let { throw it }
            savedMutations += mutation
            return (currentStory ?: ProtectedStory("10000000-0000-0000-0000-000000000001", mutation.assetId, "Title", "", "mixed", "A family member", "synthetic-account", 1, 100, 100, true, false)).copy(
                assetId = mutation.assetId, revision = (mutation.revision ?: 1) + 1, text = savedStoryText)
        }
        override suspend fun currentStory(token: Bearer, library: String, assetId: String, storyId: String): ProtectedStory? = currentStory
    }
    private fun TestScope.open(api: Api): ConnectedStore {
        val store=ConnectedStore(api,backgroundScope) { testScheduler.currentTime }
        store.authenticate("+12025550123", "12345678"); runCurrent()
        store.selectLibrary("family");runCurrent();store.openAsset(asset);runCurrent()
        assertNotNull(store.state.value.detail)
        return store
    }
    @Test fun readsOnlyWhenRequestedAndReplacesPagesWithoutPersistingHistory()=runTest {
        val api=Api();val store=open(api);assertTrue(api.reads.isEmpty())
        store.loadStories();runCurrent();assertEquals("家人的原文 <b>literal</b>",store.state.value.stories!!.result!!.items.single().text)
        store.loadStories(2);runCurrent();assertTrue(store.state.value.stories!!.result!!.items.isEmpty())
        store.loadStories(1);runCurrent();assertEquals(listOf(1,2,1),api.reads)
        store.backToPhotos();runCurrent();assertNull(store.state.value.stories)
    }
    @Test fun disabledProfileNeverRequestsStories()=runTest {
        val api=Api().apply { protectedNativeV2Enabled=false }
        val store=ConnectedStore(api,backgroundScope)
        store.authenticate("+12025550123","long-enough-password");runCurrent()
        store.selectLibrary("family");runCurrent();store.openAsset(asset);runCurrent()
        store.loadStories();runCurrent();assertTrue(api.reads.isEmpty());assertNull(store.state.value.stories)
    }
    @Test fun backgroundNavigationAndLogoutRejectUncancellableLateText()=runTest {
        for(action in listOf("background","library","logout","photo")) {
            val api=Api();val store=open(api);api.gate=CompletableDeferred()
            store.loadStories();runCurrent();assertTrue(store.state.value.stories!!.busy)
            when(action) {"background"->store.background();"library"->store.libraries();"logout"->store.logout();else->store.openAsset(asset.copy(id="2"))}
            runCurrent();api.gate!!.complete(Unit);runCurrent();assertNull(store.state.value.stories)
        }
    }
    @Test fun revocationClearsTextMediaAndUnavailableMembershipCannotRead()=runTest {
        val api=Api();val store=open(api);store.loadStories();runCurrent()
        api.storyError=ApiFailure(FailureKind.HTTP,401);api.available=false
        store.loadStories(2);runCurrent()
        assertNull(store.state.value.stories);assertNull(store.state.value.detail);assertTrue(store.state.value.previews.isEmpty())
        store.loadStories();runCurrent();assertEquals(listOf(1,2),api.reads)
    }
    @Test fun expiredSessionAnd403AlsoClearStoryData()=runTest {
        for(status in listOf(401,403)) {
            val api=Api();val store=open(api);store.loadStories();runCurrent()
            api.storyError=ApiFailure(FailureKind.HTTP,status)
            if(status==401)api.sessionError=ApiFailure(FailureKind.HTTP,401)
            store.loadStories(2);runCurrent();assertNull(store.state.value.stories);assertNull(store.state.value.detail)
            if(status==401)assertNull(store.state.value.session)
        }
    }
    @Test fun recoverableStoryFailureKeepsPhotoAndRequiresExplicitRetry()=runTest {
        val api=Api();val store=open(api);api.storyError=ApiFailure(FailureKind.OFFLINE)
        store.loadStories();runCurrent();assertNotNull(store.state.value.detail)
        assertEquals(Message.NETWORK_UNAVAILABLE,store.state.value.stories!!.problem!!.message);assertEquals(listOf(1),api.reads)
        api.storyError=null;store.loadStories();runCurrent();assertNotNull(store.state.value.stories!!.result)
    }
    @Test fun cooldownSuppressesRepeatRequestsAndNoWrongScopeTextAppears()=runTest {
        val api=Api();val store=open(api);api.storyError=ApiFailure(FailureKind.HTTP,429,1000)
        store.loadStories();runCurrent();store.loadStories();runCurrent();assertEquals(1,api.reads.size)
        advanceTimeBy(1001);api.storyError=null;api.wrongScope=true
        store.loadStories();runCurrent();assertEquals(2,api.reads.size)
        assertNull(store.state.value.stories!!.result);assertEquals(Message.INVALID_RESPONSE,store.state.value.stories!!.problem!!.message)
    }
    @Test fun longLivedSessionExpiryClearsAlreadyReadStories()=runTest {
        val api=Api();val store=open(api);store.loadStories();runCurrent()
        advanceTimeBy(86400001);runCurrent();assertNull(store.state.value.stories);assertNull(store.state.value.session)
    }

    @Test fun viewerCannotCreateOrEditStories() = runTest {
        val api = Api(); val store = open(api)
        store.loadStories(); runCurrent()
        assertFalse(store.state.value.stories!!.result!!.canCreate)
        assertFalse(store.state.value.stories!!.result!!.items.single().canEdit)
        store.editStory(); assertNull(store.state.value.storyEditor)
    }

    @Test fun editorSavePublishesServerReturnedText() = runTest {
        val api = Api().apply { canCreate = true; editEnabled = true; savedStoryText = "server canonical text" }
        val store = open(api); store.loadStories(); runCurrent(); store.editStory()
        val editor = store.state.value.storyEditor!!
        editor.updateText("client draft")
        assertTrue(editor.beginReview()); editor.confirmSave(); runCurrent()
        assertEquals(StoryEditorPhase.SAVED, editor.state.value.phase)
        assertEquals("server canonical text", editor.state.value.latest!!.text)
        assertNull(store.state.value.stories)
        assertEquals("client draft", api.savedMutations.single().draft.text)
    }

    @Test fun creationPrefillsAuthorizedDisplayNameAndExistingBlankBylineStaysBlank() = runTest {
        val api = Api().apply { canCreate = true; editEnabled = true; sessionDisplayName = "Authorized Display" }
        val store = open(api)
        store.loadStories(); runCurrent(); store.editStory()
        val createEditor = store.state.value.storyEditor!!
        assertEquals("Authorized Display", createEditor.state.value.draft.byline)
        createEditor.updateByline("")
        createEditor.updateText("A new memory")
        assertTrue(createEditor.beginReview())
        createEditor.confirmSave(); runCurrent()
        assertEquals("", api.savedMutations.single().draft.byline)
        assertEquals("synthetic-account", createEditor.state.value.latest!!.authorId)

        store.closeStoryEditor(); runCurrent()
        api.storyByline = ""
        store.loadStories(); runCurrent(); store.editStory("10000000-0000-0000-0000-000000000001")
        assertEquals("", store.state.value.storyEditor!!.state.value.draft.byline)
    }

    @Test fun conflict409NeverOverwritesDraft() = runTest {
        val api = Api().apply { editEnabled = true; saveError = ApiFailure(FailureKind.HTTP, 409) }
        val store = open(api); store.loadStories(); runCurrent(); store.editStory("10000000-0000-0000-0000-000000000001")
        val editor = store.state.value.storyEditor!!
        editor.updateText("keep this draft")
        assertTrue(editor.beginReview()); editor.confirmSave(); runCurrent()
        assertEquals(StoryEditorPhase.CONFLICT, editor.state.value.phase)
        assertEquals("keep this draft", editor.state.value.mutation!!.draft.text)
        assertEquals("家人的原文 <b>literal</b>", store.state.value.stories!!.result!!.items.single().text)
    }

    @Test fun navigationCancelsEditorAndIgnoresLateSave() = runTest {
        for (action in listOf("background", "logout", "library", "asset")) {
            val gate = CompletableDeferred<Unit>()
            val api = Api().apply { editEnabled = true; saveGate = gate }
            val store = open(api); store.loadStories(); runCurrent(); store.editStory("10000000-0000-0000-0000-000000000001")
            val editor = store.state.value.storyEditor!!
            editor.updateText("draft that must not land")
            assertTrue(editor.beginReview()); editor.confirmSave(); runCurrent()
            when (action) {
                "background" -> store.background()
                "logout" -> store.logout()
                "library" -> store.libraries()
                else -> store.openAsset(asset.copy(id = "2"))
            }
            runCurrent(); gate.complete(Unit); runCurrent()
            assertEquals(StoryEditorPhase.CLOSED, editor.state.value.phase)
            assertNull(store.state.value.storyEditor)
            assertTrue(store.state.value.stories?.result?.items?.singleOrNull()?.text != "server returned text")
        }
    }

    private fun wav(): ByteArray = java.nio.ByteBuffer.allocate(32044).order(java.nio.ByteOrder.LITTLE_ENDIAN).apply {
        put("RIFF".toByteArray()); putInt(32036); put("WAVEfmt ".toByteArray()); putInt(16)
        putShort(1); putShort(1); putInt(16000); putInt(32000); putShort(2); putShort(16)
        put("data".toByteArray()); putInt(32000)
    }.array()

    @Test fun dictationIsReviewedAndAppendedWithoutExecutingOrSaving() = runTest {
        val api = Api().apply { canCreate = true; assistantEnabled = true }
        val store = open(api); store.loadStories(); runCurrent(); store.editStory()
        val editor = store.state.value.storyEditor!!
        val speech = editor.dictation!!
        editor.updateTitle("花园里的下午"); editor.updateText("原来写好的回忆。")
        speech.loadCapabilities(); runCurrent(); assertEquals(30, speech.beginRecording())
        speech.stopRecording(wav()); runCurrent()
        assertEquals("原来写好的回忆。", editor.state.value.draft.text)
        assertFalse(editor.beginReview())
        speech.updateTranscript("奶奶和我们一起种花。")
        assertTrue(editor.insertDictation())
        assertEquals("原来写好的回忆。\n\n奶奶和我们一起种花。", editor.state.value.draft.text)
        assertFalse(editor.insertDictation())
        assertNull(speech.state.value.transcript)
        assertTrue(editor.beginReview())
        assertEquals(1, api.transcriptions); assertEquals(0, api.turns)
        assertTrue(api.savedMutations.isEmpty())
        store.closeStoryEditor(); assertEquals(StoryEditorPhase.CLOSED, editor.state.value.phase)
    }

    @Test fun lateDictationCannotEnterAnotherEditorOrSurvivePrivacyCover() = runTest {
        for (action in listOf("close", "background", "logout", "library", "asset")) {
            val gate = CompletableDeferred<Unit>()
            val api = Api().apply { canCreate = true; assistantEnabled = true; dictationGate = gate }
            val store = open(api); store.loadStories(); runCurrent(); store.editStory()
            val old = store.state.value.storyEditor!!
            val speech = old.dictation!!
            speech.loadCapabilities(); runCurrent(); speech.beginRecording(); speech.stopRecording(wav()); runCurrent()
            when (action) {
                "close" -> { store.closeStoryEditor(); runCurrent(); store.editStory() }
                "background" -> store.background()
                "logout" -> store.logout()
                "library" -> store.libraries()
                else -> store.openAsset(asset.copy(id = "2"))
            }
            runCurrent(); gate.complete(Unit); runCurrent()
            assertEquals(StoryEditorPhase.CLOSED, old.state.value.phase)
            assertNull(speech.state.value.transcript)
            assertTrue(store.state.value.storyEditor?.state?.value?.draft?.text.isNullOrEmpty())
            assertEquals(0, api.turns); assertTrue(api.savedMutations.isEmpty())
        }
    }

    @Test fun dictationDenialClearsTheEditorAndItsTypedDraft() = runTest {
        val api = Api().apply { canCreate = true; assistantEnabled = true; dictationError = ApiFailure(FailureKind.HTTP, 403) }
        val store = open(api); store.loadStories(); runCurrent(); store.editStory()
        val editor = store.state.value.storyEditor!!
        editor.updateText("private draft")
        val speech = editor.dictation!!
        speech.loadCapabilities(); runCurrent(); speech.beginRecording(); speech.stopRecording(wav()); runCurrent()
        assertNull(store.state.value.storyEditor); assertTrue(store.state.value.covered)
        assertTrue(editor.state.value.draft.text.isEmpty()); assertNull(speech.state.value.transcript)
    }
}
