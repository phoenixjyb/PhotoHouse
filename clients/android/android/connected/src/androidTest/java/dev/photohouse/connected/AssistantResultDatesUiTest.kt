package dev.photohouse.connected

import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.Asset
import dev.photohouse.protocol.DateHint
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Assistant result date labels are based only on typed source metadata. */
@RunWith(AndroidJUnit4::class)
class AssistantResultDatesUiTest {
    @get:Rule val rule = createComposeRule()

    private fun showDateJourney(zh: Boolean) {
        val library = "synthetic-library"
        fun asset(id: String, takenAt: String? = null, hint: DateHint? = null) = Asset(
            id, "image", 800, 600, null, takenAt, "/assets/$id/thumbnail?library=$library", hint,
        )
        val items = listOf(
            asset("101", takenAt = "2024-05-01", hint = DateHint("2024-09-09", "filename")),
            asset("102", hint = DateHint("2024-05-02", "filename")),
            asset("103", hint = DateHint("2024-05-03", "received")),
            asset("104"),
        )
        val turn = AssistantTurn("results", "Found four memories.", null, null, items, items.size, false, null)
        val state = mutableStateOf(AssistantClientState(
            library, 1, capabilities = AssistantCapabilities(true, true, false, false, 0),
            turns = listOf(AssistantExchange("Find these memories", turn, "synthetic-date-turn")),
        ))
        rule.setContent {
            val current = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(current.density, 1.5f)) {
                PhotoHouseTheme {
                    AssistantScreen(state.value, zh, onBack = {}, previews = emptyMap(), onRetryCapabilities = {},
                        onSend = { true }, onClear = {}, onOpen = { _, _ -> }, onCheckReceipt = {},
                        onRecord = {}, onStopRecording = {}, onCancelRecording = {}, recording = false,
                        recordError = false, onClearTranscript = {}, onPlaySpeech = {}, onStopSpeech = {})
                }
            }
        }
        val expected = if (zh) listOf("2024-05-01", "文件名日期 · 2024-05-02", "收到于 · 2024-05-03", "日期未知")
            else listOf("2024-05-01", "Filename date · 2024-05-02", "Received · 2024-05-03", "Date unknown")
        expected.forEach { label ->
            rule.onNodeWithTag("assistant-turns").performScrollToNode(hasText(label, substring = false))
            rule.onNodeWithText(label, substring = false).assertIsDisplayed()
        }
    }

    @Test fun englishResultDatesKeepSourceLabelsAtLargeText() = showDateJourney(zh = false)

    @Test fun chineseResultDatesKeepSourceLabelsAtLargeText() = showDateJourney(zh = true)
}
