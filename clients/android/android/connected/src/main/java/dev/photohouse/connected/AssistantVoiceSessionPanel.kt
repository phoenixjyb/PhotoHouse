package dev.photohouse.connected

import android.animation.ValueAnimator
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.scale
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

/** Display-only status supplied by the session owner; this composable never captures audio. */
internal enum class AssistantVoiceSessionStage {
    OPENING_MIC, LISTENING, TRANSCRIBING, FINDING, PREPARING_REPLY, SPEAKING, PAUSED,
}

internal data class AssistantVoiceSessionUiState(
    val stage: AssistantVoiceSessionStage,
    val detail: String? = null,
    val canResume: Boolean = true,
    val microphoneActive: Boolean = false,
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
        AssistantVoiceSessionStage.OPENING_MIC -> t("Opening microphone", "正在开启麦克风")
        AssistantVoiceSessionStage.LISTENING -> t("Listening", "正在聆听")
        AssistantVoiceSessionStage.TRANSCRIBING -> t("Recognizing speech", "正在识别语音")
        AssistantVoiceSessionStage.FINDING -> t("Searching memories", "正在查找回忆")
        AssistantVoiceSessionStage.PREPARING_REPLY -> t("Preparing reply", "正在准备回复")
        AssistantVoiceSessionStage.SPEAKING -> t("Speaking", "正在回答")
        AssistantVoiceSessionStage.PAUSED -> t("Voice conversation paused", "语音对话已暂停")
    }
    val confirmedActivity = (state.stage == AssistantVoiceSessionStage.LISTENING && state.microphoneActive) ||
        state.stage == AssistantVoiceSessionStage.SPEAKING
    val accent = when (state.stage) {
        AssistantVoiceSessionStage.OPENING_MIC, AssistantVoiceSessionStage.LISTENING -> MaterialTheme.colorScheme.primary
        AssistantVoiceSessionStage.TRANSCRIBING, AssistantVoiceSessionStage.FINDING -> MaterialTheme.colorScheme.tertiary
        AssistantVoiceSessionStage.PREPARING_REPLY, AssistantVoiceSessionStage.SPEAKING -> MaterialTheme.colorScheme.secondary
        AssistantVoiceSessionStage.PAUSED -> MaterialTheme.colorScheme.outline
    }
    // ValueAnimator observes Android's animator_duration_scale setting. In particular,
    // it disables this decorative pulse when the system scale is 0.
    val systemAnimationsEnabled = ValueAnimator.areAnimatorsEnabled()
    val shouldPulse = confirmedActivity && systemAnimationsEnabled
    val indicatorScale = if (shouldPulse) {
        val pulse = rememberInfiniteTransition(label = "confirmed-voice-activity")
        val scale by pulse.animateFloat(
            initialValue = 1f,
            targetValue = 1.1f,
            animationSpec = infiniteRepeatable(
                animation = tween(durationMillis = 1100, easing = FastOutSlowInEasing),
                repeatMode = RepeatMode.Reverse,
            ),
            label = "voice-activity-breathing",
        )
        scale
    } else {
        1f
    }
    val indicatorColor by animateColorAsState(accent, label = "voice-status-color")
    Card(
        modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp).testTag("assistant-voice-session"),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerHigh),
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(Modifier.size(44.dp).scale(indicatorScale).background(indicatorColor.copy(alpha = .14f), CircleShape)
                    .semantics(mergeDescendants = true) {
                        this.contentDescription = status
                    }.testTag("assistant-voice-activity-indicator")) {
                    Canvas(Modifier.align(Alignment.Center).size(14.dp)) { drawCircle(indicatorColor) }
                }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(status, style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }.testTag("assistant-voice-session-status"))
                    Text(if (state.microphoneActive) t("MICROPHONE ON", "麦克风已开启") else t("MICROPHONE OFF", "麦克风已关闭"),
                        style = MaterialTheme.typography.labelSmall, color = if (state.microphoneActive) accent else MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.testTag("assistant-voice-microphone-state"))
                }
            }
            state.detail?.takeIf { it.isNotBlank() }?.let {
                Text(it.take(ASSISTANT_VOICE_DETAIL_MAX_CHARS), style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.semantics { contentDescription = it.take(ASSISTANT_VOICE_DETAIL_MAX_CHARS) }
                        .testTag("assistant-voice-session-detail"))
            }
            Text(t("Read-only search. Changes need confirmation.", "只读查找；更改回忆前仍须确认。"),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
