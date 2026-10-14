package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/** Platform-owned foreground capture and actual speech playback; no implementation is implied here. */
interface AssistantVoiceSessionPlatform {
    suspend fun capture(maxSeconds: Int): ByteArray?
    /** Observation callback is optional; legacy platform implementations remain truthful by default. */
    suspend fun capture(maxSeconds: Int, onStarted: () -> Unit): ByteArray? = capture(maxSeconds)
    /** Returns true only after playback has actually completed. */
    suspend fun playSpeech(audio: ProtectedAnnotationAudio): Boolean
    /** Observation callback is optional; legacy implementations do not imply playback began. */
    suspend fun playSpeech(audio: ProtectedAnnotationAudio, onStarted: () -> Unit): Boolean = playSpeech(audio)
    fun stopAudio()
    /** Requests the current capture to finish and return its bounded recording. */
    fun finishCapture()
}

/** Drives the deterministic voice controller through the already-protected assistant store. */
class AssistantVoiceSessionStore(
    private val store: ConnectedStore,
    private val voiceScope: VoiceSessionScope,
    private val coroutineScope: CoroutineScope,
    private val platform: AssistantVoiceSessionPlatform,
    private val language: String,
    private val isForeground: () -> Boolean,
    /** Process-relative monotonic elapsed time; never wall-clock time or a serialized timestamp. */
    private val monotonicMillis: () -> Long = { (System.nanoTime() - MONOTONIC_ORIGIN_NANOS) / 1_000_000L },
    private val onOpen: (assetId: String, requestId: String?) -> Unit = { _, _ -> },
) : AutoCloseable {
    init { require(language in setOf("zh", "en")) }

    private val lock = Any()
    private val controller = VoiceSessionController()
    private val mutableState = MutableStateFlow(controller.state)
    private val timingTracker = VoiceTurnTimingTracker(monotonicMillis)
    val state: StateFlow<VoiceSessionState> = mutableState.asStateFlow()

    private var operationJob: Job? = null
    private var activeCapture: VoiceSessionBinding? = null
    private var observedCaptureBinding: VoiceSessionBinding? = null
    private var observedPlaybackBinding: VoiceSessionBinding? = null
    private var ownedTranscriptRequestId: String? = null
    private var ownedTurnRequestId: String? = null
    private var ownedSpeechRequestId: String? = null
    private var ownedMemoryReaderOrdinal: Int? = null
    /** The explicit start/resume choice is held for this session; capability loss ends the loop. */
    @Volatile private var sessionPrivateReplySpeechEnabled: Boolean? = null
    @Volatile private var sessionMemoryActionsEnabled: Boolean = false
    @Volatile private var closed = false
    private val storeMonitor = coroutineScope.launch {
        store.state.collect { live ->
            val current = controller.state
            if (current.phase in ACTIVE_PHASES) {
                when {
                    !scopeMatches(live) -> stopForTransition(controller.contextChanged(observedScope(live)))
                    !supportsVoice(live) -> stopForTransition(controller.contextChanged(null))
                }
            }
        }
    }
    private val workspaceReplySpeechMonitor = coroutineScope.launch {
        store.assistantWorkspaceState.collect {
            val boundMode = sessionPrivateReplySpeechEnabled
            if (!closed && boundMode != null && boundMode != store.privateReplySpeechEnabled() &&
                controller.state.phase in ACTIVE_PHASES) {
                stopForTransition(controller.contextChanged(null))
            } else if (!closed && controller.state.phase in ACTIVE_PHASES &&
                store.state.value.assistant?.speechMemoryOpeningOrdinal != null && !it.savedMemoryReadingAvailable) {
                stopForTransition(controller.contextChanged(null))
            } else if (!closed && sessionMemoryActionsEnabled && !it.savedMemoryActionsAvailable &&
                controller.state.phase in ACTIVE_PHASES) {
                stopForTransition(controller.contextChanged(null))
            }
        }
    }

    /** Dynamic guard for queued manual UI actions from this exact foreground owner. */
    fun canUseManualControls(): Boolean = synchronized(lock) {
        val live = store.state.value
        !closed && foregroundNow() && !live.covered &&
            live.session?.account_id == voiceScope.accountId && live.library == voiceScope.libraryId &&
            live.generation == voiceScope.appGeneration &&
            controller.state.phase in setOf(VoiceSessionPhase.IDLE, VoiceSessionPhase.ENDED)
    }

    /** Starts only from an explicit foreground action and a clean, qualified assistant scope. */
    fun start(): Boolean = synchronized(lock) {
        if (closed || !foregroundNow() || !scopeMatches(store.state.value) || !readyForStart()) return false
        sessionPrivateReplySpeechEnabled = store.privateReplySpeechEnabled()
        sessionMemoryActionsEnabled = store.assistantWorkspaceState.value.savedMemoryActionsAvailable
        val transition = controller.start(voiceScope, foreground = true)
        if (!transition.accepted) return false
        ownedTranscriptRequestId = null
        ownedTurnRequestId = null
        ownedSpeechRequestId = null
        ownedMemoryReaderOrdinal = null
        publish(transition.state)
        transition.effects.filterIsInstance<VoiceSessionEffect.StartCapture>().singleOrNull()?.binding?.let(::startCapture)
        true
    }

    /** Resuming is explicit and cannot recover an uncertain submitted turn by resending it. */
    fun resume(): Boolean = synchronized(lock) {
        val current = controller.state
        if (closed || current.phase != VoiceSessionPhase.PAUSED ||
            current.reason == VoiceSessionStopReason.UNCERTAIN_REQUEST || !foregroundNow() ||
            !scopeMatches(store.state.value) || !readyForStart()) return false
        sessionPrivateReplySpeechEnabled = store.privateReplySpeechEnabled()
        sessionMemoryActionsEnabled = store.assistantWorkspaceState.value.savedMemoryActionsAvailable
        val transition = controller.resume(voiceScope, foreground = true)
        if (!transition.accepted) return false
        publish(transition.state)
        transition.effects.filterIsInstance<VoiceSessionEffect.StartCapture>().singleOrNull()?.binding?.let(::startCapture)
        true
    }

    fun pause(): Boolean = stop { controller.pause() }
    fun end(): Boolean = stop { controller.end() }
    fun backgrounded(): Boolean = stop { controller.backgrounded() }
    fun audioFocusLost(): Boolean = stop { controller.audioFocusLost() }

    /** Lets the foreground user end a listen turn if endpoint detection is slow. */
    fun finishTurn(): Boolean = synchronized(lock) {
        if (closed || controller.state.phase != VoiceSessionPhase.LISTENING || activeCapture == null ||
            !foregroundNow() || !scopeMatches(store.state.value)) return false
        platform.finishCapture()
        true
    }

    private fun stop(transition: () -> VoiceSessionTransition): Boolean = synchronized(lock) {
        if (closed || controller.state.phase !in ACTIVE_PHASES) return false
        val stopped = transition()
        if (!stopped.accepted) return false
        stopForTransition(stopped)
        true
    }

    private fun stopForTransition(transition: VoiceSessionTransition) {
        if (!transition.accepted) return
        publish(transition.state)
        synchronized(lock) {
            operationJob?.cancel()
            operationJob = null
            activeCapture = null
        }
        runCatching { platform.stopAudio() }
        cancelOwnedStoreWork()
    }

    override fun close() {
        val active = synchronized(lock) { !closed && controller.state.phase in ACTIVE_PHASES }
        if (active) end()
        synchronized(lock) { closed = true }
        storeMonitor.cancel()
        workspaceReplySpeechMonitor.cancel()
        synchronized(lock) {
            operationJob?.cancel()
            operationJob = null
            activeCapture = null
            timingTracker.clear()
            publish(controller.state)
        }
    }

    private fun readyForStart(): Boolean {
        val live = store.state.value
        val assistant = live.assistant ?: return false
        val capabilities = assistant.capabilities ?: return false
        return scopeMatches(live) && store.privateAssistantConversationAvailable() && !live.busy &&
            assistant.library == voiceScope.libraryId && assistant.generation == voiceScope.appGeneration &&
            capabilities.enabled && capabilities.text && capabilities.transcribe && capabilities.speech &&
            capabilities.maxAudioSeconds in 1..30 &&
            !assistant.busy && !assistant.transcribing && assistant.transcript == null &&
            assistant.pendingTurn == null && !assistant.speechBusy && assistant.speechAudio == null
    }

    private fun scopeMatches(live: LiveState): Boolean =
        !live.covered && live.generation == voiceScope.appGeneration &&
            live.session?.account_id == voiceScope.accountId && live.library == voiceScope.libraryId &&
            live.assistant?.let { it.library == voiceScope.libraryId && it.generation == voiceScope.appGeneration } == true

    private fun supportsVoice(live: LiveState): Boolean = store.privateAssistantConversationAvailable() && live.assistant?.capabilities?.let {
        it.enabled && it.text && it.transcribe && it.speech && it.maxAudioSeconds in 1..30
    } == true

    private fun observedScope(live: LiveState): VoiceSessionScope? {
        if (live.covered) return null
        val account = live.session?.account_id ?: return null
        val library = live.library ?: return null
        val assistant = live.assistant ?: return null
        if (assistant.library != library || assistant.generation != live.generation) return null
        return runCatching { VoiceSessionScope(account, library, live.generation) }.getOrNull()
    }

    /** Never clear or cancel work that was started by a separate manual assistant control. */
    private fun cancelOwnedStoreWork() {
        val memoryReaderIsOurs = ownedMemoryReaderOrdinal != null
        ownedMemoryReaderOrdinal = null
        if (memoryReaderIsOurs) store.assistantWorkspaceCoordinator?.invalidateSavedMemoryReader()
        val assistant = store.state.value.assistant ?: return
        val transcriptIsOurs = ownedTranscriptRequestId?.let { requestId ->
            assistant.transcribing && assistant.lastRequestReceipt?.requestId == requestId
        } == true
        val turnIsOurs = ownedTurnRequestId?.let { requestId ->
            assistant.busy && assistant.pendingTurn?.requestId == requestId && assistant.lastRequestReceipt?.requestId == requestId
        } == true
        val speechIsOurs = ownedSpeechRequestId?.let { requestId ->
            assistant.lastRequestReceipt?.requestId == requestId &&
                (assistant.speechBusy || assistant.speechAudio != null)
        } == true
        if (transcriptIsOurs || turnIsOurs) store.cancelAssistantVoiceWork()
        else if (speechIsOurs) store.clearAssistantSpeech()
        ownedTranscriptRequestId = null
        ownedTurnRequestId = null
        ownedSpeechRequestId = null
    }

    private fun foregroundNow(): Boolean = runCatching(isForeground).getOrDefault(false)

    private fun bindingCurrent(binding: VoiceSessionBinding, phase: VoiceSessionPhase): Boolean {
        if (closed || !foregroundNow() || !scopeMatches(store.state.value)) {
            if (!closed && !foregroundNow()) backgrounded()
            else if (!closed && !scopeMatches(store.state.value)) stopForTransition(controller.contextChanged(observedScope(store.state.value)))
            return false
        }
        if (sessionPrivateReplySpeechEnabled?.let { it != store.privateReplySpeechEnabled() } == true) {
            stopForTransition(controller.contextChanged(null))
            return false
        }
        val current = controller.state
        return current.phase == phase && current.scope == binding.scope &&
            current.sessionGeneration == binding.sessionGeneration && current.operationGeneration == binding.operationGeneration
    }

    /** Publish a platform fact only while its exact operation still owns the foreground scope. */
    private fun observePlatformStart(binding: VoiceSessionBinding, phase: VoiceSessionPhase) = synchronized(lock) {
        if (closed || !foregroundNow() || !scopeMatches(store.state.value)) return@synchronized
        if (sessionPrivateReplySpeechEnabled?.let { it != store.privateReplySpeechEnabled() } == true) return@synchronized
        val current = controller.state
        if (current.phase != phase || current.scope != binding.scope ||
            current.sessionGeneration != binding.sessionGeneration || current.operationGeneration != binding.operationGeneration) return@synchronized
        if (phase == VoiceSessionPhase.LISTENING) {
            observedCaptureBinding = binding
            observedPlaybackBinding = null
        } else if (phase == VoiceSessionPhase.SPEAKING) {
            observedPlaybackBinding = binding
            observedCaptureBinding = null
        } else return@synchronized
        publish(current.copy(
            captureStarted = observedCaptureBinding == binding,
            playbackStarted = observedPlaybackBinding == binding,
        ))
    }

    private fun startCapture(binding: VoiceSessionBinding) {
        synchronized(lock) { activeCapture = binding }
        launchOperation(binding) {
            if (!bindingCurrent(binding, VoiceSessionPhase.LISTENING)) return@launchOperation
            val maxSeconds = store.state.value.assistant?.capabilities?.maxAudioSeconds?.takeIf { it in 1..30 }
                ?: run { fail(binding); return@launchOperation }
            val wav = withTimeoutOrNull((maxSeconds + CAPTURE_GRACE_SECONDS) * 1_000L) {
                platform.capture(maxSeconds) { observePlatformStart(binding, VoiceSessionPhase.LISTENING) }
            }
            if (wav == null) { fail(binding); return@launchOperation }
            if (!bindingCurrent(binding, VoiceSessionPhase.LISTENING)) { wav.fill(0); return@launchOperation }
            synchronized(lock) { if (activeCapture == binding) activeCapture = null }
            val transition = controller.captureCompleted(binding)
            if (!accept(transition)) { wav.fill(0); return@launchOperation }
            val asrBinding = transition.effects.filterIsInstance<VoiceSessionEffect.Transcribe>().singleOrNull()?.binding
            if (asrBinding == null) { wav.fill(0); fail(binding); return@launchOperation }
            transcribe(asrBinding, wav)
        }
    }

    private suspend fun transcribe(binding: VoiceSessionBinding, wav: ByteArray) {
        if (!bindingCurrent(binding, VoiceSessionPhase.TRANSCRIBING)) { wav.fill(0); return }
        val priorReceiptId = store.state.value.assistant?.lastRequestReceipt?.requestId
        val accepted = try { store.transcribeAssistant(wav) } catch (_: Exception) { false }
        if (!accepted) { wav.fill(0); fail(binding); return }

        // ConnectedStore owns and wipes an accepted WAV in its finally block.
        val assistantAfterSubmit = store.state.value.assistant
        val requestId = assistantAfterSubmit?.lastRequestReceipt?.requestId?.takeIf(AssistantWire::validRequestId)
            ?.takeIf { it != priorReceiptId && assistantAfterSubmit.library == voiceScope.libraryId && assistantAfterSubmit.generation == voiceScope.appGeneration }
        if (requestId == null) { fail(binding); return }
        ownedTranscriptRequestId = requestId
        val result = awaitAssistantState(binding, STEP_TIMEOUT_MILLIS) { assistant ->
            assistant?.transcript?.localRequestId == requestId ||
                assistant?.let { it.lastRequestReceipt?.requestId == requestId && !it.transcribing && it.failure != null } == true
        }
        if (!bindingCurrent(binding, VoiceSessionPhase.TRANSCRIBING)) return
        val transcript = result?.assistant?.transcript?.takeIf { it.localRequestId == requestId }
        if (transcript == null) { fail(binding); return }
        ownedTranscriptRequestId = null
        val transition = controller.transcriptReady(binding, transcript.text)
        if (!accept(transition)) return
        val request = transition.effects.filterIsInstance<VoiceSessionEffect.SubmitReadOnlyRequest>().singleOrNull()
        if (request == null) { fail(binding); return }
        val acceptedText = store.takeAssistantTranscriptForDraft(transcript)
        if (acceptedText == null) { fail(request.binding); return }
        requestAssistantTurn(request.binding, acceptedText)
    }

    private suspend fun requestAssistantTurn(binding: VoiceSessionBinding, text: String) {
        if (!bindingCurrent(binding, VoiceSessionPhase.REQUESTING)) return
        val priorReceiptId = store.state.value.assistant?.lastRequestReceipt?.requestId
        val accepted = try { store.sendAssistantText(text) } catch (_: Exception) { false }
        if (!accepted) {
            completeRequest(binding, VoiceAssistantReply("", VoiceRequestReceipt.CONFIRMED_FAILURE))
            return
        }
        val assistantAfterSubmit = store.state.value.assistant
        val requestId = assistantAfterSubmit?.pendingTurn?.requestId?.takeIf(AssistantWire::validRequestId)
            ?: assistantAfterSubmit?.lastRequestReceipt?.requestId?.takeIf { AssistantWire.validRequestId(it) && it != priorReceiptId }
        if (requestId == null) {
            completeRequest(binding, VoiceAssistantReply("", VoiceRequestReceipt.UNCERTAIN))
            return
        }
        ownedTurnRequestId = requestId
        val result = awaitAssistantState(binding, STEP_TIMEOUT_MILLIS) { assistant ->
            assistant?.turns?.any { it.localRequestId == requestId } == true ||
                assistant?.let { it.pendingTurn?.requestId == requestId && !it.busy } == true
        }
        if (!bindingCurrent(binding, VoiceSessionPhase.REQUESTING)) return
        val assistant = result?.assistant
        val exchange = assistant?.turns?.firstOrNull { it.localRequestId == requestId }
        if (exchange == null) {
            val receiptStatus = assistant?.privateRequestStatus ?: assistant?.receiptDetail?.status ?: assistant?.lastRequestReceipt?.status
            val receipt = if (receiptStatus in setOf("failed", "interrupted")) VoiceRequestReceipt.CONFIRMED_FAILURE
                else VoiceRequestReceipt.UNCERTAIN
            completeRequest(binding, VoiceAssistantReply("", receipt))
            return
        }
        ownedTurnRequestId = null
        val turn = exchange.turn
        if (turn.recovered) { reviewCompletedRequest(binding); return }
        if (turn.kind == "open" && turn.effect?.type == "open_asset") {
            val privateThread = assistant?.privateThreadId
            val workspace = store.assistantWorkspaceState.value
            val privateOpenCurrent = privateThread != null && workspace.detail?.thread?.threadId == privateThread &&
                workspace.currentTurn?.let { it.requestId == requestId && it.threadId == privateThread &&
                    it.status == AssistantWorkspaceRequestStatus.COMPLETED && !it.recovered &&
                    it.revision == workspace.detail?.thread?.revision } == true
            val asset = if (privateOpenCurrent && turn.items.map { it.id }.distinct().size == turn.items.size)
                turn.items.singleOrNull { it.id == turn.effect.assetId }
                else if (privateThread == null) turn.items.singleOrNull()?.takeIf {
                    it.id == turn.effect.assetId && turn.total == 1 && !turn.hasMore
                } else null
            if (asset == null) {
                reviewCompletedRequest(binding)
                return
            }
            endForOpen(asset, requestId)
            return
        }
        val memoryAction = turn.memoryAction
        if (turn.kind == "memory_cards" && memoryAction != null) {
            val workspace = store.assistantWorkspaceState.value
            val currentTurn = workspace.currentTurn
            val currentResult = currentTurn?.result
            val ordinal = memoryAction.ordinal
            val freshAction = workspace.savedMemoryActionsAvailable && currentTurn?.requestId == requestId &&
                currentTurn.status == AssistantWorkspaceRequestStatus.COMPLETED && !currentTurn.recovered &&
                currentTurn.threadId == assistant?.privateThreadId && currentTurn.revision == workspace.detail?.thread?.revision &&
                currentTurn.revision > 0 && currentResult?.kind == "memory_cards" &&
                currentResult.memoryCards.isNotEmpty() && ordinal in currentResult.memoryCards.indices &&
                currentResult.savedMemoryContext?.libraryId == workspace.libraryId && currentResult.memoryAction == memoryAction &&
                assistant?.turns?.lastOrNull()?.let { it.localRequestId == requestId && !it.turn.recovered &&
                    it.turn.memoryAction == memoryAction && it.turn.memoryCards == currentResult.memoryCards } == true
            if (!freshAction) { reviewCompletedRequest(binding); return }
            val exactTurn = requireNotNull(currentTurn)
            val exactResult = requireNotNull(currentResult)
            when (memoryAction.type) {
                "open" -> {
                    val coordinator = store.assistantWorkspaceCoordinator
                    if (!workspace.savedMemoryReaderAvailable || coordinator == null) {
                        reviewCompletedRequest(binding); return
                    }
                    ownedMemoryReaderOrdinal = ordinal
                    if (!coordinator.openSavedMemoryCard(ordinal)) {
                        ownedMemoryReaderOrdinal = null
                        reviewCompletedRequest(binding); return
                    }
                    val opened = withTimeoutOrNull(STEP_TIMEOUT_MILLIS) {
                        store.assistantWorkspaceState.first { latest ->
                            latest.memoryReaderHandoff != null || latest.memoryReaderErrorOrdinal == ordinal && !latest.busy
                        }
                    }?.let { latest -> latest.memoryReaderHandoff?.let { handoff ->
                        handoff.turnId == requestId && handoff.completionRevision == exactTurn.revision &&
                            handoff.ordinal == ordinal && handoff.card == exactResult.memoryCards[ordinal]
                    } == true } == true
                    if (opened && bindingCurrent(binding, VoiceSessionPhase.REQUESTING)) {
                        ownedMemoryReaderOrdinal = null
                        endForSavedMemory()
                    } else reviewCompletedRequest(binding)
                    return
                }
                "read_opening" -> {
                    if (!workspace.savedMemoryReadingAvailable || !store.canReadAssistantMemoryOpening(ordinal)) {
                        reviewCompletedRequest(binding); return
                    }
                    val transition = controller.requestCompleted(binding, VoiceAssistantReply(
                        text = exactResult.reply, receipt = VoiceRequestReceipt.CONFIRMED_SUCCESS,
                    ))
                    if (!accept(transition)) return
                    val speak = transition.effects.filterIsInstance<VoiceSessionEffect.Speak>().singleOrNull()
                    if (speak == null) { reviewCompletedRequest(binding); return }
                    fetchAndPlaySpeech(speak.binding, memoryOpeningOrdinal = ordinal,
                        parentTurnId = requestId, parentRevision = exactTurn.revision)
                    return
                }
                else -> { reviewCompletedRequest(binding); return }
            }
        }
        val privateReplySpeech = sessionPrivateReplySpeechEnabled == true
        val savedMemorySpeech = turn.kind != "memory_cards" || store.assistantWorkspaceState.value.savedMemorySpeechAvailable
        // An enabled private reply path never silently degrades to a count or truncates the reply.
        if (!savedMemorySpeech || turn.effect != null || if (privateReplySpeech) !store.canReadAssistantReply()
            else turn.kind != "results" || turn.items.isEmpty()) {
            reviewCompletedRequest(binding)
            return
        }
        val transition = controller.requestCompleted(binding, VoiceAssistantReply(
            text = turn.reply,
            receipt = VoiceRequestReceipt.CONFIRMED_SUCCESS,
            disposition = if (privateReplySpeech && turn.kind == "unsupported") VoiceReplyDisposition.REVIEW_REQUIRED
                else VoiceReplyDisposition.READ_ONLY,
            reviewCardId = requestId.takeIf { privateReplySpeech && turn.kind == "unsupported" },
        ))
        if (!accept(transition)) return
        val speak = transition.effects.filterIsInstance<VoiceSessionEffect.Speak>().singleOrNull()
        if (speak == null) { reviewCompletedRequest(binding); return }
        fetchAndPlaySpeech(speak.binding)
    }

    private suspend fun fetchAndPlaySpeech(
        binding: VoiceSessionBinding,
        memoryOpeningOrdinal: Int? = null,
        parentTurnId: String? = null,
        parentRevision: Long? = null,
    ) {
        if (!bindingCurrent(binding, VoiceSessionPhase.SPEAKING)) return
        val priorReceiptId = store.state.value.assistant?.lastRequestReceipt?.requestId
        val loaded = if (memoryOpeningOrdinal != null)
            store.loadAssistantMemoryOpening(memoryOpeningOrdinal, parentTurnId, parentRevision)
        else store.loadAssistantSpeech(language)
        if (!loaded) {
            completeSpeech(binding, success = false)
            return
        }
        val requestId = store.state.value.assistant?.lastRequestReceipt?.requestId
            ?.takeIf(AssistantWire::validRequestId)?.takeIf { it != priorReceiptId }
        if (requestId == null) { completeSpeech(binding, success = false); return }
        // Register ownership before waiting for the server-owned opening. Pause/End can now cancel
        // the in-flight GET/TTS job through ConnectedStore, including before audio is returned.
        ownedSpeechRequestId = requestId
        val capabilityMonitor = if (memoryOpeningOrdinal != null) coroutineScope.launch {
            store.assistantWorkspaceState.first { !it.savedMemoryReadingAvailable || !it.savedMemoryActionsAvailable }
            if (bindingCurrent(binding, VoiceSessionPhase.SPEAKING))
                stopForTransition(controller.contextChanged(null))
        } else null
        try {
            val result = awaitAssistantState(binding, STEP_TIMEOUT_MILLIS) { assistant ->
                assistant?.let { it.speechMemoryOpeningOrdinal == memoryOpeningOrdinal || memoryOpeningOrdinal == null } == true &&
                    (assistant.speechAudio != null && assistant.lastRequestReceipt?.requestId == requestId ||
                        !assistant.speechBusy && assistant.lastRequestReceipt?.requestId == requestId && assistant.failure != null)
            }
            if (!bindingCurrent(binding, VoiceSessionPhase.SPEAKING)) return
            val audio = result?.assistant?.speechAudio?.takeIf {
                result.assistant.lastRequestReceipt?.requestId == requestId
            }
            if (audio == null) { completeSpeech(binding, success = false); return }
            var success = false
            try {
                success = withTimeoutOrNull(STEP_TIMEOUT_MILLIS) {
                    platform.playSpeech(audio) { observePlatformStart(binding, VoiceSessionPhase.SPEAKING) }
                } == true
                store.reportAssistantPlaybackOutcome(audio, if (success) "completed" else "failed")
            } catch (cancelled: CancellationException) {
                store.reportAssistantPlaybackOutcome(audio, "cancelled")
                throw cancelled
            } catch (_: Exception) {
                success = false
                store.reportAssistantPlaybackOutcome(audio, "failed")
            } finally {
                if (!success) runCatching { platform.stopAudio() }
                audio.close()
                val latestAssistant = store.state.value.assistant
                if (ownedSpeechRequestId == requestId && latestAssistant?.lastRequestReceipt?.requestId == requestId &&
                    latestAssistant.speechAudio === audio) store.clearAssistantSpeech()
                if (ownedSpeechRequestId == requestId) ownedSpeechRequestId = null
            }
            if (!bindingCurrent(binding, VoiceSessionPhase.SPEAKING)) return
            completeSpeech(binding, success)
        } finally {
            capabilityMonitor?.cancel()
            if (ownedSpeechRequestId == requestId) {
                // If audio never arrived, clearAssistantSpeech cancels the pending workspace TTS job.
                val latestAssistant = store.state.value.assistant
                if (latestAssistant?.lastRequestReceipt?.requestId == requestId && latestAssistant.speechBusy)
                    store.clearAssistantSpeech()
                ownedSpeechRequestId = null
            }
        }
    }

    private fun completeRequest(binding: VoiceSessionBinding, reply: VoiceAssistantReply) {
        if (!bindingCurrent(binding, VoiceSessionPhase.REQUESTING)) return
        val transition = controller.requestCompleted(binding, reply)
        if (transition.accepted) stopForTransition(transition)
    }

    private fun reviewCompletedRequest(binding: VoiceSessionBinding) {
        if (!bindingCurrent(binding, VoiceSessionPhase.REQUESTING)) return
        stopForTransition(controller.suspendForReview(binding))
    }

    private fun completeSpeech(binding: VoiceSessionBinding, success: Boolean) {
        if (!bindingCurrent(binding, VoiceSessionPhase.SPEAKING)) return
        val transition = controller.speechCompleted(binding, success)
        if (!accept(transition)) return
        transition.effects.filterIsInstance<VoiceSessionEffect.StartCapture>().singleOrNull()?.binding?.let(::startCapture)
    }

    private fun endForOpen(asset: Asset, requestId: String) {
        val transition = controller.end()
        if (!accept(transition)) return
        synchronized(lock) {
            operationJob?.cancel()
            operationJob = null
            activeCapture = null
        }
        runCatching { platform.stopAudio() }
        cancelOwnedStoreWork()
        if (foregroundNow() && scopeMatches(store.state.value)) runCatching { onOpen(asset.id, requestId) }
    }

    /** End only after the source-bound memory handoff is installed and before its UI navigation runs. */
    private fun endForSavedMemory() {
        val transition = controller.end()
        if (!accept(transition)) return
        synchronized(lock) {
            operationJob?.cancel()
            operationJob = null
            activeCapture = null
        }
        runCatching { platform.stopAudio() }
        cancelOwnedStoreWork()
    }

    private suspend fun awaitAssistantState(
        binding: VoiceSessionBinding,
        timeoutMillis: Long,
        matches: (AssistantClientState?) -> Boolean,
    ): LiveState? = withTimeoutOrNull(timeoutMillis) {
        store.state.first { live -> !scopeMatches(live) || matches(live.assistant) }
            .takeIf { scopeMatches(it) && binding.scope == voiceScope }
    }

    private fun fail(binding: VoiceSessionBinding) {
        val phase = controller.state.phase
        if (phase in ACTIVE_WORK_PHASES && bindingCurrent(binding, phase)) {
            stopForTransition(controller.operationFailed(binding))
        }
    }

    private fun accept(transition: VoiceSessionTransition): Boolean {
        if (!transition.accepted) return false
        publish(transition.state)
        return true
    }

    /** Observe every controller and platform snapshot before exposing its ephemeral timing summary. */
    private fun publish(state: VoiceSessionState) {
        timingTracker.observe(state)
        mutableState.value = state.copy(clientTiming = timingTracker.latestSummary)
    }

    private fun launchOperation(binding: VoiceSessionBinding, block: suspend () -> Unit) {
        val job = coroutineScope.launch(start = CoroutineStart.LAZY) {
            try { block() }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) {
                val current = controller.state.phase
                if (current in ACTIVE_WORK_PHASES) fail(binding)
            } finally {
                synchronized(lock) { if (operationJob === coroutineContext[Job]) operationJob = null }
            }
        }
        synchronized(lock) {
            operationJob?.cancel()
            operationJob = job
            job.start()
        }
    }

    private companion object {
        val MONOTONIC_ORIGIN_NANOS: Long = System.nanoTime()
        const val STEP_TIMEOUT_MILLIS = 90_000L
        const val CAPTURE_GRACE_SECONDS = 5
        val ACTIVE_PHASES = setOf(
            VoiceSessionPhase.LISTENING, VoiceSessionPhase.TRANSCRIBING, VoiceSessionPhase.REQUESTING,
            VoiceSessionPhase.SPEAKING, VoiceSessionPhase.PAUSED,
        )
        val ACTIVE_WORK_PHASES = setOf(
            VoiceSessionPhase.LISTENING, VoiceSessionPhase.TRANSCRIBING,
            VoiceSessionPhase.REQUESTING, VoiceSessionPhase.SPEAKING,
        )
    }
}
