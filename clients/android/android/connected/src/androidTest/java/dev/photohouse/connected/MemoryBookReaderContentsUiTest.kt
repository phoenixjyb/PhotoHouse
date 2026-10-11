package dev.photohouse.connected

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
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
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class MemoryBookReaderContentsUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    @After fun close() { scope.cancel() }

    @Test fun englishOriginalContentsUsesLoadedDataAndExplicitStorySelectionAt150Percent() = journey(false)
    @Test fun chineseOriginalContentsUsesLoadedDataAndExplicitStorySelectionAt150Percent() = journey(true)

    private fun journey(zh: Boolean) {
        val api = GeneratedMemoirReaderApi()
        val positions = Positions()
        val store = ConnectedStore(api, scope, memoryCommunityApi = api, memoryCommunityEnabled = true,
            memoryBookReaderPositionPersistence = positions)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(base.density, 1.5f)) {
                val state by store.state.collectAsState()
                state.memoryBooks?.let { reading ->
                    MemoryBooksDialog(reading, store, zh, store::openMemoryBooks, store::openMemoryBook,
                        store::loadMemoryBookStory, store::resumeMemoryBookReading,
                        { store.loadMemoryBookChapter(it) }, store::loadMemoryBookFramePage,
                        store::selectMemoryBookAsset, {}, store::closeMemoryBook, store::closeMemoryBooks)
                }
            }
        }

        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5_000) { store.state.value.library == GeneratedMemoirReaderApi.LIBRARY }
        rule.runOnIdle { store.openMemoryBooks() }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.result != null }
        rule.runOnIdle { store.openMemoryBook(GeneratedMemoirReaderApi.BOOK) }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.let { it.selectedBook != null && !it.readerBusy } == true }
        rule.onNodeWithTag("memory-book-entry-1").performScrollTo().performClick()
        awaitReader(store, storyIndex = 1)

        val childReadsBeforeExpand = api.childReads
        rule.onNodeWithTag("memory-book-reader-contents-toggle").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-reader-contents-story-1").assertIsSelected().assertIsNotEnabled()
        rule.onNodeWithTag("memory-book-reader-contents-chapter-0").assertIsSelected().assertIsNotEnabled()
        rule.onNodeWithTag("memory-book-reader-contents-story-0").assertExists()
        rule.onNodeWithTag("memory-book-reader-contents-chapter-2").assertExists()
        assertEquals("opening original contents only renders loaded data", childReadsBeforeExpand, api.childReads)
        assertEquals(0, api.originalCalls)
        assertEquals(0, api.videoCalls)
        captureContents(zh)

        rule.onNodeWithTag("memory-book-reader-contents-chapter-2").performScrollTo().performClick()
        awaitReader(store, storyIndex = 1, chapterIndex = 2)
        rule.onNodeWithTag("memory-book-story-title").assertIsDisplayed()
        assertEquals("chapter navigation reuses the already loaded child", childReadsBeforeExpand, api.childReads)
        assertEquals("chapter navigation bookmarks the selected reading position", "chapter-3",
            positions.load(GeneratedMemoirReaderApi.ACCOUNT).single().chapterId)

        rule.onNodeWithTag("memory-book-reader-contents-toggle").performScrollTo().performClick()
        assertEquals("reopening contents does not prefetch another child", childReadsBeforeExpand, api.childReads)
        rule.onNodeWithTag("memory-book-reader-contents-story-0").performScrollTo().performClick()
        rule.waitUntil(5_000) {
            store.state.value.memoryBooks?.let { it.storyIndex == 0 && !it.readerBusy && !it.framesBusy } == true
        }
        assertEquals("selecting another story explicitly loads exactly that child",
            childReadsBeforeExpand + 1, api.childReads)
        assertEquals("story-0 id is the fixture's first child", GeneratedMemoirReaderApi.FIRST,
            store.state.value.memoryBooks?.story?.id)
        rule.onNodeWithTag("memory-book-story-title").assertIsDisplayed()
        assertEquals(0, api.originalCalls)
        assertEquals(0, api.videoCalls)
    }

    private fun awaitReader(store: ConnectedStore, storyIndex: Int, chapterIndex: Int? = null) {
        rule.waitUntil(5_000) {
            store.state.value.memoryBooks?.let { reading ->
                reading.storyIndex == storyIndex && !reading.readerBusy && !reading.framesBusy &&
                    (chapterIndex == null || reading.selectedChapter == chapterIndex)
            } == true
        }
    }

    private fun captureContents(zh: Boolean) {
        val bitmap = rule.onNodeWithTag("memory-book-reader-contents").captureToImage().asAndroidBitmap()
        val locale = if (zh) "zh" else "en"
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir,
            "memoir-original-contents-$locale-150.png").outputStream().use {
            check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it))
        }
        bitmap.recycle()
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
