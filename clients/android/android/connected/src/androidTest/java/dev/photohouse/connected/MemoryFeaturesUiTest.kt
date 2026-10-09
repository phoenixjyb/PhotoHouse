package dev.photohouse.connected

import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.cancel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.io.FileOutputStream

/** Synthetic gallery-to-memory journey; no MainActivity, origin, credentials, or live media. */
class MemoryFeaturesUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    @After fun close() { scope.cancel() }

    private class SyntheticApi : PhotoHouseApi {
        override val protectedNativeV2Enabled = true
        override val mediaFilterEnabled = true
        override val preparedBrowseEnabled = true
        override val preparedVideoEnabled = true
        var saves = 0
        var saved: ProtectedStory? = null
        private val image = Asset("1", "image", 800, 600, null, "2026-01-01", "/assets/1/thumbnail?library=family")
        private val video = Asset("2", "video", null, null, 12.0, "2026-01-02", "/assets/2/thumbnail?library=family")

        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("account", "+8612345678", listOf(Membership("family", "approved", "contributor", 1, null, 0, true)), "Synthetic")
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun registerNamed(phone: String, password: String, code: String, name: String) = login(phone, password)
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 50, 2, false, listOf(image, video))
        override suspend fun gallery(token: Bearer, library: String, page: Int, media: GalleryMedia) = Gallery(library, page, 50, 1, false, listOf(if (media in listOf(GalleryMedia.VIDEOS, GalleryMedia.PREPARED_VIDEOS)) video else image))
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, if (assetId == "2") video else image)
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = VideoChunk(start, 1, byteArrayOf(0))
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String) = byteArrayOf(1)
        override suspend fun stories(token: Bearer, library: String, assetId: String, page: Int): ProtectedStoryPage {
            val item = saved?.takeIf { it.assetId == assetId }
            return ProtectedStoryPage(library, assetId, page, true, false, listOfNotNull(item))
        }
        override suspend fun saveStory(token: Bearer, library: String, mutation: StoryMutation): ProtectedStory {
            saves++
            val next = ProtectedStory(
                mutation.storyId ?: "11111111-1111-1111-1111-111111111111", mutation.assetId,
                mutation.draft.title, mutation.draft.text, mutation.draft.language, mutation.draft.byline,
                "account", (mutation.revision ?: 0) + 1, 1, 2, true, true,
            )
            saved = next
            return next
        }
        override suspend fun currentStory(token: Bearer, library: String, assetId: String, storyId: String) = saved
    }

    private fun click(tag: String) {
        rule.onNodeWithTag("connected-screen").performScrollToNode(hasTestTag(tag))
        rule.onNodeWithTag(tag).performClick(); rule.waitForIdle()
    }
    private fun capture(tag: String, name: String) {
        rule.waitForIdle()
        rule.onNodeWithTag(tag).captureToImage().asAndroidBitmap().let { bitmap ->
            FileOutputStream(File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir, name)).use {
                bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
            }
            bitmap.recycle()
        }
    }
    @Test fun videoGalleryToAddReviewConfirmSavedMemoryAndBackgroundDismissal() = journey(false)
    @Test fun englishVideoMemoryReviewAndSave() = journey(true)

    @Test fun preparedVideoFilterChinese() = journey(false, true)
    @Test fun preparedVideoFilterEnglish() = journey(true, true)

    private fun journey(english: Boolean, prepared: Boolean = false) {
        val api = SyntheticApi()
        val store = ConnectedStore(api, scope)
        rule.setContent {
            val view = androidx.compose.ui.platform.LocalView.current
            androidx.compose.runtime.DisposableEffect(view) {
                val previous = view.keepScreenOn
                view.keepScreenOn = true
                onDispose { view.keepScreenOn = previous }
            }
            ConnectedApp(store, initialLanguage = "en")
        }
        click("app-settings")
        rule.onNodeWithText(if (english) "English" else "简体中文").performClick()
        rule.runOnIdle { store.authenticate("+8612345678", "password") }
        rule.waitUntil(5000) { store.state.value.session != null }
        rule.runOnIdle { store.selectLibrary("family") }
        rule.waitUntil(5000) { store.state.value.gallery != null }

        if (prepared) {
            click("gallery-media-prepared_video")
            rule.waitUntil(5000) { store.state.value.gallery?.items?.singleOrNull()?.id == "2" }
            rule.onNodeWithText(if (english) "Prepared videos" else "已准备视频").assertIsDisplayed()
            capture("connected-screen", "prepared-v19-${if (english) "en" else "zh"}.png")
            return
        }
        click("gallery-media-video")
        rule.waitUntil(5000) { store.state.value.gallery?.items?.singleOrNull()?.id == "2" }
        capture("connected-screen", "memory-v15-videos-${if (english) "en" else "zh"}.png")
        click("details-2")
        rule.waitUntil(5000) { store.state.value.detail?.asset?.id == "2" }
        click("stories-open")
        rule.waitUntil(5000) { store.state.value.stories?.result != null }
        click("story-add")
        rule.onNodeWithTag("story-editor-title").performScrollTo().performTextReplacement("First video memory")
        rule.onNodeWithTag("story-editor-text").performScrollTo().performTextReplacement("We watched this together.")
        capture("protected-story-editor", "memory-v15-editor-${if (english) "en" else "zh"}.png")
        rule.onNodeWithTag("story-editor-review").performScrollTo().performClick()
        capture("protected-story-editor", "memory-v15-review-${if (english) "en" else "zh"}.png")
        rule.onNodeWithTag("story-editor-confirm").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.storyEditor?.state?.value?.phase == StoryEditorPhase.SAVED }
        assertEquals(1, api.saves)
        rule.onNodeWithTag("story-editor-saved").assertTextEquals(if (english) "Saved revision 1" else "已保存版本 1")
        rule.onNodeWithText("We watched this together.").assertIsDisplayed()
        capture("protected-story-editor", "memory-v15-saved-${if (english) "en" else "zh"}.png")
        rule.onNodeWithTag("story-editor-done").performClick()
        rule.waitUntil(5000) { store.state.value.storyEditor == null }
        assertEquals(1, api.saves)

        rule.waitUntil(5000) { store.state.value.stories?.result != null }
        click("story-edit-11111111-1111-1111-1111-111111111111")
        rule.waitUntil(5000) { store.state.value.storyEditor != null }
        rule.runOnIdle { store.background() }
        rule.waitUntil(5000) { store.state.value.storyEditor == null }
        assertTrue(store.state.value.storyEditor == null)
    }
}
