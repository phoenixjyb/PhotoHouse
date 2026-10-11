package dev.photohouse.connected

import android.graphics.Bitmap
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Generated navigation evidence; real encryption has its own Keystore test cohort. */
@RunWith(AndroidJUnit4::class)
class MemoryBookReadingContinuityUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun close() { scope.cancel() }

    @Test fun chineseMemoirResumesExactMomentAfterRecreationAt150Percent() = journey(true)
    @Test fun englishMemoirResumesExactMomentAfterRecreationAt150Percent() = journey(false)

    private fun journey(zh: Boolean) {
        val api = GeneratedMemoirReaderApi()
        val positions = Positions()
        fun newStore() = ConnectedStore(api, scope, memoryCommunityApi = api,
            memoryCommunityEnabled = true, memoryBookReaderPositionPersistence = positions)
        var active by mutableStateOf(newStore())
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                val store = active
                val state by store.state.collectAsState()
                state.memoryBooks?.let { reading ->
                    MemoryBooksDialog(reading, store, zh, store::openMemoryBooks, store::openMemoryBook,
                        store::loadMemoryBookStory, store::resumeMemoryBookReading, { store.loadMemoryBookChapter(it) },
                        store::loadMemoryBookFramePage, store::selectMemoryBookAsset, {},
                        store::closeMemoryBook, store::closeMemoryBooks)
                }
            }
        }
        fun openBook() {
            rule.runOnIdle { active.authenticate("+12025550123", "synthetic-password") }
            rule.waitUntil(5000) { active.state.value.library == LIBRARY }
            rule.runOnIdle { active.openMemoryBooks() }
            rule.waitUntil(5000) { active.state.value.memoryBooks?.result != null }
            rule.runOnIdle { active.openMemoryBook(BOOK) }
            rule.waitUntil(5000) { active.state.value.memoryBooks?.let { it.selectedBook != null && !it.readerBusy } == true }
        }
        openBook()
        rule.onNodeWithTag("memory-book-reading-offer").assertDoesNotExist()
        rule.runOnIdle { assertTrue(positions.load(ACCOUNT).isEmpty()); assertEquals(0, api.childReads) }
        rule.onNodeWithTag("memory-book-entry-1").performScrollTo().performClick()
        rule.waitUntil(5000) { active.state.value.memoryBooks?.let { it.storyIndex == 1 && !it.framesBusy } == true }
        repeat(2) {
            rule.onNodeWithTag("memory-book-next-chapter").performClick()
            rule.waitUntil(5000) { active.state.value.memoryBooks?.let { reading -> reading.selectedChapter == it + 1 && !reading.framesBusy } == true }
        }
        rule.onNodeWithTag("memory-book-frames").performScrollTo()
        rule.onNodeWithTag("memory-book-frame-10").performClick()
        rule.waitUntil(5000) { active.state.value.memoryBooks?.selectedAssetId == "10" }
        rule.runOnIdle {
            val saved = positions.load(ACCOUNT).single()
            assertEquals(SECOND, saved.storyId); assertEquals("chapter-3", saved.chapterId); assertEquals("10", saved.assetId)
            active.closeMemoryBooks()
            active = newStore() // Same persistence, entirely new session/reader store.
        }
        val readsBeforeReopen = api.childReads
        openBook()
        rule.runOnIdle {
            assertEquals("fresh child metadata qualifies the offer", readsBeforeReopen + 1, api.childReads)
            assertNull("no automatic navigation after recreation", active.state.value.memoryBooks!!.story)
        }
        rule.onNodeWithTag("memory-book-reading-offer").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("memory-book-resume").assertIsEnabled()
        rule.onNodeWithTag("memory-book-start-over").assertIsEnabled()
        val image = rule.onNodeWithTag("memory-book-reading-offer").captureToImage().asAndroidBitmap()
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir,
            "memoir-reading-offer-${if (zh) "zh" else "en"}-150.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        rule.onNodeWithTag("memory-book-resume").performClick()
        rule.waitUntil(5000) {
            active.state.value.memoryBooks?.let { it.storyIndex == 1 && it.selectedChapter == 2 &&
                it.selectedAssetId == "10" && !it.readerBusy && !it.framesBusy } == true
        }
        rule.onNodeWithTag("memory-book-chapter-title").performScrollTo().assertIsDisplayed()
        rule.runOnIdle { active.closeMemoryBook(); active.openMemoryBook(BOOK) }
        rule.waitUntil(5000) { active.state.value.memoryBooks?.resumePosition != null && active.state.value.memoryBooks?.readerBusy == false }
        rule.onNodeWithTag("memory-book-start-over").performScrollTo().performClick()
        rule.waitUntil(5000) { active.state.value.memoryBooks?.let { it.storyIndex == 0 && it.selectedChapter == 0 &&
            it.selectedAssetId == "1" && !it.framesBusy } == true }
        rule.runOnIdle {
            assertTrue("Start over does not recreate the pointer through a preview load", positions.load(ACCOUNT).isEmpty())
            assertEquals(0, api.originalCalls); assertEquals(0, api.videoCalls)
        }
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

    private companion object {
        const val ACCOUNT = "memoir-reader"
        const val LIBRARY = "family"
        const val BOOK = "00000000-0000-4000-8000-000000000011"
        const val FIRST = "00000000-0000-4000-8000-000000000012"
        const val SECOND = "00000000-0000-4000-8000-000000000013"
    }
}
