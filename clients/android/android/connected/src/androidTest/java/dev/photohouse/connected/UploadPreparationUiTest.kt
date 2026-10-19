package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Only generated metadata: no network, account, file picker or upload side effects. */
@RunWith(AndroidJUnit4::class)
class UploadPreparationUiTest {
    @get:Rule val rule = createAndroidComposeRule<androidx.activity.ComponentActivity>()
    private val receipt = UploadHistoryItem("1", 1760000000, 100, "image", "available", "family")
    private fun preparation(state: UploadPreparationStageState = UploadPreparationStageState.FINISHED,
                            row: UploadHistoryItem = receipt): UploadPreparationState {
        val stages = UploadPreparationStage.entries.associateWith {
            if (it == UploadPreparationStage.VIDEO_PROBE) UploadPreparationStageState.NOT_APPLICABLE else state
        }
        return UploadPreparationState(UploadPreparationStatus.AVAILABLE, 1, 1,
            listOf(UploadPreparationItem(row, UploadProcessingEvidence(stages,
                UploadPreparationRecords(true, true, false),
                mapOf("preview" to UploadPreparationAvailability.UNKNOWN, "playback" to UploadPreparationAvailability.NOT_APPLICABLE)))))
    }

    @Test fun chineseEndedTasksNeverClaimViewablePreviewAndDetailsDoNotSubmitWork() = finishedTasks(true)
    @Test fun englishEndedTasksNeverClaimViewablePreviewAndDetailsDoNotSubmitWork() = finishedTasks(false)
    private fun finishedTasks(zh: Boolean) {
        var reads = 0; var writes = 0
        rule.setContent { LargeText {
            ImportStatusPanel(emptyList(), UploadHistoryState(1, 1, listOf(receipt)), setOf("family"), zh,
                true, false, true, {}, {}, { reads++ }, { reads++ }, {}, { writes++ }, {}, {}, {},
                { _, _, _ -> writes++ }, { _, _, _ -> writes++ }, {}, {}, preparation = preparation())
        } }
        rule.onNodeWithText(if (zh) "处理任务已结束" else "Processing tasks ended").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("upload-preview-unverified-1").assertTextEquals(if (zh) "预览：尚未验证" else "Preview: not verified")
        rule.onNodeWithTag("upload-preparation-stage-1-CAPTION").assertDoesNotExist()
        rule.onNodeWithTag("upload-preparation-toggle-1").performScrollTo().performClick()
        rule.onNodeWithTag("upload-preparation-stage-1-CAPTION").performScrollTo()
            .assertTextEquals(if (zh) "影像描述任务 · 已结束" else "Description task · Ended")
        saveRender("preparation-ended-${if (zh) "zh" else "en"}-150.png")
        rule.onNodeWithTag("upload-preparation-toggle-1").performScrollTo().performClick()
        rule.onNodeWithTag("upload-preparation-stage-1-CAPTION").assertDoesNotExist()
        rule.runOnIdle { assertEquals(0, reads); assertEquals(0, writes) }
    }

    @Test fun failureAndRevokedAccessDoNotOfferUploadRetryOrExposeOldEvidence() {
        val access = mutableStateOf(setOf("family")); var reads = 0; var writes = 0
        rule.setContent { LargeText {
            ImportStatusPanel(emptyList(), UploadHistoryState(1, 1, listOf(receipt)), access.value, true,
                true, false, true, {}, {}, { reads++ }, { reads++ }, {}, { writes++ }, {}, { writes++ }, {},
                { _, _, _ -> writes++ }, { _, _, _ -> writes++ }, {}, {}, preparation = preparation(UploadPreparationStageState.DEAD))
        } }
        rule.onNodeWithText("部分处理需检查").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("服务器已收到此文件，可稍后重查或联系相册主人，无需重复上传。").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("batch-retry").assertDoesNotExist()
        rule.onNodeWithTag("import-check-server").performScrollTo().performClick()
        rule.runOnIdle { assertEquals(1, reads); assertEquals(0, writes); access.value = emptySet() }
        rule.onNodeWithTag("upload-preparation-1").assertDoesNotExist()
        rule.onNodeWithTag("import-history-1").performScrollTo().assertTextEquals("#1 · 当前不可用")
        saveRender("preparation-revoked-zh-150.png")
    }

    @Test fun foreignReceiptAndUnavailableServerKeepReceiptWithoutProcessingDetails() {
        val state = mutableStateOf<UploadPreparationState?>(preparation(row = receipt.copy(libraryId = "other")))
        rule.setContent { LargeText {
            ImportStatusPanel(emptyList(), UploadHistoryState(1, 1, listOf(receipt)), setOf("family"), true,
                true, false, true, {}, {}, {}, {}, {}, {}, {}, {}, {},
                { _, _, _ -> }, { _, _, _ -> }, {}, {}, preparation = state.value)
        } }
        rule.onNodeWithTag("import-history-1").performScrollTo().assertTextEquals("#1 · 已加入资料库")
        rule.onNodeWithTag("upload-preparation-toggle-1").assertDoesNotExist()
        rule.onNodeWithTag("upload-preparation-unknown-1").assertExists()
        rule.runOnIdle { state.value = UploadPreparationState(UploadPreparationStatus.UNAVAILABLE, 1, 1) }
        rule.onNodeWithTag("upload-preparation-notice").performScrollTo()
            .assertTextEquals("处理进度暂不可用，可刷新重查，无需重复上传已收到的文件。")
        rule.onNodeWithTag("import-history-1").assertExists()
        rule.runOnIdle { state.value = UploadPreparationState(UploadPreparationStatus.UNSUPPORTED, 1, 1) }
        rule.onNodeWithTag("upload-preparation-notice").assertTextEquals("当前服务器暂不提供处理进度，上传记录仍可查看。")
        saveRender("preparation-unsupported-zh-150.png")
    }

    @Composable private fun LargeText(content: @Composable () -> Unit) {
        val density = LocalDensity.current
        CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
            PhotoHouseTheme { Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) { content() } }
        }
    }
    private fun saveRender(name: String) {
        rule.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        val committed = java.util.concurrent.CountDownLatch(1)
        instrumentation.runOnMainSync {
            rule.activity.window.decorView.viewTreeObserver.registerFrameCommitCallback { committed.countDown() }
            rule.activity.window.decorView.invalidate()
        }
        check(committed.await(5, java.util.concurrent.TimeUnit.SECONDS))
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        val values = android.content.ContentValues().apply {
            put(android.provider.MediaStore.Images.Media.DISPLAY_NAME, name)
            put(android.provider.MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(android.provider.MediaStore.Images.Media.RELATIVE_PATH, "Pictures/PhotoHousePreparation")
        }
        val uri = checkNotNull(instrumentation.targetContext.contentResolver.insert(android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values))
        try { instrumentation.targetContext.contentResolver.openOutputStream(uri).use { checkNotNull(it); check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)) } }
        finally { bitmap.recycle() }
    }
}
