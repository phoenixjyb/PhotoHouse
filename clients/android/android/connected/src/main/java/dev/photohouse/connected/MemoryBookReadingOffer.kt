package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.*

/** Offers an explicit location change; a cached pointer never navigates by itself. */
@Composable
internal fun MemoryBookReadingOffer(
    store: ConnectedStore,
    reading: MemoryBooksReading,
    book: MemoryBook,
    position: MemoryBookResumePosition,
    zh: Boolean,
    enabled: Boolean,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val renderedState by store.state.collectAsState()
    val renderedAccount = renderedState.session?.account_id
    val renderedGeneration = renderedState.generation
    val renderedChildren = book.stories.toList()
    fun currentOffer(): Boolean {
        val live = store.state.value
        val current = live.memoryBooks ?: return false
        val currentBook = current.selectedBook ?: return false
        return enabled && live.session?.account_id == renderedAccount && live.generation == renderedGeneration &&
            current.library == reading.library && current.readerScopeId == reading.readerScopeId &&
            currentBook.id == book.id && currentBook.revision == book.revision &&
            currentBook.stories == renderedChildren && current.resumePosition == position && !current.readerBusy
    }
    Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = MaterialTheme.shapes.medium,
        modifier = Modifier.fillMaxWidth().testTag("memory-book-reading-offer")) {
        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(t("Pick up where you left off", "接着上次读"), style = MaterialTheme.typography.titleMedium)
            Text(t("Continue at your saved moment, or start this book from the beginning.",
                "可以回到上次的片段，也可以从头阅读这本回忆册。"))
            Button(onClick = { if (currentOffer()) store.resumeMemoryBookReading(position) }, enabled = enabled,
                modifier = Modifier.fillMaxWidth().testTag("memory-book-resume")) {
                Text(t("Continue last read", "继续上次阅读"))
            }
            OutlinedButton(onClick = { if (currentOffer()) store.startMemoryBookReadingOver(position) }, enabled = enabled,
                modifier = Modifier.fillMaxWidth().testTag("memory-book-start-over")) {
                Text(t("Start from the beginning", "从头阅读"))
            }
        }
    }
}
