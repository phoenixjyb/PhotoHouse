package dev.photohouse.tv

import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class TvProtectedStoryControllerTest {
    @Test fun activeMemberCanReviewThenExplicitlySaveScopedAutoRefinement() {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        val api = StoryApprovalApi()
        val workspace = StoryApprovalWorkspace(api)
        val controller = ProtectedTvStoryController(api, workspace, scope)
        try {
            enterStoryReview(controller)
            assertEquals(TvStoryApprovalStage.REVIEW, controller.state.value.stage)
            assertEquals(2L, controller.state.value.currentStory?.revision)
            assertEquals(listOf("chapter-1", "chapter-2", "chapter-3"),
                controller.state.value.currentChapters.map { it.id })
            assertTrue(controller.state.value.canApply)

            controller.dispatch(TvStoryApprovalAction.ApplyProposal)

            assertEquals(TvStoryApprovalStage.APPLIED, controller.state.value.stage)
            assertEquals("chapter-2", controller.state.value.focusedChapterId)
            assertEquals("Suggested chapter two", controller.state.value.currentChapters[1].suggestedText)
            assertTrue(controller.state.value.dirty)
            assertTrue("Apply only updates the in-memory draft", workspace.updates.isEmpty())

            controller.dispatch(TvStoryApprovalAction.Save)

            val plan = workspace.updates.single()
            assertSame(api.sessionCredential, plan.token)
            assertEquals(LIBRARY, plan.library)
            assertEquals(STORY_ID, plan.storyId)
            assertTrue(plan.sourceReview)
            assertTrue(plan.contributionReferences)
            assertTrue("The approved auto-refinement suppresses a second refinement", plan.suppressAutoRefinement)
            val json = Json.parseToJsonElement(plan.body).jsonObject
            assertEquals("2", json.getValue("revision").jsonPrimitive.content)
            assertEquals("101,102,103", json.getValue("asset_ids").jsonPrimitive.content)
            assertEquals("chapter_sources_v1", json.getValue("source_policy").jsonPrimitive.content)
            val chapters = Json.parseToJsonElement(json.getValue("chapters").jsonPrimitive.content).jsonArray
            assertEquals(listOf("chapter-1", "chapter-2", "chapter-3"),
                chapters.map { it.jsonObject.getValue("id").jsonPrimitive.content })
            assertEquals("Original chapter one", chapters[0].jsonObject.getValue("narration").jsonPrimitive.content)
            assertEquals("Suggested chapter two", chapters[1].jsonObject.getValue("narration").jsonPrimitive.content)
            assertEquals("Original chapter three", chapters[2].jsonObject.getValue("narration").jsonPrimitive.content)
            val contributionRefs = Json.parseToJsonElement(json.getValue("contribution_refs").jsonPrimitive.content).jsonArray
            assertEquals(listOf("chapter-1", "chapter-2", "chapter-3"),
                contributionRefs.map { it.jsonObject.getValue("chapter_id").jsonPrimitive.content })
            assertEquals(TvStoryApprovalStage.SAVED, controller.state.value.stage)

            val readsBeforeDeparture = api.storyReads
            controller.dispatch(TvStoryApprovalAction.Cancel)
            assertEquals(TvStoryApprovalStage.SIGN_IN, controller.state.value.stage)
            assertEquals(1, api.logoutTokens.size)
            assertSame(api.sessionCredential, api.logoutTokens.single())
            controller.dispatch(TvStoryApprovalAction.LoadStories(1))
            assertEquals("Departure clears the local credential", readsBeforeDeparture, api.storyReads)
        } finally {
            scope.cancel()
        }
    }

    @Test fun revisionChangeBetweenReviewAndApplyRefusesTheProposal() {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        val api = StoryApprovalApi().apply { advanceRevisionOnSecondRead = true }
        val controller = ProtectedTvStoryController(api, StoryApprovalWorkspace(api), scope)
        try {
            enterStoryReview(controller)
            controller.dispatch(TvStoryApprovalAction.ApplyProposal)
            assertEquals(TvStoryApprovalStage.REVIEW, controller.state.value.stage)
            assertEquals(TvStoryApprovalIssue.SUGGESTION_CHANGED, controller.state.value.issue)
            assertFalse(controller.state.value.canApply)
            assertTrue(api.workspaceUpdates.isEmpty())
        } finally {
            scope.cancel()
        }
    }

    private fun enterStoryReview(controller: ProtectedTvStoryController) {
        controller.dispatch(TvStoryApprovalAction.SignIn("+12025550123", "generated-test-password"))
        assertEquals(TvStoryApprovalStage.LIBRARIES, controller.state.value.stage)
        assertEquals(listOf(LIBRARY), controller.state.value.libraries.map { it.id })
        controller.dispatch(TvStoryApprovalAction.ChooseLibrary(LIBRARY))
        assertEquals(TvStoryApprovalStage.STORIES, controller.state.value.stage)
        controller.dispatch(TvStoryApprovalAction.OpenStory(STORY_ID))
    }

    private data class UpdatePlan(
        val token: Bearer,
        val library: String,
        val storyId: String,
        val body: String,
        val sourceReview: Boolean,
        val contributionReferences: Boolean,
        val suppressAutoRefinement: Boolean,
    )

    private class StoryApprovalApi : PhotoHouseApi {
        override val protectedNativeV2Enabled = true
        val sessionCredential get() = lastSessionCredential
        private var lastSessionCredential: Bearer? = null
        val logoutTokens = mutableListOf<Bearer>()
        var storyReads = 0
        var advanceRevisionOnSecondRead = false
        val workspaceUpdates = mutableListOf<UpdatePlan>()
        private val baseStory = generatedStory(revision = 2)

        override suspend fun login(phone: String, password: String): SessionToken {
            assertEquals("+12025550123", phone)
            assertEquals("generated-test-password", password)
            return SessionToken(86400, "A".repeat(43), "Bearer")
        }

        override suspend fun session(token: Bearer): Session {
            lastSessionCredential = token
            return Session("account-generated", "+12025550123", listOf(
                Membership(LIBRARY, "active", "owner", 1, null, 3, available = true),
            ))
        }

        override suspend fun logout(token: Bearer) { logoutTokens += token }
        override suspend fun register(phone: String, password: String, code: String): SessionToken = error("unused")
        override suspend fun acceptInvitation(token: Bearer, code: String) = error("unused")
        override suspend fun gallery(token: Bearer, library: String, page: Int): Gallery = error("unused")
        override suspend fun detail(token: Bearer, library: String, assetId: String): Detail = error("unused")
        override suspend fun captions(token: Bearer, library: String, assetId: String): Captions = error("unused")
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = error("unused")
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk = error("unused")
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray = error("unused")

        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int): SavedMemoryStoryPage {
            assertSame(lastSessionCredential, token)
            assertEquals(LIBRARY, library)
            return SavedMemoryStoryPage(LIBRARY, page, 8, hasMore = false, canCreate = false,
                items = listOf(SavedMemoryStorySummary(STORY_ID, "Family picnic", "everyday", "en", 2,
                    coverAssetId = "101", itemCount = 3, chapterCount = 3, updatedAt = 10, canEdit = true)))
        }

        override suspend fun savedMemoryStory(
            token: Bearer, library: String, storyId: String, revision: Long, sourceReview: Boolean,
        ): SavedMemoryStory {
            assertSame(lastSessionCredential, token)
            assertEquals(LIBRARY, library)
            assertEquals(STORY_ID, storyId)
            assertTrue(sourceReview)
            storyReads++
            return if (advanceRevisionOnSecondRead && storyReads > 1) {
                baseStory.copy(revision = 3, autoRefinement = baseStory.autoRefinement?.copy(baseRevision = 3))
            } else baseStory
        }

        override suspend fun savedMemoryStoryContributionReferences(
            token: Bearer, library: String, storyId: String, revision: Long, chapterIds: List<String>,
        ): SavedMemoryStoryContributionReferences {
            assertSame(lastSessionCredential, token)
            assertEquals(LIBRARY, library)
            assertEquals(STORY_ID, storyId)
            assertEquals(listOf("chapter-1", "chapter-2", "chapter-3"), chapterIds)
            return generatedReferences(revision)
        }
    }

    private class StoryApprovalWorkspace(private val api: StoryApprovalApi) : StoryWorkspaceApi {
        val updates get() = api.workspaceUpdates

        override suspend fun storyPreview(token: Bearer, library: String, json: String): ByteArray = error("unused")
        override suspend fun storyTitleCapabilities(token: Bearer, library: String): ByteArray = error("unused")
        override suspend fun storyTitles(token: Bearer, library: String, json: String): ByteArray = error("unused")
        override suspend fun createGroupedStory(token: Bearer, library: String, json: String): ByteArray = error("unused")

        override suspend fun updateGroupedStory(
            token: Bearer, library: String, storyId: String, json: String,
            sourceReview: Boolean, contributionReferences: Boolean, suppressAutoRefinement: Boolean,
        ): ByteArray {
            api.workspaceUpdates += UpdatePlan(token, library, storyId, json, sourceReview,
                contributionReferences, suppressAutoRefinement)
            return generatedSavedResponse(json, revision = 3).encodeToByteArray()
        }
    }

    companion object {
        private const val LIBRARY = "family-generated"
        private const val STORY_ID = "11111111-1111-4111-8111-111111111111"
        private const val CONTRIBUTION_ID = "22222222-2222-4222-8222-222222222222"
        private const val JOB_ID = "33333333-3333-4333-8333-333333333333"

        private fun generatedStory(revision: Long) = SavedMemoryStory(
            id = STORY_ID, libraryId = LIBRARY, revision = revision, createdAt = 1, updatedAt = 10,
            canEdit = true, selectionRevision = "a".repeat(64), title = "Family picnic",
            theme = "everyday", language = "en",
            items = listOf("101", "102", "103").map { id ->
                MemoryStoryAsset(
                    Asset(id, "image", 800, 600, null, "2025-05-01", "/assets/$id/thumbnail?library=$LIBRARY"),
                    listOf(MemoryStoryEvidence("caption-$id", "ai", "", "Generated caption $id")),
                )
            },
            chapters = listOf(
                SavedMemoryStoryChapter("chapter-1", "Before", "Original chapter one", listOf("101"), listOf("caption-101")),
                SavedMemoryStoryChapter("chapter-2", "Together", "Original chapter two", listOf("102"), listOf("caption-102")),
                SavedMemoryStoryChapter("chapter-3", "After", "Original chapter three", listOf("103"), listOf("caption-103")),
            ),
            questions = emptyList(), sourcePolicy = "chapter_sources_v1", autoRefinementAvailable = true,
            autoRefinement = MemoryJob(JOB_ID, "narrative", "ready", 10, 11, 100, null,
                buildJsonObject {
                    put("version", 1); put("title", "A title the review will not adopt")
                    put("chapters", buildJsonArray {
                        add(proposedChapter("chapter-1", "Original chapter one", "caption-101"))
                        add(proposedChapter("chapter-2", "Suggested chapter two", "caption-102"))
                        add(proposedChapter("chapter-3", "Original chapter three", "caption-103"))
                    })
                    put("questions", buildJsonArray { })
                    put("needs_review", true)
                }, needsReview = true, baseRevision = revision),
        )

        private fun proposedChapter(id: String, narration: String, source: String) = buildJsonObject {
            put("id", id); put("narration", narration); put("source_ids", buildJsonArray { add(source) })
        }

        private fun generatedReferences(revision: Long) = SavedMemoryStoryContributionReferences(
            STORY_ID, LIBRARY, revision, listOf(
                SavedMemoryChapterContributionReferences("chapter-1", listOf(CONTRIBUTION_ID)),
                SavedMemoryChapterContributionReferences("chapter-2", listOf(CONTRIBUTION_ID)),
                SavedMemoryChapterContributionReferences("chapter-3", listOf(CONTRIBUTION_ID)),
            ),
        )

        private fun generatedSavedResponse(requestBody: String, revision: Long): String {
            val request = Json.parseToJsonElement(requestBody).jsonObject
            val chapters = Json.parseToJsonElement(request.getValue("chapters").jsonPrimitive.content).jsonArray
            return buildJsonObject {
                put("version", 1); put("library_id", LIBRARY); put("id", STORY_ID); put("revision", revision.toString())
                put("created_at", 1); put("updated_at", 11); put("can_edit", true); put("saved", true)
                put("state", "draft"); put("generator", "family_edited_outline"); put("needs_review", true)
                put("selection_revision", "a".repeat(64)); put("title", "Family picnic")
                put("theme", "everyday"); put("language", "en")
                put("source_policy", "chapter_sources_v1")
                put("items", buildJsonArray {
                    listOf("101", "102", "103").forEach { id ->
                        add(buildJsonObject {
                            put("id", id); put("kind", "image"); put("width", 800); put("height", 600)
                            put("duration_sec", JsonNull); put("taken_at", "2025-05-01")
                            put("thumbnail_url", "/assets/$id/thumbnail?library=$LIBRARY"); put("date_hint", JsonNull)
                            put("evidence", buildJsonArray {
                                add(buildJsonObject { put("id", "caption-$id"); put("source", "ai"); put("title", ""); put("text", "Generated caption $id") })
                            })
                        })
                    }
                })
                put("chapters", chapters); put("questions", buildJsonArray { })
            }.toString()
        }
    }
}
