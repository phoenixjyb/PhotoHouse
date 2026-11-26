package dev.photohouse.connected.core

/** Capacity of one ordered story in the protected story API. */
object StoryLimits {
    const val MAX_CHAPTERS = 12
    const val MAX_FRAMES_PER_CHAPTER = 4
    const val MAX_FRAMES = MAX_CHAPTERS * MAX_FRAMES_PER_CHAPTER
    internal val chapterId = Regex("chapter-(?:[1-9]|1[0-2])")
}
