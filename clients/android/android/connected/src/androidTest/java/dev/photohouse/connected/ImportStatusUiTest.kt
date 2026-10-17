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
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Synthetic metadata and callback counts only. No SAF, server, recording or upload is used. */
@RunWith(AndroidJUnit4::class)
class ImportStatusUiTest {
    @get:Rule val rule = createAndroidComposeRule<androidx.activity.ComponentActivity>()
    private fun item(id: String = "one", batch: String = "batch-a", status: String = "complete", bytes: Long = 100, offset: Long = bytes) =
        UploadQueueItem(UploadQueueRecord(id, "request-$id", batch, "synthetic-$id.jpg", null, bytes,
            UploadKind.IMAGE, "", offset = offset, status = status, destinationLibraryId = "family", assetId = "1"))
    private fun history() = UploadHistoryState(1, 3, listOf(
        UploadHistoryItem("1", 1760000000, 100, "image", "available", "family"),
        UploadHistoryItem("2", 1760000000, 100, "image", "awaiting_review", null),
        UploadHistoryItem("3", 1760000000, 100, "image", "unavailable", null)))

    @Test fun chineseHistorySeparatesAssignmentFromPreparationAndRevocation() = historyStates(true)
    @Test fun englishHistorySeparatesAssignmentFromPreparationAndRevocation() = historyStates(false)
    private fun historyStates(zh: Boolean) {
        val access = mutableStateOf(setOf("family"))
        val current = mutableStateOf(history())
        var writes = 0; var reads = 0; var opens = 0
        rule.setContent { LargeText {
            ImportStatusPanel(listOf(item()), current.value, access.value, zh, true, true, true,
                {}, {}, { reads++ }, { reads++ }, {}, { writes++ }, { writes++ }, { writes++ }, { writes++ },
                { _, _, _ -> writes++ }, { _, _, _ -> writes++ }, { opens++ }, { writes++ })
        } }
        rule.runOnIdle { assertEquals(0, writes); assertEquals(0, reads); assertEquals(0, opens) }
        rule.onNodeWithTag("import-check-server").performScrollTo().performClick()
        rule.runOnIdle { assertEquals(1, reads); assertEquals(0, writes) }
        rule.onNodeWithTag("batch-status-one").performScrollTo()
            .assertTextEquals(if (zh) "已加入资料库" else "Added to library")
        rule.onNodeWithTag("import-preparation-one").performScrollTo().assertIsDisplayed()
        saveRender("import-assignment-${if (zh) "zh" else "en"}-150.png")
        rule.onNodeWithTag("import-history-2").performScrollTo().assertTextEquals(if (zh) "#2 · 等待主人审核" else "#2 · Awaiting owner review")
        rule.onNodeWithTag("import-history-3").performScrollTo().assertTextEquals(if (zh) "#3 · 当前不可用" else "#3 · Currently unavailable")
        rule.onNodeWithTag("import-history-1").performScrollTo().assertTextEquals(if (zh) "#1 · 已加入资料库" else "#1 · Added to library")
        rule.onNodeWithText(if (zh) "打开" else "Open").performScrollTo().performClick()
        rule.runOnIdle { assertEquals(1, opens); assertEquals(0, writes); access.value = emptySet() }
        rule.onNodeWithTag("import-history-1").performScrollTo().assertTextEquals(if (zh) "#1 · 当前不可用" else "#1 · Currently unavailable")
        rule.onNodeWithText(if (zh) "打开" else "Open").assertDoesNotExist()
        rule.onNodeWithTag("upload-history-descriptions-1").assertDoesNotExist()
        rule.onNodeWithTag("batch-describe-item-one").assertDoesNotExist()
        saveRender("import-access-${if (zh) "zh" else "en"}-150.png")
    }

    @Test fun historyRefreshHidesStaleApprovalAndRequiresExplicitRead() {
        val current = mutableStateOf(history())
        var reads = 0; var changes = 0
        rule.setContent { LargeText {
            ImportStatusPanel(listOf(item()), current.value, setOf("family"), true, true, true, true,
                {}, {}, { reads++ }, { reads++ }, {}, { changes++ }, { changes++ }, { changes++ }, { changes++ },
                { _, _, _ -> changes++ }, { _, _, _ -> changes++ }, { changes++ }, { changes++ })
        } }
        rule.onNodeWithTag("batch-status-one").performScrollTo().assertTextEquals("已加入资料库")
        rule.runOnIdle { current.value = current.value.copy(busy = true) }
        rule.onNodeWithTag("batch-status-one").assertTextEquals("已上传，审核状态待确认")
        rule.onNodeWithTag("import-history-1").assertDoesNotExist()
        rule.onNodeWithTag("import-check-server").performScrollTo().assertIsNotEnabled()
        rule.runOnIdle { current.value = current.value.copy(busy = false, unavailable = true) }
        rule.onNodeWithTag("import-server-unavailable").performScrollTo().assertIsDisplayed()
        saveRender("import-unavailable-zh-150.png")
        rule.runOnIdle { assertEquals(0, reads); assertEquals(0, changes) }
        rule.onNodeWithTag("upload-history-refresh-collapsed").performScrollTo().performClick()
        rule.runOnIdle { assertEquals(1, reads); assertEquals(0, changes) }
    }

    @Test fun batchesFoldAndPausedProgressUsesCommittedBytesWithoutAutoResume() {
        val queue = listOf(item("paused", status = "paused", bytes = 10, offset = 4).copy(sent = 9))
        var resumes = 0; var cancels = 0
        val items = mutableStateOf(queue)
        val expanded = mutableStateOf(true)
        val workspace = mutableStateOf(true)
        rule.setContent { LargeText {
            ImportStatusPanel(items.value, null, setOf("family"), false, true, expanded.value, false,
                { expanded.value = !expanded.value }, {}, {}, {}, {}, {}, { resumes++ }, {}, { cancels++ },
                { _, _, _ -> }, { _, _, _ -> }, {}, {},
                workspaceExpanded = workspace.value, onToggleWorkspace = { workspace.value = !workspace.value })
        } }
        rule.onNodeWithTag("import-byte-progress").performScrollTo().assertTextEquals("4.0 bytes / 10.0 bytes")
        rule.runOnIdle { assertEquals(0, resumes); assertEquals(0, cancels) }
        rule.onNodeWithTag("batch-resume").performScrollTo().performClick()
        rule.runOnIdle { assertEquals(1, resumes); items.value = (1..4).map { item("a$it", batch = "batch-new") } + (1..4).map { item("b$it", batch = "batch-b") } }
        rule.onNodeWithTag("batch-status-a1").assertDoesNotExist()
        rule.onNodeWithTag("import-batch-toggle-batch-new").performScrollTo().performClick()
        rule.onNodeWithTag("batch-status-a1").assertExists()
        rule.onNodeWithTag("import-batch-toggle-batch-new").performScrollTo().performClick()
        rule.onNodeWithTag("batch-status-a1").assertDoesNotExist()
        rule.onNodeWithTag("batch-status-b1").assertDoesNotExist()
        rule.onNodeWithTag("import-batch-toggle-batch-b").performScrollTo().assertIsDisplayed()
        saveRender("import-batches-en-150.png")
        rule.onNodeWithTag("batch-queue-toggle").performScrollTo().performClick()
        rule.onNodeWithTag("import-batch-toggle-batch-b").assertDoesNotExist()
        rule.onNodeWithTag("import-workspace-toggle").performScrollTo().performClick()
        rule.onNodeWithTag("batch-queue").assertDoesNotExist()
        saveRender("import-collapsed-en-150.png")
        rule.runOnIdle { assertEquals(1, resumes); assertEquals(0, cancels) }
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
        val context = instrumentation.targetContext
        val values = android.content.ContentValues().apply {
            put(android.provider.MediaStore.Images.Media.DISPLAY_NAME, name)
            put(android.provider.MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(android.provider.MediaStore.Images.Media.RELATIVE_PATH, "Pictures/PhotoHouseImportStatus")
        }
        val uri = checkNotNull(context.contentResolver.insert(android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values))
        try { context.contentResolver.openOutputStream(uri).use { stream -> checkNotNull(stream); check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, stream)) } }
        finally { bitmap.recycle() }
    }
}
