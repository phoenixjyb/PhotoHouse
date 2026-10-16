package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.*
import org.junit.Test

class AssistantWorkspaceWireTest {
    private val thread = "22222222-2222-4222-8222-222222222222"
    private val request = "11111111-1111-4111-8111-111111111111"
    private val exchangeA = "33333333-3333-4333-8333-333333333333"
    private val exchangeB = "44444444-4444-4444-8444-444444444444"

    private fun turn(result: String, recovered: Boolean = true, status: String = "completed", error: String = "null") =
        """{"version":1,"thread_id":"$thread","request_id":"$request","status":"$status","revision":1,"recovered":$recovered,"error":$error,"result":$result}"""

    private fun result(kind: String = "results", effect: String = "null") =
        """{"version":1,"kind":"$kind","reply":"Found one.","context":{"library_id":"family-a","binding":"${"a".repeat(64)}","fingerprint":"${"b".repeat(64)}","filters":{},"visible_ids":["123"],"total":1},"filters":{},"items":[{"id":"123","kind":"image","width":640,"height":480,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/123/thumbnail?library=family-a"}],"total":1,"has_more":false,"effect":$effect}"""

    private fun savedMemoryResult(kind: String = "story", contextId: String = "11111111-1111-4111-8111-111111111111") =
        """{"version":1,"kind":"memory_cards","reply":"Found a saved memory.","context":{"kind":"saved_memory","library_id":"family-a","source_revision":"${"a".repeat(64)}","references":[{"kind":"$kind","id":"11111111-1111-4111-8111-111111111111","revision":"2","source_revision":"${"b".repeat(64)}"}]},"filters":null,"items":[],"total":1,"has_more":false,"effect":null,"memory_cards":[{"kind":"$kind","id":"$contextId","revision":"2","source_revision":"${"b".repeat(64)}","title":"Garden day","excerpt":"The family walked by the lake."}]}"""

    private fun sceneResult(query: String = "a child beside a blue bridge", score: String = "0.75") =
        """{"version":4,"kind":"results","reply":"Found one scene.","context":{"library_id":"family-a","binding":"${"a".repeat(64)}","fingerprint":"${"b".repeat(64)}","filters":{"media":["image"]},"visible_ids":["123"],"total":1,"search_version":4,"scene":{"version":1,"query":"$query","scope":{"library_id":"family-a","binding":"${"a".repeat(64)}","fingerprint":"${"b".repeat(64)}","filters":{},"visible_ids":["123"],"total":1,"search_version":2},"scores":[$score]}},"filters":{"media":["image"]},"items":[{"id":"123","kind":"image","width":640,"height":480,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/123/thumbnail?library=family-a","semantic_score":$score}],"total":1,"has_more":false,"effect":null,"interpretation":{"date_basis":"capture","people":[],"tags":[],"locations":[],"perspective":null},"semantic":{"mode":"text_to_image","score_kind":"cosine","candidate_count":1,"coverage":"complete_eligible_images","needs_review":true}}"""

    @Test fun sceneCapabilityAndSingleLineQueryAreStrict() {
        val parsed = AssistantWorkspaceWire.sceneSearchCapabilities(
            """{"version":1,"available":true,"search_version":4,"media":["image"]}""".toByteArray())
        assertTrue(parsed.available)
        assertEquals(4, parsed.searchVersion)
        assertEquals(listOf("image"), parsed.media)
        invalid { AssistantWorkspaceWire.sceneSearchCapabilities("""{"version":1,"available":true,"search_version":3,"media":["image"]}""".toByteArray()) }
        invalid { AssistantWorkspaceWire.sceneSearchCapabilities("""{"version":1,"available":true,"search_version":4,"media":["image","video"]}""".toByteArray()) }
        assertTrue(AssistantWorkspaceWire.validSceneQuery("中 English 😀"))
        assertFalse(AssistantWorkspaceWire.validSceneQuery("line\nbreak"))
        assertFalse(AssistantWorkspaceWire.validSceneQuery("\uD800"))
        assertFalse(AssistantWorkspaceWire.validSceneQuery("x".repeat(513)))
        assertTrue(AssistantWorkspaceWire.validSceneQuery("中".repeat(170)))
    }

    @Test fun sceneTurnHasASeparateExactBodyAndResultContract() {
        val body = kotlinx.serialization.json.Json.parseToJsonElement(
            AssistantWorkspaceWire.sceneTurnRequest("family-a", exchangeA, 7, "a child beside a blue bridge")).jsonObject
        assertEquals(setOf("library_id", "request_id", "expected_revision", "text", "accepts"), body.keys)
        assertEquals(listOf("scene_search_v1"), body.getValue("accepts").jsonArray.map { it.jsonPrimitive.content })
        invalidInput { AssistantWorkspaceWire.sceneTurnRequest("family-a", exchangeA, 7, "two\nlines") }

        val fresh = AssistantWorkspaceWire.turn(turn(sceneResult(), recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, fromGet = false, searchVersion = 4).result!!
        assertEquals(4, fresh.searchVersion)
        assertEquals("a child beside a blue bridge", fresh.sceneRanking!!.query)
        assertEquals(mapOf("123" to 0.75), fresh.sceneRanking!!.scores)
        assertEquals(1, fresh.sceneRanking!!.candidateCount)
        assertEquals(listOf("123"), fresh.items.map { it.id })

        invalid { AssistantWorkspaceWire.turn(turn(sceneResult(score = "0.5").replace("\"semantic_score\":0.5", "\"semantic_score\":0.4"),
            recovered = false, error = "null").toByteArray(), "family-a", thread, request, false, searchVersion = 4) }
        invalid { AssistantWorkspaceWire.turn(turn(sceneResult().replace("\"coverage\":\"complete_eligible_images\"", "\"coverage\":\"partial\""),
            recovered = false, error = "null").toByteArray(), "family-a", thread, request, false, searchVersion = 4) }
        invalid { AssistantWorkspaceWire.turn(turn(sceneResult().replace("\"media\":[\"image\"]", "\"media\":[\"video\"]"),
            recovered = false, error = "null").toByteArray(), "family-a", thread, request, false, searchVersion = 4) }
        invalid { AssistantWorkspaceWire.turn(turn(sceneResult().replace("\"effect\":null", "\"effect\":{\"type\":\"open_asset\",\"asset_id\":\"123\"}"),
            recovered = false, error = "null").toByteArray(), "family-a", thread, request, false, searchVersion = 4) }
    }

    @Test fun sceneResultCannotHideVideoCardsUnderPhotoFilters() {
        invalid { AssistantWorkspaceWire.turn(turn(sceneResult().replace("\"kind\":\"image\"", "\"kind\":\"video\""),
            recovered = false, error = "null").toByteArray(), "family-a", thread, request, false, searchVersion = 4) }
    }

    @Test fun v4ReaderCanRecoverLegacySearchButFreshV4CannotDowngrade() {
        val legacy = result().replace("\"kind\":\"results\"", "\"kind\":\"results\"")
        val oldRead = AssistantWorkspaceWire.turn(turn(legacy).toByteArray(), "family-a", thread, request,
            fromGet = true, searchVersion = 4).result!!
        assertEquals(1, oldRead.searchVersion)
        invalid { AssistantWorkspaceWire.turn(turn(legacy, recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, fromGet = false, searchVersion = 4) }
        invalid { AssistantWorkspaceWire.turn(turn(sceneResult()).toByteArray(), "family-a", thread, request,
            fromGet = true, searchVersion = 3) }
    }

    @Test fun savedMemoryCardsRequireFreshNegotiatedTurnAndExactReferenceBindings() {
        val fresh = AssistantWorkspaceWire.turn(turn(savedMemoryResult(), recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, fromGet = false, acceptSavedMemoryCards = true)
        val freshResult = fresh.result!!
        val card = freshResult.memoryCards.single()
        assertEquals("story", card.kind)
        assertEquals("Garden day", card.title)
        assertEquals(64, card.sourceRevision.length)
        assertEquals("family-a", freshResult.savedMemoryContext!!.libraryId)
        invalid { AssistantWorkspaceWire.turn(turn(savedMemoryResult(), recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, fromGet = false) }
        invalid { AssistantWorkspaceWire.turn(turn(savedMemoryResult(), recovered = true).toByteArray(),
            "family-a", thread, request, fromGet = true, acceptSavedMemoryCards = true) }
        invalid { AssistantWorkspaceWire.turn(turn(savedMemoryResult(contextId = "22222222-2222-4222-8222-222222222222"),
            recovered = false, error = "null").toByteArray(), "family-a", thread, request, false, true) }
        invalid { AssistantWorkspaceWire.turn(turn(savedMemoryResult().replace("\"revision\":\"2\"", "\"revision\":2"),
            recovered = false, error = "null").toByteArray(), "family-a", thread, request, false, true) }
    }

    @Test fun savedMemoryActionsAreStrictFreshAndBoundToAnExistingCard() {
        val base = savedMemoryResult()
        fun action(value: String) = base.dropLast(1) + ",\"memory_action\":$value}"
        val accepted = AssistantWorkspaceWire.turn(turn(action("{\"type\":\"read_opening\",\"ordinal\":0}"),
            recovered = false, error = "null").toByteArray(), "family-a", thread, request,
            fromGet = false, acceptSavedMemoryCards = true, acceptSavedMemoryActions = true)
        assertEquals(AssistantSavedMemoryAction("read_opening", 0), accepted.result!!.memoryAction)
        invalid { AssistantWorkspaceWire.turn(turn(action("{\"type\":\"open\",\"ordinal\":0}"), recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, fromGet = false, acceptSavedMemoryCards = true) }
        invalid { AssistantWorkspaceWire.turn(turn(action("{\"type\":\"delete\",\"ordinal\":0}"), recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, false, true, true) }
        invalid { AssistantWorkspaceWire.turn(turn(action("{\"type\":\"open\",\"ordinal\":1}"), recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, false, true, true) }
        invalid { AssistantWorkspaceWire.turn(turn(action("{\"type\":\"open\",\"ordinal\":0,\"extra\":true}"), recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, false, true, true) }
        invalid { AssistantWorkspaceWire.turn(turn(action("{\"type\":\"open\",\"ordinal\":0}"), recovered = true).toByteArray(),
            "family-a", thread, request, fromGet = true, acceptSavedMemoryCards = true, acceptSavedMemoryActions = true) }
        val clarification = """{"version":1,"kind":"clarification","reply":"Which memory?","context":null,"filters":null,"items":[],"total":0,"has_more":false,"effect":null,"memory_cards":[],"memory_action":{"type":"open","ordinal":0}}"""
        invalid { AssistantWorkspaceWire.turn(turn(clarification, recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, false, true, true) }
    }

    @Test fun actionNegotiationSendsTheExactOptInPairOnlyWhenQualified() {
        val requestBody = AssistantWorkspaceWire.turnRequest("family-a", exchangeA, 0, "find a memory",
            acceptSavedMemoryCards = true, acceptSavedMemoryActions = true)
        val accepted = kotlinx.serialization.json.Json.parseToJsonElement(requestBody).jsonObject
        assertEquals(listOf("saved_memory_cards_v1", "saved_memory_actions_v1"),
            accepted.getValue("accepts").jsonArray.map { it.jsonPrimitive.content })
        val legacy = kotlinx.serialization.json.Json.parseToJsonElement(
            AssistantWorkspaceWire.turnRequest("family-a", exchangeA, 0, "find a memory", acceptSavedMemoryCards = true)).jsonObject
        assertEquals(listOf("saved_memory_cards_v1"), legacy.getValue("accepts").jsonArray.map { it.jsonPrimitive.content })
        invalidInput { AssistantWorkspaceWire.turnRequest("family-a", exchangeA, 0, "find a memory",
            acceptSavedMemoryCards = false, acceptSavedMemoryActions = true) }
    }

    @Test fun memoryFollowupParentIsAnExactOptionalPositiveRevisionObject() {
        val parent = AssistantSavedMemoryParent(request, 7)
        val legacy = AssistantWorkspaceWire.turnRequest("family-a", exchangeA, 7, "find saved memories")
        val followup = AssistantWorkspaceWire.turnRequest("family-a", exchangeA, 8,
            "what is the first saved memory about", true, parent)
        val oldObject = kotlinx.serialization.json.Json.parseToJsonElement(legacy).jsonObject
        val newObject = kotlinx.serialization.json.Json.parseToJsonElement(followup).jsonObject
        assertFalse(oldObject.containsKey("memory_parent"))
        assertEquals(setOf("request_id", "revision"), newObject.getValue("memory_parent").jsonObject.keys)
        assertEquals(request, newObject.getValue("memory_parent").jsonObject.getValue("request_id").jsonPrimitive.content)
        assertEquals("7", newObject.getValue("memory_parent").jsonObject.getValue("revision").jsonPrimitive.content)
        invalidInput { AssistantWorkspaceWire.turnRequest("family-a", exchangeA, 8, "valid", true, parent.copy(revision = 0)) }
        invalidInput { AssistantWorkspaceWire.turnRequest("family-a", exchangeA, 8, "valid", true, parent.copy(revision = Long.MAX_VALUE)) }
        invalidInput { AssistantWorkspaceWire.turnRequest("family-a", exchangeA, 8, "valid", true, parent.copy(requestId = "bad")) }
    }

    @Test fun savedMemoryCardTextAndRevisionMatchServerBounds() {
        val largest = savedMemoryResult().replace("\"revision\":\"2\"", "\"revision\":\"9223372036854775806\"")
        val accepted = AssistantWorkspaceWire.turn(turn(largest, recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, fromGet = false, acceptSavedMemoryCards = true)
        assertEquals("9223372036854775806", accepted.result!!.memoryCards.single().revision)
        val tabbedExcerpt = savedMemoryResult().replace("The family walked by the lake.", "The family\\twalked by the lake.")
        assertEquals(1, AssistantWorkspaceWire.turn(turn(tabbedExcerpt, recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, fromGet = false, acceptSavedMemoryCards = true).result!!.memoryCards.size)
        invalid { AssistantWorkspaceWire.turn(turn(savedMemoryResult().replace("\"revision\":\"2\"", "\"revision\":\"9223372036854775807\""),
            recovered = false, error = "null").toByteArray(), "family-a", thread, request, false, true) }
        invalid { AssistantWorkspaceWire.turn(turn(savedMemoryResult().replace("Garden day", ""), recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, false, true) }
        invalid { AssistantWorkspaceWire.turn(turn(savedMemoryResult().replace("The family walked by the lake.", "bad\\u202e text"),
            recovered = false, error = "null").toByteArray(), "family-a", thread, request, false, true) }
    }

    @Test fun savedMemoryReaderEnvelopeReusesTheStrictMemoirDetailParser() {
        val id = "11111111-1111-4111-8111-111111111111"
        val child = "22222222-2222-4222-8222-222222222222"
        val reader = """{"version":1,"type":"memoir","id":"$id","revision":"2","can_edit":false,"title":"Family year","introduction":"A year together.","language":"en","stories":[{"id":"$child","title":"Summer","revision":"3","item_count":1,"cover_asset_id":"1"}]}"""
        val envelope = """{"version":1,"kind":"memoir","reader":$reader}"""
        val decoded = AssistantWorkspaceWire.savedMemoryReader(envelope.toByteArray(), "family-a") as SavedMemoryReaderPayload.Memoir
        assertEquals(id, decoded.value.id)
        assertEquals(2L, decoded.value.revision)
        assertEquals(child, decoded.value.stories.single().id)
        invalid { AssistantWorkspaceWire.savedMemoryReader(envelope.replace("memoir", "story").toByteArray(), "family-a") }
        invalid { AssistantWorkspaceWire.savedMemoryReader(envelope.replace("\"revision\":\"2\"", "\"revision\":2").toByteArray(), "family-a") }
    }

    @Test fun enforcesScopeCorrelationAndRecoveredEffectSuppression() {
        val valid = AssistantWorkspaceWire.turn(turn(result()).toByteArray(), "family-a", thread, request, fromGet = true)
        assertEquals(AssistantWorkspaceRequestStatus.COMPLETED, valid.status)
        assertTrue(valid.recovered)
        assertEquals(listOf("123"), valid.result!!.items.map { it.id })

        invalid { AssistantWorkspaceWire.turn(turn(result().replace("family-a", "family-b")).toByteArray(), "family-a", thread, request, true) }
        invalid { AssistantWorkspaceWire.turn(turn(result().replace("\"visible_ids\":[\"123\"]", "\"visible_ids\":[\"124\"]")).toByteArray(), "family-a", thread, request, true) }
        invalid { AssistantWorkspaceWire.turn(turn(result("open", "{\"type\":\"open_asset\",\"asset_id\":\"123\"}")).toByteArray(), "family-a", thread, request, true) }
        invalid { AssistantWorkspaceWire.turn(turn(result(), recovered = false).toByteArray(), "family-a", thread, request, true) }
        invalid { AssistantWorkspaceWire.turn(turn(result()).replace(request, "33333333-3333-4333-8333-333333333333").toByteArray(), "family-a", thread, request, true) }
        val opaqueFilters = result().replace("\"filters\":{}", "\"filters\":{\"unexpected\":true}")
        invalid { AssistantWorkspaceWire.turn(turn(opaqueFilters).toByteArray(), "family-a", thread, request, true) }
        val noContext = result().replace(Regex("\"context\":\\{.*?\\},\"filters\""), "\"context\":null,\"filters\"")
        invalid { AssistantWorkspaceWire.turn(turn(noContext).toByteArray(), "family-a", thread, request, true) }
    }

    @Test fun rejectsUnknownDuplicateAndBooleanRevisionFields() {
        val capabilities = """{"version":1,"available":true,"threads":true,"preferences":true,"preferences_applied":false,"server_owned_turns":false}"""
        assertTrue(AssistantWorkspaceWire.capabilities(capabilities.toByteArray()).available)
        invalid { AssistantWorkspaceWire.capabilities(capabilities.replace("}", ",\"extra\":1}").toByteArray()) }
        invalid { AssistantWorkspaceWire.capabilities(capabilities.replace("\"version\":1", "\"version\":1,\"version\":1").toByteArray()) }
        invalid { AssistantWorkspaceWire.capabilities(capabilities.replace("\"available\":true", "\"available\":\"true\"").toByteArray()) }
        val prefs = """{"version":1,"locale":null,"reply_length":null,"voice_pace":null,"revision":false}"""
        invalid { AssistantWorkspaceWire.preferences(prefs.toByteArray()) }
    }

    @Test fun capabilitiesRemainCompatibleAndExposeOptionalHistoryFeatures() {
        val legacy = """{"version":1,"available":true,"threads":true,"preferences":false,"preferences_applied":false,"server_owned_turns":false}"""
        val old = AssistantWorkspaceWire.capabilities(legacy.toByteArray())
        assertFalse(old.historyPaging)
        assertFalse(old.threadLabels)
        val extended = legacy.dropLast(1) + ",\"history_paging\":true,\"thread_labels\":false}"
        val latest = AssistantWorkspaceWire.capabilities(extended.toByteArray())
        assertTrue(latest.historyPaging)
        assertFalse(latest.threadLabels)
        invalid { AssistantWorkspaceWire.capabilities(extended.replace("\"thread_labels\":false", "\"thread_labels\":\"false\"").toByteArray()) }
    }

    @Test fun searchV2CapabilityAndResultAreBoundedStrictAndHumanReadable() {
        val legacy = """{"version":1,"available":true,"threads":true,"preferences":false,"preferences_applied":false,"server_owned_turns":true}"""
        val v2 = legacy.dropLast(1) + ",\"search\":{\"version\":2,\"date_basis\":\"capture\",\"perspective\":{\"label\":\"妈妈\"}}}"
        val capabilities = AssistantWorkspaceWire.capabilities(v2.toByteArray())
        assertEquals(2, capabilities.searchVersion)
        assertEquals("capture", capabilities.searchDateBasis)
        assertEquals("妈妈", capabilities.searchPerspectiveLabel)
        invalid { AssistantWorkspaceWire.capabilities(v2.replace("\"version\":2", "\"version\":1").toByteArray()) }
        invalid { AssistantWorkspaceWire.capabilities(v2.replace("capture", "taken_at").toByteArray()) }
        invalid { AssistantWorkspaceWire.capabilities(v2.replace("妈妈", "😀".repeat(129)).toByteArray()) }
        invalid { AssistantWorkspaceWire.capabilities(v2.replace("妈妈", "").toByteArray()) }

        val interpretation = """{"date_basis":"capture","people":[],"tags":[],"locations":[],"perspective":{"label":"妈妈"}}"""
        val context = """{"library_id":"family-a","binding":"${"a".repeat(64)}","fingerprint":"${"b".repeat(64)}","filters":{"text":"海边"},"visible_ids":["123"],"total":1,"search_version":2}"""
        val item = """{"id":"123","kind":"image","width":640,"height":480,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/123/thumbnail?library=family-a","match_reasons":[{"source":"generated_caption","source_id":"81","revision":"${"c".repeat(64)}"},{"source":"capture_date","value":"2025-06-01"}]}"""
        val result = """{"version":2,"kind":"results","reply":"Found one.","context":$context,"filters":{"text":"海边"},"items":[$item],"total":1,"has_more":false,"effect":null,"interpretation":$interpretation}"""
        val parsed = AssistantWorkspaceWire.turn(turn(result).toByteArray(), "family-a", thread, request,
            fromGet = true, searchVersion = 2).result!!
        assertEquals(2, parsed.searchVersion)
        assertEquals("妈妈", parsed.searchInterpretation!!.perspective!!.label)
        assertEquals(listOf(AssistantMatchReason.Caption(true, "81"), AssistantMatchReason.CaptureDate("2025-06-01")),
            parsed.matchReasons.getValue("123"))
        invalid { AssistantWorkspaceWire.turn(turn(result.replace("\"search_version\":2", "\"search_version\":1")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 2) }
        invalid { AssistantWorkspaceWire.turn(turn(result.replace("\"text\":\"海边\"", "\"text\":\" ")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 2) }
        invalid { AssistantWorkspaceWire.turn(turn(result.replace("\"source_id\":\"81\"", "\"source_id\":\"81\",\"id\":\"99\"")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 2) }
        invalid { AssistantWorkspaceWire.turn(turn(result.replace("\"people\":[]", "\"people\":[{\"id\":\"5\",\"label\":\"A\"}]")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 2) }
        invalid { AssistantWorkspaceWire.turn(turn(result.replace("\"perspective\":{\"label\":\"妈妈\"}", "\"perspective\":{\"label\":\"\"}")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 2) }
        val selectedLabel = result.replace("\"people\":[]", "\"people\":[{\"id\":\"5\",\"label\":\"\"}]")
            .replace("\"filters\":{\"text\":\"海边\"}", "\"filters\":{\"text\":\"海边\",\"people\":{\"ids\":[\"5\"],\"match\":\"any\"}}")
        invalid { AssistantWorkspaceWire.turn(turn(selectedLabel).toByteArray(), "family-a", thread, request,
            true, searchVersion = 2) }
        assertEquals(2, AssistantWorkspaceWire.turn(turn(result, recovered = false).toByteArray(), "family-a", thread,
            request, fromGet = false, acceptSavedMemoryCards = true, searchVersion = 2).result!!.searchVersion)
        invalid { AssistantWorkspaceWire.turn(turn(result(kind = "results"), recovered = false).toByteArray(), "family-a", thread,
            request, fromGet = false, searchVersion = 2) }

        for (kind in listOf("clarification", "unsupported")) {
            val noContext = """{"version":2,"kind":"$kind","reply":"Try again.","context":null,"filters":null,"items":[],"total":0,"has_more":false,"effect":null,"interpretation":{"date_basis":"capture","people":[],"tags":[],"locations":[],"perspective":null}}"""
            val parsedEmpty = AssistantWorkspaceWire.turn(turn(noContext).toByteArray(), "family-a", thread, request,
                fromGet = true, searchVersion = 2).result!!
            assertEquals(kind, parsedEmpty.kind)
            assertTrue(parsedEmpty.items.isEmpty())
            invalid { AssistantWorkspaceWire.turn(turn(noContext.replace("\"filters\":null", "\"filters\":{}")).toByteArray(),
                "family-a", thread, request, true, searchVersion = 2) }
        }
    }

    @Test fun searchV3CapabilityContextAndDescriptionFilterAreStrictAndRecoverable() {
        val legacy = """{"version":1,"available":true,"threads":true,"preferences":false,"preferences_applied":false,"server_owned_turns":true}"""
        val capabilities = AssistantWorkspaceWire.capabilities(
            (legacy.dropLast(1) + ",\"search\":{\"version\":3,\"date_basis\":\"capture\",\"perspective\":null}}").toByteArray())
        assertEquals(3, capabilities.searchVersion)

        val descriptive = """{"version":1,"concepts":[{"surface":"garden picnic","alternatives":["family picnic","outdoor meal"]},{"surface":"red kite","alternatives":["kite flying"]}]}"""
        val filters = """{"descriptive":$descriptive}"""
        val context = """{"library_id":"family-a","binding":"${"a".repeat(64)}","fingerprint":"${"b".repeat(64)}","filters":$filters,"visible_ids":["123"],"total":1,"search_version":3}"""
        val interpretation = """{"date_basis":"capture","people":[],"tags":[],"locations":[],"perspective":null}"""
        val item = """{"id":"123","kind":"image","width":640,"height":480,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/123/thumbnail?library=family-a"}"""
        val result = """{"version":3,"kind":"results","reply":"Found one.","context":$context,"filters":$filters,"items":[$item],"total":1,"has_more":false,"effect":null,"interpretation":$interpretation}"""
        val parsed = AssistantWorkspaceWire.turn(turn(result).toByteArray(), "family-a", thread, request,
            fromGet = true, searchVersion = 3).result!!
        assertEquals(3, parsed.searchVersion)
        assertEquals(descriptive, parsed.filters!!.getValue("descriptive").toString())
        assertEquals(3, AssistantWorkspaceWire.turn(turn(result, recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, fromGet = false, searchVersion = 3).result!!.searchVersion)

        fun withFilter(filter: String): String = result.replace(filters, "{\"descriptive\":$filter}")
        invalid { AssistantWorkspaceWire.turn(turn(withFilter("{\"version\":2,\"concepts\":[]}")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 3) }
        invalid { AssistantWorkspaceWire.turn(turn(withFilter("{\"version\":1,\"concepts\":[{\"surface\":\"Garden\",\"alternatives\":[\"one\",\"ＯＮＥ\"]}]}")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 3) }
        invalid { AssistantWorkspaceWire.turn(turn(withFilter("{\"version\":1,\"concepts\":[{\"surface\":\"garden\",\"alternatives\":[\"one\"]},{\"surface\":\"ＧＡＲＤＥＮ\",\"alternatives\":[\"two\"]}]}")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 3) }
        invalid { AssistantWorkspaceWire.turn(turn(withFilter("{\"version\":1,\"concepts\":[{\"surface\":\" spaced \",\"alternatives\":[\"one\"]}]}")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 3) }
        invalid { AssistantWorkspaceWire.turn(turn(withFilter("{\"version\":1,\"concepts\":[{\"surface\":\"bad\\u0000text\",\"alternatives\":[\"one\"]}]}")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 3) }
        invalid { AssistantWorkspaceWire.turn(turn(withFilter("{\"version\":1,\"concepts\":[{\"surface\":\"${"x".repeat(129)}\",\"alternatives\":[\"one\"]}]}")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 3) }
        invalid { AssistantWorkspaceWire.turn(turn(withFilter("{\"version\":1,\"concepts\":[{\"surface\":\"${"😀".repeat(33)}\",\"alternatives\":[\"one\"]}]}")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 3) }
        invalid { AssistantWorkspaceWire.turn(turn(withFilter("{\"version\":1,\"concepts\":[{\"surface\":\"one\",\"alternatives\":[\"a\",\"b\",\"c\",\"d\",\"e\"]}]}")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 3) }
        val oversizedDescription = """{"version":1,"concepts":[""" + (1..6).joinToString(",") { index ->
            """{"surface":"${"s".repeat(127)}$index","alternatives":["${"a".repeat(128)}","${"b".repeat(128)}","${"c".repeat(128)}","${"d".repeat(128)}"]}"""
        } + "]}"
        invalid { AssistantWorkspaceWire.turn(turn(withFilter(oversizedDescription)).toByteArray(),
            "family-a", thread, request, true, searchVersion = 3) }
        invalid { AssistantWorkspaceWire.turn(turn(result.replace("\"search_version\":3", "\"search_version\":2")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 3) }
        invalid { AssistantWorkspaceWire.turn(turn(result.replace("\"version\":3", "\"version\":2")).toByteArray(),
            "family-a", thread, request, true, searchVersion = 3) }
        val storedV2Filters = "{}"
        val storedV2Context = """{"library_id":"family-a","binding":"${"a".repeat(64)}","fingerprint":"${"b".repeat(64)}","filters":$storedV2Filters,"visible_ids":["123"],"total":1,"search_version":2}"""
        val storedV2 = """{"version":2,"kind":"results","reply":"Found one.","context":$storedV2Context,"filters":$storedV2Filters,"items":[$item],"total":1,"has_more":false,"effect":null,"interpretation":$interpretation}"""
        val recoveredV2 = AssistantWorkspaceWire.turn(turn(storedV2).toByteArray(), "family-a", thread, request,
            fromGet = true, searchVersion = 3).result!!
        assertEquals(2, recoveredV2.searchVersion)
        invalid { AssistantWorkspaceWire.turn(turn(storedV2, recovered = false, error = "null").toByteArray(),
            "family-a", thread, request, fromGet = false, searchVersion = 3) }
        val v2Context = context.replace("\"search_version\":3", "\"search_version\":2")
        val v2Result = result.replace("\"version\":3", "\"version\":2").replace(context, v2Context)
        invalid { AssistantWorkspaceWire.turn(turn(v2Result).toByteArray(), "family-a", thread, request,
            true, searchVersion = 2) }
    }

    @Test fun preV4ClientRejectsSceneSearchNegotiationAndUnmodeledSemanticPayloads() {
        val capabilities = """{"version":1,"available":true,"threads":true,"preferences":false,"preferences_applied":false,"server_owned_turns":true,"search":{"version":4,"date_basis":"capture","perspective":null}}"""
        invalid { AssistantWorkspaceWire.capabilities(capabilities.toByteArray()) }
        val unsolicitedCapability = capabilities.replace("\"search\":{\"version\":4,\"date_basis\":\"capture\",\"perspective\":null}",
            "\"scene_search\":{\"version\":1,\"available\":true}")
        invalid { AssistantWorkspaceWire.capabilities(unsolicitedCapability.toByteArray()) }

        val interpretation = """{"date_basis":"capture","people":[],"tags":[],"locations":[],"perspective":null}"""
        val context = """{"library_id":"family-a","binding":"${"a".repeat(64)}","fingerprint":"${"b".repeat(64)}","filters":{},"visible_ids":["123"],"total":1,"search_version":3}"""
        val item = """{"id":"123","kind":"image","width":640,"height":480,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/123/thumbnail?library=family-a"}"""
        val v3 = """{"version":3,"kind":"results","reply":"Found one.","context":$context,"filters":{},"items":[$item],"total":1,"has_more":false,"effect":null,"interpretation":$interpretation}"""
        val parsed = AssistantWorkspaceWire.turn(turn(v3).toByteArray(), "family-a", thread, request,
            fromGet = true, searchVersion = 3).result!!
        assertEquals("existing v3 results remain readable", 3, parsed.searchVersion)
        val v4 = v3.replace("\"version\":3", "\"version\":4").replace("\"search_version\":3", "\"search_version\":4")
        invalid { AssistantWorkspaceWire.turn(turn(v4).toByteArray(), "family-a", thread, request,
            fromGet = true, searchVersion = 3) }
        val semanticContext = v3.replace("\"search_version\":3}", "\"search_version\":3,\"scene_search\":{\"version\":1,\"mode\":\"semantic_scene\"}}")
        invalid { AssistantWorkspaceWire.turn(turn(semanticContext).toByteArray(), "family-a", thread, request,
            fromGet = true, searchVersion = 3) }
        val semanticScore = v3.replace("\"thumbnail_url\":\"/assets/123/thumbnail?library=family-a\"",
            "\"thumbnail_url\":\"/assets/123/thumbnail?library=family-a\",\"semantic_score\":0.91")
        invalid { AssistantWorkspaceWire.turn(turn(semanticScore).toByteArray(), "family-a", thread, request,
            fromGet = true, searchVersion = 3) }
    }

    @Test fun privateReplySpeechCapabilityAndRequestStayOptionalAndNarrow() {
        val legacy = """{"version":1,"available":true,"threads":true,"preferences":false,"preferences_applied":false,"server_owned_turns":false}"""
        assertFalse(AssistantWorkspaceWire.capabilities(legacy.toByteArray()).replySpeech)
        val enabled = legacy.dropLast(1) + ",\"reply_speech\":true}"
        assertTrue(AssistantWorkspaceWire.capabilities(enabled.toByteArray()).replySpeech)
        invalid { AssistantWorkspaceWire.capabilities(enabled.replace("\"reply_speech\":true", "\"reply_speech\":\"true\"").toByteArray()) }

        val speechId = "55555555-5555-4555-8555-555555555555"
        val body = AssistantWorkspaceWire.replySpeechRequest("family-a", 9, request, speechId)
        val parsed = kotlinx.serialization.json.Json.parseToJsonElement(body).jsonObject
        assertEquals(setOf("library_id", "expected_revision"), parsed.keys)
        assertEquals("family-a", parsed.getValue("library_id").jsonPrimitive.content)
        assertEquals("9", parsed.getValue("expected_revision").jsonPrimitive.content)
        invalidInput { AssistantWorkspaceWire.replySpeechRequest("family-a", 9, request, request) }
        invalidInput { AssistantWorkspaceWire.replySpeechRequest("family-a", 9, request, "not-a-uuid") }
        invalidInput { AssistantWorkspaceWire.replySpeechRequest("family-a", Long.MAX_VALUE, request, speechId) }
        invalidInput { AssistantWorkspaceWire.replySpeechRequest("", 9, request, speechId) }
    }

    @Test fun replySpeechWavEnforcesPcmFramingAndThirtySecondLimit() {
        fun wav(seconds: Int): ByteArray {
            val rate = 16_000
            val dataBytes = seconds * rate * 2
            return ByteArray(44 + dataBytes).also { bytes ->
                fun ascii(offset: Int, value: String) = value.toByteArray().copyInto(bytes, offset)
                fun u16(offset: Int, value: Int) { bytes[offset] = value.toByte(); bytes[offset + 1] = (value shr 8).toByte() }
                fun u32(offset: Int, value: Int) {
                    for (i in 0..3) bytes[offset + i] = (value ushr (i * 8)).toByte()
                }
                ascii(0, "RIFF"); u32(4, bytes.size - 8); ascii(8, "WAVE")
                ascii(12, "fmt "); u32(16, 16); u16(20, 1); u16(22, 1)
                u32(24, rate); u32(28, rate * 2); u16(32, 2); u16(34, 16)
                ascii(36, "data"); u32(40, dataBytes)
            }
        }
        val valid = wav(1)
        assertSame(valid, AssistantWorkspaceWire.replySpeechAudio(valid))
        invalid { AssistantWorkspaceWire.replySpeechAudio(wav(31)) }
        invalid { AssistantWorkspaceWire.replySpeechAudio(valid.copyOf().also { it[20] = 3 }) }
        invalid { AssistantWorkspaceWire.replySpeechAudio(valid.copyOf().also { it[4] = 0 }) }
    }

    @Test fun listLabelsAreOptInNullableBoundedUnicodeAndControlFree() {
        val prefix = """{"version":1,"threads":[{"thread_id":"$thread","library_id":"family-a","created_at":"2026-10-13T00:00:00Z","updated_at":"2026-10-13T00:00:00Z","expires_at":"2026-11-12T00:00:00Z","revision":2,"exchange_count":2"""
        val without = AssistantWorkspaceWire.threadList((prefix + "}]}").toByteArray(), "family-a")
        assertNull(without.threads.single().label)
        val labeled = AssistantWorkspaceWire.threadList((prefix + ",\"label\":\"旅行照片 · 北京\"}]}").toByteArray(), "family-a", includeLabels = true)
        assertEquals("旅行照片 · 北京", labeled.threads.single().label)
        val unicodeBoundary = AssistantWorkspaceWire.threadList((prefix + ",\"label\":\"${"😀".repeat(64)}\"}]}").toByteArray(), "family-a", includeLabels = true)
        assertEquals(64, unicodeBoundary.threads.single().label!!.codePointCount(0, unicodeBoundary.threads.single().label!!.length))
        val empty = AssistantWorkspaceWire.threadList((prefix + ",\"label\":null}]}").toByteArray(), "family-a", includeLabels = true)
        assertNull(empty.threads.single().label)
        invalid { AssistantWorkspaceWire.threadList((prefix + ",\"label\":\"${"a".repeat(65)}\"}]}").toByteArray(), "family-a", true) }
        invalid { AssistantWorkspaceWire.threadList((prefix + ",\"label\":\"${"😀".repeat(65)}\"}]}").toByteArray(), "family-a", true) }
        invalid { AssistantWorkspaceWire.threadList((prefix + ",\"label\":\"line\\nbreak\"}]}").toByteArray(), "family-a", true) }
        invalid { AssistantWorkspaceWire.threadList((prefix + ",\"label\":null}]}").toByteArray(), "family-a", false) }
    }

    @Test fun historyPagesRequireOneOrderedOwnedSnapshotAndConsistentCursor() {
        val rows = """[{"exchange_id":"$exchangeA","revision":2,"created_at":"2026-10-13T00:00:00Z","expires_at":"2026-11-12T00:00:00Z","input_text":"older question","reply":"older answer","cards":[],"receipt_count":0},{"exchange_id":"$exchangeB","revision":4,"created_at":"2026-10-13T00:00:00Z","expires_at":"2026-11-12T00:00:00Z","input_text":"newer question","reply":"newer answer","cards":[],"receipt_count":0}]"""
        fun page(threadId: String = thread, snapshot: Int = 5, before: Int = 5, exchanges: String = rows,
                 older: Boolean = true, next: String = "2") =
            """{"version":1,"thread_id":"$threadId","snapshot_revision":$snapshot,"before_revision":$before,"exchanges":$exchanges,"has_older_exchanges":$older,"next_before_revision":$next}"""

        val parsed = AssistantWorkspaceWire.historyPage(page().toByteArray(), "family-a", thread, 5, 5)
        assertEquals(listOf(2L, 4L), parsed.exchanges.map { it.revision })
        assertTrue(parsed.hasOlderExchanges)
        assertEquals(2L, parsed.nextBeforeRevision)
        assertEquals("older answer", parsed.exchanges.first().reply)

        invalid { AssistantWorkspaceWire.historyPage(page(threadId = "55555555-5555-4555-8555-555555555555").toByteArray(), "family-a", thread, 5, 5) }
        invalid { AssistantWorkspaceWire.historyPage(page(snapshot = 6).toByteArray(), "family-a", thread, 5, 5) }
        invalid { AssistantWorkspaceWire.historyPage(page(before = 4).toByteArray(), "family-a", thread, 5, 5) }
        invalid { AssistantWorkspaceWire.historyPage(page(exchanges = rows.replace("\"revision\":4", "\"revision\":2")).toByteArray(), "family-a", thread, 5, 5) }
        invalid { AssistantWorkspaceWire.historyPage(page(exchanges = rows.replace(exchangeB, exchangeA)).toByteArray(), "family-a", thread, 5, 5) }
        invalid { AssistantWorkspaceWire.historyPage(page(exchanges = rows.replace("\"revision\":4", "\"revision\":5")).toByteArray(), "family-a", thread, 5, 5) }
        invalid { AssistantWorkspaceWire.historyPage(page(older = false).toByteArray(), "family-a", thread, 5, 5) }
        invalid { AssistantWorkspaceWire.historyPage(page(exchanges = "[]").toByteArray(), "family-a", thread, 5, 5) }
        val noMore = page(exchanges = rows, older = false, next = "null")
        val terminal = AssistantWorkspaceWire.historyPage(noMore.toByteArray(), "family-a", thread, 5, 5)
        assertFalse(terminal.hasOlderExchanges)
        assertNull(terminal.nextBeforeRevision)
        invalid { AssistantWorkspaceWire.historyPage(page().replace("\"has_older_exchanges\":true", "\"has_older_exchanges\":true,\"future\":false").toByteArray(), "family-a", thread, 5, 5) }
    }

    @Test fun parsesPrivateHistoryWithoutReturningCardIdentifiersAndAllowsClearingPreference() {
        val history = """{"version":1,"thread":{"thread_id":"$thread","library_id":"family-a","created_at":"2026-10-13T00:00:00Z","updated_at":"2026-10-13T00:00:00Z","expires_at":"2026-11-12T00:00:00Z","revision":1},"latest_request_id":null,"exchanges":[{"exchange_id":"33333333-3333-4333-8333-333333333333","revision":1,"created_at":"2026-10-13T00:00:00Z","expires_at":"2026-11-12T00:00:00Z","input_text":"find photos","reply":"Found photos","cards":[{"type":"media","count":2,"actionable":false}],"receipt_count":1}]}"""
        val longerReply = history.replace("\"latest_request_id\":null", "\"latest_request_id\":null,\"has_older_exchanges\":true")
            .replace("\"reply\":\"Found photos\"", "\"reply\":\"${"r".repeat(3000)}\"")
        val parsed = AssistantWorkspaceWire.threadDetail(longerReply.toByteArray(), "family-a", thread)
        assertEquals(0, parsed.thread.exchangeCount)
        assertTrue(parsed.hasOlderExchanges)
        assertNull(parsed.latestRequestId)
        assertNull(parsed.exchanges.single().requestId)
        assertEquals(2, parsed.exchanges.single().cards.single().count)
        assertEquals(3000, parsed.exchanges.single().reply.length)
        invalid { AssistantWorkspaceWire.threadDetail(history.replace("\"actionable\":false", "\"actionable\":false,\"id\":\"secret\"").toByteArray(), "family-a", thread) }
        val clearLocale = AssistantWorkspaceWire.preferencesRequest("family-a", 7,
            mapOf(AssistantWorkspacePreference.LOCALE to null))
        assertTrue(clearLocale.contains("\"locale\":null"))
    }

    @Test fun requestBodiesAreNarrowAndBounded() {
        val body = AssistantWorkspaceWire.turnRequest("family-a", request, 3, "找照片")
        assertTrue(body.contains("\"library_id\":\"family-a\""))
        assertTrue(body.contains("\"request_id\":\"$request\""))
        assertFalse(body.contains("context")); assertFalse(body.contains("reply")); assertFalse(body.contains("cards"))
        val optedIn = kotlinx.serialization.json.Json.parseToJsonElement(
            AssistantWorkspaceWire.turnRequest("family-a", request, 3, "find saved story lake", true),
        ).jsonObject
        assertEquals(setOf("library_id", "request_id", "expected_revision", "text", "accepts"), optedIn.keys)
        assertEquals("saved_memory_cards_v1", optedIn.getValue("accepts").jsonArray.single().jsonPrimitive.content)
        invalidInput { AssistantWorkspaceWire.turnRequest("family-a", request, 0, "x".repeat(1025)) }
        invalidInput { AssistantWorkspaceWire.turnRequest("family-a", request, 0, "bad\u007ftext") }
        invalidInput { AssistantWorkspaceWire.createThreadRequest("family-a", thread.replace("4", "1")) }
    }

    @Test fun parentCorrelationOverloadDelegatesForLegacyImplementations() = runBlocking {
        val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
        var received = false
        val legacy = object : AssistantWorkspaceApi {
            override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                           expectedRevision: Long, text: String): AssistantWorkspaceTurn {
                received = text == "Find photos"
                return AssistantWorkspaceTurn(1, threadId, requestId, AssistantWorkspaceRequestStatus.PENDING,
                    expectedRevision, false, null, null)
            }
        }
        val returned = legacy.submitTurn(token, "family-a", thread, request, 0, "Find photos", "33333333-3333-4333-8333-333333333333")
        assertTrue(received)
        assertEquals(AssistantWorkspaceRequestStatus.PENDING, returned.status)
    }

    @Test fun historyApiOverloadPreservesLegacyListAndFailsUnavailableByDefault() = runBlocking {
        val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
        var listCalls = 0
        val legacy = object : AssistantWorkspaceApi {
            override suspend fun listThreads(token: Bearer, library: String): AssistantWorkspaceThreadList {
                listCalls++
                return AssistantWorkspaceThreadList(1, emptyList())
            }
        }
        assertTrue(legacy.listThreads(token, "family-a", includeLabels = true).threads.isEmpty())
        assertEquals(1, listCalls)
        try { legacy.readHistory(token, "family-a", thread, 2, 2); fail("legacy API unexpectedly supports paging") }
        catch (e: ApiFailure) { assertEquals(FailureKind.HTTP, e.kind); assertEquals(503, e.status) }
        try { legacy.speakTurn(token, "family-a", thread, request, 2, "55555555-5555-4555-8555-555555555555"); fail("legacy API unexpectedly supports private reply speech") }
        catch (e: ApiFailure) { assertEquals(FailureKind.HTTP, e.kind); assertEquals(503, e.status) }
    }

    private fun invalid(block: () -> Any?) {
        try { block(); fail("malformed workspace response was accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, e.kind) }
    }
    private fun invalidInput(block: () -> Any?) {
        try { block(); fail("invalid workspace request was accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
    }
}
