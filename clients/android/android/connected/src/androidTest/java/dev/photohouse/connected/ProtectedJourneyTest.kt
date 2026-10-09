package dev.photohouse.connected

import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.io.ByteArrayOutputStream

/** Synthetic protected-native journey. No configured origin, credentials or live data. */
class ProtectedJourneyTest {
    @get:Rule val rule = createComposeRule()
    private var rootView: android.view.View? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    @After fun stop() { scope.cancel() }

    private class SyntheticApi : PhotoHouseApi {
        override val protectedNativeV2Enabled = true
        override var photoDeliveryEnabled = true
        var previewAvailable = false
        var loginPhone: String? = null
        var loginPassword: String? = null
        var registeredName: String? = null
        var registrationCode: String? = null
        var displayCalls = 0
        var originalCalls = 0
        var failNextStories = false
        var storyCalls = 0
        var storyText = "Literal family text / 家人亲笔文字"
        var storyCanEdit = false

        private val asset = Asset("1", "image", 1, 1, null, "2026-01-01", "/assets/1/thumbnail?library=synthetic-library")
        private val display = png()

        override suspend fun login(phone: String, password: String): SessionToken {
            loginPhone = phone; loginPassword = password
            return SessionToken(86400, "T".repeat(43), "Bearer")
        }
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun registerNamed(phone: String, password: String, code: String, name: String): SessionToken {
            registeredName = name; registrationCode = code
            return login(phone, password)
        }
        override suspend fun session(token: Bearer) = Session(
            "synthetic-account", "+8612345678",
            listOf(Membership("synthetic-library", "approved", "viewer", 1, null, 0, true)), displayName = registeredName)
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) =
            Gallery(library, page, 50, 1, false, listOf(asset))
        override suspend fun detail(token: Bearer, library: String, assetId: String) =
            Detail(library, false, asset)
        override suspend fun captions(token: Bearer, library: String, assetId: String) =
            Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = if (previewAvailable) display else null
        override suspend fun displayPhoto(token: Bearer, library: String, assetId: String): ByteArray {
            displayCalls++; return display
        }
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray {
            originalCalls++; return display
        }
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) =
            VideoChunk(start, 1, byteArrayOf(0))
        override suspend fun stories(token: Bearer, library: String, assetId: String, page: Int): ProtectedStoryPage {
            storyCalls++
            if (failNextStories) { failNextStories = false; throw ApiFailure(FailureKind.OFFLINE) }
            val items = if (page == 1) listOf(ProtectedStory(
                "11111111-1111-1111-1111-111111111111", assetId,
                "Lake day / 湖边的一天", storyText, "mixed",
                "Synthetic writer / 示例作者", "22222222-2222-2222-2222-222222222222",
                1, 100, 100, storyCanEdit, false)) else emptyList()
            return ProtectedStoryPage(library, assetId, page, false, page == 1, items)
        }

        private fun png(): ByteArray {
            val bitmap = Bitmap.createBitmap(900, 1200, Bitmap.Config.ARGB_8888).apply { eraseColor(0xff607b66.toInt()) }
            return ByteArrayOutputStream().use { out ->
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)
                bitmap.recycle(); out.toByteArray()
            }
        }
    }

    private fun start(api: SyntheticApi, initialLanguage: String = "en"): ConnectedStore {
        val store = ConnectedStore(api, scope)
        rule.setContent { rootView = androidx.compose.ui.platform.LocalView.current; ConnectedApp(store, initialLanguage = initialLanguage) }
        return store
    }
    private fun scroll(tag: String) { rule.onNodeWithTag("connected-screen").performScrollToNode(hasTestTag(tag)) }
    private fun clickTag(tag: String) { scroll(tag); rule.onNodeWithTag(tag).performScrollTo().performClick(); rule.waitForIdle() }
    private fun clickText(text: String) {
        val matcher = hasText(text) and hasClickAction()
        rule.onNodeWithTag("connected-screen").performScrollToNode(matcher)
        rule.onNode(matcher).performClick(); rule.waitForIdle()
    }
    private fun awaitLibrary(store: ConnectedStore, library: String = "synthetic-library") {
        rule.waitUntil(5000) { store.state.value.library == library }
        rule.waitForIdle()
    }
    private fun input(label: String, text: String) {
        val matcher = hasText(label) and hasSetTextAction()
        rule.onNodeWithTag("connected-screen").performScrollToNode(matcher)
        rule.onNode(matcher).performTextInput(text)
    }

    @Test fun namedInvitedRegistrationValidationAndPreviewJourneyInBothLanguages() {
        val api = SyntheticApi().apply { photoDeliveryEnabled = false; previewAvailable = true }
        val store = start(api)
        for (zh in listOf(false, true)) {
            if (zh) {
                clickTag("app-settings")
                rule.onNodeWithText("简体中文").performClick()
            }
            clickText(if (zh) "收到邀请？注册" else "Have an invitation? Register")
            val phoneField = hasText(if (zh) "手机号码" else "Phone number") and hasSetTextAction()
            rule.onNodeWithTag("connected-screen").performScrollToNode(phoneField)
            rule.onNode(phoneField).performTextReplacement("13800138000")
            input(if (zh) "密码（8–128 个字符）" else "Password (8–128 characters)", "12345678")
            input(if (zh) "邀请码" else "Invitation code", "synthetic-invitation")
            val submit = if (zh) "使用邀请注册" else "Register with invitation"
            rule.onNodeWithText(submit).assertIsNotEnabled()
            input(if (zh) "你的名字" else "Your name", "😀".repeat(65))
            rule.onNodeWithText(submit).assertIsNotEnabled()
            rule.onNodeWithTag("registration-name").performScrollTo().performTextReplacement("  小溪   Jane  ")
            rule.onNodeWithText(submit).assertIsEnabled()
            val screenshot = rule.onRoot().captureToImage().asAndroidBitmap()
            File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir, "registration-v12-${if (zh) "zh" else "en"}.png")
                .outputStream().use { screenshot.compress(Bitmap.CompressFormat.PNG, 100, it) }
            screenshot.recycle()
            clickText(submit)
            rule.waitUntil(10000) {
                rootView?.let { androidx.core.view.ViewCompat.getRootWindowInsets(it)?.isVisible(androidx.core.view.WindowInsetsCompat.Type.ime()) } == false
            }
            assertEquals("+8613800138000", api.loginPhone)
            assertEquals("小溪 Jane", api.registeredName)
            assertEquals("synthetic-invitation", api.registrationCode)
            awaitLibrary(store)
            clickText(if (zh) "资料库" else "Libraries")
            scroll("account-name")
            rule.onNodeWithTag("account-name").assertTextContains(if (zh) "欢迎，小溪 Jane" else "Welcome, 小溪 Jane")
            clickText(if (zh) "打开资料库" else "Open library")
            awaitLibrary(store)
            clickTag("media-1")
            assertTrue("Preview entry: ${store.state.value.problem}", store.state.value.viewingOriginal)
            rule.waitUntil(10000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().size == 1 }
            if (rule.onAllNodesWithTag("photo-exit-fullscreen").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("photo-exit-fullscreen").performClick()
            rule.onNodeWithTag("photo-fit-width").performScrollTo().performClick()
            rule.onNodeWithTag("photo-actual-size").performScrollTo().performClick()
            assertEquals(0, api.originalCalls); assertEquals(0, api.displayCalls)
            rule.runOnIdle { store.background() }
            rule.onNodeWithTag("original-image").assertDoesNotExist()
            rule.runOnIdle { store.foreground() }; rule.waitForIdle()
            rule.runOnIdle { store.logout() }; rule.waitForIdle()
            rule.onNodeWithTag("account-name").assertDoesNotExist()
            clickText(if (zh) "收到邀请？注册" else "Have an invitation? Register")
            rule.onNodeWithTag("registration-name").assert(hasText("", substring = false))
            clickText(if (zh) "已有账号？登录" else "Already registered? Sign in")
        }
    }

    @Test fun protectedLoginStoriesMediaPagingRetryRefreshAndLogout() {
        val api = SyntheticApi()
        val store = start(api)

        rule.onNode(hasText("Phone number") and hasSetTextAction()).performTextReplacement("13800138000")
        input("Password", "eight888")
        clickText("Sign in")
        awaitLibrary(store)
        assertEquals("+8613800138000", api.loginPhone)
        assertEquals("eight888", api.loginPassword)

        clickTag("details-1")
        clickText("View photo")
        rule.waitUntil(5000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().isNotEmpty() }
        assertEquals(1, api.displayCalls)
        assertEquals("Display route must be used; originals remain untouched", 0, api.originalCalls)
        if (rule.onAllNodesWithTag("photo-exit-fullscreen").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("photo-exit-fullscreen").performClick()
        rule.onNodeWithText("Close photo").performScrollTo().performClick(); rule.waitForIdle()

        clickTag("stories-open")
        rule.waitUntil(5000) { rule.onAllNodesWithTag("story-11111111-1111-1111-1111-111111111111").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("connected-screen").performScrollToNode(hasText("Literal family text / 家人亲笔文字"))
        rule.onNodeWithText("Literal family text / 家人亲笔文字").assertIsDisplayed()
        scroll("story-11111111-1111-1111-1111-111111111111")
        val bitmap = rule.onRoot().captureToImage().asAndroidBitmap()
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir, "protected-stories-en.png")
            .outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        clickTag("stories-next")
        rule.onNodeWithTag("connected-screen").performScrollToNode(hasText("No family stories on this page yet."))
        rule.onNodeWithText("No family stories on this page yet.").assertIsDisplayed()
        clickTag("stories-previous")
        rule.onNodeWithTag("connected-screen").performScrollToNode(hasText("Lake day / 湖边的一天"))
        rule.onNodeWithText("Lake day / 湖边的一天").assertIsDisplayed()
        clickTag("stories-refresh")
        assertTrue(api.storyCalls >= 4)

        api.failNextStories = true
        clickTag("stories-refresh")
        rule.waitUntil(5000) { rule.onAllNodesWithTag("stories-retry").fetchSemanticsNodes().isNotEmpty() }
        clickTag("stories-retry")
        rule.waitUntil(5000) { rule.onAllNodesWithText("Lake day / 湖边的一天").fetchSemanticsNodes().isNotEmpty() }

        clickTag("app-settings")
        rule.onNodeWithText("Sign out").performClick(); rule.waitForIdle()
        assertTrue(!store.hasSession)
        rule.onNodeWithTag("protected-stories").assertDoesNotExist()
    }
    @Test fun longStoryReaderScrollsToEndAndClearsOnBackground() {
        val api = SyntheticApi().apply { storyText = "我们在湖边散步，听风吹过树梢。\n".repeat(1000) + "最后一段 / End of memory" }
        val store = start(api)
        rule.runOnIdle { store.authenticate("+8612345678", "eight888") }
        rule.waitForIdle(); awaitLibrary(store); clickTag("details-1");clickTag("stories-open")
        clickTag("story-read-full")
        rule.waitUntil(5000) { rule.onAllNodesWithTag("story-reader").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("story-reader").performScrollToNode(hasText("最后一段 / End of memory", substring = true))
        rule.onNode(hasText("最后一段 / End of memory", substring = true)).assertIsDisplayed()
        val bitmap = rule.onNode(isDialog()).captureToImage().asAndroidBitmap()
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir, "protected-story-long.png")
            .outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        rule.runOnIdle { store.background() };rule.waitForIdle()
        rule.onNodeWithTag("story-reader").assertDoesNotExist()
        assertTrue(store.state.value.stories == null)
    }

    @Test fun immersiveStoryReaderKeepsFamilyIdentityAndOnlyShowsAllowedEdit() {
        val api = SyntheticApi().apply { storyText = "A family recollection. ".repeat(100); storyCanEdit = true }
        val store = start(api, initialLanguage = "zh")
        rule.runOnIdle { store.authenticate("+8612345678", "eight888") }
        rule.waitForIdle(); awaitLibrary(store); clickTag("details-1"); clickTag("stories-open")
        clickTag("story-read-full")
        rule.onNodeWithTag("story-reader").assertExists()
        rule.onNodeWithTag("story-reader-source").assertTextEquals("家人回忆")
        rule.onNodeWithTag("story-reader-title").assertTextEquals("Lake day / 湖边的一天")
        rule.onNodeWithTag("story-reader-byline-label").assertTextEquals("署名 · 自行填写")
        rule.onNodeWithTag("story-reader-byline").assertTextEquals("Synthetic writer / 示例作者")
        rule.onNodeWithTag("story-reader-asset-note").assertTextEquals("属于这张照片或视频")
        val storyBitmap = rule.onNode(isDialog()).captureToImage().asAndroidBitmap()
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir, "story-reader-phone-zh.png")
            .outputStream().use { storyBitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        storyBitmap.recycle()
        rule.onNodeWithTag("story-reader-edit").assertIsDisplayed().performClick()
        rule.waitUntil(5000) { rule.onAllNodesWithTag("protected-story-editor").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("story-editor-title").assertIsDisplayed()
    }

    @Test fun previewOnlyProfileOpensViewerModesWithoutOriginalOrDisplayRequests() {
        val api = SyntheticApi().apply { photoDeliveryEnabled = false; previewAvailable = true }
        val store = start(api)
        rule.runOnIdle { store.authenticate("+8612345678", "eight888") }
        rule.waitForIdle(); awaitLibrary(store); clickTag("media-1")
        rule.waitUntil(10000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().size == 1 }
        if (rule.onAllNodesWithTag("photo-exit-fullscreen").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("photo-exit-fullscreen").performClick()
        assertTrue(store.state.value.photoPreviewOnly)
        fun viewerTag(tag: String) { rule.onNodeWithTag(tag).performScrollTo().performClick(); rule.waitForIdle() }
        viewerTag("photo-fit-width")
        rule.onNodeWithTag("photo-fit-mode").assertTextContains("width", substring = true)
        viewerTag("photo-fit-height")
        rule.onNodeWithTag("photo-fit-mode").assertTextContains("height", substring = true)
        viewerTag("photo-actual-size")
        rule.onNodeWithTag("photo-fit-mode").assertTextContains("Actual", substring = true)
        val pixels = rule.onNodeWithTag("photo-viewport").captureToImage().asAndroidBitmap()
        val greenWidth = (0 until pixels.width).count { pixels.getPixel(it, pixels.height / 2) == 0xff607b66.toInt() }
        assertTrue("Actual size must use physical pixels, not dp: $greenWidth", kotlin.math.abs(greenWidth - minOf(900, pixels.width)) <= 2)
        pixels.recycle()
        rule.onNodeWithTag("photo-quality").assertTextEquals("Preview quality")
        rule.onNode(hasText("Zoom in") and hasClickAction()).performScrollTo().performClick()
        rule.onNode(hasText("Zoom out") and hasClickAction()).performScrollTo().performClick()
        rule.onNode(hasText("Full screen") and hasClickAction()).performScrollTo().performClick()
        rule.onNodeWithTag("photo-controls").assertDoesNotExist()
        rule.onNodeWithTag("photo-exit-fullscreen").assertIsDisplayed().performClick()
        viewerTag("photo-fit-width")
        val bitmap = rule.onRoot().captureToImage().asAndroidBitmap()
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir, "protected-preview-viewer.png")
            .outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        assertEquals(0, api.originalCalls); assertEquals(0, api.displayCalls)
        rule.onNode(hasText("Close photo") and hasClickAction()).performScrollTo().performClick()
        rule.waitForIdle(); clickTag("app-settings")
        rule.onNodeWithText("简体中文").performClick(); rule.waitForIdle()
        clickTag("view-protected-preview")
        rule.waitUntil(10000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().size == 1 }
        if (rule.onAllNodesWithTag("photo-exit-fullscreen").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("photo-exit-fullscreen").performClick()
        viewerTag("photo-fit-width")
        rule.onNodeWithTag("photo-fit-mode").assertTextEquals("适合宽度")
        viewerTag("photo-fit-height")
        rule.onNodeWithTag("photo-fit-mode").assertTextEquals("适合高度")
        viewerTag("photo-actual-size")
        rule.onNodeWithTag("photo-quality").assertTextEquals("预览画质")
        val chinese = rule.onRoot().captureToImage().asAndroidBitmap()
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir, "protected-preview-viewer-zh.png")
            .outputStream().use { chinese.compress(Bitmap.CompressFormat.PNG, 100, it) }
        rule.runOnIdle { store.background() }; rule.waitForIdle()
        rule.onNodeWithTag("original-viewer").assertDoesNotExist()
        assertTrue(store.state.value.originalPhoto == null)
    }

}
