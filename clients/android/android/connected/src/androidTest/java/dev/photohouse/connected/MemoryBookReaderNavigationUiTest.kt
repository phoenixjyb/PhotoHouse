package dev.photohouse.connected

import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import dev.photohouse.connected.core.ConnectedStore
import dev.photohouse.connected.core.MemoryBookReaderPosition
import dev.photohouse.connected.core.MemoryBookReaderPositionPersistence
import dev.photohouse.connected.core.MemoryBookReaderPositions
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MemoryBookReaderNavigationUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    @After fun close() { scope.cancel() }

    @Test fun staleChapterAndStoryButtonsCannotMoveCurrentReaderOrBookmark() {
        val api = GeneratedMemoirReaderApi()
        val positions = Positions()
        val store = mount(api, positions)
        openBook(store)
        rule.onNodeWithTag("memory-book-entry-1").performScrollTo().performClick()
        awaitReader(store, storyIndex = 1)

        rule.runOnIdle { store.loadMemoryBookChapter(1) }
        awaitReader(store, storyIndex = 1, chapterIndex = 1)
        val stalePreviousChapter = captureClick("memory-book-previous-chapter")
        val stalePreviousStory = captureClick("memory-book-previous")

        val currentNextChapter = captureClick("memory-book-next-chapter")
        rule.runOnIdle { assertTrue("current rendered action is accepted", currentNextChapter()) }
        awaitReader(store, storyIndex = 1, chapterIndex = 2)

        // Dispose the old controls before opening a replacement reader. A Compose
        // semantics dispatcher for a still-attached button deliberately uses its
        // latest callback and is not a detached rendered action.
        rule.runOnIdle { store.closeMemoryBook() }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-previous-chapter").assertDoesNotExist()
        rule.runOnIdle { store.openMemoryBook(GeneratedMemoirReaderApi.BOOK) }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.let { it.selectedBook != null && !it.readerBusy } == true }
        rule.runOnIdle { store.loadMemoryBookStory(0) }
        awaitReader(store, storyIndex = 0)
        rule.runOnIdle { store.loadMemoryBookChapter(2) }
        awaitReader(store, storyIndex = 0, chapterIndex = 2)
        val beforeStaleActions = store.state.value.memoryBooks!!
        val bookmarkBeforeStaleActions = positions.load(GeneratedMemoirReaderApi.ACCOUNT).single()
        val childReadsBeforeStaleActions = api.childReads

        rule.runOnIdle {
            assertTrue("stale chapter callback is still a handled UI action", stalePreviousChapter())
            assertTrue("stale story callback is still a handled UI action", stalePreviousStory())
        }
        rule.waitForIdle()
        val afterStaleActions = store.state.value.memoryBooks!!
        assertEquals(0, afterStaleActions.storyIndex)
        assertEquals(2, afterStaleActions.selectedChapter)
        assertEquals("9", afterStaleActions.selectedAssetId)
        assertEquals(bookmarkBeforeStaleActions, positions.load(GeneratedMemoirReaderApi.ACCOUNT).single())
        assertEquals(childReadsBeforeStaleActions, api.childReads)
        assertEquals(beforeStaleActions.story?.id, afterStaleActions.story?.id)

        val currentPreviousChapter = captureClick("memory-book-previous-chapter")
        rule.runOnIdle { assertTrue("current action still navigates", currentPreviousChapter()) }
        awaitReader(store, storyIndex = 0, chapterIndex = 1)
        assertEquals("chapter button remains connected to store navigation", "chapter-2",
            store.state.value.memoryBooks?.story?.chapters?.get(1)?.id)
    }

    @Test fun staleFrameButtonCannotChangeSelectedMomentOrBookmark() {
        val api = GeneratedMemoirReaderApi()
        val positions = Positions()
        val store = mount(api, positions)
        openBook(store)
        rule.onNodeWithTag("memory-book-entry-0").performScrollTo().performClick()
        awaitReader(store, storyIndex = 0)
        rule.onNodeWithTag("memory-book-frames").performScrollTo()

        val staleFrameTwo = captureClick("memory-book-frame-2")
        rule.runOnIdle { assertTrue("current frame action is accepted", staleFrameTwo()) }
        awaitSelectedAsset(store, "2")
        assertEquals("valid frame selection writes its bookmark", "2",
            positions.load(GeneratedMemoirReaderApi.ACCOUNT).single().assetId)

        rule.runOnIdle { store.loadMemoryBookChapter(1) }
        awaitReader(store, storyIndex = 0, chapterIndex = 1)
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-frame-2").assertDoesNotExist()
        val bookmarkBeforeStaleAction = positions.load(GeneratedMemoirReaderApi.ACCOUNT).single()
        val childReadsBeforeStaleAction = api.childReads
        rule.runOnIdle { assertTrue("old callback remains a handled UI action", staleFrameTwo()) }
        rule.waitForIdle()

        assertEquals("5", store.state.value.memoryBooks?.selectedAssetId)
        assertEquals(bookmarkBeforeStaleAction, positions.load(GeneratedMemoirReaderApi.ACCOUNT).single())
        assertEquals(childReadsBeforeStaleAction, api.childReads)
    }

    private fun mount(api: GeneratedMemoirReaderApi, positions: Positions): ConnectedStore {
        val store = ConnectedStore(api, scope, memoryCommunityApi = api, memoryCommunityEnabled = true,
            memoryBookReaderPositionPersistence = positions)
        rule.setContent {
            val state by store.state.collectAsState()
            state.memoryBooks?.let { reading ->
                MemoryBooksDialog(reading, store, true, store::openMemoryBooks, store::openMemoryBook,
                    store::loadMemoryBookStory, store::resumeMemoryBookReading,
                    { store.loadMemoryBookChapter(it) }, store::loadMemoryBookFramePage,
                    store::selectMemoryBookAsset, {}, store::closeMemoryBook, store::closeMemoryBooks)
            }
        }
        return store
    }

    private fun openBook(store: ConnectedStore) {
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5_000) { store.state.value.library == GeneratedMemoirReaderApi.LIBRARY }
        rule.runOnIdle { store.openMemoryBooks() }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.result != null }
        rule.runOnIdle { store.openMemoryBook(GeneratedMemoirReaderApi.BOOK) }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.let { it.selectedBook != null && !it.readerBusy } == true }
    }

    private fun awaitReader(store: ConnectedStore, storyIndex: Int, chapterIndex: Int? = null) {
        rule.waitUntil(5_000) {
            store.state.value.memoryBooks?.let { reading ->
                reading.storyIndex == storyIndex && !reading.readerBusy && !reading.framesBusy &&
                    (chapterIndex == null || reading.selectedChapter == chapterIndex)
            } == true
        }
    }

    private fun awaitSelectedAsset(store: ConnectedStore, assetId: String) {
        rule.waitUntil(5_000) {
            store.state.value.memoryBooks?.let { it.selectedAssetId == assetId && !it.heroBusy } == true
        }
    }

    private fun captureClick(tag: String): () -> Boolean {
        val node = rule.onNodeWithTag(tag).fetchSemanticsNode()
        val action = node.config[SemanticsActions.OnClick].action
        assertNotNull("$tag exposes an accessible click action", action)
        return checkNotNull(action)
    }

    private class Positions : MemoryBookReaderPositionPersistence {
        private var rows = emptyList<MemoryBookReaderPosition>()
        override fun load(accountId: String) = rows.filter { it.accountId == accountId }
        override fun save(accountId: String, position: MemoryBookReaderPosition) {
            rows = rows.filterNot { it.accountId == accountId } + MemoryBookReaderPositions.upsert(accountId, load(accountId), position)
        }
        override fun remove(accountId: String, libraryId: String, bookId: String) {
            rows = rows.filterNot { it.accountId == accountId } + MemoryBookReaderPositions.without(accountId, load(accountId), libraryId, bookId)
        }
        override fun clear(accountId: String) { rows = rows.filterNot { it.accountId == accountId } }
    }
}
