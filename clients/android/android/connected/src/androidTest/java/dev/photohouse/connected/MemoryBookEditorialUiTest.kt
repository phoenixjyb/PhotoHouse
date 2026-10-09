package dev.photohouse.connected

import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.SoftwareKeyboardController
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.*
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import android.content.ContentValues
import android.os.Environment
import android.provider.MediaStore
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import kotlinx.serialization.json.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MemoryBookEditorialUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun close() { scope.cancel() }
    private val s1 = "11111111-1111-4111-8111-111111111111"
    private val s2 = "22222222-2222-4222-8222-222222222222"
    private val contribution = "33333333-3333-4333-8333-333333333333"

    @Test fun sourcePickerAndAdjacentTransitionRemainReachableAtNormalAnd150PercentFont() {
        val source1 = EditorialSourceIdentity(s1, "2", "chapter-1", contribution)
        val source2 = EditorialSourceIdentity(s2, "5", "chapter-1", "44444444-4444-4444-8444-444444444444")
        val book = MemoryBook("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 7, true, "家庭回忆册", "", "zh",
            listOf(MemoryBookStorySummary(s1, "花园的一天", 2, 1, "1"), MemoryBookStorySummary(s2, "回家的路", 5, 1, "2")))
        val state = MemoryBookEditorialStoreState(MemoryBookEditorialStoreStatus.READY, "7",
            MemoryBookEditorial(book.id, "7", listOf(EditorialChild(s1, "2"), EditorialChild(s2, "5")), EditorialState.CURRENT,
                listOf(source1), listOf(EditorialTransition(s1, s2, "后来我们沿路回家。", listOf(source2)))),
            MemoryBookEditorialDraft(listOf(source1), listOf(EditorialTransition(s1, s2, "后来我们沿路回家。", listOf(source2)))), dirty = true)
        val catalog = MemoryBookEditorialCatalogState(sources = listOf(source1, source2))
        val store = ConnectedStore(PanelApi(), scope)

        val fontScale = mutableFloatStateOf(1f)
        rule.setContent {
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, fontScale.floatValue)) {
                PhotoHouseTheme {
                    androidx.compose.foundation.layout.Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                        MemoryBookEditorialPanel(book, store, state, catalog, true, companionBusy = false)
                    }
                }
            }
        }
        rule.onNodeWithTag("memory-book-editorial-disclosure").performClick()
        rule.onNodeWithText("引言来源").assertExists()
        rule.onNodeWithTag("editorial-source-group-intro-$s1/chapter-1").performClick()
        rule.onNodeWithTag("editorial-source-check-intro-$s1/chapter-1-0").assertIsOn()
        rule.onNodeWithTag("memory-book-transition-0").performClick()
        rule.onNodeWithTag("memory-book-transition-text-0").assertTextContains("后来我们沿路回家。")
        rule.onNodeWithTag("memory-book-editorial-save").performScrollTo().assertIsDisplayed()
        capture("memory-book-editorial-font100.png")
        rule.runOnIdle { fontScale.floatValue = 1.5f }
        rule.waitForIdle()
        capture("memory-book-editorial-font150.png")
        rule.onNodeWithText("11111111-1111-4111-8111-111111111111").assertDoesNotExist()
    }

    @Test fun sourceSearchPagesKeepIdentityBoundSelectionsUnavailableRefsAndBusyGuardsAt150Percent() {
        val sources = buildList {
            for (chapter in 1..3) {
                val count = if (chapter < 3) 12 else 1
                for (ordinal in 1..count) {
                    add(EditorialSourceIdentity(s1, "2", "chapter-$chapter",
                        "00000000-0000-4000-8000-${(chapter * 100 + ordinal).toString().padStart(12, '0')}"))
                }
            }
        }
        val first = sources.first()
        val unavailable = EditorialSourceIdentity(s1, "1", "chapter-1", "99999999-9999-4999-8999-999999999999")
        val book = MemoryBook("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 7, true, "Family Garden", "", "en",
            listOf(MemoryBookStorySummary(s1, "Garden memories", 2, 3, "1"), MemoryBookStorySummary(s2, "Walk home", 5, 1, "2")))
        val initial = MemoryBookEditorialStoreState(
            status = MemoryBookEditorialStoreStatus.READY,
            revision = "7",
            draft = MemoryBookEditorialDraft(listOf(first, unavailable), emptyList()),
            dirty = true,
        )
        val current = mutableStateOf(initial)
        val languageZh = mutableStateOf(false)
        val catalog = MemoryBookEditorialCatalogState(sources = sources)
        val store = ConnectedStore(PanelApi(), scope)
        rule.setContent {
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, 1.5f)) {
                PhotoHouseTheme {
                    androidx.compose.foundation.layout.Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                        MemoryBookEditorialPanel(book, store, current.value, catalog, languageZh.value, companionBusy = false)
                    }
                }
            }
        }
        rule.onNodeWithTag("memory-book-editorial-disclosure").performClick()
        rule.onNodeWithTag("editorial-source-search-intro").performTextInput("garden")
        assertSemanticsTextContains("editorial-source-counts-intro", "25 available")
        rule.onNodeWithTag("editorial-source-group-intro-$s1/chapter-1").performClick()
        rule.onNodeWithTag("editorial-source-check-intro-$s1/chapter-1-0").assertIsOn()
        capture("memory-book-source-search-en-font150.png")
        rule.onNodeWithTag("editorial-source-page-next-intro").assertIsEnabled().performScrollTo().performClick()
        rule.onNodeWithTag("editorial-source-page-intro").assertTextEquals("Page 2 of 3")
        assertSemanticsTextContains("editorial-source-counts-intro", "1 selected elsewhere")
        rule.onNodeWithTag("editorial-source-unavailable-heading-intro").assertExists()
        rule.onNodeWithTag("editorial-source-unavailable-check-intro-0").assertIsOn()
        rule.onNodeWithTag("editorial-source-group-intro-$s1/chapter-2").performClick()
        rule.onNodeWithTag("editorial-source-check-intro-$s1/chapter-2-1").performClick().assertIsOn()
        rule.onNodeWithTag("editorial-source-page-previous-intro").assertIsEnabled().performScrollTo().performClick()
        assertSemanticsTextContains("editorial-source-counts-intro", "1 selected elsewhere")

        rule.runOnIdle { languageZh.value = true }
        rule.waitForIdle()
        assertEquals("", rule.onNodeWithTag("editorial-source-search-intro")
            .fetchSemanticsNode().config[SemanticsProperties.EditableText].text)
        rule.onNodeWithTag("editorial-source-page-intro").assertTextEquals("第 1 / 3 页")
        rule.onNodeWithTag("editorial-source-group-intro-$s1/chapter-1").performClick()
        rule.onNodeWithTag("editorial-source-check-intro-$s1/chapter-1-0").assertIsOn()
        capture("memory-book-source-search-zh-font150.png")
        rule.onNodeWithTag("editorial-source-page-next-intro").assertIsEnabled().performScrollTo().performClick()
        rule.onNodeWithTag("editorial-source-group-intro-$s1/chapter-2").performClick()
        rule.onNodeWithTag("editorial-source-check-intro-$s1/chapter-2-1").assertIsOn()
        rule.onNodeWithTag("editorial-source-unavailable-check-intro-0").assertIsOn().performScrollTo().performClick()
        rule.waitForIdle()
        rule.onNodeWithTag("editorial-source-unavailable-heading-intro").assertDoesNotExist()

        rule.runOnIdle { current.value = current.value.copy(status = MemoryBookEditorialStoreStatus.SAVING) }
        rule.onNodeWithTag("editorial-source-search-intro").assertIsNotEnabled()
        rule.onNodeWithTag("editorial-source-page-previous-intro").assertIsNotEnabled()
        rule.onNodeWithTag("editorial-source-check-intro-$s1/chapter-2-1").assertIsNotEnabled()
    }

    @Test fun unavailableConflictAndUncertainStatesHaveExplicitControls() {
        val book = MemoryBook("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 7, true, "家庭回忆册", "", "zh",
            listOf(MemoryBookStorySummary(s1, "花园的一天", 2, 1, "1"), MemoryBookStorySummary(s2, "回家的路", 5, 1, "2")))
        val current = mutableStateOf(MemoryBookEditorialStoreState(status = MemoryBookEditorialStoreStatus.UNAVAILABLE))
        val catalog = mutableStateOf(MemoryBookEditorialCatalogState())
        val store = ConnectedStore(PanelApi(), scope)
        rule.setContent {
            PhotoHouseTheme {
                androidx.compose.foundation.layout.Column {
                    MemoryBookEditorialPanel(book, store, current.value, catalog.value, true, companionBusy = false)
                }
            }
        }
        rule.onNodeWithTag("memory-book-editorial-disclosure").performClick()
        rule.onNodeWithTag("memory-book-editorial-unavailable").assertExists()
        rule.runOnIdle { current.value = current.value.copy(status = MemoryBookEditorialStoreStatus.CONFLICT, dirty = true,
            revision = "8", serverEditorial = MemoryBookEditorial(book.id, "8", listOf(EditorialChild(s1, "2"), EditorialChild(s2, "5")),
                EditorialState.CURRENT, emptyList(), listOf(EditorialTransition(s1, s2, "", emptyList()))),
            draft = MemoryBookEditorialDraft(emptyList(), listOf(EditorialTransition(s1, s2, "Keep reviewed text", emptyList()))))
            catalog.value = MemoryBookEditorialCatalogState(sources = emptyList()) }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-editorial-refresh-conflict").assertExists()
        rule.onNodeWithTag("memory-book-editorial-apply-reviewed").assertExists()
        rule.runOnIdle { current.value = current.value.copy(status = MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN) }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-editorial-retry").assertExists()
        rule.onNodeWithTag("memory-book-transition-0").performClick()
        rule.onNodeWithTag("memory-book-transition-text-0").assertIsNotEnabled()
    }

    @Test fun uncertainSaveCloseWarningExplainsLaterCheckChoice() {
        var left = false
        rule.setContent {
            PhotoHouseTheme {
                MemoryBookEditorialUncertainExitDialog(true, MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN,
                    onRetry = {}, onLeave = { left = true }, onStay = {})
            }
        }
        rule.onNodeWithText("服务端可能已接受此次保存。你可以重试同一请求、留在此处继续处理，或先离开稍后核对；离开会清除本地草稿。").assertExists()
        rule.onNodeWithTag("memory-book-editorial-exit-later").performClick()
        assertTrue(left)
    }

    @Test fun ownerSelectsSourcesRetriesLostAcknowledgementAndReopensSavedArrangementAt150Percent() {
        val api = ReaderApi()
        val store = ConnectedStore(api, scope, memoryCommunityApi = api, memoryCommunityEnabled = true)
        var keyboardController: SoftwareKeyboardController? = null
        rule.setContent {
            val keyboard = LocalSoftwareKeyboardController.current
            SideEffect { keyboardController = keyboard }
            val state by store.state.collectAsState()
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, 1.5f)) {
                state.memoryBooks?.let { reading ->
                    MemoryBooksDialog(reading, store, true, store::openMemoryBooks, store::openMemoryBook,
                        store::loadMemoryBookStory, store::resumeMemoryBookReading, { store.loadMemoryBookChapter(it) },
                        store::loadMemoryBookFramePage, store::selectMemoryBookAsset, {}, store::closeMemoryBook, store::closeMemoryBooks)
                }
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password-only") }
        rule.waitUntil(5_000) { store.state.value.session != null && !store.state.value.busy }
        rule.runOnIdle { store.selectLibrary("family"); store.openMemoryBooks() }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.result != null }
        rule.runOnIdle { store.openMemoryBook(api.bookId) }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.selectedBook != null }
        assertEquals(0, api.metadataCalls)
        rule.onNodeWithTag("memory-book-editorial-disclosure").performScrollTo().performClick()
        rule.waitUntil(5_000) { store.memoryBookEditorialState.value.status == MemoryBookEditorialStoreStatus.READY }
        val metadataAfterCatalogLoad = api.metadataCalls
        rule.onNodeWithTag("editorial-source-search-intro").performTextInput("花园")
        assertSemanticsTextContains("editorial-source-counts-intro", "共 2 项")
        assertEquals(metadataAfterCatalogLoad, api.metadataCalls)
        assertEquals(0, api.detailCalls)
        assertEquals(0, api.audioCalls)
        rule.onNodeWithTag("editorial-source-clear-intro").performClick()
        rule.runOnIdle { keyboardController?.hide() }
        rule.onNodeWithTag("editorial-source-group-intro-$s1/chapter-1").performScrollTo().performClick()
        rule.onNodeWithTag("editorial-source-check-intro-$s1/chapter-1-0").performScrollTo().assertIsDisplayed().performClick().assertIsOn()
        rule.onNodeWithTag("memory-book-transition-0").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-transition-text-0").performScrollTo().performTextInput("Together we remembered the garden.")
        rule.runOnIdle { keyboardController?.hide() }
        rule.onNodeWithTag("editorial-source-group-transition-0-$s1/chapter-1").performScrollTo().performClick()
        rule.onNodeWithTag("editorial-source-check-transition-0-$s1/chapter-1-0").performScrollTo().assertIsDisplayed().performClick().assertIsOn()
        rule.onNodeWithTag("memory-books-close").performClick()
        rule.onNodeWithTag("memory-book-discard-dialog").assertIsDisplayed()
        rule.onNodeWithTag("memory-book-discard-cancel").performClick()
        rule.onNodeWithTag("memory-book-editorial-save").performScrollTo().assertIsEnabled().performClick()
        rule.waitUntil(5_000) { store.memoryBookEditorialState.value.status == MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN }
        rule.onNodeWithTag("memory-books-close").performClick()
        rule.onNodeWithTag("memory-book-editorial-exit-dialog").assertIsDisplayed()
        rule.onNodeWithTag("memory-book-editorial-exit-stay").performClick()
        rule.onNodeWithTag("memory-book-editorial-retry").performScrollTo().performClick()
        rule.waitUntil(5_000) { store.memoryBookEditorialState.value.status == MemoryBookEditorialStoreStatus.READY && !store.memoryBookEditorialState.value.dirty }
        assertEquals(2, api.saveBodies.size)
        assertEquals(api.saveBodies[0], api.saveBodies[1])
        assertEquals(8L, api.revision)
        assertEquals(8L, store.state.value.memoryBooks?.selectedBook?.revision)
        rule.onNodeWithTag("memory-books-close").performClick()
        rule.waitUntil(5_000) { store.state.value.memoryBooks == null }
        rule.runOnIdle { store.openMemoryBooks() }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.result != null }
        rule.runOnIdle { store.openMemoryBook(api.bookId) }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-book-editorial-disclosure").performScrollTo().performClick()
        rule.waitUntil(5_000) { store.memoryBookEditorialState.value.status == MemoryBookEditorialStoreStatus.READY }
        assertEquals(1, store.memoryBookEditorialState.value.draft?.introductionSourceRefs?.size)
        assertEquals("Together we remembered the garden.", store.memoryBookEditorialState.value.draft?.transitions?.single()?.text)
        rule.onNodeWithTag("memory-book-transition-0").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-transition-text-0").performScrollTo().assertTextContains("Together we remembered the garden.")
        capture("memory-book-editorial-reader-reopened-font150.png")
    }

    @Test fun inspectTextCitationSeparatesOriginalAndDerivedTextAt150Percent() {
        val api = ReaderApi().apply { contributionKind = "text" }
        val store = openStore(api)
        var coordinator: ReaderAudioCoordinator? = null
        renderEditorialPanel(store, zh = false) { coordinator = it }
        rule.onNodeWithTag("memory-book-editorial-disclosure").performClick()
        rule.waitUntil(5_000) { store.memoryBookEditorialState.value.status == MemoryBookEditorialStoreStatus.READY }
        rule.onNodeWithTag("editorial-source-group-intro-$s1/chapter-1").performScrollTo().performClick()
        rule.onNodeWithTag("editorial-source-check-intro-$s1/chapter-1-0").assertIsOff()
        rule.onNodeWithTag("editorial-source-inspect-intro-$s1/chapter-1-0").performScrollTo().performClick()
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.sourceInspection?.source != null }
        assertEquals(sourceIdentity(), store.state.value.memoryBooks?.sourceInspection?.source)
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.sourceInspection?.detail != null }
        rule.onNodeWithTag("editorial-source-original-text").assertTextEquals("A family member's original words.")
        rule.onNodeWithTag("editorial-source-inspector").assertExists()
        rule.onNodeWithText("Original contribution").assertExists()
        rule.onNodeWithTag("editorial-source-transcript").assertTextEquals("Transcript: Derived transcript")
        rule.onNodeWithTag("editorial-source-polished").assertTextEquals("Polished text: Polished derived wording")
        assertEquals("Inspection does not change citation selection", 0,
            store.memoryBookEditorialState.value.draft?.introductionSourceRefs?.size ?: 0)
        assertEquals(0, api.audioCalls)
        assertNotNull(coordinator)
        capture("memory-book-source-original-text-font150.png")
        rule.onNodeWithTag("memory-book-editorial-disclosure").performClick()
        assertNull(store.state.value.memoryBooks?.sourceInspection?.detail)
    }

    @Test fun inspectAudioFetchesOnlyOnRequestAndPlaybackRespectsRecordingLeaseAt150Percent() {
        val api = ReaderApi().apply { contributionKind = "audio" }
        val store = openStore(api)
        var coordinator: ReaderAudioCoordinator? = null
        renderEditorialPanel(store) { coordinator = it }
        rule.onNodeWithTag("memory-book-editorial-disclosure").performClick()
        rule.waitUntil(5_000) { store.memoryBookEditorialState.value.status == MemoryBookEditorialStoreStatus.READY }
        rule.onNodeWithTag("editorial-source-group-intro-$s1/chapter-1").performScrollTo().performClick()
        rule.onNodeWithTag("editorial-source-inspect-intro-$s1/chapter-1-0").performScrollTo().performClick()
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.sourceInspection?.detail != null }
        assertEquals(0, api.audioCalls)
        rule.onNodeWithTag("editorial-source-load-audio").performScrollTo().performClick()
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.sourceInspection?.audio != null }
        assertEquals(1, api.audioCalls)
        var speechStopped = false
        rule.runOnIdle { coordinator!!.acquire(ReaderAudioKind.SPEECH) { speechStopped = true } }
        rule.onNodeWithTag("editorial-source-play-audio").performScrollTo().performClick()
        rule.waitUntil(5_000) { rule.onAllNodesWithText("暂停原始录音").fetchSemanticsNodes().isNotEmpty() }
        assertTrue("Original playback releases the active speech lease", speechStopped)
        var recordingLease: ReaderAudioCoordinator.Lease? = null
        rule.runOnIdle { recordingLease = coordinator!!.acquire(ReaderAudioKind.RECORDING) {} }
        rule.onNodeWithTag("upload-annotation-audio-toggle").performClick()
        rule.onNodeWithTag("annotation-audio-busy").assertExists()
        capture("memory-book-source-original-audio-font150.png")
        // Recording blocks playback after it interrupts speech; an explicit retry works when recording ends.
        coordinator?.release(recordingLease)
        rule.onNodeWithTag("upload-annotation-audio-toggle").performClick()
        rule.waitUntil(5_000) { rule.onAllNodesWithText("暂停原始录音").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("editorial-source-inspector-close").performScrollTo().performClick()
        assertTrue(store.state.value.memoryBooks?.sourceInspection?.audio?.isClosed != false)
        assertEquals(1, api.audioCalls)
    }

    private fun openStore(api: ReaderApi): ConnectedStore {
        val store = ConnectedStore(api, scope, memoryCommunityApi = api, memoryCommunityEnabled = true)
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password-only") }
        rule.waitUntil(5_000) { store.state.value.session != null && !store.state.value.busy }
        rule.runOnIdle { store.selectLibrary("family"); store.openMemoryBooks() }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.result != null }
        rule.runOnIdle { store.openMemoryBook(api.bookId) }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.selectedBook != null }
        return store
    }

    private fun sourceIdentity() = EditorialSourceIdentity(s1, "2", "chapter-1", contribution)

    private fun assertSemanticsTextContains(tag: String, expected: String) {
        val text = rule.onNodeWithTag(tag).fetchSemanticsNode().config[SemanticsProperties.Text]
            .joinToString(" ") { it.text }
        assertTrue("Expected '$expected' in text '$text'", text.contains(expected))
    }

    private fun renderEditorialPanel(store: ConnectedStore, zh: Boolean = true, onCoordinator: (ReaderAudioCoordinator) -> Unit) {
        // One coordinator belongs to this synthetic reader throughout all of
        // its recompositions; no object construction is a composition effect.
        val readerAudio = ReaderAudioCoordinator()
        rule.setContent {
            val live by store.state.collectAsState()
            val editorial by store.memoryBookEditorialState.collectAsState()
            val catalog by store.memoryBookEditorialCatalogState.collectAsState()
            SideEffect { onCoordinator(readerAudio) }
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, 1.5f),
                LocalReaderAudioCoordinator provides readerAudio) {
                val reading = live.memoryBooks
                val book = reading?.selectedBook
                if (book != null) PhotoHouseTheme {
                    androidx.compose.foundation.layout.Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                        MemoryBookEditorialPanel(book, store, editorial, catalog, zh, companionBusy = false,
                            inspection = reading.sourceInspection)
                    }
                }
            }
        }
    }

    private inner class ReaderApi : PanelApi(), MemoryCommunityApi, MemoryBookEditorialApi {
        val bookId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        override val protectedNativeV2Enabled = true
        var revision = 7L
        var metadataCalls = 0
        var loseFirstAcknowledgement = true
        var contributionKind = "text"
        var detailCalls = 0
        var audioCalls = 0
        val saveBodies = mutableListOf<String>()
        private var saved: ByteArray? = null
        private val acknowledgements = mutableMapOf<String, Pair<String, ByteArray>>()
        override suspend fun session(token: Bearer) = Session("synthetic-owner", "+12025550123",
            listOf(Membership("family", "approved", "owner", 1, null, 0, true)))
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 50, 0, false, emptyList())
        override suspend fun capabilities(token: Bearer, library: String) =
            """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":false,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}""".toByteArray()
        private fun book() = """{"version":1,"type":"memoir","id":"$bookId","revision":"$revision","can_edit":true,"title":"合成家庭回忆册","introduction":"由合成资料组成的测试回忆册。","language":"zh","stories":[{"id":"$s1","title":"花园的一天","revision":"2","item_count":1,"cover_asset_id":"1"},{"id":"$s2","title":"回家的路","revision":"5","item_count":1,"cover_asset_id":"2"}]}"""
        override suspend fun listBooks(token: Bearer, library: String, page: Int) =
            """{"version":1,"library_id":"$library","page":$page,"page_size":8,"has_more":false,"can_create":false,"items":[${book()}]}""".toByteArray()
        override suspend fun getBook(token: Bearer, library: String, bookId: String) = book().toByteArray()
        override suspend fun getBookEditorialSourceReferences(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStoryContributionReferences {
            metadataCalls++
            return SavedMemoryStoryContributionReferences(storyId, library, revision,
                listOf(SavedMemoryChapterContributionReferences("chapter-1", listOf(contribution))))
        }
        override suspend fun savedMemoryContributionDetail(token: Bearer, library: String, storyId: String, contributionId: String): MemoryContributionDetail {
            detailCalls++
            return MemoryContributionDetail(
                MemoryContributionReceipt(MemoryContribution(contributionId, storyId, "synthetic-member", contributionKind,
                    "en", "Member", "0".repeat(64), 1200, "chapter-1", 1, "accepted", 1,
                    if (contributionKind == "text") "A family member's original words." else null, true), false, false),
                MemoryContributionDerivation(1, "ready", "Derived transcript", "Polished derived wording", emptyList(), null, 1, 1),
            )
        }
        override suspend fun contributionAudio(token: Bearer, library: String, storyId: String, contributionId: String): ByteArray {
            audioCalls++
            return silentWav(160_000)
        }
        override suspend fun getBookEditorial(token: Bearer, library: String, bookId: String) = saved?.copyOf() ?:
            """{"version":1,"id":"$bookId","revision":"$revision","children":[{"story_id":"$s1","revision":"2"},{"story_id":"$s2","revision":"5"}],"state":"empty","introduction_source_refs":[],"transitions":[]}""".toByteArray()
        override suspend fun saveBookEditorial(token: Bearer, library: String, bookId: String, json: String): ByteArray {
            saveBodies += json
            val input = Json.parseToJsonElement(json).jsonObject
            val mutation = input.getValue("mutation_id").jsonPrimitive.content
            acknowledgements[mutation]?.let { (body, response) -> check(body == json); return response.copyOf() }
            check(input.getValue("revision").jsonPrimitive.content == revision.toString())
            revision++
            val response = buildJsonObject {
                put("version", 1); put("id", bookId); put("revision", revision.toString()); put("state", "current")
                put("children", input.getValue("children")); put("introduction_source_refs", input.getValue("introduction_source_refs")); put("transitions", input.getValue("transitions"))
            }.toString().toByteArray()
            saved = response.copyOf(); acknowledgements[mutation] = json to response.copyOf()
            if (loseFirstAcknowledgement) { loseFirstAcknowledgement = false; throw ApiFailure(FailureKind.OFFLINE) }
            return response
        }
    }

    private fun silentWav(samples: Int): ByteArray = ByteArray(44 + samples * 2).also { bytes ->
        fun ascii(offset: Int, value: String) = value.forEachIndexed { index, char -> bytes[offset + index] = char.code.toByte() }
        fun u16(offset: Int, value: Int) { bytes[offset] = value.toByte(); bytes[offset + 1] = (value shr 8).toByte() }
        fun u32(offset: Int, value: Int) { repeat(4) { bytes[offset + it] = (value ushr (8 * it)).toByte() } }
        ascii(0, "RIFF"); u32(4, bytes.size - 8); ascii(8, "WAVE"); ascii(12, "fmt "); u32(16, 16)
        u16(20, 1); u16(22, 1); u32(24, 16000); u32(28, 32000); u16(32, 2); u16(34, 16)
        ascii(36, "data"); u32(40, samples * 2)
    }

    private fun capture(name: String) {
        val bitmap = rule.onNodeWithTag("memory-book-editorial-card").captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, name)
            put(MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/PhotoHouseEditorialUi")
        }
        val uri = checkNotNull(context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values))
        context.contentResolver.openOutputStream(uri).use { output -> assertTrue(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, output!!)) }
        bitmap.recycle()
    }

    private open class PanelApi : PhotoHouseApi {
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("synthetic-account", "+8612345678", emptyList())
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int): Gallery = error("unused")
        override suspend fun detail(token: Bearer, library: String, assetId: String): Detail = error("unused")
        override suspend fun captions(token: Bearer, library: String, assetId: String): Captions = error("unused")
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk = error("unused")
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray = error("unused")
    }
}
