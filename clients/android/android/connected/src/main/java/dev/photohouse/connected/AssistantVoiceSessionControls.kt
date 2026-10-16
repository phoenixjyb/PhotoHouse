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

internal fun assistantVoiceListeningDetail(zh: Boolean): String = if (zh) {
    "请说出想查找的内容；也可说“暂停”或“结束语音”。麦克风已开启。"
} else {
    "Say what you would like to find, or say “pause” or “end voice chat.” Microphone is on."
}

/** Stage-specific recovery guidance; it does not retry or resume the session. */
internal fun assistantVoiceFailureDetail(reason: VoiceSessionStopReason?, zh: Boolean): String? = when (reason) {
    VoiceSessionStopReason.TRANSCRIPTION_FAILED -> if (zh)
        "这段语音未能识别。准备好后点“继续”，再说一次。"
    else "Could not recognize that recording. Resume when ready and say it again."
    VoiceSessionStopReason.REQUEST_FAILED -> if (zh)
        "这次请求未能完成。请查看屏幕提示，再决定是否继续。"
    else "The request could not finish. Check the on-screen message before resuming."
    VoiceSessionStopReason.SPEECH_FAILED -> if (zh)
        "语音播放未完成。可以先查看屏幕内容；点“继续”会返回语音查找。"
    else "Audio playback did not finish. Read the on-screen reply; Resume returns to voice search."
    else -> null
}

internal data class AssistantVoiceControls(
    val session: AssistantVoiceSessionUiState?,
    val start: (() -> Unit)?,
    val pause: () -> Unit,
    val resume: () -> Unit,
    val end: () -> Unit,
    val finishTurn: () -> Unit,
    val permissionDenied: Boolean,
    val canUseManualControls: () -> Boolean,
    val canStartMemoryReading: (AssistantMemoryVoiceSelection) -> Boolean,
    val startMemoryReading: (AssistantMemoryVoiceSelection) -> Boolean,
    val memoryReadingReady: Boolean,
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
    var pendingMemorySelection by remember(owner) { mutableStateOf<AssistantMemoryVoiceSelection?>(null) }
    var denied by remember(owner) { mutableStateOf(false) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (permissionWanted || pendingMemorySelection != null) {
            val capturedSelection = pendingMemorySelection
            permissionWanted = false
            pendingMemorySelection = null
            val current = store.state.value
            if (granted && !current.covered && current.generation == voiceScope.appGeneration &&
                current.library == voiceScope.libraryId && current.session?.account_id == voiceScope.accountId) {
                denied = false
                if (capturedSelection != null) {
                    if (owner.canStartMemoryReading(capturedSelection)) owner.startMemoryReading(capturedSelection)
                } else owner.start()
            } else denied = !granted
        }
    }
    DisposableEffect(owner, lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) {
                permissionWanted = false
                pendingMemorySelection = null
                owner.backgrounded()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            permissionWanted = false
            pendingMemorySelection = null
            lifecycleOwner.lifecycle.removeObserver(observer)
            owner.close()
        }
    }
    val available = store.privateAssistantConversationAvailable() && live.assistant?.capabilities?.let {
        it.enabled && it.text && it.transcribe && it.speech && it.maxAudioSeconds in 1..30
    } == true
    val readingPosition = voice.readingSegment?.let { it + 1 }
    val readingCount = voice.readingSegmentCount
    val readingPositionDetail = if (voice.readingContinuation && readingPosition != null && readingCount != null) {
        if (zh) "第${readingPosition}/${readingCount}段；麦克风已关闭。"
        else "Segment $readingPosition of $readingCount. Microphone off."
    } else null
    val detail = when (voice.reason) {
        VoiceSessionStopReason.READING_FINISHED -> if (zh)
            "这段已保存内容已读完。打开回忆可浏览后续章节；点“继续”会返回语音查找。"
        else "This saved section is complete. Open the memory to browse later sections; Resume returns to voice search."
        VoiceSessionStopReason.READING_NEEDS_SELECTION -> if (zh)
            "请选择已完成内容卡片上的“语音继续”，再开始朗读下一段。"
        else "Choose Continue by voice on a completed saved section to read the next section."
        VoiceSessionStopReason.READING_UNAVAILABLE -> if (zh)
            "朗读下一段暂不可用。请回到已保存内容卡片重新选择。"
        else "The next saved section is unavailable. Choose it again from the saved memory card."
        VoiceSessionStopReason.USER_PAUSED -> if (zh) "点击继续后将重新开始语音查找。" else "Resume starts voice search again."
        VoiceSessionStopReason.REVIEW_REQUIRED -> if (zh) "请查看当前回复或结果；更改需要单独确认。" else "Review the current reply or result; changes need separate confirmation."
        VoiceSessionStopReason.UNCERTAIN_REQUEST -> if (zh) "结果尚不确定，请先查询回执；不会自动重发。" else "The outcome is uncertain. Check the receipt; no request is resent."
        VoiceSessionStopReason.BACKGROUNDED, VoiceSessionStopReason.CONTEXT_CHANGED -> if (zh) "离开前台或切换资料库后，聆听已停止。" else "Listening stopped when the foreground context changed."
        VoiceSessionStopReason.AUDIO_FOCUS_LOST -> if (zh) "音频被其他应用使用，已停止聆听。" else "Another app took audio focus; listening stopped."
        VoiceSessionStopReason.EMPTY_TRANSCRIPT, VoiceSessionStopReason.CAPTURE_FAILED -> if (zh) "没有收到可用语音。准备好后可继续。" else "No usable speech was captured. Resume when ready."
        VoiceSessionStopReason.TRANSCRIPTION_FAILED, VoiceSessionStopReason.REQUEST_FAILED, VoiceSessionStopReason.SPEECH_FAILED ->
            assistantVoiceFailureDetail(voice.reason, zh)
        else -> when (voice.phase) {
            VoiceSessionPhase.LISTENING -> if (voice.readingContinuation && voice.captureStarted) {
                if (zh) "麦克风已开启，正在等待你的指令。"
                else "Microphone is on and waiting for your instruction."
            } else if (voice.captureStarted) {
                assistantVoiceListeningDetail(zh)
            } else if (zh) "正在开启麦克风；出现“正在聆听”后再开始说话。" else "The microphone is opening. Speak when Listening appears."
            VoiceSessionPhase.TRANSCRIBING -> if (voice.readingContinuation) {
                if (zh) "麦克风已关闭，正在识别你的朗读指令。" else "Microphone off. Recognizing your reading instruction."
            } else if (zh) "麦克风已关闭，正在识别你刚才说的话。" else "Microphone off. Recognizing what you said."
            VoiceSessionPhase.REQUESTING -> if (zh) "麦克风已关闭，正在查找相关回忆。" else "Microphone off. Searching for matching memories."
            VoiceSessionPhase.SPEAKING -> if (voice.playbackStarted) {
                if (voice.readingContinuation) readingPositionDetail
                else if (store.privateReplySpeechEnabled()) {
                    if (zh) "麦克风已关闭，正在播报。暂停或结束请点屏幕按钮。" else "Microphone off. Playing the reply; use Pause or End."
                } else if (zh) "麦克风已关闭，正在播报。暂停或结束请点屏幕按钮。" else "Microphone off. Reading results; use Pause or End."
            } else readingPositionDetail ?: if (zh) "麦克风已关闭，正在准备语音。暂停或结束请点屏幕按钮。"
            else "Microphone off. Preparing speech; use Pause or End."
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
            clientTiming = voice.clientTiming, readingContinuation = voice.readingContinuation,
            readingSegment = voice.readingSegment, readingSegmentCount = voice.readingSegmentCount,
            reason = voice.reason)
    }
    return AssistantVoiceControls(session,
        start = if (!available) null else ({
            if (permissionWanted || pendingMemorySelection != null) {
                // A general Start cancels a pending section-specific permission action.
                permissionWanted = false
                pendingMemorySelection = null
            } else {
                denied = false
                if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) owner.start()
                else { permissionWanted = true; permission.launch(Manifest.permission.RECORD_AUDIO) }
            }
        }),
        pause = { permissionWanted = false; pendingMemorySelection = null; owner.pause() },
        resume = { permissionWanted = false; pendingMemorySelection = null; owner.resume() },
        end = { permissionWanted = false; pendingMemorySelection = null; owner.end() },
        finishTurn = { owner.finishTurn() }, permissionDenied = denied,
        canUseManualControls = owner::canUseManualControls,
        canStartMemoryReading = owner::canStartMemoryReading,
        startMemoryReading = { selection ->
            if (!available || permissionWanted || pendingMemorySelection != null ||
                voice.phase !in setOf(VoiceSessionPhase.IDLE, VoiceSessionPhase.ENDED) ||
                !owner.canStartMemoryReading(selection)) return@AssistantVoiceControls false
            denied = false
            if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                owner.startMemoryReading(selection)
            } else {
                permissionWanted = false
                pendingMemorySelection = selection
                permission.launch(Manifest.permission.RECORD_AUDIO)
                true
            }
        }, memoryReadingReady = available && !permissionWanted && pendingMemorySelection == null &&
            voice.phase in setOf(VoiceSessionPhase.IDLE, VoiceSessionPhase.ENDED))
}
