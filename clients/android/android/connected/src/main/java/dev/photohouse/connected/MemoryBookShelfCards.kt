package dev.photohouse.connected

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.photohouse.connected.core.MemoryBook

/** Presentational shelf cards. The caller owns loading, scrolling height, and scope authorization. */
@Composable
internal fun MemoryBookShelfCards(
    books: List<MemoryBook>,
    covers: Map<String, ByteArray>,
    unavailableBookIds: Set<String>,
    loadingCovers: Boolean,
    zh: Boolean,
    onOpen: (MemoryBook) -> Unit,
    onRetryCovers: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val renderLifetime = remember(
        IdentityKey(books), IdentityKey(covers), IdentityKey(unavailableBookIds),
        IdentityKey(onOpen), IdentityKey(onRetryCovers),
    ) { Any() }
    var activeLifetime by remember { mutableStateOf<Any?>(null) }
    SideEffect { activeLifetime = renderLifetime }
    DisposableEffect(renderLifetime) {
        onDispose {
            if (activeLifetime === renderLifetime) activeLifetime = null
        }
    }

    val visibleBooks = books.take(MAX_SHELF_BOOKS)
    val scrollState = rememberLazyListState()
    // Recreate event nodes for a replaced render without losing the current scroll position.
    key(renderLifetime) {
        LazyColumn(
            state = scrollState,
            modifier = modifier.testTag("memory-book-shelf-cards"),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (visibleBooks.isEmpty()) {
                item(key = "empty-shelf") {
                    Text(
                        if (zh) "此页没有回忆册。" else "No books on this page.",
                        modifier = Modifier.fillMaxWidth().padding(24.dp).testTag("memory-book-shelf-empty"),
                    )
                }
            } else {
                items(visibleBooks, key = { it.id }) { book ->
                    val open = {
                        if (activeLifetime === renderLifetime && visibleBooks.any { it === book }) onOpen(book)
                    }
                    Card(
                        modifier = Modifier.fillMaxWidth()
                            .testTag("memory-book-${book.id}")
                            .clickable(onClick = open),
                        shape = RoundedCornerShape(22.dp),
                    ) {
                        Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            MemoryBookShelfCover(
                                bookId = book.id,
                                bytes = covers[book.id],
                                zh = zh,
                            )
                            Text(
                                book.title,
                                style = MaterialTheme.typography.titleLarge,
                                fontFamily = FontFamily.Serif,
                                maxLines = 3,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.testTag("memory-book-shelf-title-${book.id}"),
                            )
                            val storyCount = book.stories.size
                            val mediaEntryCount = book.stories.sumOf { it.itemCount.coerceAtLeast(0).toLong() }
                            Text(
                                if (zh) "$storyCount 则故事 · $mediaEntryCount 条媒体记录"
                                else "$storyCount stories · $mediaEntryCount media entries",
                                style = MaterialTheme.typography.bodyMedium,
                                modifier = Modifier.testTag("memory-book-shelf-counts-${book.id}"),
                            )
                            book.introduction.takeMemoirExcerpt()?.let { excerpt ->
                                Text(
                                    excerpt,
                                    style = MaterialTheme.typography.bodyLarge,
                                    maxLines = 4,
                                    overflow = TextOverflow.Ellipsis,
                                    modifier = Modifier.testTag("memory-book-shelf-introduction-${book.id}"),
                                )
                            }
                            Button(
                                onClick = open,
                                modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                                    .testTag("memory-book-open-${book.id}"),
                            ) {
                                Text(if (zh) "阅读回忆册" else "Read memoir")
                            }
                        }
                    }
                }
            }
            if (loadingCovers) {
                item(key = "covers-loading") {
                    LinearProgressIndicator(
                        Modifier.fillMaxWidth().testTag("memory-book-shelf-covers-loading"),
                    )
                }
            } else if (unavailableBookIds.isNotEmpty()) {
                item(key = "covers-retry") {
                    val retry = {
                        if (activeLifetime === renderLifetime) onRetryCovers()
                    }
                    OutlinedButton(
                        onClick = retry,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                            .testTag("memory-book-shelf-retry-covers"),
                    ) {
                        Text(if (zh) "重新加载封面" else "Retry covers")
                    }
                }
            }
        }
    }
}

@Composable
private fun MemoryBookShelfCover(bookId: String, bytes: ByteArray?, zh: Boolean) {
    val shape = RoundedCornerShape(18.dp)
    val bitmap = remember(bookId, bytes) { bytes?.let(::decodeShelfCover) }
    DisposableEffect(bitmap) {
        onDispose { if (bitmap != null && !bitmap.isRecycled) bitmap.recycle() }
    }
    Box(
        Modifier.fillMaxWidth().aspectRatio(1.64f).clip(shape)
            .testTag("memory-book-cover-$bookId"),
        contentAlignment = Alignment.Center,
    ) {
        if (bitmap != null && !bitmap.isRecycled) {
            Image(
                bitmap = bitmap.asImageBitmap(),
                contentDescription = null,
                modifier = Modifier.fillMaxSize(),
                contentScale = androidx.compose.ui.layout.ContentScale.Crop,
            )
        } else {
            MemoirCoverFallback(bookId = bookId, zh = zh)
        }
    }
}

@Composable
private fun MemoirCoverFallback(bookId: String, zh: Boolean) {
    val scheme = MaterialTheme.colorScheme
    val palettes = listOf(
        scheme.primaryContainer to scheme.tertiaryContainer,
        scheme.secondaryContainer to scheme.primaryContainer,
        scheme.tertiaryContainer to scheme.secondaryContainer,
    )
    val palette = palettes[(bookId.hashCode() and Int.MAX_VALUE) % palettes.size]
    Column(
        Modifier.fillMaxSize()
            .background(Brush.linearGradient(listOf(palette.first, palette.second)))
            .testTag("memory-book-cover-fallback-$bookId")
            .clearAndSetSemantics { },
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("✦", color = scheme.onSecondaryContainer, fontSize = 42.sp, lineHeight = 48.sp)
        Text(
            if (zh) "家庭回忆" else "Family memories",
            color = scheme.onSurfaceVariant,
            style = MaterialTheme.typography.titleMedium,
            fontFamily = FontFamily.Serif,
        )
    }
}

private fun decodeShelfCover(bytes: ByteArray): Bitmap? {
    if (bytes.isEmpty() || bytes.size > MAX_COVER_BYTES) return null
    return try {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        val width = bounds.outWidth
        val height = bounds.outHeight
        if (width !in 1..MAX_SOURCE_DIMENSION || height !in 1..MAX_SOURCE_DIMENSION) return null

        var sample = 1
        while (width.toLong() / sample * (height.toLong() / sample) > MAX_DECODE_PIXELS ||
            maxOf(width, height) / sample > MAX_DECODE_DIMENSION) {
            sample *= 2
        }
        val decoded = BitmapFactory.decodeByteArray(bytes, 0, bytes.size,
            BitmapFactory.Options().apply {
                inSampleSize = sample
                inPreferredConfig = Bitmap.Config.ARGB_8888
            }) ?: return null
        if (decoded.width <= 0 || decoded.height <= 0 || decoded.width > MAX_DECODE_DIMENSION ||
            decoded.height > MAX_DECODE_DIMENSION || decoded.width.toLong() * decoded.height > MAX_DECODE_PIXELS) {
            decoded.recycle()
            null
        } else decoded
    } catch (_: OutOfMemoryError) {
        null
    } catch (_: Exception) {
        null
    }
}

private fun String.takeMemoirExcerpt(limit: Int = MAX_INTRODUCTION_CODE_POINTS): String? {
    val clean = trim()
    if (clean.isEmpty()) return null
    val count = clean.codePointCount(0, clean.length)
    if (count <= limit) return clean
    return clean.substring(0, clean.offsetByCodePoints(0, limit)) + "…"
}

/** Remember keys that compare their wrapped values by identity, not collection contents. */
private class IdentityKey(private val value: Any) {
    override fun equals(other: Any?): Boolean = other is IdentityKey && other.value === value
    override fun hashCode(): Int = System.identityHashCode(value)
}

private const val MAX_SHELF_BOOKS = 8
private const val MAX_INTRODUCTION_CODE_POINTS = 240
private const val MAX_COVER_BYTES = 8 * 1024 * 1024
private const val MAX_SOURCE_DIMENSION = 16_384
private const val MAX_DECODE_DIMENSION = 2_048
private const val MAX_DECODE_PIXELS = 1_500_000L
