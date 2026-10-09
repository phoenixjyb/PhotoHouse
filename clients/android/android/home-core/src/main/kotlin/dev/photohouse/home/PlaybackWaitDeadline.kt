package dev.photohouse.home

/** Monotonic, caller-confined deadline for one continuous player wait.
 * Changing from prepare to buffering/seek must not extend an existing wait.
 * No media, identifiers or network state is retained here.
 */
class PlaybackWaitDeadline(private val timeoutMillis: Long = 30_000) {
    enum class Phase { PREPARING, SEEKING, BUFFERING }
    init { require(timeoutMillis > 0) }
    private var startedAt: Long? = null
    private var fired = false

    fun update(phase: Phase?, nowMillis: Long): Phase? {
        require(nowMillis >= 0)
        if (phase == null) { startedAt = null; fired = false; return null }
        val start = startedAt ?: nowMillis.also { startedAt = it }
        if (fired || nowMillis < start || nowMillis - start < timeoutMillis) return null
        fired = true
        return phase
    }
    fun reset() { startedAt = null; fired = false }
}
