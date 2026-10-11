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
        val api = FixtureApi()
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

    private class FixtureApi : PhotoHouseApi, MemoryCommunityApi {
        override val protectedNativeV2Enabled = true
        var childReads = 0
        var originalCalls = 0
        var videoCalls = 0
        private val assets = (1..12).map { Asset(it.toString(), "image", 800, 600, null, null, "/synthetic-thumbnail") }
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session(ACCOUNT, "+12025550123",
            listOf(Membership(LIBRARY, "approved", "viewer", 1, null, 0, true)))
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 50, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, assets.first { it.id == assetId })
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk {
            videoCalls++; error("Original playback is outside this reader fixture")
        }
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray {
            originalCalls++; error("Original photos are outside this reader fixture")
        }
        override suspend fun capabilities(token: Bearer, library: String) =
            """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":false,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}""".toByteArray()
        private fun book() = """{"version":1,"type":"memoir","id":"$BOOK","revision":"2","can_edit":false,"title":"Garden memoir / 花园回忆册","introduction":"A generated reading fixture.","language":"zh","stories":[{"id":"$FIRST","title":"A garden day / 花园的一天","revision":"3","item_count":12,"cover_asset_id":"1"},{"id":"$SECOND","title":"The way home / 回家的路","revision":"5","item_count":12,"cover_asset_id":"1"}]}"""
        override suspend fun listBooks(token: Bearer, library: String, page: Int) =
            """{"version":1,"library_id":"$library","page":$page,"page_size":8,"has_more":false,"can_create":false,"items":[${book()}]}""".toByteArray()
        override suspend fun getBook(token: Bearer, library: String, bookId: String) = book().toByteArray()
        override suspend fun savedMemoryStory(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStory {
            childReads++
            return SavedMemoryStory(storyId, library, revision, 1710000000, 1720000000, false, "a".repeat(64),
                "Generated story / 合成故事", "everyday", "zh", assets.map { MemoryStoryAsset(it, emptyList()) },
                (1..3).map { chapter -> SavedMemoryStoryChapter("chapter-$chapter", "Chapter $chapter / 第 $chapter 章",
                    "A generated family walk.", assets.drop((chapter - 1) * 4).take(4).map { it.id }, emptyList()) }, emptyList())
        }
    }

    private companion object {
        const val ACCOUNT = "memoir-reader"
        const val LIBRARY = "family"
        const val BOOK = "00000000-0000-4000-8000-000000000011"
        const val FIRST = "00000000-0000-4000-8000-000000000012"
        const val SECOND = "00000000-0000-4000-8000-000000000013"
    }
}
