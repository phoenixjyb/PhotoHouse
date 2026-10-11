package dev.photohouse.connected

import android.graphics.Bitmap
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.MemoryBook
import dev.photohouse.connected.core.MemoryBookStorySummary
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.io.File

@RunWith(AndroidJUnit4::class)
class MemoryBookShelfCardsUiTest {
    @get:Rule val rule = createComposeRule()

    @Test fun englishGeneratedShelfCardsUseCoversCountsAndGuardDetachedActionsAt150Percent() = runJourney(zh = false)

    @Test fun chineseGeneratedShelfCardsUseCoversCountsAndGuardDetachedActionsAt150Percent() = runJourney(zh = true)

    private fun runJourney(zh: Boolean) {
        val first = book(
            id = "00000000-0000-4000-8000-000000000121",
            title = if (zh) "春日花园" else "A day in the garden",
            intro = "家人讲述。".repeat(60),
            stories = listOf(
                MemoryBookStorySummary("00000000-0000-4000-8000-000000000131", "Garden day", 2, 9, "101"),
                MemoryBookStorySummary("00000000-0000-4000-8000-000000000132", "The walk home", 3, 4, "102"),
            ),
        )
        val second = book(
            id = "00000000-0000-4000-8000-000000000122",
            title = if (zh) "回家的路" else "The way home",
            intro = "",
            stories = listOf(MemoryBookStorySummary("00000000-0000-4000-8000-000000000133", "Home", 1, 2, "201")),
        )
        val validCover = generatedJpeg()
        val malformedCover = byteArrayOf(0x52, 0x49, 0x46, 0x46, 0x01, 0x02, 0x03)
        val opened = mutableListOf<String>()
        val retried = mutableListOf<String>()
        val replacementOpened = mutableListOf<String>()
        val replacementRetried = mutableListOf<String>()
        var showShelf by mutableStateOf(true)

        val initial = ShelfModel(
            books = listOf(first, second),
            covers = mapOf(first.id to validCover, second.id to malformedCover),
            unavailable = setOf(second.id),
            loading = false,
            onOpen = { opened += it.id },
            onRetry = { retried += "retry" },
        )
        var model by mutableStateOf(initial)
        rule.setContent {
            val density = LocalDensity.current
            val current = model
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    if (showShelf) {
                        MemoryBookShelfCards(
                            books = current.books,
                            covers = current.covers,
                            unavailableBookIds = current.unavailable,
                            loadingCovers = current.loading,
                            zh = zh,
                            onOpen = current.onOpen,
                            onRetryCovers = current.onRetry,
                        )
                    }
                }
            }
        }

        rule.onNodeWithTag("memory-book-shelf-cards", useUnmergedTree = true).assertExists()
        reveal("memory-book-${first.id}")
        rule.onNodeWithTag("memory-book-${first.id}", useUnmergedTree = true).assertExists()
        rule.onNodeWithTag("memory-book-cover-${first.id}", useUnmergedTree = true).assertExists()
        reveal("memory-book-shelf-counts-${first.id}")
        rule.onNodeWithTag("memory-book-shelf-counts-${first.id}", useUnmergedTree = true).assertTextEquals(
            if (zh) "2 则故事 · 13 条媒体记录" else "2 stories · 13 media entries",
        )
        val excerpt = "家人讲述。".repeat(48) + "…"
        reveal("memory-book-shelf-introduction-${first.id}")
        rule.onNodeWithTag("memory-book-shelf-introduction-${first.id}", useUnmergedTree = true).assertTextEquals(excerpt)
        reveal("memory-book-cover-${second.id}")
        rule.onNodeWithTag("memory-book-cover-fallback-${second.id}", useUnmergedTree = true).assertExists()
        reveal("memory-book-open-${first.id}")
        rule.onNodeWithTag("memory-book-open-${first.id}", useUnmergedTree = true).assertExists()
        reveal("memory-book-shelf-retry-covers")
        rule.onNodeWithTag("memory-book-shelf-retry-covers", useUnmergedTree = true).assertExists()
        check(opened.isEmpty() && retried.isEmpty()) { "rendering the shelf must not call its actions" }
        reveal("memory-book-shelf-introduction-${first.id}")
        capture(if (zh) "zh" else "en")

        reveal("memory-book-open-${first.id}")
        rule.onNodeWithTag("memory-book-open-${first.id}", useUnmergedTree = true).performClick()
        reveal("memory-book-shelf-retry-covers")
        rule.onNodeWithTag("memory-book-shelf-retry-covers", useUnmergedTree = true).performClick()
        check(opened == listOf(first.id))
        check(retried == listOf("retry"))

        reveal("memory-book-open-${first.id}")
        val detachedRead = captureClick("memory-book-open-${first.id}")
        reveal("memory-book-shelf-retry-covers")
        val detachedRetry = captureClick("memory-book-shelf-retry-covers")
        rule.runOnIdle {
            model = ShelfModel(emptyList(), emptyMap(), emptySet(), false,
                onOpen = { opened += "empty:$it" }, onRetry = { retried += "empty" })
        }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-${first.id}", useUnmergedTree = true).assertDoesNotExist()
        rule.onNodeWithTag("memory-book-shelf-empty", useUnmergedTree = true).assertTextEquals(
            if (zh) "此页没有回忆册。" else "No books on this page.",
        )

        // Same IDs with new collection/callback instances form a new render lifetime.
        val replacementBooks = listOf(first.copy(), second.copy())
        rule.runOnIdle {
            model = ShelfModel(
                replacementBooks,
                mapOf(first.id to validCover.copyOf(), second.id to malformedCover.copyOf()),
                setOf(second.id), false,
                onOpen = { replacementOpened += it.id },
                onRetry = { replacementRetried += "retry" },
            )
        }
        rule.waitForIdle()
        reveal("memory-book-open-${first.id}")
        rule.onNodeWithTag("memory-book-open-${first.id}", useUnmergedTree = true).assertExists()
        rule.runOnIdle {
            detachedRead()
            detachedRetry()
        }
        rule.waitForIdle()
        check(opened == listOf(first.id))
        check(retried == listOf("retry"))
        check(replacementOpened.isEmpty() && replacementRetried.isEmpty()) {
            "actions captured from a detached render must not reach replacement callbacks"
        }

        reveal("memory-book-open-${second.id}")
        rule.onNodeWithTag("memory-book-open-${second.id}", useUnmergedTree = true).performClick()
        reveal("memory-book-shelf-retry-covers")
        rule.onNodeWithTag("memory-book-shelf-retry-covers", useUnmergedTree = true).performClick()
        check(replacementOpened == listOf(second.id))
        check(replacementRetried == listOf("retry"))

        reveal("memory-book-open-${first.id}")
        val unmountedRead = captureClick("memory-book-open-${first.id}")
        reveal("memory-book-shelf-retry-covers")
        val unmountedRetry = captureClick("memory-book-shelf-retry-covers")
        rule.runOnIdle { showShelf = false }
        rule.waitForIdle()
        rule.runOnIdle {
            unmountedRead()
            unmountedRetry()
        }
        rule.waitForIdle()
        check(replacementOpened == listOf(second.id))
        check(replacementRetried == listOf("retry")) {
            "callbacks captured before unmount must not invoke actions afterward"
        }
    }

    private fun book(id: String, title: String, intro: String, stories: List<MemoryBookStorySummary>) =
        MemoryBook(id, revision = 3, canEdit = false, title = title, introduction = intro, language = "zh", stories = stories)

    private fun generatedJpeg(): ByteArray {
        val bitmap = Bitmap.createBitmap(480, 280, Bitmap.Config.ARGB_8888)
        bitmap.eraseColor(android.graphics.Color.rgb(92, 130, 110))
        return ByteArrayOutputStream().use { output ->
            check(bitmap.compress(Bitmap.CompressFormat.JPEG, 88, output))
            bitmap.recycle()
            output.toByteArray()
        }
    }

    private fun captureClick(tag: String): () -> Boolean {
        val node = rule.onNodeWithTag(tag, useUnmergedTree = true).fetchSemanticsNode()
        return checkNotNull(node.config[androidx.compose.ui.semantics.SemanticsActions.OnClick].action)
    }

    private fun reveal(tag: String) {
        rule.onNodeWithTag("memory-book-shelf-cards", useUnmergedTree = true).performScrollToNode(hasTestTag(tag))
    }

    private fun capture(language: String) {
        val bitmap = rule.onNodeWithTag("memory-book-shelf-cards", useUnmergedTree = true).captureToImage().asAndroidBitmap()
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir,
            "memory-book-shelf-cards-$language-150.png").outputStream().use {
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        bitmap.recycle()
    }

    private data class ShelfModel(
        val books: List<MemoryBook>,
        val covers: Map<String, ByteArray>,
        val unavailable: Set<String>,
        val loading: Boolean,
        val onOpen: (MemoryBook) -> Unit,
        val onRetry: () -> Unit,
    )
}
