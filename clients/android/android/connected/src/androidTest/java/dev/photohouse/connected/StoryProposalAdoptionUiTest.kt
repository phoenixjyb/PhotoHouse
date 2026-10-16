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
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.Asset
import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class StoryProposalAdoptionUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun stop() { scope.cancel() }

    private val storyId = "11111111-1111-1111-1111-111111111111"

    private fun story() = SavedMemoryStory(
        id = storyId, libraryId = "family", revision = 7, createdAt = 1, updatedAt = 1,
        canEdit = true, selectionRevision = "a".repeat(64), title = "Saved story", theme = "everyday",
        language = "zh", items = emptyList(),
        chapters = listOf(
            SavedMemoryStoryChapter("chapter-1", "Opening", "Current opening", emptyList(), emptyList()),
            SavedMemoryStoryChapter("chapter-2", "Later", "Current later chapter", emptyList(), emptyList()),
        ), questions = emptyList(),
    )

    private fun community(scope: Long) = MemoryCommunityStoryState(storyId = storyId, readerScopeId = scope)

    private fun job() = MemoryJob(
        id = "job-1", kind = "narrative", state = "ready", createdAt = 1, updatedAt = 1,
        expiresAt = 2, errorCode = null, result = null, needsReview = true, baseRevision = 7,
    )

    private fun proposal() = StoryProposal("Proposal title", listOf(
        StoryProposalChapter("chapter-1", "Proposed opening", emptyList()),
        StoryProposalChapter("chapter-2", "Proposed later chapter", emptyList()),
    ), listOf("Confirm the year"))

    @Test fun adoptionRequiresExplicitChapterTitleAndReviewChoicesAndResetsWithReaderScope() {
        var readerScopeId by mutableStateOf(1L)
        var currentCommunity by mutableStateOf(community(1))
        var eligible by mutableStateOf(true)
        var zh by mutableStateOf(false)
        var adopted: Pair<List<String>, Boolean>? by mutableStateOf(null)
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
            PhotoHouseTheme {
                ReviewViewport("adoption-viewport") {
                    StoryProposalReview(
                        tagPrefix = "adoption", readerScopeId = readerScopeId, story = story(),
                        community = currentCommunity, job = job(), proposal = proposal(),
                        bindOriginals = true, zh = zh,
                        canAdopt = { selected, adoptTitle ->
                            eligible && selected.isNotEmpty() && selected.all { it.startsWith("chapter-") }
                        },
                        onAdopt = { selected, adoptTitle ->
                            adopted = selected to adoptTitle
                            true
                        },
                    )
                }
            }
            }
        }

        rule.onNodeWithTag("adoption-adopt-import").assertIsNotEnabled()
        rule.onNodeWithTag("adoption-adopt-chapter-0").assertIsOff()
        rule.onNodeWithTag("adoption-adopt-chapter-1").assertIsOff()
        rule.onNodeWithTag("adoption-adopt-chapter-0").performScrollTo().performClick()
        rule.onNodeWithTag("adoption-adopt-import").assertIsNotEnabled()
        rule.onNodeWithTag("adoption-adopt-acknowledgment").performScrollTo().performClick()
        rule.onNodeWithTag("adoption-adopt-import").assertIsEnabled()

        rule.runOnIdle { eligible = false }
        rule.onNodeWithTag("adoption-adopt-import").assertIsNotEnabled()
        rule.onNodeWithTag("adoption-adopt-source-warning").assertExists()
        rule.runOnIdle { eligible = true }

        rule.onNodeWithTag("adoption-adopt-title").performScrollTo().performClick()
        rule.onNodeWithTag("adoption-adopt-acknowledgment").assertIsOff()
        rule.onNodeWithTag("adoption-adopt-import").assertIsNotEnabled()
        rule.onNodeWithTag("adoption-adopt-acknowledgment").performScrollTo().performClick()
        rule.onNodeWithTag("adoption-adopt-import").performScrollTo()
        capture("story-proposal-selection-en-150.png", "adoption-viewport")
        rule.runOnIdle { zh = true }
        capture("story-proposal-selection-zh-150.png", "adoption-viewport")
        rule.onNodeWithTag("adoption-adopt-import").performScrollTo().performClick()
        rule.runOnIdle {
            assertEquals(listOf("chapter-1") to true, adopted)
            readerScopeId = 2
            currentCommunity = community(2)
        }
        rule.onNodeWithTag("adoption-adopt-chapter-0").assertIsOff()
        rule.onNodeWithTag("adoption-adopt-title").assertIsOff()
        rule.onNodeWithTag("adoption-adopt-acknowledgment").assertIsOff()
        rule.onNodeWithTag("adoption-adopt-import").assertIsNotEnabled()
    }

    @Test fun readOnlyProposalHasNoAdoptionControls() {
        rule.setContent {
            PhotoHouseTheme {
                ReviewViewport("readonly-adoption-viewport") {
                    StoryProposalReview(
                        tagPrefix = "readonly", readerScopeId = 3, story = story().copy(canEdit = false),
                        community = community(3), job = job(), proposal = proposal(),
                        bindOriginals = true, zh = false,
                    )
                }
            }
        }
        rule.onNodeWithTag("readonly-adopt-import").assertDoesNotExist()
        rule.onNodeWithTag("readonly-adopt-chapter-0").assertDoesNotExist()
        rule.onNodeWithTag("readonly-adopt-title").assertDoesNotExist()
    }

    @Test fun importedProposalBannerStaysScrollableAtLargeTextInBothLanguages() {
        val binding = MemoryCommunityBinding(
            Bearer.from(SessionToken(86400, "P".repeat(43), "Bearer")), "family", 1,
        )
        val api = object : StoryWorkspaceApi {
            override suspend fun storyPreview(token: Bearer, library: String, json: String) = error("unused")
            override suspend fun storyTitleCapabilities(token: Bearer, library: String) = error("unused")
            override suspend fun storyTitles(token: Bearer, library: String, json: String) = error("unused")
            override suspend fun createGroupedStory(token: Bearer, library: String, json: String) = error("unused")
        }
        val savedStory = SavedMemoryStory(
            id = storyId, libraryId = "family", revision = 7, createdAt = 1, updatedAt = 1,
            canEdit = true, selectionRevision = "a".repeat(64), title = "Garden day", theme = "everyday",
            language = "zh", items = listOf(MemoryStoryAsset(
                Asset("1", "image", 800, 600, null, null, "/assets/1/thumbnail"), emptyList(),
            )),
            chapters = listOf(SavedMemoryStoryChapter("chapter-1", "Opening", "Original family words", listOf("1"), emptyList())),
            questions = emptyList(),
        )
        val references = SavedMemoryStoryContributionReferences(
            storyId, "family", 7, listOf(SavedMemoryChapterContributionReferences("chapter-1", emptyList())),
        )
        val longQuestion = "请核对这段回忆 " + "请核对回忆细节".repeat(20)
        val questionsJson = (1..6).joinToString(",") { "\"$longQuestion $it\"" }
        val job = MemoryJob(
            id = "22222222-2222-4222-8222-222222222222", kind = "narrative", state = "ready",
            createdAt = 1, updatedAt = 1, expiresAt = 2, errorCode = null,
            result = Json.parseToJsonElement(
                """{"version":1,"needs_review":true,"title":"A proposal title","chapters":[{"id":"chapter-1","narration":"AI proposed wording","source_ids":[]}],"questions":[$questionsJson]}""",
            ).jsonObject,
            needsReview = true, baseRevision = 7,
        )
        val proposalDraft = storyProposalAdoptionDraft(savedStory, references, job, listOf("chapter-1"), false)
        assertTrue("The generated proposal should pass the same adoption preflight used by the editor.", proposalDraft != null)
        val store = StoryWorkspaceStore(
            StoryWorkspaceRepository(api, { binding }), scope, { binding }, dictationApi = null,
            currentAccount = { "synthetic-member" },
        )
        assertTrue(store.seedSavedStoryForEdit(savedStory, references))
        assertTrue(store.applyReviewedStoryProposal(requireNotNull(proposalDraft)))

        var zh by mutableStateOf(true)
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    GroupedStoryReview(store, zh, {}, {}, isSavedEdit = true)
                }
            }
        }

        for (languageZh in listOf(true, false)) {
            rule.runOnIdle { zh = languageZh }
            rule.onNodeWithTag("story-proposal-import-provenance").assertExists()
            rule.onNodeWithTag("story-proposal-import-unreviewed").assertExists()
            rule.onNodeWithTag("story-proposal-import-question-0").assertDoesNotExist()
            rule.onNodeWithTag("story-proposal-import-provenance").performScrollTo()
            capture("story-proposal-import-${if (languageZh) "zh" else "en"}-150-collapsed.png")

            rule.onNodeWithTag("story-proposal-import-questions-toggle").performScrollTo().performClick()
            rule.onNodeWithTag("story-proposal-import-question-5").performScrollTo().assertExists()
            rule.onNodeWithTag("grouped-story-title").performScrollTo().assertExists()
            rule.onNodeWithTag("grouped-story-chapter-words").performScrollTo().assertExists()
            rule.onNodeWithTag("grouped-story-save").performScrollTo().assertExists()
            capture("story-proposal-import-${if (languageZh) "zh" else "en"}-150-expanded-bottom.png")

            rule.onNodeWithTag("story-proposal-import-questions-toggle").performScrollTo().performClick()
            rule.onNodeWithTag("story-proposal-import-question-5").assertDoesNotExist()
            rule.onNodeWithTag("grouped-story-save").performScrollTo().assertExists()
        }
    }

    private fun capture(name: String, tag: String = "grouped-story-review") {
        val image = rule.onNodeWithTag(tag).captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        File(context.cacheDir, name).outputStream().use { out ->
            assertTrue(image.compress(Bitmap.CompressFormat.PNG, 100, out))
        }
        image.recycle()
    }

    @Composable
    private fun ReviewViewport(tag: String, content: @Composable () -> Unit) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).testTag(tag)) {
            content()
        }
    }
}
