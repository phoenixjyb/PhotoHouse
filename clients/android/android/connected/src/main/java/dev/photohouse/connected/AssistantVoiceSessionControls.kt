package dev.photohouse.connected

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import dev.photohouse.connected.core.*

internal data class AssistantVoiceControls(
    val session: AssistantVoiceSessionUiState?,
    val start: (() -> Unit)?,
    val pause: () -> Unit,
    val resume: () -> Unit,
    val end: () -> Unit,
    val finishTurn: () -> Unit,
    val permissionDenied: Boolean,
    val canUseManualControls: () -> Boolean,
)

/** Mounting does not listen. Only Start/Resume and their exact permission callback can do so. */
@Composable
internal fun rememberAssistantVoiceControls(
    store: ConnectedStore, live: LiveState, zh: Boolean,
    onOpen: (String, String?) -> Unit,
): AssistantVoiceControls? {
    val account = live.session?.account_id ?: return null
    val library = live.library ?: return null
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val coroutineScope = rememberCoroutineScope()
    val factory = LocalAssistantVoicePlatformFactory.current
    val open = rememberUpdatedState(onOpen)
    val voiceScope = remember(account, library, live.generation) { VoiceSessionScope(account, library, live.generation) }
    val owner = remember(store, voiceScope, factory, zh, lifecycleOwner) {
        var current: AssistantVoiceSessionStore? = null
        val platform = factory.create(context) { current?.audioFocusLost() }
        AssistantVoiceSessionStore(store, voiceScope, coroutineScope, platform, if (zh) "zh" else "en",
            isForeground = { lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED) && !store.state.value.covered },
            onOpen = { id, request -> open.value(id, request) }).also { current = it }
    }
    val voice by owner.state.collectAsState()
    var permissionWanted by remember(owner) { mutableStateOf(false) }
    var denied by remember(owner) { mutableStateOf(false) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (permissionWanted) {
            permissionWanted = false
            val current = store.state.value
            if (granted && !current.covered && current.generation == voiceScope.appGeneration &&
                current.library == voiceScope.libraryId && current.session?.account_id == voiceScope.accountId) {
                denied = false
                owner.start()
            } else denied = !granted
        }
    }
    DisposableEffect(owner, lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) {
                permissionWanted = false
                owner.backgrounded()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            permissionWanted = false
            lifecycleOwner.lifecycle.removeObserver(observer)
            owner.close()
        }
    }
    val available = store.privateAssistantConversationAvailable() && live.assistant?.capabilities?.let {
        it.enabled && it.text && it.transcribe && it.speech && it.maxAudioSeconds in 1..30
    } == true
    val detail = when (voice.reason) {
        VoiceSessionStopReason.USER_PAUSED -> if (zh) "点击继续后才会再次聆听。" else "Resume when you are ready to listen again."
        VoiceSessionStopReason.REVIEW_REQUIRED -> if (zh) "请查看当前回复或结果；更改需要单独确认。" else "Review the current reply or result; changes need separate confirmation."
        VoiceSessionStopReason.UNCERTAIN_REQUEST -> if (zh) "结果尚不确定，请先查询回执；不会自动重发。" else "The outcome is uncertain. Check the receipt; no request is resent."
        VoiceSessionStopReason.BACKGROUNDED, VoiceSessionStopReason.CONTEXT_CHANGED -> if (zh) "离开前台或切换资料库后，聆听已停止。" else "Listening stopped when the foreground context changed."
        VoiceSessionStopReason.AUDIO_FOCUS_LOST -> if (zh) "音频被其他应用使用，已停止聆听。" else "Another app took audio focus; listening stopped."
        VoiceSessionStopReason.EMPTY_TRANSCRIPT, VoiceSessionStopReason.CAPTURE_FAILED -> if (zh) "没有收到可用语音。准备好后可继续。" else "No usable speech was captured. Resume when ready."
        VoiceSessionStopReason.TRANSCRIPTION_FAILED, VoiceSessionStopReason.REQUEST_FAILED, VoiceSessionStopReason.SPEECH_FAILED ->
            if (zh) "本轮未能完成，已暂停；请查看回复或回执。" else "This turn could not finish. Review its reply or receipt before continuing."
        else -> when (voice.phase) {
            VoiceSessionPhase.LISTENING -> if (voice.captureStarted) {
                if (zh) "请说出想查找的内容。麦克风已开启。" else "Say what you would like to find. Microphone is on."
            } else if (zh) "正在开启麦克风；出现“正在聆听”后再开始说话。" else "The microphone is opening. Speak when Listening appears."
            VoiceSessionPhase.TRANSCRIBING -> if (zh) "麦克风已关闭，正在识别你刚才说的话。" else "Microphone off. Recognizing what you said."
            VoiceSessionPhase.REQUESTING -> if (zh) "麦克风已关闭，正在查找相关回忆。" else "Microphone off. Searching for matching memories."
            VoiceSessionPhase.SPEAKING -> if (voice.playbackStarted) {
                if (store.privateReplySpeechEnabled()) {
                    if (zh) "麦克风已关闭，正在播报助手回复。" else "Microphone off. Playing the assistant reply."
                } else if (zh) "麦克风已关闭，正在播报当前查找结果。" else "Microphone off. Reading the current search results."
            } else if (zh) "麦克风已关闭，正在准备语音回复。" else "Microphone off. Preparing the spoken reply."
            else -> null
        }
    }
    val session = when (voice.phase) {
        VoiceSessionPhase.IDLE, VoiceSessionPhase.ENDED -> null
        else -> AssistantVoiceSessionUiState(when (voice.phase) {
            VoiceSessionPhase.LISTENING -> if (voice.captureStarted) AssistantVoiceSessionStage.LISTENING else AssistantVoiceSessionStage.OPENING_MIC
            VoiceSessionPhase.TRANSCRIBING -> AssistantVoiceSessionStage.TRANSCRIBING
            VoiceSessionPhase.REQUESTING -> AssistantVoiceSessionStage.FINDING
            VoiceSessionPhase.SPEAKING -> if (voice.playbackStarted) AssistantVoiceSessionStage.SPEAKING else AssistantVoiceSessionStage.PREPARING_REPLY
            else -> AssistantVoiceSessionStage.PAUSED
        }, detail, canResume = available && live.assistant?.pendingTurn == null,
            microphoneActive = voice.phase == VoiceSessionPhase.LISTENING && voice.captureStarted,
            clientTiming = voice.clientTiming)
    }
    return AssistantVoiceControls(session,
        start = if (!available) null else ({
            denied = false
            if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) owner.start()
            else { permissionWanted = true; permission.launch(Manifest.permission.RECORD_AUDIO) }
        }),
        pause = { owner.pause() }, resume = { owner.resume() },
        end = { permissionWanted = false; owner.end() }, finishTurn = { owner.finishTurn() }, permissionDenied = denied, canUseManualControls = owner::canUseManualControls)
}
