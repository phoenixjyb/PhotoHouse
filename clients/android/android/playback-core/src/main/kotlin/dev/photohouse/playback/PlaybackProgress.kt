package dev.photohouse.playback

/** Bounded, memory-only history. Each store owns a separate access scope. */
class PlaybackProgress(private val capacity: Int = 100) {
    init { require(capacity > 0) }
    private val entries = linkedMapOf<String, Int>()
    private var generation = 0L
    fun open(identity: String): PlaybackBookmark {
        val epoch = generation
        return PlaybackBookmark(entries[identity] ?: 0) { position, duration ->
            if (epoch == generation && duration > 0 && position in 0..duration) {
                // A finished/very short video should start from the beginning next time.
                entries.remove(identity)
                if (position >= 3000 && duration - position > 3000) entries[identity] = position
                while (entries.size > capacity) entries.remove(entries.keys.first())
            }
        }
    }
    fun clear() { generation++; entries.clear() }
}

/** The identity includes the exact representation; it never contains a credential. */
class PlaybackBookmark internal constructor(val positionMillis: Int, private val save: (Int, Int) -> Unit) {
    private var closed = false
    fun record(position: Int, duration: Int) { if (!closed) save(position, duration) }
    fun close() { closed = true }
}
