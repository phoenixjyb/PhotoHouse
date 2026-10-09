package dev.photohouse.connected.core

/** Metadata for one currently visible chapter; never chapter prose or source recordings. */
data class MemoryBookChapterDiscussionContext(
    val accountId: String, val generation: Long, val library: String, val readerScopeId: Long,
    val bookId: String, val bookRevision: Long, val storyId: String, val storyRevision: Long,
    val chapterId: String, val chapterIndex: Int, val storyTitle: String, val chapterTitle: String,
    val conversationId: String,
)

/** The returned text is only a composer draft. Calling this never sends a request. */
fun memoryBookChapterDiscussionQuestion(context: MemoryBookChapterDiscussionContext, zh: Boolean): String? {
    fun boundedTitle(value: String) = value.isNotBlank() && '\u0000' !in value &&
        value.toByteArray(Charsets.UTF_8).size <= 512
    if (context.chapterIndex !in 0..5 || !boundedTitle(context.storyTitle) || !boundedTitle(context.chapterTitle)) return null
    val text = if (zh) {
        "我正在阅读《${context.storyTitle}》的第 ${context.chapterIndex + 1} 篇章“${context.chapterTitle}”。" +
            "请根据现有来源聊聊这一章，并提出一个可以请家人补充的问题。保留不确定之处，不要编造经历或对白。"
    } else {
        "I'm reading “${context.storyTitle}”, chapter ${context.chapterIndex + 1}: “${context.chapterTitle}”. " +
            "Discuss this chapter using the available sources, and ask one question I could put to my family. " +
            "Keep uncertain details uncertain; do not invent experiences or dialogue."
    }
    return text.takeIf { it.toByteArray(Charsets.UTF_8).size <= 4096 }
}
