package dev.photohouse.connected.core

/**
 * Client-observed elapsed times for one successfully completed voice turn.
 * These measure local phase boundaries (including scheduling, network wait and
 * playback startup); they are not provider-side ASR, model or TTS latency.
 * The summary deliberately carries no session IDs, transcript, reply, source or
 * audio data and is never persisted or transmitted by this type.
 */
data class VoiceTurnTimingSummary(
    val transcriptionMillis: Long,
    val requestMillis: Long,
    val speechPreparationMillis: Long,
    val playbackMillis: Long,
) {
    init {
        require(transcriptionMillis >= 0)
        require(requestMillis >= 0)
        require(speechPreparationMillis >= 0)
        require(playbackMillis >= 0)
    }
}

/**
 * Pure observer for completed client voice turns. Call [observe] with the
 * controller's explicit state snapshots and a monotonic millisecond clock.
 * Only a full TRANSCRIBING → REQUESTING → SPEAKING (confirmed playback start)
 * → LISTENING cycle publishes a summary. No provider timing is inferred.
 */
class VoiceTurnTimingTracker(private val monotonicMillis: () -> Long) {
    private data class Identity(val scope: VoiceSessionScope, val sessionGeneration: Long)

    private data class Progress(
        val transcriptionStartedAt: Long? = null,
        val transcriptionMillis: Long? = null,
        val requestStartedAt: Long? = null,
        val requestMillis: Long? = null,
        val speechStartedAt: Long? = null,
        val speechPreparationMillis: Long? = null,
        val playbackStartedAt: Long? = null,
    )

    private var highestAppGeneration = -1L
    private var highestSessionGeneration = -1L
    private var identity: Identity? = null
    private var blockedAtCurrentGeneration = false
    private var closedAtCurrentGeneration = false
    private var highestOperationGeneration = -1L
    private var lastPhase: VoiceSessionPhase? = null
    private var lastCaptureStarted = false
    private var lastPlaybackStarted = false
    private var progress: Progress? = null
    private var publishedSummary: VoiceTurnTimingSummary? = null
    private var lastClockSample: Long? = null
    private var clockInvalidForSession = false

    /** The most recently completed summary in the active session, if any. */
    @get:Synchronized
    val latestSummary: VoiceTurnTimingSummary? get() = publishedSummary

    /**
     * Observe one immutable controller snapshot. Stale generations are ignored;
     * malformed transitions clear the current summary and pending turn.
     */
    @Synchronized
    fun observe(state: VoiceSessionState) {
        if (state.phase == VoiceSessionPhase.IDLE) {
            clearCurrent()
            identity = null
            clearClockSession()
            return
        }

        val scope = state.scope
        if (scope == null || state.sessionGeneration <= 0 || state.operationGeneration <= 0) {
            clearCurrent()
            identity = null
            return
        }

        val incoming = Identity(scope, state.sessionGeneration)
        if (isOlder(incoming)) return

        if (isNewer(incoming)) {
            clearCurrent()
            clearClockSession()
            highestAppGeneration = scope.appGeneration
            highestSessionGeneration = state.sessionGeneration
            identity = null
            blockedAtCurrentGeneration = false
            closedAtCurrentGeneration = false
            highestOperationGeneration = state.operationGeneration
            if (state.phase == VoiceSessionPhase.PAUSED || state.phase == VoiceSessionPhase.ENDED) {
                closedAtCurrentGeneration = true
                return
            }
            if (state.phase != VoiceSessionPhase.LISTENING || state.reason != null || state.playbackStarted) {
                blockCurrentGeneration(state)
                return
            }
            identity = incoming
            lastPhase = state.phase
            lastCaptureStarted = state.captureStarted
            lastPlaybackStarted = false
            return
        }

        // Same app/session generation. A scope change without a generation
        // change is ambiguous and must not let either scope publish timings.
        if (identity != null && identity != incoming) {
            clearCurrent()
            identity = null
            blockedAtCurrentGeneration = true
            closedAtCurrentGeneration = false
            highestOperationGeneration = maxOf(highestOperationGeneration, state.operationGeneration)
            return
        }

        if (state.phase == VoiceSessionPhase.PAUSED || state.phase == VoiceSessionPhase.ENDED) {
            if (identity == incoming && state.operationGeneration < highestOperationGeneration) return
            clearCurrent()
            identity = null
            clearClockSession()
            closedAtCurrentGeneration = true
            highestOperationGeneration = maxOf(highestOperationGeneration, state.operationGeneration)
            return
        }

        if (blockedAtCurrentGeneration || closedAtCurrentGeneration || identity != incoming) return
        if (state.operationGeneration < highestOperationGeneration) return
        if (state.reason != null) {
            invalidate(state)
            return
        }

        val previousPhase = lastPhase
        val previousOperation = highestOperationGeneration
        if (state.operationGeneration == previousOperation) {
            observeSameOperation(state, previousPhase)
            return
        }

        // The controller advances the operation generation at each phase
        // transition. A different phase with a non-advancing generation is
        // rejected above; operation-generation gaps are okay only on a valid
        // adjacent phase edge so skipped phases never produce a summary.
        when {
            previousPhase == VoiceSessionPhase.LISTENING &&
                state.phase == VoiceSessionPhase.TRANSCRIBING &&
                lastCaptureStarted &&
                !state.captureStarted && !state.playbackStarted -> {
                val started = sampleClock()
                progress = started?.let { Progress(transcriptionStartedAt = it) }
            }

            previousPhase == VoiceSessionPhase.TRANSCRIBING &&
                state.phase == VoiceSessionPhase.REQUESTING &&
                !state.captureStarted && !state.playbackStarted -> {
                val startedAt = progress?.transcriptionStartedAt
                val boundary = sampleClock()
                val transcriptionMillis = startedAt?.let { elapsed(it, boundary) }
                progress = if (transcriptionMillis != null && boundary != null) {
                    Progress(
                        transcriptionStartedAt = startedAt,
                        transcriptionMillis = transcriptionMillis,
                        requestStartedAt = boundary,
                    )
                } else null
            }

            previousPhase == VoiceSessionPhase.REQUESTING &&
                state.phase == VoiceSessionPhase.SPEAKING &&
                !state.captureStarted && !state.playbackStarted -> {
                val requestStart = progress?.requestStartedAt
                val transcriptionMillis = progress?.transcriptionMillis
                val boundary = sampleClock()
                val requestMillis = requestStart?.let { elapsed(it, boundary) }
                progress = if (requestMillis != null && transcriptionMillis != null && boundary != null) {
                    Progress(
                        transcriptionMillis = transcriptionMillis,
                        requestMillis = requestMillis,
                        speechStartedAt = boundary,
                    )
                } else null
            }

            previousPhase == VoiceSessionPhase.SPEAKING &&
                state.phase == VoiceSessionPhase.LISTENING &&
                !state.playbackStarted -> {
                val previous = progress
                val playbackStart = previous?.playbackStartedAt
                val playbackMillis = if (lastPlaybackStarted) playbackStart?.let { elapsed(it, sampleClock()) } else null
                if (previous != null && playbackMillis != null &&
                    previous.transcriptionMillis != null && previous.requestMillis != null &&
                    previous.speechPreparationMillis != null) {
                    publishedSummary = VoiceTurnTimingSummary(
                        transcriptionMillis = previous.transcriptionMillis,
                        requestMillis = previous.requestMillis,
                        speechPreparationMillis = previous.speechPreparationMillis,
                        playbackMillis = playbackMillis,
                    )
                } else {
                    publishedSummary = null
                }
                progress = null
            }

            else -> {
                invalidate(state)
                return
            }
        }

        highestOperationGeneration = state.operationGeneration
        lastPhase = state.phase
        lastCaptureStarted = state.captureStarted
        lastPlaybackStarted = state.playbackStarted
    }

    private fun observeSameOperation(state: VoiceSessionState, previousPhase: VoiceSessionPhase?) {
        if (state.phase != previousPhase || state.reason != null) {
            invalidate(state)
            return
        }
        when (state.phase) {
            VoiceSessionPhase.LISTENING -> {
                if (lastCaptureStarted && !state.captureStarted || state.playbackStarted) invalidate(state)
                else lastCaptureStarted = state.captureStarted
            }
            VoiceSessionPhase.SPEAKING -> {
                if (lastPlaybackStarted && !state.playbackStarted || state.captureStarted) {
                    invalidate(state)
                } else if (!lastPlaybackStarted && state.playbackStarted) {
                    val startedAt = progress?.speechStartedAt
                    val boundary = sampleClock()
                    val preparation = startedAt?.let { elapsed(it, boundary) }
                    val current = progress
                    progress = if (current != null && preparation != null && boundary != null) {
                        current.copy(speechPreparationMillis = preparation, playbackStartedAt = boundary)
                    } else null
                    lastPlaybackStarted = true
                }
            }
            VoiceSessionPhase.TRANSCRIBING, VoiceSessionPhase.REQUESTING -> {
                if (state.captureStarted || state.playbackStarted) invalidate(state)
            }
            else -> invalidate(state)
        }
    }

    private fun invalidate(state: VoiceSessionState) {
        publishedSummary = null
        progress = null
        highestOperationGeneration = maxOf(highestOperationGeneration, state.operationGeneration)
        lastPhase = state.phase
        lastCaptureStarted = state.captureStarted
        lastPlaybackStarted = state.playbackStarted
    }

    private fun blockCurrentGeneration(state: VoiceSessionState) {
        publishedSummary = null
        progress = null
        identity = null
        blockedAtCurrentGeneration = true
        highestOperationGeneration = state.operationGeneration
        lastPhase = state.phase
        lastCaptureStarted = state.captureStarted
        lastPlaybackStarted = state.playbackStarted
    }

    private fun clearCurrent() {
        publishedSummary = null
        progress = null
        lastPhase = null
        lastCaptureStarted = false
        lastPlaybackStarted = false
    }

    /** Clear all observations and generation fences when the owning voice store closes. */
    @Synchronized
    fun clear() {
        clearCurrent()
        identity = null
        blockedAtCurrentGeneration = false
        closedAtCurrentGeneration = false
        highestAppGeneration = -1L
        highestSessionGeneration = -1L
        highestOperationGeneration = -1L
        clearClockSession()
    }

    private fun clearClockSession() {
        lastClockSample = null
        clockInvalidForSession = false
    }

    private fun isOlder(incoming: Identity): Boolean =
        incoming.scope.appGeneration < highestAppGeneration ||
            (incoming.scope.appGeneration == highestAppGeneration &&
                incoming.sessionGeneration < highestSessionGeneration)

    private fun isNewer(incoming: Identity): Boolean =
        incoming.scope.appGeneration > highestAppGeneration ||
            (incoming.scope.appGeneration == highestAppGeneration &&
                incoming.sessionGeneration > highestSessionGeneration)

    private fun sampleClock(): Long? {
        if (clockInvalidForSession) return null
        val current = runCatching(monotonicMillis).getOrNull()
        if (current == null || current < 0 || lastClockSample?.let { current < it } == true) {
            clockInvalidForSession = true
            publishedSummary = null
            progress = null
            return null
        }
        lastClockSample = current
        return current
    }

    private fun elapsed(start: Long, end: Long?): Long? {
        if (start < 0 || end == null || end < start) return null
        val difference = end - start
        return difference.takeIf { it >= 0 }
    }

}
