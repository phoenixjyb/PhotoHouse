package dev.photohouse.connected

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.Asset
import kotlinx.serialization.json.Json
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Synthetic negotiated search result copy; no account, store, network, or media is used. */
@RunWith(AndroidJUnit4::class)
class AssistantSearchV2UiTest {
    @get:Rule val rule = createComposeRule()

    private fun show(zh: Boolean) {
        val item = Asset("123", "video", 640, 480, 3.0, "2024-01-02", "/assets/123/thumbnail?library=synthetic-library")
        val filters = Json.parseToJsonElement(
            """{"people":{"ids":["71","72"],"match":"all"},"text":"海边散步","date":{"from":"2024-01-02","to":null},"media":["video"]}""")
            .let { it as kotlinx.serialization.json.JsonObject }
        val turn = AssistantTurn(
            kind = "results", reply = "Found one video.", context = null, filters = filters,
            items = listOf(item), total = 1, hasMore = false, effect = null,
            searchVersion = 2,
            searchInterpretation = AssistantSearchInterpretation(
                dateBasis = "capture",
                people = listOf(AssistantSearchFacetSelection("71", "妈妈"), AssistantSearchFacetSelection("72", "小雨")),
                tags = emptyList(), locations = emptyList(), perspective = AssistantSearchPerspective("妈妈"),
            ),
            matchReasons = mapOf("123" to listOf(
                AssistantMatchReason.ReviewedPerson("71"),
                AssistantMatchReason.Caption(generated = true, sourceId = "88"),
                AssistantMatchReason.CaptureDate("2024-01-02"),
            )),
        )
        val state = mutableStateOf(AssistantClientState(
            library = "synthetic-library", generation = 1,
            turns = listOf(AssistantExchange("找妈妈和小雨在海边散步的视频", turn, "synthetic-search-v2")),
        ))
        val workspace = AssistantWorkspaceState(capabilities = AssistantWorkspaceCapabilities(
            version = 1, available = true, threads = true, preferences = true,
            preferencesApplied = true, serverOwnedTurns = true, searchVersion = 2,
            searchDateBasis = "capture", searchPerspectiveLabel = "妈妈",
        ))
        rule.setContent {
            val current = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(current.density, 1.5f)) {
                PhotoHouseTheme {
                    AssistantScreen(state.value, zh, onBack = {}, previews = emptyMap(), onRetryCapabilities = {},
                        onSend = { true }, onClear = {}, onOpen = { _, _ -> }, onCheckReceipt = {},
                        onRecord = {}, onStopRecording = {}, onCancelRecording = {}, recording = false,
                        recordError = false, onClearTranscript = {}, onPlaySpeech = {}, onStopSpeech = {},
                        savedMemoryWorkspace = workspace)
                }
            }
        }
        rule.onNodeWithTag("assistant-search-perspective").assertIsDisplayed()
        rule.onNodeWithText(if (zh) "视角：妈妈" else "Perspective: 妈妈", substring = false).assertIsDisplayed()
        val interpretationTag = "assistant-search-interpretation-synthetic-search-v2"
        rule.onNodeWithTag("assistant-turns").performScrollToNode(
            androidx.compose.ui.test.hasTestTag(interpretationTag))
        rule.onNodeWithTag(interpretationTag).assertIsDisplayed()
        listOf(
            if (zh) "同时出现：妈妈、小雨" else "Together in the photo: 妈妈, 小雨",
            if (zh) "文字：海边散步" else "Text: 海边散步",
            if (zh) "拍摄日期：从 2024-01-02 起" else "Capture date: From 2024-01-02",
            if (zh) "媒体：视频" else "Media: videos",
        ).forEach { label ->
            rule.onNodeWithTag("assistant-turns").performScrollToNode(androidx.compose.ui.test.hasText(label, substring = false))
            rule.onNodeWithText(label, substring = false).assertIsDisplayed()
        }
        val reasons = listOf(
            if (zh) "人物：妈妈" else "Person: 妈妈",
            if (zh) "匹配 AI 生成的照片说明" else "AI-generated caption match",
        )
        reasons.forEach { reason ->
            rule.onNodeWithTag("assistant-turns").performScrollToNode(androidx.compose.ui.test.hasText(reason, substring = false))
            rule.onNodeWithText(reason, substring = false).assertIsDisplayed()
        }
    }

    @Test fun englishNegotiatedSearchInterpretationAndReasonsAtLargeText() = show(zh = false)
    @Test fun chineseNegotiatedSearchInterpretationAndReasonsAtLargeText() = show(zh = true)
}
