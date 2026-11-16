package dev.photohouse.connected

import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
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
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

@RunWith(AndroidJUnit4::class)
class StoryProposalAdoptionUiTest {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()
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

    @Test fun importedProposalReviewStaysReachableOnPhoneViewport() =
        runImportedProposalJourney(360.dp, "phone")

    @Test fun importedProposalReviewStaysReachableOnTabletViewport() =
        runImportedProposalJourney(720.dp, "tablet")

    private fun runImportedProposalJourney(viewportWidth: Dp, screenshotPrefix: String) {
        val binding = MemoryCommunityBinding(
            Bearer.from(SessionToken(86400, "P".repeat(43), "Bearer")), "family", 1,
        )
        val updateCalls = AtomicInteger()
        val updateStoryId = AtomicReference<String?>()
        val updateBody = AtomicReference<String?>()
        val api = object : StoryWorkspaceApi {
            override suspend fun storyPreview(token: Bearer, library: String, json: String) = error("unused")
            override suspend fun storyTitleCapabilities(token: Bearer, library: String) = error("unused")
            override suspend fun storyTitles(token: Bearer, library: String, json: String) = error("unused")
            override suspend fun createGroupedStory(token: Bearer, library: String, json: String) = error("unused")
            override suspend fun updateGroupedStory(token: Bearer, library: String, storyId: String, json: String,
                sourceReview: Boolean, contributionReferences: Boolean): ByteArray {
                updateCalls.incrementAndGet()
                updateStoryId.set(storyId)
                updateBody.set(json)
                throw ApiFailure(FailureKind.HTTP, 503)
            }
        }
        val savedStory = SavedMemoryStory(
            id = storyId, libraryId = "family", revision = 7, createdAt = 1, updatedAt = 1,
            canEdit = true, selectionRevision = "a".repeat(64), title = "Garden day", theme = "everyday",
            language = "zh", items = listOf(
                MemoryStoryAsset(Asset("1", "image", 800, 600, null, null, "/assets/1/thumbnail"), emptyList()),
                MemoryStoryAsset(Asset("2", "image", 800, 600, null, null, "/assets/2/thumbnail"), emptyList()),
            ),
            chapters = listOf(
                SavedMemoryStoryChapter("chapter-1", "Opening", "Original family words", listOf("1"), emptyList()),
                SavedMemoryStoryChapter("chapter-2", "Later", "Original later words", listOf("2"), emptyList()),
            ),
            questions = emptyList(),
        )
        val references = SavedMemoryStoryContributionReferences(
            storyId, "family", 7, listOf(
                SavedMemoryChapterContributionReferences("chapter-1", emptyList()),
                SavedMemoryChapterContributionReferences("chapter-2", emptyList()),
            ),
        )
        val longQuestion = "请核对这段回忆 " + "请核对回忆细节".repeat(20)
        val questionsJson = (1..6).joinToString(",") { "\"$longQuestion $it\"" }
        val job = MemoryJob(
            id = "22222222-2222-4222-8222-222222222222", kind = "narrative", state = "ready",
            createdAt = 1, updatedAt = 1, expiresAt = 2, errorCode = null,
            result = Json.parseToJsonElement(
                """{"version":1,"needs_review":true,"title":"A proposal title","chapters":[{"id":"chapter-1","narration":"Original family words","source_ids":[]},{"id":"chapter-2","narration":"AI proposed wording","source_ids":[]}],"questions":[$questionsJson]}""",
            ).jsonObject,
            needsReview = true, baseRevision = 7,
        )
        val proposalDraft = storyProposalAdoptionDraft(savedStory, references, job, listOf("chapter-1", "chapter-2"), false)
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
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Box(Modifier.width(viewportWidth).height(420.dp)) {
                        PhotoHouseTheme {
                            GroupedStoryReview(store, zh, {}, {}, isSavedEdit = true)
                        }
                    }
                }
            }
        }

        rule.onNodeWithTag("grouped-story-chapter-position").assertIsDisplayed().assertTextEquals("篇章 2 / 2")
        rule.onNodeWithTag("story-proposal-import-applied").assertIsDisplayed()
        rule.onNodeWithTag("grouped-story-save").assertIsDisplayed()
        captureApprovedDraft("story-proposal-after-approval-$screenshotPrefix.png")

        for (languageZh in listOf(true, false)) {
            rule.runOnIdle { zh = languageZh }
            rule.onNodeWithTag("story-proposal-import-provenance").assertExists()
            rule.onNodeWithTag("story-proposal-import-applied").assertTextEquals(if (languageZh) "已带入草稿" else "Applied to draft")
            rule.onNodeWithTag("story-proposal-import-unreviewed").assertExists()
            rule.onNodeWithTag("story-proposal-import-question-0").assertDoesNotExist()

            rule.onNodeWithTag("story-proposal-import-questions-toggle").performScrollTo().performClick()
            rule.onNodeWithTag("story-proposal-import-question-5").performScrollTo().assertExists()
            rule.onNodeWithTag("grouped-story-title").performScrollTo().assertExists()
            rule.onNodeWithTag("grouped-story-chapter-words").performScrollTo().assertExists()
            rule.onNodeWithTag("grouped-story-chapter-position").assertTextEquals(
                if (languageZh) "篇章 2 / 2" else "Chapter 2 / 2",
            )
            rule.onNodeWithTag("grouped-story-chapter-words").assertTextContains("AI proposed wording")
            rule.onNodeWithTag("story-proposal-import-save-bar").assertIsDisplayed()
            rule.onNodeWithTag("grouped-story-save").assertIsDisplayed()
            rule.onAllNodesWithTag("grouped-story-save").assertCountEquals(1)
            assertEquals("Importing a proposal must not write to the library.", 0, updateCalls.get())

            rule.onNodeWithTag("story-proposal-import-questions-toggle").performScrollTo().performClick()
            rule.onNodeWithTag("story-proposal-import-question-5").assertDoesNotExist()
            val save = rule.onNodeWithTag("grouped-story-save")
            save.assertTextEquals(if (languageZh) "保存到相册库" else "Save to library")
            save.assertIsNotEnabled()
        }
        rule.onNodeWithTag("grouped-story-reviewed").assertIsDisplayed().performClick()
        rule.onNodeWithTag("grouped-story-save").assertIsDisplayed().assertIsEnabled().performClick()
        rule.waitUntil(timeoutMillis = 5_000) { updateCalls.get() == 1 }
        assertEquals(storyId, updateStoryId.get())
        val body = Json.parseToJsonElement(requireNotNull(updateBody.get())).jsonObject
        assertEquals("7", body["revision"]?.jsonPrimitive?.content)
        val updatedChapters = Json.parseToJsonElement(body["chapters"]!!.jsonPrimitive.content).jsonArray
        assertEquals("Original family words", updatedChapters[0].jsonObject["narration"]?.jsonPrimitive?.content)
        assertEquals("AI proposed wording", updatedChapters[1].jsonObject["narration"]?.jsonPrimitive?.content)
        rule.waitForIdle()
        assertEquals("Only the explicit library save should issue one update.", 1, updateCalls.get())
    }

    private fun captureApprovedDraft(name: String) = rule.runOnIdle {
        val view = rule.activity.window.decorView
        val image = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
        view.draw(Canvas(image))
        File(rule.activity.cacheDir, name).outputStream().use { out ->
            assertTrue(image.compress(Bitmap.CompressFormat.PNG, 100, out))
        }
        image.recycle()
    }

    private fun capture(name: String, tag: String) {
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
