package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.runBlocking
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
