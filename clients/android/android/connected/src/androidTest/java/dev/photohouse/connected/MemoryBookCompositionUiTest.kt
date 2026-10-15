package dev.photohouse.connected

import android.graphics.Bitmap
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.SoftwareKeyboardController
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.serialization.json.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Generated protected-library journeys for explicit memoir composition and exact save retry. */
@RunWith(AndroidJUnit4::class)
class MemoryBookCompositionUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    @After fun close() { scope.cancel() }

    @Test fun englishOwnerReviewsRetriesAndOpensCreatedMemoirAt150Percent() = journey(zh = false)
    @Test fun chineseOwnerReviewsRetriesAndOpensCreatedMemoirAt150Percent() = journey(zh = true)
    @Test fun englishVoiceIntroductionRequiresReviewAndKeepsBothTextsAt150Percent() = voiceIntroductionJourney(zh = false)
    @Test fun chineseVoiceIntroductionRequiresReviewAndKeepsBothTextsAt150Percent() = voiceIntroductionJourney(zh = true)

    @Test fun englishOwnerEditsSameMemoirAndRetriesCommittedSaveAt150Percent() = editJourney(zh = false)
    @Test fun chineseOwnerEditsSameMemoirAndRetriesCommittedSaveAt150Percent() = editJourney(zh = true)

    private fun editJourney(zh: Boolean) {
        val api = CompositionApi(editExisting = true)
        val store = ConnectedStore(api, scope, memoryCommunityApi = api, memoryCommunityEnabled = true)
        var keyboardController: SoftwareKeyboardController? = null
        rule.setContent {
            val density = LocalDensity.current
            val keyboard = LocalSoftwareKeyboardController.current
            SideEffect { keyboardController = keyboard }
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = if (zh) "zh" else "en")
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5_000) { store.state.value.library == GeneratedMemoirReaderApi.LIBRARY }
        rule.runOnIdle { store.openMemoryBooks() }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.result?.items?.isNotEmpty() == true }
        rule.runOnIdle { store.openMemoryBook(GeneratedMemoirReaderApi.BOOK) }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.selectedBook != null }
        val originalNavigation = checkNotNull(store.captureMemoryBookReaderNavigation())
        val detachedEdit = captureClick("memory-book-edit")
        rule.onNodeWithTag("memory-book-edit").performScrollTo().performClick()
        awaitCompositionState(store) { it.status == MemoryBookCompositionStatus.READY && !it.busy }
        assertEquals(GeneratedMemoirReaderApi.BOOK, store.memoryBookCompositionState.value.editingBookId)
        assertEquals(2L, store.memoryBookCompositionState.value.editingBookRevision)
        assertTrue(store.memoryBookCompositionState.value.canEdit)
        assertFalse("edit is allowed without create authority", store.memoryBookCompositionState.value.canCreate)
        rule.onNodeWithTag("memory-book-compose-title").assertTextContains("Earlier memoir")
        rule.onNodeWithTag("memory-book-compose-save").performScrollTo().assertIsNotEnabled()
        rule.runOnIdle {
            assertFalse(store.loadMemoryBookStory(originalNavigation, 0))
            assertFalse(store.startSavedMemoryBookEdit(originalNavigation))
        }
        // An untouched edit closes immediately. Its detached entry cannot reopen the editor.
        rule.onNodeWithTag("memory-book-compose-close").performScrollTo().performClick()
        awaitCompositionState(store) { it.status == MemoryBookCompositionStatus.CLOSED }
        rule.runOnIdle { assertTrue(detachedEdit()) }
        assertEquals(MemoryBookCompositionStatus.CLOSED, store.memoryBookCompositionState.value.status)
        rule.onNodeWithTag("memory-book-edit").performScrollTo().performClick()
        awaitCompositionState(store) { it.status == MemoryBookCompositionStatus.READY && !it.busy }
        rule.onNodeWithTag("memory-book-compose-remove-${GeneratedMemoirReaderApi.FIRST}").performScrollTo().performClick()
        awaitCompositionState(store) { it.selectedStories.size == 1 }
        rule.onNodeWithTag("memory-book-compose-story-${GeneratedMemoirReaderApi.FIRST}").performScrollTo().performClick()
        awaitCompositionState(store) { it.selectedStories.map { entry -> entry.summary.id } ==
            listOf(GeneratedMemoirReaderApi.SECOND, GeneratedMemoirReaderApi.FIRST) }
        // Reorder twice: restore original, then keep the reviewed new order.
        rule.onNodeWithTag("memory-book-compose-up-${GeneratedMemoirReaderApi.FIRST}").performScrollTo().performClick()
        awaitCompositionState(store) { it.selectedStories.first().summary.id == GeneratedMemoirReaderApi.FIRST }
        rule.onNodeWithTag("memory-book-compose-up-${GeneratedMemoirReaderApi.SECOND}").performScrollTo().performClick()
        awaitCompositionState(store) { it.selectedStories.first().summary.id == GeneratedMemoirReaderApi.SECOND }
        val title = if (zh) "家人的花园回忆" else "Our garden memories"
        val intro = if (zh) "回家的路与花园的一天，按家人的讲述来读。" else "Read the way home and our garden day through the family’s words."
        rule.onNodeWithTag("memory-book-compose-title").performScrollTo().performTextReplacement(title)
        rule.onNodeWithTag("memory-book-compose-intro-toggle").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-compose-intro").performScrollTo().performTextReplacement(intro)
        awaitCompositionState(store) { it.title == title && it.introduction == intro }
        rule.runOnIdle { keyboardController?.hide() }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-compose-selected-${GeneratedMemoirReaderApi.SECOND}").performScrollTo()
        captureComposer(if (zh) "edit-zh" else "edit-en")
        api.failNextSave = true
        rule.onNodeWithTag("memory-book-compose-save").performScrollTo().performClick()
        awaitCompositionState(store) { it.status == MemoryBookCompositionStatus.RETRY_REQUIRED && !it.busy }
        val parentReadsBeforeRetry = api.getBookIds.size
        rule.onNodeWithTag("memory-book-compose-retry").performScrollTo().performClick()
        awaitCompositionState(store) { it.status == MemoryBookCompositionStatus.SAVED && !it.busy }
        assertEquals(2, api.savedRequests.size)
        assertEquals(listOf(GeneratedMemoirReaderApi.BOOK, GeneratedMemoirReaderApi.BOOK), api.savedRequests.map { it.bookId })
        assertEquals(api.savedRequests[0].body, api.savedRequests[1].body)
        assertEquals("retry must not read the superseded parent revision", parentReadsBeforeRetry, api.getBookIds.size)
        assertEquals("3", api.savedRevision())
        if (zh) rule.onNodeWithTag("memory-book-compose-close").performScrollTo().performClick()
        else rule.onNodeWithTag("memory-book-compose-open-saved").performScrollTo().performClick()
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.selectedBook?.revision == 3L }
        val saved = checkNotNull(store.state.value.memoryBooks?.selectedBook)
        assertEquals(GeneratedMemoirReaderApi.BOOK, saved.id)
        assertEquals(title, saved.title)
        assertEquals(intro, saved.introduction)
        assertEquals(listOf(GeneratedMemoirReaderApi.SECOND, GeneratedMemoirReaderApi.FIRST), saved.stories.map { it.id })
        rule.onNodeWithText(intro).performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("memory-books-back").performClick()
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.selectedBook == null }
        assertEquals(1, store.state.value.memoryBooks?.result?.items?.size)
        assertEquals(3L, store.state.value.memoryBooks?.result?.items?.single()?.revision)
        assertEquals(0, api.childWriteCalls)
        assertEquals(0, api.queueNarrativeCalls)
        assertEquals(0, api.transcriptionCalls)
    }

    private fun journey(zh: Boolean) {
        val api = CompositionApi()
        val store = ConnectedStore(api, scope, memoryCommunityApi = api, memoryCommunityEnabled = true)
        var keyboardController: SoftwareKeyboardController? = null
        rule.setContent {
            val density = LocalDensity.current
            val keyboard = LocalSoftwareKeyboardController.current
            SideEffect { keyboardController = keyboard }
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = if (zh) "zh" else "en")
            }
        }

        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5_000) { store.state.value.library == GeneratedMemoirReaderApi.LIBRARY }
        rule.runOnIdle { store.openMemoryBooks() }
        rule.waitUntil(5_000) {
            val shelf = store.state.value.memoryBooks
            shelf != null && !shelf.busy && shelf.result?.canCreate == true
        }
        // Loading candidates is not an uncertain save. Closing an untouched loading
        // composer must be immediate, and a late candidate response must stay inert.
        val initialGate = CompletableDeferred<Unit>()
        api.candidateGate = initialGate
        rule.onNodeWithTag("memory-books-create").performClick()
        rule.waitUntil(5_000) { api.candidateRequests == 1 && store.memoryBookCompositionState.value.busy }
        rule.onNodeWithTag("memory-book-compose-close").performScrollTo().performClick()
        rule.waitUntil(5_000) { store.memoryBookCompositionState.value.status == MemoryBookCompositionStatus.CLOSED }
        rule.onNodeWithTag("memory-book-compose-exit-dialog").assertDoesNotExist()
        rule.onNodeWithTag("memory-book-discard-dialog").assertDoesNotExist()
        api.candidateGate = null
        initialGate.complete(Unit)
        rule.waitForIdle()
        assertEquals(MemoryBookCompositionStatus.CLOSED, store.memoryBookCompositionState.value.status)
        assertTrue(api.savedRequests.isEmpty())
        val oldCreate = captureClick("memory-books-create")
        rule.onNodeWithTag("memory-books-create").performClick()
        rule.waitUntil(5_000) {
            val state = store.memoryBookCompositionState.value
            state.status == MemoryBookCompositionStatus.READY && !state.busy && state.candidatePage != null
        }

        // Closing an untouched composer keeps the same shelf scope. Its former Create
        // control must still be inert; account/shelf checks alone cannot establish this.
        val untouchedShelfScope = store.state.value.memoryBooks?.shelfScopeId
        rule.onNodeWithTag("memory-book-compose-close").performScrollTo().performClick()
        rule.waitUntil(5_000) { store.memoryBookCompositionState.value.status == MemoryBookCompositionStatus.CLOSED }
        val requestsBeforeDetachedCreate = api.bookListPages.size
        rule.runOnIdle { assertTrue(oldCreate()) }
        rule.waitForIdle()
        assertEquals(MemoryBookCompositionStatus.CLOSED, store.memoryBookCompositionState.value.status)
        assertEquals(untouchedShelfScope, store.state.value.memoryBooks?.shelfScopeId)
        assertEquals(requestsBeforeDetachedCreate, api.bookListPages.size)
        rule.onNodeWithTag("memory-books-create").performClick()
        rule.waitUntil(5_000) {
            val state = store.memoryBookCompositionState.value
            state.status == MemoryBookCompositionStatus.READY && !state.busy && state.candidatePage != null
        }
        val initialEpoch = store.memoryBookCompositionState.value.actionEpoch
        val defaultTitle = if (zh) "我们的家庭回忆" else "Our family memories"
        rule.onNodeWithTag("memory-book-compose-title").assertTextContains(defaultTitle)
        val expectedFirst = "Garden day / 花园的一天"
        val expectedSecond = "The way home / 回家的路"

        rule.onNodeWithTag("memory-book-compose-story-${GeneratedMemoirReaderApi.FIRST}")
            .performScrollTo().performClick()
        awaitComposition(store) { it.selectedStories.map { selection -> selection.summary.id } == listOf(GeneratedMemoirReaderApi.FIRST) }
        rule.onNodeWithTag("memory-book-compose-story-${GeneratedMemoirReaderApi.SECOND}")
            .performScrollTo().performClick()
        awaitComposition(store) {
            it.selectedStories.map { selection -> selection.summary.id } ==
                listOf(GeneratedMemoirReaderApi.FIRST, GeneratedMemoirReaderApi.SECOND)
        }
        assertEquals(expectedFirst, store.memoryBookCompositionState.value.selectedStories[0].summary.title)
        assertEquals(expectedSecond, store.memoryBookCompositionState.value.selectedStories[1].summary.title)
        assertEquals(listOf(3L, 5L), store.memoryBookCompositionState.value.selectedStories.map { it.summary.revision })
        assertEquals(listOf(12, 12), store.memoryBookCompositionState.value.selectedStories.map { it.summary.itemCount })
        assertEquals(listOf("everyday", "everyday"), store.memoryBookCompositionState.value.selectedStories.map { it.summary.theme })

        rule.onNodeWithTag("memory-book-compose-up-${GeneratedMemoirReaderApi.SECOND}")
            .performScrollTo().performClick()
        awaitComposition(store) {
            it.selectedStories.map { selection -> selection.summary.id } ==
                listOf(GeneratedMemoirReaderApi.SECOND, GeneratedMemoirReaderApi.FIRST)
        }

        rule.onNodeWithTag("memory-book-compose-intro-toggle").performScrollTo().performClick()
        val introduction = if (zh) "这一册按家人的分享来阅读。" else "Read these memories through the family’s own stories."
        rule.onNodeWithTag("memory-book-compose-intro").performScrollTo().performTextReplacement(introduction)
        rule.waitUntil(5_000) { store.memoryBookCompositionState.value.introduction == introduction }
        rule.runOnIdle { keyboardController?.hide() }
        rule.waitForIdle()

        val oldSave = captureClick("memory-book-compose-save")
        val oldReorder = captureClick("memory-book-compose-up-${GeneratedMemoirReaderApi.FIRST}")
        val oldClose = captureClick("memory-book-compose-close")
        rule.onNodeWithTag("memory-book-compose-selected-${GeneratedMemoirReaderApi.SECOND}").performScrollTo()
        captureComposer(if (zh) "zh" else "en")

        api.failNextSave = true
        rule.onNodeWithTag("memory-book-compose-save").performScrollTo().performClick()
        rule.waitUntil(5_000) {
            val state = store.memoryBookCompositionState.value
            !state.busy && state.pendingRetry && state.status == MemoryBookCompositionStatus.RETRY_REQUIRED
        }
        assertEquals("one create attempt reached the API", 1, api.savedRequests.size)
        val frozenRequest = api.savedRequests.single()
        assertNull("this is a create, not an update", frozenRequest.bookId)
        val frozen = Json.parseToJsonElement(frozenRequest.body).jsonObject
        assertEquals(defaultTitle, frozen.getValue("title").jsonPrimitive.content)
        assertEquals(introduction, frozen.getValue("introduction").jsonPrimitive.content)
        assertEquals(if (zh) "zh" else "en", frozen.getValue("language").jsonPrimitive.content)
        assertEquals(listOf(GeneratedMemoirReaderApi.SECOND, GeneratedMemoirReaderApi.FIRST),
            frozen.getValue("story_ids").jsonPrimitive.content.split(','))
        val frozenMutationId = frozen.getValue("mutation_id").jsonPrimitive.content
        val frozenDraftRevision = store.memoryBookCompositionState.value.draftRevision
        rule.onNodeWithTag("memory-book-compose-title").assertIsNotEnabled()
        rule.onNodeWithTag("memory-book-compose-intro").assertIsNotEnabled()
        rule.onNodeWithTag("memory-book-compose-save").assertIsNotEnabled()
        rule.onNodeWithTag("memory-book-compose-up-${GeneratedMemoirReaderApi.FIRST}").assertIsNotEnabled()

        // Closing with an uncertain result presents an explicit choice. Stay preserves the exact draft.
        rule.onNodeWithTag("memory-book-compose-close").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-compose-exit-dialog").assertIsDisplayed()
        rule.onNodeWithTag("memory-book-compose-exit-stay").performClick()
        rule.waitUntil(5_000) {
            val state = store.memoryBookCompositionState.value
            state.status == MemoryBookCompositionStatus.RETRY_REQUIRED && state.pendingRetry && !state.busy
        }
        assertEquals("staying does not mutate the frozen request", frozenRequest.body, api.savedRequests.single().body)
        assertEquals(1, api.savedRequests.size)
        assertEquals("Stay preserves the reviewed draft revision", frozenDraftRevision,
            store.memoryBookCompositionState.value.draftRevision)

        rule.onNodeWithTag("memory-book-compose-retry").performScrollTo().performClick()
        rule.waitUntil(5_000) {
            val state = store.memoryBookCompositionState.value
            !state.busy && state.status == MemoryBookCompositionStatus.CREATED && state.createdBook != null
        }
        assertEquals("retry uses the identical body and does not create a second draft", 2, api.savedRequests.size)
        assertEquals(listOf(null, null), api.savedRequests.map { it.bookId })
        assertEquals(api.savedRequests[0].body, api.savedRequests[1].body)
        assertEquals(frozenMutationId,
            Json.parseToJsonElement(api.savedRequests[1].body).jsonObject.getValue("mutation_id").jsonPrimitive.content)
        val created = checkNotNull(store.memoryBookCompositionState.value.createdBook)
        assertEquals(CompositionApi.CREATED_BOOK, created.id)
        assertEquals(defaultTitle, created.title)
        assertEquals(introduction, created.introduction)
        assertEquals(if (zh) "zh" else "en", created.language)
        assertEquals(listOf(GeneratedMemoirReaderApi.SECOND, GeneratedMemoirReaderApi.FIRST), created.stories.map { it.id })

        // Only the explicit Open action leaves the composer and opens the verified protected reader.
        rule.onNodeWithTag("memory-book-compose-open-saved").performScrollTo().performClick()
        rule.waitUntil(5_000) {
            val reading = store.state.value.memoryBooks
            reading?.selectedBook?.id == CompositionApi.CREATED_BOOK && !reading.readerBusy
        }
        assertEquals(listOf(CompositionApi.CREATED_BOOK), api.getBookIds)
        assertNull("opening a book does not automatically load or play its child story", store.state.value.memoryBooks?.story)
        rule.onNodeWithTag("memory-book-entry-0").performScrollTo().performClick()
        rule.waitUntil(5_000) {
            val reading = store.state.value.memoryBooks
            reading?.story?.id == GeneratedMemoirReaderApi.SECOND && !reading.readerBusy
        }
        assertEquals(GeneratedMemoirReaderApi.SECOND, store.state.value.memoryBooks?.selectedBook?.stories?.first()?.id)

        assertEquals("two selection reads, two fresh-save reads, and one explicit reader load", 5, api.storyDetailReads.size)
        assertEquals(0, api.queueNarrativeCalls)
        assertEquals(0, api.transcriptionCalls)
        assertEquals(0, api.audioContributionCalls)
        assertEquals(0, api.childWriteCalls)
        assertEquals(0, api.base.originalCalls)
        assertEquals(0, api.base.videoCalls)

        // Back refreshes the original shelf; the new item is now visible there.
        rule.onNodeWithTag("memory-books-back").performClick()
        rule.waitUntil(5_000) {
            val reading = store.state.value.memoryBooks
            reading != null && reading.selectedBook == null && !reading.busy && reading.result?.items?.any { it.id == CompositionApi.CREATED_BOOK } == true
        }
        assertTrue("shelf refresh observed the newly created memoir", api.bookListPages.size >= 2)
        assertEquals(CompositionApi.CREATED_BOOK, store.state.value.memoryBooks?.result?.items?.first()?.id)

        // The former panel's detached Save/reorder/Close callbacks must not reach the reopened composer.
        rule.onNodeWithTag("memory-books-create").performClick()
        rule.waitUntil(5_000) {
            val state = store.memoryBookCompositionState.value
            state.status == MemoryBookCompositionStatus.READY && !state.busy && state.candidatePage != null
        }
        val replacement = store.memoryBookCompositionState.value
        assertNotEquals(initialEpoch, replacement.actionEpoch)
        assertTrue(replacement.selectedStories.isEmpty())
        rule.runOnIdle {
            assertTrue(oldCreate())
            assertTrue(oldSave())
            assertTrue(oldReorder())
            assertTrue(oldClose())
        }
        rule.waitForIdle()
        assertEquals("old callbacks cannot close the replacement composer", MemoryBookCompositionStatus.READY,
            store.memoryBookCompositionState.value.status)
        assertTrue("old callbacks cannot add choices to the replacement", store.memoryBookCompositionState.value.selectedStories.isEmpty())
        assertEquals("old Save cannot issue another create", 2, api.savedRequests.size)
        assertEquals("new composer retains the localized default title", defaultTitle, store.memoryBookCompositionState.value.title)
    }

    /** Synthetic helper-driven ASR exercises review UI without requesting microphone permission. */
    private fun voiceIntroductionJourney(zh: Boolean) {
        val api = CompositionApi(
            voiceEnabledForTest = true,
            transcriptForTest = if (zh) "我们一起照看花园。" else "We looked after the garden together.",
        )
        val store = ConnectedStore(api, scope, memoryCommunityApi = api, memoryCommunityEnabled = true)
        var keyboardController: SoftwareKeyboardController? = null
        rule.setContent {
            val density = LocalDensity.current
            val keyboard = LocalSoftwareKeyboardController.current
            SideEffect { keyboardController = keyboard }
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = if (zh) "zh" else "en")
            }
        }

        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5_000) { store.state.value.library == GeneratedMemoirReaderApi.LIBRARY }
        rule.runOnIdle { store.openMemoryBooks() }
        rule.waitUntil(5_000) {
            val shelf = store.state.value.memoryBooks
            shelf != null && !shelf.busy && shelf.result?.canCreate == true
        }
        rule.onNodeWithTag("memory-books-create").performClick()
        rule.waitUntil(5_000) {
            val state = store.memoryBookCompositionState.value
            state.status == MemoryBookCompositionStatus.READY && !state.busy && state.candidatePage != null
        }
        rule.onNodeWithTag("memory-book-compose-story-${GeneratedMemoirReaderApi.FIRST}")
            .performScrollTo().performClick()
        awaitComposition(store) { it.selectedStories.map { selected -> selected.summary.id } == listOf(GeneratedMemoirReaderApi.FIRST) }

        rule.onNodeWithTag("memory-book-compose-intro-toggle").performScrollTo().performClick()
        val voiceCapabilityBaseline = api.capabilityRequests
        val starter = if (zh) "先写下这次家庭回忆。" else "First notes for this family memory."
        rule.onNodeWithTag("memory-book-compose-intro").performScrollTo().performTextReplacement(starter)
        rule.waitUntil(5_000) { store.memoryBookCompositionState.value.introduction == starter }
        assertEquals("opening or editing the introduction makes no additional voice capability request", voiceCapabilityBaseline, api.capabilityRequests)
        rule.onNodeWithTag("memory-book-compose-save").performScrollTo().assertIsEnabled()

        // The explicit Dictate action is the first point allowed to query capabilities.
        rule.onNodeWithTag("memory-book-compose-intro-dictate").performScrollTo().performClick()
        rule.waitUntil(5_000) {
            val helper = store.memoryBookCompositionDictationCoordinator.state.value
            helper != null && !helper.state.value.loading && helper.state.value.capabilities != null
        }
        assertEquals(voiceCapabilityBaseline + 1, api.capabilityRequests)
        val originalHelper = checkNotNull(store.memoryBookCompositionDictationCoordinator.state.value)
        api.transcriptionGate = CompletableDeferred()
        rule.runOnIdle {
            assertNotNull("test uses an in-memory synthetic recording session", originalHelper.beginRecording())
            originalHelper.stopRecording(uiSyntheticWav())
        }
        rule.waitUntil(5_000) { api.transcriptionCalls == 1 && originalHelper.state.value.transcribing }

        val latest = if (zh) "现在补充：这是刚刚确认的最新简介。" else "Latest reviewed introduction wording, typed while transcription is pending."
        rule.onNodeWithTag("memory-book-compose-intro").performScrollTo().performTextReplacement(latest)
        rule.waitUntil(5_000) { store.memoryBookCompositionState.value.introduction == latest }
        rule.onNodeWithTag("memory-book-compose-save").performScrollTo().assertIsNotEnabled()
        assertTrue("no memoir save request is sent while transcript review is pending", api.savedRequests.isEmpty())

        api.transcriptionGate?.complete(Unit)
        rule.waitUntil(5_000) { originalHelper.state.value.transcript == api.transcriptForTest }
        val editedTranscript = if (zh) "识别文字经过我检查和修改。" else "Transcript reviewed and corrected by me."
        rule.onNodeWithTag("memory-dictation-transcript").performScrollTo().performTextReplacement(editedTranscript)
        rule.waitUntil(5_000) { originalHelper.state.value.transcript == editedTranscript }
        rule.runOnIdle { keyboardController?.hide() }
        rule.onNodeWithTag("memory-dictation-transcript-ready").performScrollTo()
        captureVoiceIntroduction(if (zh) "zh" else "en")

        // A failed combined insert keeps the original editor wording and complete transcript.
        val nearLimit = "x".repeat(5_990)
        rule.onNodeWithTag("memory-book-compose-intro").performScrollTo().performTextReplacement(nearLimit)
        rule.waitUntil(5_000) { store.memoryBookCompositionState.value.introduction == nearLimit }
        val staleAdd = captureClick("memory-dictation-insert")
        rule.onNodeWithTag("memory-dictation-insert").performScrollTo().performClick()
        rule.onNodeWithTag("memory-dictation-insert-rejected").performScrollTo().assertExists()
        assertEquals(nearLimit, store.memoryBookCompositionState.value.introduction)
        assertEquals(editedTranscript, originalHelper.state.value.transcript)

        // Shortening the current editor wording makes explicit insertion possible; the latest
        // editor text and the reviewed transcript both survive and no save is automatic.
        rule.onNodeWithTag("memory-book-compose-intro").performScrollTo().performTextReplacement(latest)
        rule.waitUntil(5_000) { store.memoryBookCompositionState.value.introduction == latest }
        rule.onNodeWithTag("memory-dictation-insert").performScrollTo().performClick()
        val combined = "$latest\n$editedTranscript"
        rule.waitUntil(5_000) {
            store.memoryBookCompositionState.value.introduction == combined && originalHelper.state.value.transcript == null
        }
        assertEquals(1, api.transcriptionCalls)
        assertTrue("review and insertion never trigger persistence", api.savedRequests.isEmpty())

        // Closing a consumed helper and opening a replacement fences callbacks from the old
        // transcript control and its old Close action by helper identity.
        val staleClose = captureClick("memory-book-compose-intro-voice-close")
        rule.onNodeWithTag("memory-book-compose-intro-voice-close").performScrollTo().performClick()
        rule.waitUntil(5_000) { store.memoryBookCompositionDictationCoordinator.state.value == null }
        rule.onNodeWithTag("memory-book-compose-intro-dictate").performScrollTo().performClick()
        rule.waitUntil(5_000) {
            val helper = store.memoryBookCompositionDictationCoordinator.state.value
            helper != null && helper !== originalHelper && !helper.state.value.loading && helper.state.value.capabilities != null
        }
        val replacementHelper = checkNotNull(store.memoryBookCompositionDictationCoordinator.state.value)
        rule.runOnIdle {
            staleAdd()
            staleClose()
        }
        rule.waitForIdle()
        assertSame("a stale Add cannot replace the new helper transcript", replacementHelper,
            store.memoryBookCompositionDictationCoordinator.state.value)
        assertNull(replacementHelper.state.value.transcript)
        assertEquals(combined, store.memoryBookCompositionState.value.introduction)
        assertTrue(api.savedRequests.isEmpty())

        // Explicitly discard the composition: it clears the replacement helper and all draft state.
        rule.onNodeWithTag("memory-book-compose-close").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-discard-dialog").assertIsDisplayed()
        rule.onNodeWithTag("memory-book-discard-confirm").performClick()
        rule.waitUntil(5_000) {
            store.memoryBookCompositionState.value.status == MemoryBookCompositionStatus.CLOSED &&
                store.memoryBookCompositionDictationCoordinator.state.value == null
        }
        assertTrue(store.memoryBookCompositionState.value.title.isEmpty())
        assertTrue(store.memoryBookCompositionState.value.introduction.isEmpty())
        assertTrue(store.memoryBookCompositionState.value.selectedStories.isEmpty())
        assertTrue(api.savedRequests.isEmpty())
    }

    private fun awaitCompositionState(store: ConnectedStore, predicate: (MemoryBookCompositionStoreState) -> Boolean) {
        rule.waitUntil(5_000) {
            val state = store.memoryBookCompositionState.value
            !state.busy && predicate(state)
        }
    }

    private fun awaitComposition(store: ConnectedStore, predicate: (MemoryBookCompositionStoreState) -> Boolean) {
        rule.waitUntil(5_000) {
            val state = store.memoryBookCompositionState.value
            !state.busy && state.status == MemoryBookCompositionStatus.READY && predicate(state)
        }
    }

    private fun captureClick(tag: String): () -> Boolean {
        val node = rule.onNodeWithTag(tag).fetchSemanticsNode()
        return checkNotNull(node.config[SemanticsActions.OnClick].action) { "$tag must expose an accessible action" }
    }

    private fun captureComposer(language: String) {
        val image = rule.onNodeWithTag("memory-book-compose").captureToImage().asAndroidBitmap()
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir,
            "memory-book-composition-$language-150.png").outputStream().use {
            image.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        image.recycle()
    }

    private class CompositionApi(
        val base: GeneratedMemoirReaderApi = GeneratedMemoirReaderApi(),
        private val voiceEnabledForTest: Boolean = false,
        val transcriptForTest: String = "Synthetic recognized introduction words.",
        private val editExisting: Boolean = false,
    ) : PhotoHouseApi by base, MemoryCommunityApi by base {
        override val protectedNativeV2Enabled = true
        override val assistantEnabled get() = voiceEnabledForTest

        data class SaveRequest(val bookId: String?, val body: String)
        private data class StoryRecord(val title: String, val revision: Long, val cover: String = "1")

        val savedRequests = mutableListOf<SaveRequest>()
        val getBookIds = mutableListOf<String>()
        val bookListPages = mutableListOf<Int>()
        val storyDetailReads = mutableListOf<Pair<String, Long>>()
        var failNextSave = false
        var queueNarrativeCalls = 0
        var transcriptionCalls = 0
        var capabilityRequests = 0
        var transcriptionGate: CompletableDeferred<Unit>? = null
        var candidateGate: CompletableDeferred<Unit>? = null
        var candidateRequests = 0
        var audioContributionCalls = 0
        var childWriteCalls = 0
        private var createdBookJson: String? = null
        private var lastAppliedBody: String? = null
        fun savedRevision() = Json.parseToJsonElement(checkNotNull(createdBookJson)).jsonObject.getValue("revision").jsonPrimitive.content

        private val stories = mapOf(
            GeneratedMemoirReaderApi.FIRST to StoryRecord("Garden day / 花园的一天", 3),
            GeneratedMemoirReaderApi.SECOND to StoryRecord("The way home / 回家的路", 5),
        )

        override suspend fun session(token: Bearer) = Session(
            GeneratedMemoirReaderApi.ACCOUNT, "+12025550123",
            listOf(Membership(GeneratedMemoirReaderApi.LIBRARY, "approved", "owner", 1, null, 0, true)),
        )

        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int): SavedMemoryStoryPage =
            savedMemoryStories(token, library, page, null)

        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int, theme: String?): SavedMemoryStoryPage {
            candidateRequests++
            val pendingGate = candidateGate
            if (pendingGate != null) withContext(NonCancellable) { pendingGate.await() }
            val summaries = if (page == 1 && (theme == null || theme == "everyday")) stories.map { (id, story) ->
                SavedMemoryStorySummary(id, story.title, "everyday", "zh", story.revision, story.cover,
                    itemCount = 12, chapterCount = 3, updatedAt = 1_720_000_000, canEdit = false)
            } else emptyList()
            return SavedMemoryStoryPage(library, page, 8, hasMore = false, canCreate = false, items = summaries)
        }

        override suspend fun savedMemoryStory(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStory {
            storyDetailReads += storyId to revision
            val record = checkNotNull(stories[storyId])
            check(revision == record.revision)
            val assets = (1..12).map { number ->
                val assetId = number.toString()
                MemoryStoryAsset(Asset(assetId, "image", 800, 600, null, null, "/synthetic-thumbnail"), emptyList())
            }
            return SavedMemoryStory(storyId, library, record.revision, 1_710_000_000, 1_720_000_000,
                canEdit = false, selectionRevision = if (storyId == GeneratedMemoirReaderApi.FIRST) "a".repeat(64) else "b".repeat(64),
                title = record.title, theme = "everyday", language = "zh", items = assets,
                chapters = (1..3).map { chapter ->
                    SavedMemoryStoryChapter("chapter-$chapter", "Chapter $chapter / 第 $chapter 章", "A saved family story.",
                        assets.drop((chapter - 1) * 4).take(4).map { it.asset.id }, emptyList())
                }, questions = emptyList())
        }

        override suspend fun listBooks(token: Bearer, library: String, page: Int): ByteArray {
            bookListPages += page
            val existing = createdBookJson
            val items = if (existing == null) listOf(oldBookJson()) else if (editExisting) listOf(existing) else listOf(existing, oldBookJson())
            return buildJsonObject {
                put("version", 1); put("library_id", library); put("page", page); put("page_size", 8)
                put("has_more", false); put("can_create", !editExisting)
                putJsonArray("items") { items.forEach { add(Json.parseToJsonElement(it)) } }
            }.toString().toByteArray()
        }

        override suspend fun getBook(token: Bearer, library: String, bookId: String): ByteArray {
            getBookIds += bookId
            val json = if (editExisting) createdBookJson ?: oldBookJson() else checkNotNull(createdBookJson)
            check(bookId == if (editExisting) GeneratedMemoirReaderApi.BOOK else CREATED_BOOK)
            return json.toByteArray()
        }

        override suspend fun saveBook(token: Bearer, library: String, bookId: String?, json: String): ByteArray {
            savedRequests += SaveRequest(bookId, json)
            val fail = failNextSave
            failNextSave = false
            if (fail && !editExisting) throw ApiFailure(FailureKind.OFFLINE)
            check(bookId == if (editExisting) GeneratedMemoirReaderApi.BOOK else null)
            if (editExisting && lastAppliedBody == json) return checkNotNull(createdBookJson).toByteArray()
            val request = Json.parseToJsonElement(json).jsonObject
            val ids = request.getValue("story_ids").jsonPrimitive.content.split(',')
            check(ids.isNotEmpty() && ids.distinct().size == ids.size)
            val title = request.getValue("title").jsonPrimitive.content
            val introduction = request.getValue("introduction").jsonPrimitive.content
            val language = request.getValue("language").jsonPrimitive.content
            check(request.getValue("revision").jsonPrimitive.content == if (editExisting) "2" else "0")
            createdBookJson = bookJson(if (editExisting) GeneratedMemoirReaderApi.BOOK else CREATED_BOOK,
                if (editExisting) 3 else 1, true, title, introduction, language, ids)
            lastAppliedBody = json
            if (fail) throw ApiFailure(FailureKind.OFFLINE)
            return checkNotNull(createdBookJson).toByteArray()
        }

        override suspend fun queueNarrative(token: Bearer, library: String, json: String): ByteArray {
            queueNarrativeCalls++
            error("Composition must not queue narrative generation")
        }

        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray): AssistantTranscript {
            transcriptionCalls++
            error("Composition must not transcribe audio")
        }

        override suspend fun assistantCapabilities(token: Bearer, library: String): AssistantCapabilities {
            capabilityRequests++
            check(voiceEnabledForTest)
            return AssistantCapabilities(enabled = true, text = true, transcribe = true, speech = false, maxAudioSeconds = 5)
        }

        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray, requestId: String): AssistantTranscript {
            transcriptionCalls++
            check(voiceEnabledForTest)
            check(wav.size == 44 + 16_000 * 2)
            transcriptionGate?.await()
            return AssistantTranscript(transcriptForTest, "en", AssistantRequestReceipt(requestId, "enabled", "succeeded"))
        }

        override suspend fun createAudioContribution(token: Bearer, library: String, storyId: String,
            metadataBase64: String, wav: ByteArray): ByteArray {
            audioContributionCalls++
            error("Composition must not create audio contributions")
        }

        override suspend fun createTextContribution(token: Bearer, library: String, storyId: String, json: String): ByteArray {
            childWriteCalls++
            error("Composition must not rewrite child stories")
        }

        private fun oldBookJson() = bookJson(GeneratedMemoirReaderApi.BOOK, 2, editExisting,
            "Earlier memoir", "", "zh", listOf(GeneratedMemoirReaderApi.FIRST, GeneratedMemoirReaderApi.SECOND))

        private fun bookJson(
            id: String, revision: Long, canEdit: Boolean, title: String, introduction: String, language: String,
            storyIds: List<String>,
        ): String = buildJsonObject {
            put("version", 1); put("type", "memoir"); put("id", id); put("revision", revision.toString())
            put("can_edit", canEdit); put("title", title); put("introduction", introduction); put("language", language)
            putJsonArray("stories") {
                storyIds.forEach { storyId ->
                    val story = checkNotNull(stories[storyId])
                    add(buildJsonObject {
                        put("id", storyId); put("title", story.title); put("revision", story.revision.toString())
                        put("item_count", 12); put("cover_asset_id", story.cover)
                    })
                }
            }
        }.toString()

        companion object {
            const val CREATED_BOOK = "00000000-0000-4000-8000-000000000014"
        }
    }

    private fun captureVoiceIntroduction(language: String) {
        val image = rule.onNodeWithTag("memory-book-compose").captureToImage().asAndroidBitmap()
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir,
            "memory-book-composition-voice-intro-$language-150.png").outputStream().use {
            image.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        image.recycle()
    }

    private fun uiSyntheticWav(): ByteArray {
        val pcm = ByteArray(16_000 * 2)
        return ByteArray(44 + pcm.size).also { wav ->
            val out = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
            out.put("RIFF".toByteArray()); out.putInt(wav.size - 8)
            out.put("WAVEfmt ".toByteArray()); out.putInt(16); out.putShort(1); out.putShort(1)
            out.putInt(16_000); out.putInt(32_000); out.putShort(2); out.putShort(16)
            out.put("data".toByteArray()); out.putInt(pcm.size); out.put(pcm)
            pcm.fill(0)
        }
    }
}
