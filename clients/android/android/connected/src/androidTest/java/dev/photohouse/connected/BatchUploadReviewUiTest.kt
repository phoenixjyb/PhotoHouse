package dev.photohouse.connected

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
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

/** Synthetic review states only; never reads media, contacts a server, or opens a picker. */
@RunWith(AndroidJUnit4::class)
class BatchUploadReviewUiTest {
    @get:Rule val rule = createAndroidComposeRule<androidx.activity.ComponentActivity>()
    @Test fun chineseEmptyFullAndReadyAt150Percent() = review(true)
    @Test fun englishEmptyFullAndReadyAt150Percent() = review(false)

    private fun review(zh: Boolean) {
        val issue = mutableStateOf<BatchUploadEnqueueIssue?>(BatchUploadEnqueueIssue.EMPTY_SELECTION)
        var starts = 0
        var discards = 0
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                        BatchUploadReviewCard(
                            selectedCount = if (issue.value == BatchUploadEnqueueIssue.EMPTY_SELECTION) 0 else 3,
                            selectedBytes = if (issue.value == BatchUploadEnqueueIssue.EMPTY_SELECTION) 0 else 8192,
                            skippedCount = if (issue.value == BatchUploadEnqueueIssue.EMPTY_SELECTION) 2 else 0,
                            availableSlots = if (issue.value == BatchUploadEnqueueIssue.QUEUE_LIMIT) 2 else 100,
                            destinationLabel = if (zh) "合成测试相册" else "Synthetic test library",
                            issue = issue.value, needsNetworkConfirmation = false, zh = zh,
                            onStart = { starts++ }, onDiscard = { discards++ },
                        )
                    }
                }
            }
        }
        for ((index, value) in listOf(BatchUploadEnqueueIssue.EMPTY_SELECTION, BatchUploadEnqueueIssue.QUEUE_LIMIT, null).withIndex()) {
            rule.runOnIdle { issue.value = value }
            if (value == null) {
                rule.onNodeWithTag("batch-review-problem").assertDoesNotExist()
                rule.onNodeWithTag("batch-start").performScrollTo().assertIsEnabled()
            } else {
                rule.onNodeWithTag("batch-review-problem").performScrollTo().assertIsDisplayed()
                rule.onNodeWithTag("batch-start").performScrollTo().assertIsNotEnabled()
            }
            rule.onNodeWithTag("batch-discard").assertIsDisplayed().assertIsEnabled()
            rule.runOnIdle { assertEquals(0, starts); assertEquals(0, discards) }
            saveRender("upload-review-$index-${if (zh) "zh" else "en"}-150.png")
        }
        rule.onNodeWithTag("batch-start").performClick()
        rule.onNodeWithTag("batch-discard").performClick()
        rule.runOnIdle { assertEquals(1, starts); assertEquals(1, discards) }
    }

    @Test fun chineseNetworkChangeRequiresVisibleReview() = networkChange(true)
    @Test fun englishNetworkChangeRequiresVisibleReview() = networkChange(false)

    private fun networkChange(zh: Boolean) {
        // The network changes without recomposition, just as it can while a picker is open.
        var currentNetwork = UploadNetwork.UNMETERED
        val forcedReview = mutableStateOf(false)
        val approved = mutableStateOf(false)
        var starts = 0
        rule.setContent {
            val density = LocalDensity.current
            val visibleConfirmation = !approved.value && forcedReview.value
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                        BatchUploadReviewCard(3, 8192, 0, 100,
                            if (zh) "合成测试相册" else "Synthetic test library", null,
                            visibleConfirmation, zh,
                            onStart = {
                                when (batchUploadStartDecision(currentNetwork, approved.value, visibleConfirmation)) {
                                    BatchUploadStartDecision.REQUIRE_NETWORK_REVIEW -> forcedReview.value = true
                                    BatchUploadStartDecision.ACKNOWLEDGE_NETWORK_REVIEW -> approved.value = true
                                    BatchUploadStartDecision.START -> starts++
                                }
                            }, onDiscard = {})
                    }
                }
            }
        }
        rule.onNodeWithTag("batch-start").assertTextEquals(if (zh) "开始" else "Start")
        rule.runOnIdle { currentNetwork = UploadNetwork.METERED }
        rule.onNodeWithTag("batch-start").performClick()
        rule.runOnIdle { assertEquals(0, starts); assertEquals(false, approved.value) }
        rule.onNodeWithTag("batch-network-review").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("batch-start").performScrollTo().assertTextEquals(if (zh) "继续" else "Continue")
        saveRender("upload-network-${if (zh) "zh" else "en"}-150.png")
        rule.onNodeWithTag("batch-start").performClick()
        rule.runOnIdle { assertEquals(0, starts); assertEquals(true, approved.value) }
        rule.onNodeWithTag("batch-network-review").assertDoesNotExist()
        rule.onNodeWithTag("batch-start").assertTextEquals(if (zh) "开始" else "Start").performClick()
        rule.runOnIdle { assertEquals(1, starts) }
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
            put(android.provider.MediaStore.Images.Media.RELATIVE_PATH, "Pictures/PhotoHouseUploadRecovery")
        }
        val uri = checkNotNull(context.contentResolver.insert(android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values))
        try {
            context.contentResolver.openOutputStream(uri).use { stream ->
                checkNotNull(stream)
                check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, stream))
            }
        } finally { bitmap.recycle() }
    }
}
