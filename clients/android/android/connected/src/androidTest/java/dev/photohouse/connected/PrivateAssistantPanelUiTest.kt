package dev.photohouse.connected

import android.content.ContentValues
import android.provider.MediaStore
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextReplacement
import androidx.compose.ui.test.getBoundsInRoot
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.unit.Density
import androidx.activity.ComponentActivity
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.AssistantWorkspaceCapabilities
import dev.photohouse.connected.core.AssistantWorkspaceExchange
import dev.photohouse.connected.core.AssistantWorkspacePendingTurn
import dev.photohouse.connected.core.AssistantWorkspacePreferences
import dev.photohouse.connected.core.AssistantWorkspaceState
import dev.photohouse.connected.core.AssistantWorkspaceThreadDetail
import dev.photohouse.connected.core.AssistantWorkspaceThreadList
import dev.photohouse.connected.core.AssistantWorkspaceThreadSummary
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Synthetic private workspace UI. No store, network, recorder, or inference provider is used. */
@RunWith(AndroidJUnit4::class)
class PrivateAssistantPanelUiTest {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()

    private val libraryId = "synthetic-library"
    private val threadId = "123e4567-e89b-42d3-a456-426614174101"
    private val requestId = "123e4567-e89b-42d3-a456-426614174102"
    private val createdAt = "2026-10-10T08:00:00Z"

    private val capabilities = AssistantWorkspaceCapabilities(
        version = 1,
        available = true,
        threads = true,
        preferences = true,
        preferencesApplied = true,
        serverOwnedTurns = true,
        appliedPreferences = setOf("locale"),
    )

    private fun thread(exchangeCount: Int = 2) = AssistantWorkspaceThreadSummary(
        threadId = threadId,
        libraryId = libraryId,
        createdAt = createdAt,
        updatedAt = createdAt,
        expiresAt = "2026-11-09T08:00:00Z",
        revision = exchangeCount.toLong(),
        exchangeCount = exchangeCount,
    )

    private fun exchange(index: Int, input: String, reply: String) = AssistantWorkspaceExchange(
        exchangeId = "exchange-$index",
        revision = index.toLong(),
        createdAt = createdAt,
        expiresAt = "2026-11-09T08:00:00Z",
        inputText = input,
        reply = reply,
        cards = emptyList(),
        receiptCount = 0,
        requestId = null,
    )

    private fun state(
        exchanges: List<AssistantWorkspaceExchange> = listOf(
            exchange(1, "旅行时拍下的老照片在哪里？", "我可以帮你查看这个资料库里的照片。"),
            exchange(2, "谢谢，先不用打开照片。", "好的，我会先保留在这段私人对话里。"),
        ),
        draft: String = "",
        pending: Boolean = false,
    ): AssistantWorkspaceState {
        val detailThread = thread(exchanges.size + if (pending) 1 else 0)
        return AssistantWorkspaceState(
            accountId = "synthetic-account",
            libraryId = libraryId,
            generation = 1,
            capabilities = capabilities,
            threads = AssistantWorkspaceThreadList(1, listOf(detailThread)),
            detail = AssistantWorkspaceThreadDetail(1, detailThread, exchanges),
            draft = draft,
            pendingTurn = if (pending) AssistantWorkspacePendingTurn(
                threadId = threadId,
                requestId = requestId,
                expectedRevision = detailThread.revision,
                text = "上一条已提交的问题",
            ) else null,
            uncertain = pending,
            preferences = AssistantWorkspacePreferences(1, "zh", null, null, 1),
            unsupportedPreferences = emptySet(),
            continuationEnabled = true,
        )
    }

    private class Callbacks {
        val drafts = mutableListOf<String>()
        val openedThreads = mutableListOf<String>()
        val locales = mutableListOf<String?>()
        val openedAssets = mutableListOf<String>()
        var sends = 0
        var recoveries = 0
        var deletes = 0
        var newThreads = 0
        var refreshes = 0
        var dismissals = 0
    }

    @Suppress("DEPRECATION")
    private fun show(
        state: MutableState<AssistantWorkspaceState>,
        zh: Boolean,
        callbacks: Callbacks,
        fontScale: Float = 1.5f,
    ) {
        rule.activity.runOnUiThread {
            rule.activity.window.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        }
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, fontScale)) {
                PhotoHouseTheme {
                    PrivateAssistantPanel(
                        state = state.value,
                        zh = zh,
                        onNew = { callbacks.newThreads++ },
                        onRefresh = { callbacks.refreshes++ },
                        onOpenThread = { callbacks.openedThreads += it },
                        onDraft = {
                            callbacks.drafts += it
                            state.value = state.value.copy(draft = it)
                        },
                        onSend = { callbacks.sends++ },
                        onRecover = { callbacks.recoveries++ },
                        onDelete = { callbacks.deletes++ },
                        onSetLocale = { callbacks.locales += it },
                        onDismiss = { callbacks.dismissals++ },
                        onOpenAsset = { callbacks.openedAssets += it },
                    )
                }
            }
        }
        rule.waitForIdle()
    }

    @Test
    fun chineseHistoryShowsPlainTextWithoutOpeningItemsOrStartingAudio() {
        val privateText = "保持原样：<img src=x onerror=alert(1)>"
        val uiState = mutableStateOf(state(exchanges = listOf(
            exchange(1, "家庭相册里这句应保持纯文本：$privateText", "这段回复只显示为私人对话文字。"),
        )))
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks)

        rule.onNodeWithTag("private-assistant-history-heading").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-exchange-0").assertIsDisplayed()
        rule.onNodeWithText("家庭相册里这句应保持纯文本：$privateText").assertIsDisplayed()
        rule.onNodeWithText("这段回复只显示为私人对话文字。").assertIsDisplayed()
        rule.onNodeWithText("播放", substring = true).assertDoesNotExist()
        rule.onNodeWithText("录音", substring = true).assertDoesNotExist()

        assertEquals(emptyList<String>(), callbacks.openedAssets)
        assertEquals(emptyList<String>(), callbacks.openedThreads)
        assertEquals(emptyList<String>(), callbacks.drafts)
        assertEquals(0, callbacks.sends)
        assertEquals(0, callbacks.recoveries)
        assertEquals(0, callbacks.deletes)
        assertEquals(0, callbacks.newThreads)
    }

    @Test
    fun pendingTurnKeepsDraftEditableAndOnlyExplicitStatusCheckCallsRecovery() {
        val uiState = mutableStateOf(state(draft = "保留这份草稿", pending = true))
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks)

        val composer = rule.onNodeWithTag("private-assistant-composer")
        composer.assertIsEnabled()
        composer.performTextReplacement("编辑后的草稿")
        rule.waitForIdle()
        composer.assertTextContains("编辑后的草稿")
        rule.onNodeWithTag("private-assistant-send").assertIsNotEnabled()
        assertEquals("编辑后的草稿", uiState.value.draft)
        assertEquals(0, callbacks.sends)
        assertEquals(0, callbacks.recoveries)

        rule.onNodeWithTag("private-assistant-recover").performScrollTo()
        rule.onNodeWithTag("private-assistant-recover").assertIsDisplayed()
        assertEquals(0, callbacks.recoveries)
        rule.onNodeWithTag("private-assistant-recover").performClick()
        assertEquals(1, callbacks.recoveries)
        assertEquals(0, callbacks.sends)
    }

    @Test
    fun localePickerOffersSystemChineseAndEnglishAndReportsOnlySelectedChoices() {
        val uiState = mutableStateOf(state())
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks)

        rule.onNodeWithTag("private-assistant-locale").performScrollTo()
        rule.onNodeWithText("回复语言").assertIsDisplayed()
        rule.onNodeWithText("跟随请求语言").assertIsDisplayed()
        rule.onNodeWithText("中文").assertIsDisplayed()
        rule.onNodeWithText("English").assertIsDisplayed()

        rule.onNodeWithText("English").performClick()
        rule.onNodeWithText("跟随请求语言").performClick()
        assertEquals(listOf("en", null), callbacks.locales)
        assertEquals(0, callbacks.sends)
    }

    @Test
    fun deleteRequiresAcknowledgementAndThenOneExplicitConfirmation() {
        val uiState = mutableStateOf(state())
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks)

        rule.onNodeWithTag("private-assistant-delete").performScrollTo()
        rule.onNodeWithTag("private-assistant-delete").performClick()
        rule.onNodeWithText("删除这段对话？").assertIsDisplayed()
        val confirm = rule.onNodeWithTag("private-assistant-delete-confirm")
        confirm.assertIsNotEnabled()
        assertEquals(0, callbacks.deletes)

        rule.onNodeWithTag("private-assistant-delete-ack").performClick()
        confirm.assertIsEnabled()
        assertEquals(0, callbacks.deletes)
        confirm.performClick()
        assertEquals(1, callbacks.deletes)
    }

    @Test
    fun largeTextHistoryScrollsToVisibleComposerAndBottomActions() {
        val exchanges = (1..12).map { index ->
            exchange(index, "第 $index 轮问题：" + "合成的家庭旅行记录 ".repeat(5), "第 $index 轮回复：" + "只用于 UI 布局检查。".repeat(5))
        }
        val uiState = mutableStateOf(state(exchanges = exchanges, draft = "底部草稿"))
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks)

        rule.onNodeWithTag("private-assistant-send").performScrollTo()
        rule.waitForIdle()
        rule.onNodeWithTag("private-assistant-composer").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-send").assertIsDisplayed()
        val root = rule.onRoot().getBoundsInRoot()
        val action = rule.onNodeWithTag("private-assistant-send")
        val fullAction = action.getUnclippedBoundsInRoot()
        val visibleAction = action.getBoundsInRoot()
        assertTrue(
            "large text should leave the bottom action fully inside the viewport: full=$fullAction visible=$visibleAction root=$root",
            fullAction.top >= root.top && fullAction.bottom <= root.bottom &&
                kotlin.math.abs(fullAction.top.value - visibleAction.top.value) < 0.5f &&
                kotlin.math.abs(fullAction.bottom.value - visibleAction.bottom.value) < 0.5f,
        )
        captureBottomScreenshot("private-assistant-zh-large-bottom")
        assertEquals(0, callbacks.sends)
        assertEquals(0, callbacks.deletes)
    }

    private fun captureBottomScreenshot(name: String) {
        val bitmap = rule.onRoot().captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val uri = requireNotNull(context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, "$name.png")
                put(MediaStore.Images.Media.MIME_TYPE, "image/png")
                put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/PhotoHousePrivateAssistant")
            }))
        try {
            context.contentResolver.openOutputStream(uri).use { output ->
                requireNotNull(output)
                assertTrue(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, output))
            }
        } finally {
            bitmap.recycle()
        }
    }
}
