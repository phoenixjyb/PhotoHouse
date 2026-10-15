package dev.photohouse.connected

import android.graphics.Bitmap
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import dev.photohouse.connected.core.*
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class StoryProposalWordingReviewUiTest {
    @get:Rule val rule = createComposeRule()

    private val storyId = "11111111-1111-1111-1111-111111111111"
    private val sourceId = "family-source-1"

    private fun story(id: String = storyId, revision: Long = 7) = SavedMemoryStory(
        id = id, libraryId = "family", revision = revision, createdAt = 1, updatedAt = 1,
        canEdit = false, selectionRevision = "a".repeat(64), title = "Saved story", theme = "everyday",
        language = "zh", items = emptyList(),
        chapters = listOf(
            SavedMemoryStoryChapter("same", "Same chapter", "Same exact wording", emptyList(), emptyList()),
            SavedMemoryStoryChapter("changed", "Changed chapter", "Current changed wording", emptyList(), emptyList()),
        ), questions = emptyList(),
    )

    private fun community(id: String = storyId, scope: Long = 1) = MemoryCommunityStoryState(
        storyId = id, readerScopeId = scope,
    )

    private fun job(id: String = "job-1", revision: Long = 7) = MemoryJob(
        id = id, kind = "narrative", state = "ready", createdAt = 1, updatedAt = 1,
        expiresAt = 2, errorCode = null, result = null, needsReview = true, baseRevision = revision,
    )

    private fun proposal(changedText: String = "Proposed changed wording") = StoryProposal(
        title = "Proposal title", chapters = listOf(
            StoryProposalChapter("same", "Same exact wording", listOf(sourceId)),
            StoryProposalChapter("changed", changedText, emptyList()),
            StoryProposalChapter("unmatched", "Unmatched proposed wording", emptyList()),
        ), questions = listOf("Question to keep visible"),
    )

    @Test fun mixedReviewKeepsReferencesAndOtherReviewContentWhileFilteringAndResetsOnScopeChanges() {
        var zh by mutableStateOf(false)
        var readerScopeId by mutableStateOf(1L)
        var currentStory by mutableStateOf(story())
        var currentCommunity by mutableStateOf(community())
        var currentJob by mutableStateOf(job())
        var currentProposal by mutableStateOf(proposal())
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    ReviewViewport("wording-viewport") {
                        StoryProposalReview("wording", readerScopeId, currentStory, currentCommunity, currentJob,
                            currentProposal, bindOriginals = true, zh = zh)
                    }
                }
            }
        }

        rule.onNodeWithTag("wording-wording-summary").assertTextEquals("Chapter wording: 1 different · 1 matching · 1 unavailable")
        rule.onNodeWithTag("wording-wording-scope").assertTextEquals(
            "Only chapter wording is compared. Review the title, references and questions separately.")
        rule.onNodeWithTag("wording-title").assertTextEquals("Proposal title")
        rule.onNodeWithTag("wording-question-0").assertTextEquals("• Question to keep visible")
        rule.onNodeWithTag("wording-narration-0").assertTextEquals("Same exact wording")
        rule.onNodeWithTag("wording-wording-same-0").assertDoesNotExist()
        rule.onNodeWithTag("wording-original-toggle-0").assertExists()
        rule.onNodeWithTag("wording-narration-1").assertTextEquals("Proposed changed wording")
        rule.onNodeWithTag("wording-original-toggle-1").assertExists()
        rule.onNodeWithTag("wording-narration-2").assertTextEquals("Unmatched proposed wording")
        rule.onNodeWithTag("wording-wording-unavailable-2").assertTextEquals("Current wording unavailable")

        rule.onNodeWithTag("wording-sources-toggle-0").performScrollTo().performClick()
        rule.onNodeWithTag("wording-sources-0").assertExists()
        rule.onNodeWithText("Source not loaded", substring = true).assertExists()
        rule.onNodeWithTag("wording-original-toggle-0").performScrollTo().performClick()
        rule.onNodeWithTag("wording-original-text-0").assertTextEquals("Same exact wording")
        rule.onNodeWithTag("wording-original-toggle-1").performScrollTo().performClick()
        rule.onNodeWithTag("wording-original-text-1").assertTextEquals("Current changed wording")
        rule.onNodeWithTag("wording-wording-filter").performScrollTo().performClick()
        rule.onNodeWithText("Same exact wording").assertDoesNotExist()
        rule.onNodeWithTag("wording-wording-same-0").assertTextEquals("Wording matches the current story")
        rule.onNodeWithTag("wording-narration-0").assertDoesNotExist()
        rule.onNodeWithTag("wording-original-toggle-0").assertDoesNotExist()
        rule.onNodeWithTag("wording-original-text-0").assertDoesNotExist()
        rule.onNodeWithTag("wording-chapter-title-0").assertExists()
        rule.onNodeWithTag("wording-sources-toggle-0").assertExists()
        rule.onNodeWithTag("wording-sources-0").assertExists()
        rule.onNodeWithTag("wording-title").assertExists()
        rule.onNodeWithTag("wording-question-0").assertExists()

        rule.runOnIdle { readerScopeId = 2; currentCommunity = community(scope = 2) }
        rule.onNodeWithTag("wording-narration-0").assertTextEquals("Same exact wording")
        rule.onNodeWithTag("wording-original-text-1").assertDoesNotExist()
        rule.onNodeWithTag("wording-wording-filter").assertTextEquals("Focus on changed wording")

        rule.onNodeWithTag("wording-wording-filter").performScrollTo().performClick()
        rule.runOnIdle {
            readerScopeId = 3
            currentStory = story(id = "22222222-2222-2222-2222-222222222222", revision = 8)
            currentCommunity = community(id = "22222222-2222-2222-2222-222222222222", scope = 3)
            currentJob = job(id = "job-2", revision = 8)
        }
        rule.onNodeWithTag("wording-narration-0").assertTextEquals("Same exact wording")
        rule.onNodeWithTag("wording-original-text-1").assertDoesNotExist()

        rule.onNodeWithTag("wording-wording-filter").performScrollTo().performClick()
        rule.runOnIdle { currentProposal = proposal(changedText = "A revised proposal") }
        rule.onNodeWithTag("wording-narration-0").assertTextEquals("Same exact wording")
        rule.onNodeWithTag("wording-narration-1").assertTextEquals("A revised proposal")

        rule.runOnIdle { zh = true }
        rule.onNodeWithTag("wording-wording-filter").performScrollTo().assertTextEquals("只看正文变化")
        rule.onNodeWithTag("wording-wording-summary").performScrollTo()
        capture("story-proposal-wording-zh-font150")
        rule.runOnIdle { zh = false }
        rule.onNodeWithTag("wording-wording-summary").performScrollTo()
        capture("story-proposal-wording-en-font150")
    }

    @Test fun allSameReviewShowsCountsTitleQuestionAndCompactRowsWithoutOriginalText() {
        var allSameProposal by mutableStateOf(StoryProposal("All same title", listOf(
            StoryProposalChapter("same", "Same exact wording", emptyList()),
            StoryProposalChapter("changed", "Current changed wording", emptyList()),
        ), listOf("Still review this question")))
        val currentStory = story()
        rule.setContent {
            PhotoHouseTheme {
                ReviewViewport("all-same-viewport") {
                    StoryProposalReview("all-same", 9, currentStory, community(scope = 9), job(), allSameProposal,
                        bindOriginals = true, zh = true)
                }
            }
        }
        rule.onNodeWithTag("all-same-wording-summary").assertTextEquals(
            "章节正文：0 章不同 · 2 章相同 · 0 章暂不可对照")
        rule.onNodeWithTag("all-same-title").assertTextEquals("All same title")
        rule.onNodeWithTag("all-same-question-0").assertTextEquals("• Still review this question")
        rule.onNodeWithTag("all-same-wording-same-0").assertDoesNotExist()
        rule.onNodeWithTag("all-same-wording-same-1").assertDoesNotExist()
        rule.onNodeWithTag("all-same-narration-0").assertTextEquals("Same exact wording")
        rule.onNodeWithTag("all-same-narration-1").assertTextEquals("Current changed wording")
        rule.onNodeWithTag("all-same-original-toggle-0").assertExists()
        rule.onNodeWithTag("all-same-original-toggle-1").assertExists()
        rule.onNodeWithTag("all-same-wording-filter").performScrollTo().performClick()
        rule.onNodeWithTag("all-same-narration-0").assertDoesNotExist()
        rule.onNodeWithTag("all-same-narration-1").assertDoesNotExist()
        rule.onNodeWithTag("all-same-wording-same-0").assertTextEquals("正文与当前故事相同")
        rule.onNodeWithTag("all-same-wording-same-1").assertTextEquals("正文与当前故事相同")
        rule.onNodeWithTag("all-same-original-toggle-0").assertDoesNotExist()
        rule.onNodeWithTag("all-same-original-toggle-1").assertDoesNotExist()
        rule.onNodeWithTag("all-same-title").assertTextEquals("All same title")
        rule.onNodeWithTag("all-same-question-0").assertTextEquals("• Still review this question")
    }

    @Test fun unboundProposalIsUnavailableEvenWhenTextLooksIdentical() {
        val unbound = StoryProposal("Unbound title", listOf(
            StoryProposalChapter("same", "Same exact wording", emptyList()),
        ), emptyList())
        rule.setContent {
            PhotoHouseTheme {
                ReviewViewport("unbound-viewport") {
                    StoryProposalReview("unbound", 4, null, community(scope = 4), job(), unbound,
                        bindOriginals = false, zh = false)
                }
            }
        }
        rule.onNodeWithTag("unbound-wording-summary").assertTextEquals("Chapter wording: 0 different · 0 matching · 1 unavailable")
        rule.onNodeWithTag("unbound-narration-0").assertTextEquals("Same exact wording")
        rule.onNodeWithTag("unbound-wording-unavailable-0").assertTextEquals("Current wording unavailable")
        rule.onNodeWithTag("unbound-wording-same-0").assertDoesNotExist()
    }

    @Test fun duplicateChapterIdsAreUnavailableAndBlankNarrationUsesLiteralEquality() {
        val duplicateStory = story().copy(chapters = listOf(
            SavedMemoryStoryChapter("same", "First copy", "Same exact wording", emptyList(), emptyList()),
            SavedMemoryStoryChapter("same", "Second copy", "Same exact wording", emptyList(), emptyList()),
            SavedMemoryStoryChapter("blank", "Blank", "", emptyList(), emptyList()),
        ))
        val duplicateProposal = StoryProposal("Duplicate title", listOf(
            StoryProposalChapter("same", "Same exact wording", emptyList()),
            StoryProposalChapter("blank", "", emptyList()),
            StoryProposalChapter("repeated", "One", emptyList()),
            StoryProposalChapter("repeated", "Two", emptyList()),
        ), emptyList())
        rule.setContent {
            PhotoHouseTheme {
                ReviewViewport("duplicates-viewport") {
                    StoryProposalReview("duplicates", 5, duplicateStory, community(scope = 5), job(), duplicateProposal,
                        bindOriginals = true, zh = false)
                }
            }
        }
        rule.onNodeWithTag("duplicates-wording-summary").assertTextEquals(
            "Chapter wording: 0 different · 1 matching · 3 unavailable")
        rule.onNodeWithTag("duplicates-narration-1").assertTextEquals("")
        rule.onNodeWithTag("duplicates-wording-same-1").assertDoesNotExist()
        rule.onNodeWithTag("duplicates-wording-unavailable-0").assertTextEquals("Current wording unavailable")
        rule.onNodeWithTag("duplicates-wording-unavailable-2").assertTextEquals("Current wording unavailable")
        rule.onNodeWithTag("duplicates-wording-unavailable-3").assertTextEquals("Current wording unavailable")
        rule.onNodeWithTag("duplicates-wording-filter").performScrollTo().performClick()
        rule.onNodeWithTag("duplicates-narration-1").assertDoesNotExist()
        rule.onNodeWithTag("duplicates-wording-same-1").assertTextEquals("Wording matches the current story")
    }

    private fun capture(name: String) {
        val bitmap = rule.onNodeWithTag("wording-viewport").captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.filesDir.resolve("$name.png").outputStream().use { out ->
            assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, out))
        }
        bitmap.recycle()
    }

    @Composable
    private fun ReviewViewport(tag: String, content: @Composable () -> Unit) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).testTag(tag)) {
            content()
        }
    }
}
