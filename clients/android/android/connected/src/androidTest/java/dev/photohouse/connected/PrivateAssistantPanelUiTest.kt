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
import dev.photohouse.connected.core.AssistantSavedMemoryCard
import dev.photohouse.connected.core.AssistantSavedMemoryContext
import dev.photohouse.connected.core.AssistantSavedMemoryReference
import dev.photohouse.connected.core.AssistantWorkspaceRequestStatus
import dev.photohouse.connected.core.AssistantWorkspaceTurn
import dev.photohouse.connected.core.AssistantTurn
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

    private fun thread(exchangeCount: Int = 2, revision: Long = exchangeCount.toLong(), label: String? = null) = AssistantWorkspaceThreadSummary(
        threadId = threadId,
        libraryId = libraryId,
        createdAt = createdAt,
        updatedAt = createdAt,
        expiresAt = "2026-11-09T08:00:00Z",
        revision = revision,
        exchangeCount = exchangeCount,
        label = label,
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
        assistantCapabilities: AssistantWorkspaceCapabilities = capabilities,
        hasOlderExchanges: Boolean = false,
        threadLabel: String? = null,
        historyRefreshRequired: Boolean = false,
        includeFreshMemoryCard: Boolean = false,
    ): AssistantWorkspaceState {
        val detailRevision = (exchanges.maxOfOrNull { it.revision } ?: 0L) + if (pending) 1 else 0
        val detailThread = thread(exchanges.size + if (pending) 1 else 0, detailRevision, threadLabel)
        return AssistantWorkspaceState(
            accountId = "synthetic-account",
            libraryId = libraryId,
            generation = 1,
            capabilities = assistantCapabilities,
            threads = AssistantWorkspaceThreadList(1, listOf(detailThread)),
            detail = AssistantWorkspaceThreadDetail(1, detailThread, exchanges, hasOlderExchanges = hasOlderExchanges),
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
            continuationEnabled = assistantCapabilities.serverOwnedTurns,
            historyRefreshRequired = historyRefreshRequired,
            savedMemoryCardsAvailable = includeFreshMemoryCard,
            currentTurn = if (includeFreshMemoryCard) {
                val card = AssistantSavedMemoryCard("story", "123e4567-e89b-42d3-a456-426614174103", "2",
                    "a".repeat(64), "Garden day", "The family walked beside the lake and shared a picnic.")
                AssistantWorkspaceTurn(1, threadId, requestId, AssistantWorkspaceRequestStatus.COMPLETED, detailRevision,
                    false, null, AssistantTurn("memory_cards", "Found one saved memory.", null, null, emptyList(), 1, false, null,
                        memoryCards = listOf(card), savedMemoryContext = AssistantSavedMemoryContext(libraryId, "b".repeat(64),
                            listOf(AssistantSavedMemoryReference(card.kind, card.id, card.revision, card.sourceRevision)))))
            } else null,
        )
    }

    private class Callbacks {
        val drafts = mutableListOf<String>()
        val openedThreads = mutableListOf<Pair<String, Long>>()
        val locales = mutableListOf<String?>()
        val openedAssets = mutableListOf<String>()
        val openedMemoryCards = mutableListOf<Int>()
        var sends = 0
        var recoveries = 0
        var deletes = 0
        var abandons = 0
        val voiceContinuations = mutableListOf<Pair<String, Long>>()
        val textContinuations = mutableListOf<Pair<String, Long>>()
        val olderPageReads = mutableListOf<Triple<String, Long, Long>>()
        val historyReloads = mutableListOf<Pair<String, Long>>()
        var reconciliations = 0
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
        onContinueVoice: ((String, Long) -> Unit)? = null,
        onContinueText: ((String, Long) -> Unit)? = null,
        onAbandonPending: ((String, String, Long) -> Unit)? = null,
        onLoadOlder: ((String, Long, Long) -> Unit)? = null,
        onReloadHistory: ((String, Long) -> Unit)? = null,
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
                        onOpenThread = { id, revision -> callbacks.openedThreads += id to revision },
                        onDraft = {
                            callbacks.drafts += it
                            state.value = state.value.copy(draft = it)
                        },
                        onSend = { callbacks.sends++ },
                        onRecover = { callbacks.recoveries++ },
                        onDelete = { _, _ -> callbacks.deletes++ },
                        onSetLocale = { callbacks.locales += it },
                        onDismiss = { callbacks.dismissals++ },
                        onOpenAsset = { callbacks.openedAssets += it },
                        onOpenSavedMemoryCard = { callbacks.openedMemoryCards += it },
                        onAbandonPending = onAbandonPending,
                        onContinueVoice = onContinueVoice,
                        onContinueText = onContinueText,
                        onLoadOlder = { id, revision, before ->
                            callbacks.olderPageReads += Triple(id, revision, before)
                            onLoadOlder?.invoke(id, revision, before)
                        },
                        onReloadHistory = { id, revision ->
                            callbacks.historyReloads += id to revision
                            onReloadHistory?.invoke(id, revision)
                        },
                        onReconcileCreation = { callbacks.reconciliations++ },
                    )
                }
            }
        }
        rule.waitForIdle()
    }

    @Test
    fun freshSavedMemoryCardHasExplicitLocalizedOpenActionAtLargeText() {
        val uiState = mutableStateOf(state(includeFreshMemoryCard = true))
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks, fontScale = 2f)

        rule.onNodeWithTag("private-assistant-memory-cards").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Garden day").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-open-memory-0").performScrollTo().assertIsDisplayed().assertIsEnabled()
        rule.onNodeWithText("打开已保存故事").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-open-memory-0").performClick()
        assertEquals(listOf(0), callbacks.openedMemoryCards)

        uiState.value = uiState.value.copy(memoryReaderOrdinal = null, memoryReaderErrorOrdinal = 0)
        rule.onNodeWithTag("private-assistant-memory-error-0").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-memory-retry-0").performScrollTo().assertIsEnabled().performClick()
        assertEquals(listOf(0, 0), callbacks.openedMemoryCards)
    }

    private fun openManagement() {
        rule.onNodeWithTag("private-assistant-manage-toggle").performScrollTo().performClick()
        rule.waitForIdle()
    }

    @Test
    fun selectedConversationStartsCompactWithHistoryAndContinuationReachable() {
        val uiState = mutableStateOf(state(threadLabel = "旅行标签"))
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks,
            onContinueVoice = { id, revision -> callbacks.voiceContinuations += id to revision },
            onContinueText = { id, revision -> callbacks.textContinuations += id to revision })

        rule.onNodeWithTag("private-assistant-current-summary").assertIsDisplayed()
        rule.onNodeWithText("管理对话").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-history-heading").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-exchange-0").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-continue-text").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-continue-voice").assertIsDisplayed()
        captureBottomScreenshot("private-assistant-zh-large-current")
        rule.onNodeWithTag("private-assistant-thread-list").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-new").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-locale").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-delete").assertDoesNotExist()
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.textContinuations)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.voiceContinuations)
        assertEquals(0, callbacks.newThreads)
        assertEquals(0, callbacks.refreshes)
        assertEquals(emptyList<String?>(), callbacks.locales)
        assertEquals(0, callbacks.deletes)
        assertEquals(0, callbacks.sends)
    }

    @Test
    fun managementToggleExpandsAndCollapsesLocallyWithoutCallbacks() {
        val uiState = mutableStateOf(state())
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks,
            onContinueVoice = { id, revision -> callbacks.voiceContinuations += id to revision },
            onContinueText = { id, revision -> callbacks.textContinuations += id to revision })

        openManagement()
        rule.onNodeWithTag("private-assistant-thread-list").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-new").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-refresh").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-locale").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-delete").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-thread-list").performScrollTo()
        captureBottomScreenshot("private-assistant-zh-large-management")
        rule.onNodeWithTag("private-assistant-history-heading").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-continue-text").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-continue-voice").assertIsDisplayed()

        rule.onNodeWithTag("private-assistant-manage-toggle").performScrollTo().performClick()
        rule.waitForIdle()
        rule.onNodeWithTag("private-assistant-thread-list").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-new").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-locale").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-delete").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-history-heading").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-continue-text").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-continue-voice").assertIsDisplayed()
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.openedThreads)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.textContinuations)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.voiceContinuations)
        assertEquals(0, callbacks.newThreads)
        assertEquals(0, callbacks.refreshes)
        assertEquals(emptyList<String?>(), callbacks.locales)
        assertEquals(0, callbacks.deletes)
        assertEquals(0, callbacks.sends)
    }

    @Test
    fun scopeChangeResetsManagementDisclosure() {
        val uiState = mutableStateOf(state())
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks)

        openManagement()
        rule.onNodeWithTag("private-assistant-thread-list").performScrollTo().assertIsDisplayed()
        val current = uiState.value
        uiState.value = current.copy(
            accountId = "other-synthetic-account",
            libraryId = "other-synthetic-library",
            threads = current.threads?.copy(threads = current.threads!!.threads.map {
                it.copy(libraryId = "other-synthetic-library")
            }),
            detail = current.detail?.copy(thread = current.detail!!.thread.copy(libraryId = "other-synthetic-library")),
        )
        rule.waitForIdle()

        rule.onNodeWithTag("private-assistant-thread-list").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-current-summary").assertIsDisplayed()
        rule.onNodeWithText("管理对话").assertIsDisplayed()
        assertEquals(0, callbacks.newThreads)
        assertEquals(0, callbacks.refreshes)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.openedThreads)
        assertEquals(0, callbacks.sends)
        assertEquals(0, callbacks.recoveries)
        assertEquals(0, callbacks.deletes)
    }

    @Test
    fun generationFenceResetsManagementAndDeleteConfirmation() {
        val uiState = mutableStateOf(state())
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks)

        openManagement()
        rule.onNodeWithTag("private-assistant-thread-list").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-delete").performScrollTo().performClick()
        rule.onNodeWithTag("private-assistant-delete-ack").performClick()
        rule.onNodeWithTag("private-assistant-delete-confirm").assertIsEnabled()

        uiState.value = uiState.value.copy(generation = requireNotNull(uiState.value.generation) + 1)
        rule.waitForIdle()

        rule.onNodeWithTag("private-assistant-delete-dialog").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-thread-list").assertDoesNotExist()
        assertEquals(0, callbacks.deletes)
        openManagement()
        rule.onNodeWithTag("private-assistant-delete").performScrollTo().performClick()
        rule.onNodeWithTag("private-assistant-delete-confirm").assertIsNotEnabled()
        assertEquals(0, callbacks.deletes)
    }

    @Test
    fun generationFenceClearsAbandonConfirmationAcknowledgement() {
        val uiState = mutableStateOf(state(draft = "保留草稿", pending = true))
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks, onAbandonPending = { _, _, _ -> callbacks.abandons++ })

        rule.onNodeWithTag("private-assistant-abandon-pending").performScrollTo().performClick()
        rule.onNodeWithTag("private-assistant-abandon-ack").performClick()
        rule.onNodeWithTag("private-assistant-abandon-confirm").assertIsEnabled()
        uiState.value = uiState.value.copy(generation = requireNotNull(uiState.value.generation) + 1)
        rule.waitForIdle()

        rule.onNodeWithTag("private-assistant-abandon-dialog").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-abandon-pending").performScrollTo().performClick()
        rule.onNodeWithTag("private-assistant-abandon-confirm").assertIsNotEnabled()
        assertEquals(0, callbacks.abandons)
        assertEquals(0, callbacks.sends)
    }

    @Test
    fun refreshRequiredHidesPotentiallyStaleDatesAndCounts() {
        val uiState = mutableStateOf(state(historyRefreshRequired = true))
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks)

        rule.onNodeWithTag("private-assistant-refresh-needed").assertIsDisplayed()
        rule.onNodeWithText("2 轮对话").assertDoesNotExist()
        openManagement()
        rule.onNodeWithTag("private-assistant-thread-$threadId").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("2026-10-10 08:00").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-exchange-0").performScrollTo().assertIsDisplayed()
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
        rule.onNodeWithTag("private-assistant-current-summary").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-thread-list").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-exchange-0").assertIsDisplayed()
        rule.onNodeWithText("家庭相册里这句应保持纯文本：$privateText").assertIsDisplayed()
        rule.onNodeWithText("这段回复只显示为私人对话文字。").assertIsDisplayed()
        rule.onNodeWithText("播放", substring = true).assertDoesNotExist()
        rule.onNodeWithText("录音", substring = true).assertDoesNotExist()

        assertEquals(emptyList<String>(), callbacks.openedAssets)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.openedThreads)
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
        rule.onNodeWithTag("private-assistant-thread-list").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-uncertain").performScrollTo().assertIsDisplayed()
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
    fun voiceContinuationRunsOnlyAfterExplicitButtonTapWithRenderedThreadRevision() {
        val uiState = mutableStateOf(state())
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks, onContinueVoice = { id, revision ->
            callbacks.voiceContinuations += id to revision
        })

        rule.onNodeWithTag("private-assistant-continue-voice").performScrollTo().assertIsDisplayed()
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.voiceContinuations)
        rule.onNodeWithTag("private-assistant-continue-voice").performClick()
        assertEquals(listOf(threadId to 2L), callbacks.voiceContinuations)
        assertEquals(0, callbacks.sends)
    }

    @Test
    fun textContinuationRequiresExplicitTapAndReadingDoesNotActivateVoice() {
        val uiState = mutableStateOf(state())
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks, onContinueVoice = { id, revision ->
            callbacks.voiceContinuations += id to revision
        }, onContinueText = { id, revision ->
            callbacks.textContinuations += id to revision
        })

        assertEquals(emptyList<Pair<String, Long>>(), callbacks.textContinuations)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.voiceContinuations)
        openManagement()
        rule.onNodeWithTag("private-assistant-thread-$threadId").performScrollTo().performClick()
        assertEquals(listOf(threadId to 2L), callbacks.openedThreads)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.textContinuations)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.voiceContinuations)

        rule.onNodeWithTag("private-assistant-continue-text").performScrollTo().assertIsDisplayed()
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.textContinuations)
        rule.onNodeWithTag("private-assistant-continue-text").performClick()
        assertEquals(listOf(threadId to 2L), callbacks.textContinuations)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.voiceContinuations)
        assertEquals(0, callbacks.sends)
    }

    @Test
    fun olderHistoryRequiresExplicitTapUsesRenderedCursorAndPreservesDraft() {
        val pagingCapabilities = capabilities.copy(
            historyPaging = true,
            threadLabels = true,
        )
        val uiState = mutableStateOf(state(
            exchanges = listOf(
                exchange(10, "Recent question", "Recent answer"),
                exchange(11, "Latest question", "Latest answer"),
            ),
            draft = "keep this editable draft",
            assistantCapabilities = pagingCapabilities,
            hasOlderExchanges = true,
            threadLabel = "旅行标签",
        ))
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks,
            onContinueVoice = { id, revision -> callbacks.voiceContinuations += id to revision },
            onContinueText = { id, revision -> callbacks.textContinuations += id to revision },
            onLoadOlder = { _, _, _ ->
                val before = uiState.value
                val detail = requireNotNull(before.detail)
                uiState.value = before.copy(detail = detail.copy(
                    exchanges = listOf(exchange(8, "Earlier question", "Earlier answer")) + detail.exchanges,
                ))
            })

        openManagement()
        rule.onNodeWithTag("private-assistant-history-heading").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-thread-$threadId").performScrollTo()
            .assertTextContains("旅行标签", substring = true)
        assertEquals(emptyList<Triple<String, Long, Long>>(), callbacks.olderPageReads)
        rule.onNodeWithTag("private-assistant-thread-$threadId").performScrollTo().performClick()
        assertEquals(listOf(threadId to 11L), callbacks.openedThreads)
        assertEquals(emptyList<Triple<String, Long, Long>>(), callbacks.olderPageReads)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.voiceContinuations)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.textContinuations)

        rule.onNodeWithTag("private-assistant-continue-text").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-continue-voice").performScrollTo().assertIsDisplayed()
        val older = rule.onNodeWithTag("private-assistant-history-older").performScrollTo()
        older.assertIsDisplayed()
        assertEquals(emptyList<Triple<String, Long, Long>>(), callbacks.olderPageReads)
        older.performClick()
        assertEquals(listOf(Triple(threadId, 11L, 10L)), callbacks.olderPageReads)
        assertEquals(listOf("Earlier question"), uiState.value.detail!!.exchanges.take(1).map { it.inputText })
        assertEquals("keep this editable draft", uiState.value.draft)
        val composer = rule.onNodeWithTag("private-assistant-composer").performScrollTo()
        composer.performTextReplacement("edited after paging")
        assertEquals("edited after paging", uiState.value.draft)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.voiceContinuations)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.textContinuations)
        assertEquals(0, callbacks.sends)
    }

    @Test
    fun historyOnlyCapabilityKeepsLabelsAndOlderPagingReadableWithoutTurnActions() {
        val historyOnly = capabilities.copy(serverOwnedTurns = false, historyPaging = true, threadLabels = true)
        val uiState = mutableStateOf(state(
            assistantCapabilities = historyOnly,
            hasOlderExchanges = true,
            threadLabel = "旧照片问题",
            draft = "read-only draft",
        ))
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks,
            onContinueVoice = { id, revision -> callbacks.voiceContinuations += id to revision },
            onContinueText = { id, revision -> callbacks.textContinuations += id to revision })

        openManagement()
        rule.onNodeWithTag("private-assistant-history-heading").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-thread-$threadId").performScrollTo()
            .assertTextContains("旧照片问题", substring = true)
        rule.onNodeWithTag("private-assistant-history-older").performScrollTo().assertIsEnabled()
        rule.onNodeWithTag("private-assistant-send").assertIsNotEnabled()
        rule.onNodeWithTag("private-assistant-continue-text").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-continue-voice").assertDoesNotExist()
        assertEquals(emptyList<Triple<String, Long, Long>>(), callbacks.olderPageReads)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.textContinuations)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.voiceContinuations)
        assertEquals(0, callbacks.sends)
    }

    @Test
    fun historyConflictRequiresExplicitReloadAtRenderedRevision() {
        val uiState = mutableStateOf(state(hasOlderExchanges = true, historyRefreshRequired = true)
            .copy(continuationEnabled = false))
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks)

        rule.onNodeWithTag("private-assistant-history-changed").performScrollTo().assertIsDisplayed()
        val reload = rule.onNodeWithTag("private-assistant-history-reload").performScrollTo()
        reload.assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-history-older").assertDoesNotExist()
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.historyReloads)
        reload.performClick()
        assertEquals(listOf(threadId to 2L), callbacks.historyReloads)
        assertEquals(emptyList<Triple<String, Long, Long>>(), callbacks.olderPageReads)
    }

    @Test
    fun abandoningPendingRequestShowsWarningRequiresAcknowledgementAndDoesNotSend() {
        val uiState = mutableStateOf(state(draft = "保留草稿", pending = true))
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks, onAbandonPending = { id, request, revision ->
            assertEquals(threadId, id)
            assertEquals(requestId, request)
            assertEquals(3L, revision)
            callbacks.abandons++
        })

        rule.onNodeWithTag("private-assistant-abandon-pending").performScrollTo().performClick()
        rule.onNodeWithText("服务器仍可能完成上一条请求。已提交的问题和未发送草稿会保留在此手机，不会自动再次发送。此操作不会删除已保存的对话，也不会写入家庭回忆。")
            .assertIsDisplayed()
        val confirm = rule.onNodeWithTag("private-assistant-abandon-confirm")
        confirm.assertIsNotEnabled()
        assertEquals(0, callbacks.abandons)

        rule.onNodeWithTag("private-assistant-abandon-ack").performClick()
        confirm.assertIsEnabled()
        confirm.performClick()
        assertEquals(1, callbacks.abandons)
        assertEquals(0, callbacks.sends)
        assertEquals(0, callbacks.recoveries)
    }

    @Test
    fun pendingCreationSeparatesGetReconcileFromSameIdPostRetry() {
        val uiState = mutableStateOf(state().copy(pendingCreationId = "pending-client-id"))
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks)

        rule.onNodeWithTag("private-assistant-thread-list").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-pending-creation").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-retry-creation").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-new").performScrollTo().performClick()
        assertEquals(1, callbacks.reconciliations)
        assertEquals(0, callbacks.newThreads)
        rule.onNodeWithTag("private-assistant-retry-creation").performClick()
        assertEquals(1, callbacks.newThreads)
        assertEquals(1, callbacks.reconciliations)
    }

    @Test
    fun missingSelectedThreadKeepsManagementControlsVisible() {
        val uiState = mutableStateOf(state().copy(detail = null))
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks)

        rule.onNodeWithTag("private-assistant-current-summary").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-thread-list").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-new").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-refresh").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-thread-$threadId").performScrollTo().assertIsDisplayed()
        assertEquals(0, callbacks.newThreads)
        assertEquals(0, callbacks.refreshes)
        assertEquals(emptyList<Pair<String, Long>>(), callbacks.openedThreads)
        assertEquals(0, callbacks.sends)
    }

    @Test
    fun localePickerOffersSystemChineseAndEnglishAndReportsOnlySelectedChoices() {
        val uiState = mutableStateOf(state())
        val callbacks = Callbacks()
        show(uiState, zh = true, callbacks)

        openManagement()
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

        openManagement()
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
        rule.onNodeWithText("写下问题，发送前可以修改。").assertIsDisplayed()
        uiState.value = uiState.value.copy(draft = "中".repeat(342))
        rule.waitForIdle()
        rule.onNodeWithText("内容太长，请缩短后发送。").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-send").assertIsNotEnabled()
        uiState.value = uiState.value.copy(draft = "底部草稿")
        rule.waitForIdle()
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
