package dev.photohouse.connected

import android.graphics.Bitmap
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import org.junit.*
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
@OptIn(ExperimentalTestApi::class)
class MemoryGroupsUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val first = Asset("101", "image", 800, 600, null, "2026-01-01T10:00:00", "/assets/101/thumbnail?library=family-a")
    private val second = first.copy(id = "102", thumbnail_url = "/assets/102/thumbnail?library=family-a")
    private val source = ProtectedStory("11111111-1111-4111-8111-111111111111", "101", "湖边的一天", "我们沿着湖边散步，一起看夕阳。", "zh", "合成家人", "synthetic", 1, 1, 1, true, true)
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
    private val groupId = "22222222-2222-4222-8222-222222222222"
    @After fun stop() { scope.cancel() }
    private inner class Api : MemoryGroupsApi {
        override val memoryGroupsEnabled = true
        var result: MemoryGroup? = null
        val mutations = mutableListOf<MemoryGroupMutation>()
        var loseFirstSave = true
        val requests = mutableListOf<Pair<List<String>, List<String>>>()
        override suspend fun capabilities(token: Bearer, library: String) = MemoryGroupsCapabilities(true, true, true, 24, true)
        override suspend fun list(token: Bearer, library: String, assetId: String) = MemoryGroupPage(library, assetId, false, listOfNotNull(result))
        override suspend fun proposals(token: Bearer, library: String, seedIds: List<String>, excludedIds: List<String>): MemoryGroupProposals {
            requests += seedIds.toList() to excludedIds.toList()
            return MemoryGroupProposals(library, seedIds, true, MemoryGroupProposalStatus.READY,
                if (second.id in excludedIds) emptyList() else listOf(MemoryGroupCandidate(second, "101", "within_recorded_window")))
        }
        override suspend fun save(token: Bearer, library: String, mutation: MemoryGroupMutation): MemoryGroup {
            mutations += mutation
            result = MemoryGroup(groupId, library, mutation.revision + 1, mutation.theme, mutation.assetIds, mutation.excludedAssetIds,
                mutation.sourceStoryIds, listOf(first, second).filter { it.id in mutation.assetIds },
                if (source.id in mutation.sourceStoryIds) listOf(source) else emptyList(), true)
            if (loseFirstSave) { loseFirstSave = false; throw ApiFailure(FailureKind.OFFLINE) }
            return result!!
        }
    }
    @Test fun suggestionReviewExactRetryAndBilingualLargeText() {
        val api = Api()
        val store = MemoryGroupsStore(api, scope, token, "family-a", first, listOf(first, second), listOf(source), { true }, {},
            preview = { generatedPreview() })
        var zh by mutableStateOf(true)
        rule.setContent { CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, 1.5f)) {
            PhotoHouseTheme { MemoryGroupsDialog(store, zh) { discard -> if (discard || store.canClose()) { store.close(); true } else false } }
        } }
        rule.runOnIdle { store.load() }
        rule.waitUntil(5000) { store.state.value.phase == MemoryGroupsStorePhase.READY }
        scrollTo("memory-group-create").performClick()
        scrollTo("memory-group-source-${source.id}").performClick()
        scrollTo("memory-group-suggest").performClick()
        rule.waitUntil(5000) { store.state.value.proposals != null }
        scrollTo("memory-group-select-102").assertIsOff().performClick()
        Assert.assertEquals(listOf("101", "102"), store.state.value.selectedAssetIds)
        scrollTo("memory-group-review").performClick()
        scrollTo("memory-group-save").assertIsDisplayed()
        val command = InstrumentationRegistry.getInstrumentation().uiAutomation.executeShellCommand("input keyevent KEYCODE_TAB")
        android.os.ParcelFileDescriptor.AutoCloseInputStream(command).use { it.readBytes() }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-group-save").performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-group-save").assertIsFocused()
        capture("memory-group-review-zh150.png")
        rule.onNodeWithTag("memory-group-save").performClick()
        rule.waitUntil(5000) { store.state.value.phase == MemoryGroupsStorePhase.UNCERTAIN }
        scrollTo("memory-group-retry").assertIsDisplayed()
        rule.onNodeWithTag("memory-groups-close").performClick()
        rule.onNodeWithText("继续编辑").performClick()
        scrollTo("memory-group-retry").performClick()
        rule.waitUntil(5000) { store.state.value.phase == MemoryGroupsStorePhase.SAVED }
        Assert.assertEquals(2, api.mutations.size); Assert.assertEquals(api.mutations[0], api.mutations[1])
        scrollTo("memory-group-saved").assertIsDisplayed()
        rule.runOnIdle { zh = false }
        scrollToText("Told by: 合成家人").assertIsDisplayed()
        rule.onNodeWithText(source.text).assertExists()
        capture("memory-group-saved-en150.png")
    }
    @Test fun otherMemberKeepsOriginalAndManualAdjustments() {
        val api = Api().apply { loseFirstSave = false; result = MemoryGroup(groupId, "family-a", 1, "trip",
            listOf("101", "102"), emptyList(), listOf(source.id), listOf(first, second), listOf(source), true) }
        val store = MemoryGroupsStore(api, scope, token, "family-a", second, listOf(first, second), emptyList(), { true }, {})
        rule.setContent { PhotoHouseTheme { MemoryGroupsDialog(store, true) { false } } }
        rule.runOnIdle { store.load() }
        rule.waitUntil(5000) { store.state.value.phase == MemoryGroupsStorePhase.READY }
        rule.onNodeWithText(source.text).assertExists()
        scrollTo("memory-group-edit-$groupId").performClick()
        scrollTo("memory-group-source-${source.id}").assertIsOn()
        scrollTo("memory-group-member-102-action").performClick()
        Assert.assertEquals(listOf("101"), store.state.value.selectedAssetIds)
        Assert.assertEquals(listOf(source.id), store.state.value.sourceStoryIds)
        scrollTo("memory-group-review").performClick()
        scrollTo("memory-group-save").performClick()
        rule.waitUntil(5000) { store.state.value.phase == MemoryGroupsStorePhase.SAVED }
        Assert.assertEquals(listOf("101"), api.mutations.single().assetIds)
        Assert.assertEquals(listOf("102"), api.mutations.single().excludedAssetIds)
        scrollTo("memory-group-edit-$groupId").performClick()
        Assert.assertEquals(MemoryGroupsStorePhase.EDITING, store.state.value.phase)
    }
    private fun scrollTo(tag: String): SemanticsNodeInteraction {
        rule.onNodeWithTag("memory-groups-content").performScrollToNode(hasTestTag(tag))
        return rule.onNodeWithTag(tag)
    }
    private fun scrollToText(text: String): SemanticsNodeInteraction {
        rule.onNodeWithTag("memory-groups-content").performScrollToNode(hasText(text))
        return rule.onNodeWithText(text)
    }
    private fun generatedPreview(): ByteArray {
        val bitmap = Bitmap.createBitmap(240, 180, Bitmap.Config.ARGB_8888)
        val canvas = android.graphics.Canvas(bitmap)
        canvas.drawColor(android.graphics.Color.rgb(184, 207, 188))
        val paint = android.graphics.Paint().apply { color = android.graphics.Color.rgb(241, 214, 146) }
        canvas.drawCircle(170f, 45f, 24f, paint)
        paint.color = android.graphics.Color.rgb(70, 121, 118)
        canvas.drawRect(0f, 110f, 240f, 180f, paint)
        val output = java.io.ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.PNG, 100, output); bitmap.recycle()
        return output.toByteArray()
    }
    private fun capture(name: String) {
        val bitmap = rule.onNodeWithTag("memory-groups-dialog").captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        File(context.filesDir, name).outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
}
