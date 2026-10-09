package dev.photohouse.connected

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import android.graphics.Bitmap
import android.content.ContentValues
import android.os.Environment
import android.provider.MediaStore

@RunWith(AndroidJUnit4::class)
class HomeMemorySectionUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val screenshotId = System.currentTimeMillis()
    @After fun close() = scope.cancel()

    private class Api(
        override val protectedNativeV2Enabled: Boolean,
        private val memberships: List<Membership>,
    ) : PhotoHouseApi {
        var storyRequests = 0
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("synthetic-account", "+12025550123", memberships)
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 8, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String): Detail = error("unexpected detail request")
        override suspend fun captions(token: Bearer, library: String, assetId: String): Captions = error("unexpected captions request")
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk = error("unexpected video request")
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray = error("unexpected original request")
        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int, theme: String?): SavedMemoryStoryPage {
            storyRequests++
            return SavedMemoryStoryPage(library, page, 8, false, false, emptyList())
        }
    }

    private class BooksApi : MemoryCommunityApi {
        var listRequests = 0
        override suspend fun capabilities(token: Bearer, library: String) =
            """{"version":1,"enabled":true,"contributions_enabled":false,"generation_enabled":false,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}""".toByteArray()
        override suspend fun listBooks(token: Bearer, library: String, page: Int): ByteArray {
            listRequests++
            return """{"version":1,"library_id":"$library","page":$page,"page_size":8,"has_more":false,"can_create":false,"items":[]}""".toByteArray()
        }
    }

    private val owner = listOf(Membership("family", "approved", "owner", 1, null, 0, true))

    private fun signIn(store: ConnectedStore) {
        rule.runOnUiThread { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5_000) { store.state.value.session != null }
    }

    private fun captureHomeAt150Percent() {
        val bitmap = rule.onNodeWithTag("connected-screen").captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, "home-memory-section-font150-$screenshotId.png")
            put(MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/PhotoHouseMemoryHome")
        }
        val uri = checkNotNull(context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values))
        context.contentResolver.openOutputStream(uri).use { out ->
            checkNotNull(out)
            check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, out))
        }
        bitmap.recycle()
    }

    @Test fun eachEntryOpensItsOwnProtectedReader() {
        val api = Api(protectedNativeV2Enabled = true, memberships = owner)
        val books = BooksApi()
        val store = ConnectedStore(api, scope, memoryCommunityApi = books, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(base.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = "zh")
            }
        }
        rule.onNodeWithTag("home-memory-section").assertDoesNotExist()
        signIn(store)
        rule.waitUntil(5_000) { store.state.value.library == "family" }

        rule.onNodeWithText("家庭回忆").assertExists()
        rule.onNodeWithText("一段已保存的故事，逐章阅读").assertExists()
        rule.onNodeWithText("集中翻阅较长的家庭回忆").assertExists()
        captureHomeAt150Percent()
        rule.onNodeWithTag("open-saved-memory-stories").performClick()
        rule.waitUntil(5_000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-stories").assertExists()
        assertEquals(1, api.storyRequests)
        rule.onNodeWithTag("saved-memory-close").performClick()
        rule.waitUntil(5_000) { store.state.value.savedMemoryStories == null }

        rule.onNodeWithTag("open-memory-books").performClick()
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.result != null }
        rule.onNodeWithTag("memory-books").assertExists()
        assertEquals(1, books.listRequests)
    }

    @Test fun privateSectionDoesNotAppearWithoutFeatureFlagsOrMembership() {
        val disabledApi = Api(protectedNativeV2Enabled = false, memberships = owner)
        val disabledStore = ConnectedStore(disabledApi, scope)
        rule.setContent { ConnectedApp(disabledStore, initialLanguage = "zh") }
        rule.onNodeWithTag("home-memory-section").assertDoesNotExist()
        signIn(disabledStore)
        rule.onNodeWithTag("home-memory-section").assertDoesNotExist()
        assertEquals(0, disabledApi.storyRequests)
    }

    @Test fun privateSectionDoesNotAppearWithoutAvailableMembership() {
        val noMembershipApi = Api(protectedNativeV2Enabled = true, memberships = emptyList())
        val noMembershipStore = ConnectedStore(noMembershipApi, scope, memoryCommunityApi = BooksApi(), memoryCommunityEnabled = true)
        rule.setContent { ConnectedApp(noMembershipStore, initialLanguage = "zh") }
        rule.onNodeWithTag("home-memory-section").assertDoesNotExist()
        signIn(noMembershipStore)
        rule.onNodeWithTag("home-memory-section").assertDoesNotExist()
        assertEquals(0, noMembershipApi.storyRequests)
    }

    @Test fun storyOnlyFeatureUsesMatchingIntroWithoutAutomaticRequests() {
        val api = Api(protectedNativeV2Enabled = true, memberships = owner)
        val store = ConnectedStore(api, scope)
        rule.setContent { ConnectedApp(store, initialLanguage = "zh") }
        signIn(store)
        rule.waitUntil(5_000) { store.state.value.library == "family" }

        rule.onNodeWithTag("home-memory-section").assertExists()
        rule.onNodeWithTag("open-saved-memory-stories").assertExists()
        rule.onNodeWithTag("open-memory-books").assertDoesNotExist()
        rule.onNodeWithText("打开一段已保存的故事，按章节回看。").assertExists()
        assertEquals(0, api.storyRequests)
    }

    @Test fun booksOnlyFeatureUsesMatchingIntroWithoutAutomaticRequests() {
        val api = Api(protectedNativeV2Enabled = false, memberships = owner)
        val books = BooksApi()
        val store = ConnectedStore(api, scope, memoryCommunityApi = books, memoryCommunityEnabled = true)
        rule.setContent { ConnectedApp(store, initialLanguage = "zh") }
        signIn(store)
        rule.waitUntil(5_000) { store.state.value.library == "family" }

        rule.onNodeWithTag("home-memory-section").assertExists()
        rule.onNodeWithTag("open-saved-memory-stories").assertDoesNotExist()
        rule.onNodeWithTag("open-memory-books").assertExists()
        rule.onNodeWithText("翻阅集中整理的较长家庭回忆册。").assertExists()
        assertEquals(0, api.storyRequests)
        assertEquals(0, books.listRequests)
    }

    @Test fun privateSectionIsHiddenWhileSessionIsCovered() {
        val api = Api(protectedNativeV2Enabled = true, memberships = owner)
        val store = ConnectedStore(api, scope, memoryCommunityApi = BooksApi(), memoryCommunityEnabled = true)
        rule.setContent { ConnectedApp(store, initialLanguage = "zh") }
        signIn(store)
        rule.waitUntil(5_000) { store.state.value.library == "family" }
        rule.runOnUiThread { store.background() }
        rule.waitUntil(5_000) { store.state.value.covered }
        rule.onNodeWithTag("home-memory-section").assertDoesNotExist()
        rule.onNodeWithText("检查会话期间，私人内容已遮盖。").assertExists()
        rule.runOnUiThread { store.foreground() }
        rule.waitUntil(5_000) { !store.state.value.covered && store.state.value.library == "family" }
        rule.onNodeWithTag("home-memory-section").assertExists()
    }
}
