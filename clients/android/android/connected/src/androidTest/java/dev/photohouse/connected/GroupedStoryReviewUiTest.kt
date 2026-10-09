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
import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.*
import org.junit.*
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class GroupedStoryReviewUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun stop() { scope.cancel() }
    @Test fun bilingualLargeTextReviewAndUncertainRetryRemainReachable() {
        val bound = MemoryCommunityBinding(Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer")), "family-a", 1)
        val fake = object : StoryWorkspaceApi {
            override suspend fun storyPreview(token: Bearer, library: String, json: String) = """{"version":1,"library_id":"family-a","selection_revision":"${"a".repeat(64)}","state":"draft","saved":false,"title":"花园里的一天","theme":"everyday","language":"zh","generator":"evidence_outline","needs_review":true,"items":[{"id":"1","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/1/thumbnail?library=family-a","date_hint":null,"evidence":[{"id":"family-11111111-1111-4111-8111-111111111111","source":"family","title":"合成讲述","text":"这是家人的原话，保留原本的语气。","revision":1}]}],"chapters":[{"id":"chapter-1","title":"一起种花","narration":"我们在花园里一起种花。","asset_ids":["1"],"evidence_ids":["family-11111111-1111-4111-8111-111111111111"]}],"questions":["那一天，还有什么想留下的回忆？"]}""".toByteArray()
            override suspend fun storyTitleCapabilities(token: Bearer, library: String) =
                """{"version":1,"enabled":false,"max_suggestions":3,"needs_review":true}""".toByteArray()
            override suspend fun storyTitles(token: Bearer, library: String, json: String) = error("disabled")
            override suspend fun createGroupedStory(token: Bearer, library: String, json: String): ByteArray =
                throw ApiFailure(FailureKind.OFFLINE)
        }
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(fake, { bound }), scope, { bound })
        store.selectAsset("1")
        var zh by mutableStateOf(true)
        rule.setContent {
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, 1.5f)) {
                PhotoHouseTheme { GroupedStoryReview(store, zh, {}, {}) }
            }
        }
        rule.onNodeWithTag("grouped-story-preview").performClick()
        rule.waitUntil(5000) { store.state.value.status == StoryWorkspaceStoreStatus.EDITING }
        rule.onNodeWithTag("grouped-story-title").performScrollTo().assertTextContains("花园里的一天")
        capture("grouped-story-review-zh150.png")
        rule.onNodeWithText("核对来源（1）").performScrollTo().performClick()
        rule.onNodeWithText("家人讲述").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("这是家人的原话，保留原本的语气。").assertExists()
        rule.onNodeWithText("family-11111111-1111-4111-8111-111111111111").assertDoesNotExist()
        capture("grouped-story-sources-zh150.png")
        rule.onNodeWithTag("grouped-story-save").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("grouped-story-reviewed").performScrollTo().performClick()
        rule.onNodeWithTag("grouped-story-save").performScrollTo().assertIsEnabled()
        rule.onNodeWithTag("grouped-story-title").performScrollTo().performTextReplacement("家人讲述的花园故事")
        rule.onNodeWithTag("grouped-story-save").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("grouped-story-reviewed").performScrollTo().assertIsOff().performClick()
        rule.onNodeWithTag("grouped-story-save").performScrollTo().assertIsEnabled()
        rule.runOnIdle { zh = false }
        rule.onNodeWithTag("grouped-story-title").performScrollTo().assertIsDisplayed()
        capture("grouped-story-review-en150.png")
        rule.onNodeWithTag("grouped-story-save").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.status == StoryWorkspaceStoreStatus.SAVE_UNCERTAIN }
        rule.onNodeWithTag("grouped-story-retry").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("grouped-story-close").performScrollTo().performClick()
        rule.onNodeWithText("Leave this draft?").assertIsDisplayed()
        rule.onNodeWithText("Keep editing").performClick()
        Assert.assertTrue(store.state.value.hasPendingSave)
    }
    private fun capture(name: String) {
        val image = rule.onNodeWithTag("grouped-story-review").captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        File(context.filesDir, name).outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
}
