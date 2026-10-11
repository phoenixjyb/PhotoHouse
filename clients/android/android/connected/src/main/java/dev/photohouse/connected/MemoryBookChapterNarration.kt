package dev.photohouse.connected

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import dev.photohouse.connected.core.*

/** Immutable, transient speech identity. No text or audio is written to storage. */
private data class MemoirNarrationSnapshot(
    val account: String,
    val generation: Long,
    val library: String,
    val readerScope: Long,
    val book: String,
    val bookRevision: Long,
    val children: List<Pair<String, Long>>,
    val story: String,
    val storyRevision: Long,
    val chapterIndex: Int,
    val chapter: String,
    val text: String,
    val language: String,
) {
    // Retain a deliberate request across one chapter transition, but never a
    // story, account, revision or reader replacement.
    val readerKey get() = listOf(account, generation, library, readerScope,
        book, bookRevision, children, story, storyRevision)
}

private fun memoirNarrationSnapshot(state: LiveState): MemoirNarrationSnapshot? {
    val account = state.session?.account_id ?: return null
    val reading = state.memoryBooks ?: return null
    val book = reading.selectedBook ?: return null
    val story = reading.story ?: return null
    val entry = book.stories.getOrNull(reading.storyIndex ?: return null) ?: return null
    val chapter = story.chapters.getOrNull(reading.selectedChapter) ?: return null
    if (state.library != reading.library || entry.id != story.id || entry.revision != story.revision) return null
    return MemoirNarrationSnapshot(account, state.generation, reading.library, reading.readerScopeId,
        book.id, book.revision, book.stories.map { it.id to it.revision }, story.id, story.revision,
        reading.selectedChapter, chapter.id, "${story.title}. ${chapter.title}. ${chapter.narration}", story.language)
}

private data class PendingMemoirNarration(
    val advance: MemoryBookSpeechAdvanceScope,
    val destination: MemoirNarrationSnapshot,
    val request: ChapterReadAloudStartRequest,
)

/** Next-chapter speech is one explicit user action, with no cross-story autoplay. */
@Composable
internal fun MemoryBookChapterNarration(store: ConnectedStore, zh: Boolean) {
    val state by store.state.collectAsState()
    val snapshot = memoirNarrationSnapshot(state) ?: return
    val lifecycleOwner = LocalLifecycleOwner.current
    var completed by remember(snapshot) { mutableStateOf(false) }
    var pending by remember(snapshot.readerKey) { mutableStateOf<PendingMemoirNarration?>(null) }
    val matchingRequest = pending?.takeIf { it.destination == snapshot }
    val advance = if (completed) store.captureMemoryBookSpeechAdvance() else null

    LaunchedEffect(snapshot, pending?.request?.uniqueId) {
        if (pending?.destination != null && pending?.destination != snapshot) pending = null
    }
    DisposableEffect(lifecycleOwner, snapshot) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_PAUSE || event == Lifecycle.Event.ON_STOP) {
                pending = null
                completed = false
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
    Column(Modifier.fillMaxWidth().testTag("memory-book-chapter-narration"),
        verticalArrangement = Arrangement.spacedBy(8.dp)) {
        ChapterReadAloud(snapshot.text, snapshot.language, snapshot, zh,
            labels = ChapterReadAloudLabels(
                read = if (zh) "朗读本章" else "Read aloud",
                stop = if (zh) "停止朗读" else "Stop reading",
                tagPrefix = "memory-book-narration",
            ),
            enabled = state.memoryBooks?.story?.chapters?.getOrNull(snapshot.chapterIndex)?.narration?.isNotBlank() == true &&
                (matchingRequest == null || store.isCurrentMemoryBookSpeechDestination(matchingRequest.advance)),
            startRequest = matchingRequest?.request,
            onStartRequestConsumed = { id, _ ->
                if (pending?.request?.uniqueId == id) pending = null
            },
            onCompletionChanged = { done ->
                if (memoirNarrationSnapshot(store.state.value) == snapshot) completed = done
            },
        )
        if (advance != null) OutlinedButton(
            onClick = {
                if (!completed || memoirNarrationSnapshot(store.state.value) != snapshot ||
                    lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED).not() ||
                    !store.isCurrentMemoryBookSpeechAdvance(advance) || !store.advanceMemoryBookSpeech(advance)) return@OutlinedButton
                val destination = memoirNarrationSnapshot(store.state.value) ?: return@OutlinedButton
                if (!store.isCurrentMemoryBookSpeechDestination(advance)) return@OutlinedButton
                completed = false
                pending = PendingMemoirNarration(advance, destination, ChapterReadAloudStartRequest(destination))
            },
            modifier = Modifier.fillMaxWidth().testTag("memory-book-continue-narration"),
        ) {
            Text(if (zh) "继续朗读下一章" else "Read next chapter aloud")
        }
    }
}
