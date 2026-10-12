package dev.photohouse.connected

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

/** Display-only status supplied by the session owner; this composable never captures audio. */
internal enum class AssistantVoiceSessionStage {
    LISTENING, TRANSCRIBING, FINDING, SPEAKING, PAUSED,
}

internal data class AssistantVoiceSessionUiState(
    val stage: AssistantVoiceSessionStage,
    val detail: String? = null,
    val canResume: Boolean = true,
)

internal const val ASSISTANT_VOICE_DETAIL_MAX_CHARS = 120

@Composable
@OptIn(ExperimentalLayoutApi::class)
internal fun AssistantVoiceSessionPanel(
    state: AssistantVoiceSessionUiState,
    zh: Boolean,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onEnd: () -> Unit,
    onFinishTurn: (() -> Unit)? = null,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val status = when (state.stage) {
        AssistantVoiceSessionStage.LISTENING -> t("Listening", "正在聆听")
        AssistantVoiceSessionStage.TRANSCRIBING -> t("Transcribing", "正在转写")
        AssistantVoiceSessionStage.FINDING -> t("Finding memories", "正在查找回忆")
        AssistantVoiceSessionStage.SPEAKING -> t("Speaking", "正在回答")
        AssistantVoiceSessionStage.PAUSED -> t("Voice conversation paused", "语音对话已暂停")
    }
    Card(
        modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp).testTag("assistant-voice-session"),
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(status, style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.onSecondaryContainer,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }.testTag("assistant-voice-session-status"))
            state.detail?.takeIf { it.isNotBlank() }?.let {
                Text(it.take(ASSISTANT_VOICE_DETAIL_MAX_CHARS), style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSecondaryContainer,
                    modifier = Modifier.testTag("assistant-voice-session-detail"))
            }
            Text(t("Read-only search. Changes need confirmation.",
                "只读查找；更改回忆前仍须确认。"),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSecondaryContainer)
            FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)) {
                if (state.stage == AssistantVoiceSessionStage.LISTENING && onFinishTurn != null) {
                    Button(onClick = onFinishTurn, modifier = Modifier.heightIn(min = 48.dp).testTag("assistant-voice-finish-turn")) {
                        Text(t("Finish turn", "说完了"))
                    }
                }
                if (state.stage == AssistantVoiceSessionStage.PAUSED) {
                    Button(onClick = onResume, enabled = state.canResume, modifier = Modifier.heightIn(min = 48.dp).testTag("assistant-voice-resume")) {
                        Text(t("Resume", "继续"))
                    }
                } else {
                    Button(onClick = onPause, modifier = Modifier.heightIn(min = 48.dp).testTag("assistant-voice-pause")) {
                        Text(t("Pause", "暂停"))
                    }
                }
                TextButton(onClick = onEnd, modifier = Modifier.heightIn(min = 48.dp).testTag("assistant-voice-end")) {
                    Text(t("End", "结束"))
                }
            }
        }
    }
}
