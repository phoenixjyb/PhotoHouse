package dev.photohouse.connected.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.*
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class MemoryCommunityWireTest {
    private val story = "11111111-1111-1111-1111-111111111111"
    private val account = "22222222-2222-2222-2222-222222222222"
    private val contribution = "33333333-3333-3333-3333-333333333333"
    private val book = "44444444-4444-4444-4444-444444444444"

    private fun reject(block: () -> Unit) {
        try { block(); fail("invalid memory community response was accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, e.kind) }
    }

    @Test fun parsesCapabilityFlagsIndependentlyAndRejectsInvalidDependencies() {
        val caps = """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":false,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}"""
        assertFalse(ProtectedMemoryCommunityWire.capabilities(caps.toByteArray()).generationEnabled)
        reject { ProtectedMemoryCommunityWire.capabilities(caps.replace("\"enabled\":true", "\"enabled\":false").toByteArray()) }
        reject { ProtectedMemoryCommunityWire.capabilities(caps.replace("\"enabled\":true", "\"enabled\":true,\"enabled\":true").toByteArray()) }
    }

    @Test fun parsesContributionPagesAndDetailWithExactNullableFields() {
        val page = """{"version":1,"story_id":"$story","page":1,"page_size":16,"has_more":false,"can_review":false,"can_delete":false,"items":[{"id":"$contribution","story_id":"$story","author_id":"$account","kind":"text","language":"zh","byline":"家人","sha256":"${"a".repeat(64)}","duration_ms":null,"chapter_id":null,"base_story_revision":"2","state":"accepted","created_at":1720000000,"text":"原话","processing_consent":true}]}"""
        val parsed = ProtectedMemoryCommunityWire.contributionPage(page.toByteArray(), story, 1)
        assertEquals("原话", parsed.items.single().text)
        assertTrue(parsed.items.single().processingConsent)
        reject { ProtectedMemoryCommunityWire.contributionPage(page.replace("\"page_size\":16", "\"page_size\":8").toByteArray(), story, 1) }
        reject { ProtectedMemoryCommunityWire.contributionPage(page.replace("\"story_id\":\"$story\"", "\"story_id\":\"$book\"", false).toByteArray(), story, 1) }
        reject { ProtectedMemoryCommunityWire.contributionPage(page.replace("\"base_story_revision\":\"2\"", "\"base_story_revision\":2").toByteArray(), story, 1) }

        val wrapped = """{"version":1,"id":"$contribution","story_id":"$story","author_id":"$account","kind":"text","language":"zh","byline":"家人","sha256":"${"a".repeat(64)}","duration_ms":null,"chapter_id":null,"base_story_revision":"2","state":"accepted","created_at":1720000000,"text":"原话","processing_consent":true,"can_review":true,"can_delete":false,"derivation":{"revision":1,"state":"ready","transcript":null,"polished_text":"修订建议","tags":["family"],"error_code":null,"created_at":1720000000,"updated_at":1720000001}}"""
        assertEquals("修订建议", ProtectedMemoryCommunityWire.contributionDetail(wrapped.toByteArray(), story, contribution).derivation?.polishedText)
    }

    @Test fun requestSerializationIsClosedBoundedAndRetryStable() {
        val mutation = "55555555-5555-5555-5555-555555555555"
        val request = MemoryContributionRequest("text", "A family's words", "en", "Member", true,
            "chapter-1", 2, mutation)
        val raw = ProtectedMemoryCommunityWire.textRequest(request)
        val value = Json.parseToJsonElement(raw).jsonObject
        assertEquals(setOf("kind", "text", "language", "byline", "consent", "chapter_id", "revision", "mutation_id"), value.keys)
        assertEquals("2", value.getValue("revision").toString().trim('"'))
        assertEquals(mutation, value.getValue("mutation_id").toString().trim('"'))
        assertEquals(raw, ProtectedMemoryCommunityWire.textRequest(request))
        assertThrows(IllegalArgumentException::class.java) {
            ProtectedMemoryCommunityWire.textRequest(request.copy(text = "x".repeat(8193)))
        }

        val bookRequest = MemoryBookMutation("Family book", "en", "Introduction", listOf(story, book), 0,
            mutationId = mutation)
        assertTrue(ProtectedMemoryCommunityWire.bookRequest(bookRequest).contains("\"story_ids\":\"$story,$book\""))

        val turn = MemoryTurnRequest(3, "memoir question", mutation)
        val legacyTurnJson = ProtectedMemoryCommunityWire.turnRequest(turn)
        assertEquals(legacyTurnJson, ProtectedMemoryCommunityWire.turnRequest(turn.copy(editorialContext = true)))
        assertEquals(setOf("revision", "mutation_id", "text"), Json.parseToJsonElement(legacyTurnJson).jsonObject.keys)

        val narrative = MemoryNarrativeRequest("book", book, 3, "Preserve uncertainty", mutation)
        val legacyNarrativeJson = ProtectedMemoryCommunityWire.narrativeRequest(narrative)
        assertEquals(legacyNarrativeJson, ProtectedMemoryCommunityWire.narrativeRequest(
            narrative.copy(editorialContext = true)))
        assertEquals(setOf("target_type", "target_id", "revision", "mutation_id", "instructions"),
            Json.parseToJsonElement(legacyNarrativeJson).jsonObject.keys)
    }

    @Test fun audioMetadataIsBase64AndCanonicalWavMustMatchCapability() {
        val caps = MemoryCommunityCapabilities(true, true, true, 30, "wav_pcm16_mono_16000", 5, 8192, "until_owner_deletes")
        val request = MemoryContributionRequest("audio", "", "en", "Member", true, null, 1,
            "55555555-5555-5555-5555-555555555555")
        val encoded = ProtectedMemoryCommunityWire.audioMetadata(request, caps)
        assertTrue(encoded.length <= 4096)
        assertTrue(String(java.util.Base64.getDecoder().decode(encoded), Charsets.UTF_8).contains("\"kind\":\"audio\""))
        assertTrue(ProtectedMemoryCommunityWire.validWav(wav(8000), 1))
        assertTrue(ProtectedMemoryCommunityWire.validWav(wav(8000), 30))
        assertTrue("backend accepts any positive complete sample frame", ProtectedMemoryCommunityWire.validWav(wav(1), 1))
        assertTrue("valid ancillary RIFF chunks are allowed", ProtectedMemoryCommunityWire.validWav(wavWithAncillaryChunk(8000), 1))
        assertFalse(ProtectedMemoryCommunityWire.validWav(wav(1).copyOf(45), 1))
        assertFalse(ProtectedMemoryCommunityWire.validWav(wavWithAncillaryChunk(8000).copyOf(50), 1))
        assertFalse(ProtectedMemoryCommunityWire.validWav(wav(8000), 0))
    }

    @Test fun parsesBookConversationAndJobWireRevisionsAsDecimalStrings() {
        val bookJson = """{"version":1,"type":"memoir","id":"$book","revision":"3","can_edit":true,"title":"Family book","introduction":"","language":"en","stories":[{"id":"$story","title":"Day","revision":"2","item_count":1,"cover_asset_id":"42"}]}"""
        assertEquals(3, ProtectedMemoryCommunityWire.bookDetail(bookJson.toByteArray(), book, 3).revision)
        val bookPage = """{"version":1,"library_id":"family-a","page":1,"page_size":8,"has_more":false,"can_create":true,"items":[$bookJson]}"""
        val parsedBookPage = ProtectedMemoryCommunityWire.bookPage(bookPage.toByteArray(), "family-a", 1)
        assertEquals(1, parsedBookPage.items.size)
        assertTrue(parsedBookPage.canCreate)
        reject { ProtectedMemoryCommunityWire.bookDetail(bookJson.replace("\"revision\":\"3\"", "\"revision\":3").toByteArray(), book, 1) }
        val conversationRequest = MemoryConversationRequest("66666666-6666-6666-6666-666666666666", "story", story)
        val convoJson = """{"version":1,"id":"${conversationRequest.id}","target_type":"story","target_id":"$story","expires_at":1721000000}"""
        assertEquals(conversationRequest.id, ProtectedMemoryCommunityWire.conversation(convoJson.toByteArray(), conversationRequest).id)
        val conversations = """{"version":1,"items":[{"id":"${conversationRequest.id}","created_at":1720000000,"expires_at":1721000000}]}"""
        assertEquals(conversationRequest.id, ProtectedMemoryCommunityWire.conversations(conversations.toByteArray()).items.single().id)
        val turns = """{"version":1,"id":"${conversationRequest.id}","expires_at":1721000000,"page":1,"has_more":false,"items":[{"id":"88888888-8888-8888-8888-888888888888","sequence":1,"input_text":"Question","reply_text":null,"reply_kind":null,"job_id":"77777777-7777-7777-7777-777777777777","state":"queued"}]}"""
        assertEquals(1, ProtectedMemoryCommunityWire.turns(turns.toByteArray(), conversationRequest.id, 1).items.single().sequence)
        val jobJson = """{"version":1,"id":"77777777-7777-7777-7777-777777777777","kind":"chat","state":"ready","created_at":1,"updated_at":2,"expires_at":3,"error_code":null,"result":{"version":1,"kind":"answer","reply":"Reply","source_ids":[],"questions":[],"proposal":null},"needs_review":true,"base_revision":"2"}"""
        assertEquals(2, ProtectedMemoryCommunityWire.job(jobJson.toByteArray()).baseRevision)
        val multilineJob = jobJson.replace("\"Reply\"", "\"Line one\\nLine two\\tIndented\"")
        assertEquals("Line one\nLine two\tIndented", ProtectedMemoryCommunityWire.job(multilineJob.toByteArray()).result?.get("reply")?.jsonPrimitive?.content)
        reject { ProtectedMemoryCommunityWire.job(jobJson.replace("\"Reply\"", "\"Bad\\u0007text\"").toByteArray()) }
        reject { ProtectedMemoryCommunityWire.job(jobJson.replace("\"base_revision\":\"2\"", "\"base_revision\":2").toByteArray()) }
        reject { ProtectedMemoryCommunityWire.job(jobJson.replace("\"proposal\":null", "\"proposal\":{} ").toByteArray()) }
    }

    @Test fun conversationPreviewsAcceptOnlyLegacyOrBoundedCollapsedUnicodeShape() {
        val id = "66666666-6666-6666-6666-666666666666"
        val legacy = """{"version":1,"items":[{"id":"$id","created_at":1720000000,"expires_at":1721000000}]}"""
        assertNull(ProtectedMemoryCommunityWire.conversations(legacy.toByteArray()).items.single().firstMessagePreview)

        fun preview(value: String) = """{"version":1,"items":[{"id":"$id","created_at":1720000000,"expires_at":1721000000,"first_message_preview":$value}]}"""
        val valid = ProtectedMemoryCommunityWire.conversations(preview("\"种花 🌻 and family\"").toByteArray()).items.single()
        assertEquals("种花 🌻 and family", valid.firstMessagePreview)
        val eightyAstral = "😀".repeat(80)
        assertEquals(eightyAstral, ProtectedMemoryCommunityWire.conversations(preview(JsonPrimitive(eightyAstral).toString()).toByteArray()).items.single().firstMessagePreview)
        reject { ProtectedMemoryCommunityWire.conversations(preview(JsonPrimitive("😀".repeat(81)).toString()).toByteArray()) }
        reject { ProtectedMemoryCommunityWire.conversations(preview("\" leading\"").toByteArray()) }
        reject { ProtectedMemoryCommunityWire.conversations(preview("\"trailing \"").toByteArray()) }
        reject { ProtectedMemoryCommunityWire.conversations(preview("\"two  spaces\"").toByteArray()) }
        reject { ProtectedMemoryCommunityWire.conversations(preview("\"bad\\u0085control\"").toByteArray()) }
        reject { ProtectedMemoryCommunityWire.conversations(preview("\"bad\\u0001control\"").toByteArray()) }
        reject { ProtectedMemoryCommunityWire.conversations(preview("\"\\ud800\"").toByteArray()) }
        reject { ProtectedMemoryCommunityWire.conversations(preview("123").toByteArray()) }

        val mixed = """{"version":1,"items":[{"id":"$id","created_at":1720000000,"expires_at":1721000000},{"id":"$book","created_at":1720000000,"expires_at":1721000000,"first_message_preview":"Preview"}]}"""
        reject { ProtectedMemoryCommunityWire.conversations(mixed.toByteArray()) }
        reject { ProtectedMemoryCommunityWire.conversations(legacy.replace("\"expires_at\":1721000000", "\"expires_at\":1721000000,\"other\":1").toByteArray()) }
    }

    @Test fun turnsAcceptExactLegacyOrBoundedOptInReplyContextAndRejectMalformedContext() {
        val conversation = "66666666-6666-6666-6666-666666666666"
        val turn = "88888888-8888-8888-8888-888888888888"
        val legacyItem = """{"id":"$turn","sequence":16,"input_text":"Question","reply_text":"Answer","reply_kind":"answer","job_id":null,"state":"ready"}"""
        val legacy = """{"version":1,"id":"$conversation","expires_at":1720000000,"page":1,"has_more":false,"items":[$legacyItem]}"""
        val oldTurn = ProtectedMemoryCommunityWire.turns(legacy.toByteArray(), conversation, 1).items.single()
        assertNull(oldTurn.replySourceIds)
        assertNull(oldTurn.replyQuestions)

        val enhancedItem = """{"id":"$turn","sequence":16,"input_text":"Question","reply_text":"Answer","reply_kind":"answer","job_id":null,"state":"ready","reply_source_ids":["contribution-33333333-3333-4333-8333-333333333333","caption-101"],"reply_questions":["Which flowers were planted?","后来发生了什么？"]}"""
        val enhanced = """{"version":1,"id":"$conversation","expires_at":1720000000,"page":1,"has_more":false,"items":[$enhancedItem]}"""
        val parsed = ProtectedMemoryCommunityWire.turns(enhanced.toByteArray(), conversation, 1).items.single()
        assertEquals(listOf("contribution-33333333-3333-4333-8333-333333333333", "caption-101"), parsed.replySourceIds)
        assertEquals(listOf("Which flowers were planted?", "后来发生了什么？"), parsed.replyQuestions)
        val emptyMetadata = enhancedItem.replace("[\"contribution-33333333-3333-4333-8333-333333333333\",\"caption-101\"]", "[]")
            .replace("[\"Which flowers were planted?\",\"后来发生了什么？\"]", "[]")
        assertEquals(emptyList<String>(), ProtectedMemoryCommunityWire.turns(
            enhanced.replace(enhancedItem, emptyMetadata).toByteArray(), conversation, 1).items.single().replyQuestions)

        reject { ProtectedMemoryCommunityWire.turns(enhanced.replace(",\"reply_questions\":[\"Which flowers were planted?\",\"后来发生了什么？\"]", "").toByteArray(), conversation, 1) }
        reject { ProtectedMemoryCommunityWire.turns(enhanced.replace("\"state\":\"ready\",", "\"state\":\"ready\",\"unexpected\":true,").toByteArray(), conversation, 1) }
        reject { ProtectedMemoryCommunityWire.turns(enhanced.replace("\"caption-101\"]", "\"caption-101\",\"caption-101\"]").toByteArray(), conversation, 1) }
        reject { ProtectedMemoryCommunityWire.turns(enhanced.replace("\"caption-101\"]", "\"源-101\"]").toByteArray(), conversation, 1) }
        reject { ProtectedMemoryCommunityWire.turns(enhanced.replace("\"caption-101\"]", "\"a${"x".repeat(128)}\"]").toByteArray(), conversation, 1) }
        reject { ProtectedMemoryCommunityWire.turns(enhanced.replace("\"后来发生了什么？\"]", "\"${"字".repeat(171)}\"]").toByteArray(), conversation, 1) }
        reject { ProtectedMemoryCommunityWire.turns(enhanced.replace("\"后来发生了什么？\"]", "\" \"]").toByteArray(), conversation, 1) }
        val tooManyIds = (1..97).joinToString(",") { "\"caption-$it\"" }
        reject { ProtectedMemoryCommunityWire.turns(enhanced.replace("[\"contribution-33333333-3333-4333-8333-333333333333\",\"caption-101\"]", "[$tooManyIds]").toByteArray(), conversation, 1) }
        reject { ProtectedMemoryCommunityWire.turns(enhanced.replace("[\"Which flowers were planted?\",\"后来发生了什么？\"]",
            "[\"one?\",\"two?\",\"three?\",\"four?\"]").toByteArray(), conversation, 1) }
    }

    @Test fun legacyTurnUsesOnlyAnExactlyMatchingReadyChatJobForReplyContextFallback() {
        val turnId = "88888888-8888-8888-8888-888888888888"
        val jobId = "77777777-7777-7777-7777-777777777777"
        val turn = MemoryTurn(turnId, 16, "Question", "Answer", "answer", jobId, "ready")
        val validResult = Json.parseToJsonElement(
            """{"version":1,"kind":"answer","reply":"Answer","source_ids":["caption-101"],"questions":["More?"],"proposal":null}""").jsonObject
        fun job(id: String = jobId, kind: String = "chat", state: String = "ready", revision: Long = 3,
                result: kotlinx.serialization.json.JsonObject? = validResult) =
            MemoryJob(id, kind, state, 1, 2, 3, null, result, true, revision)
        assertEquals(MemoryReplyContext(listOf("caption-101"), listOf("More?")), memoryReplyContext(turn, job(), 3))
        assertNull(memoryReplyContext(turn, job(id = turnId), 3))
        assertNull(memoryReplyContext(turn, job(kind = "narrative"), 3))
        assertNull(memoryReplyContext(turn, job(state = "running"), 3))
        assertNull(memoryReplyContext(turn, job(revision = 2), 3))
        val wrongReply = Json.parseToJsonElement(
            """{"version":1,"kind":"answer","reply":"Other","source_ids":[],"questions":["More?"],"proposal":null}""").jsonObject
        assertNull(memoryReplyContext(turn, job(result = wrongReply), 3))
        val wrongKind = Json.parseToJsonElement(
            """{"version":1,"kind":"clarification","reply":"Answer","source_ids":[],"questions":["More?"],"proposal":null}""").jsonObject
        assertNull(memoryReplyContext(turn, job(result = wrongKind), 3))
        val optInEmpty = turn.copy(replySourceIds = emptyList(), replyQuestions = emptyList())
        assertEquals(emptyList<String>(), memoryReplyContext(optInEmpty, job(), 3)?.questions)
        assertNull(memoryReplyContext(turn.copy(replyText = null, replySourceIds = emptyList(), replyQuestions = emptyList()), job(), 3))
        val invalidRef = Json.parseToJsonElement(
            """{"version":1,"kind":"answer","reply":"Answer","source_ids":["源-101"],"questions":["More?"],"proposal":null}""").jsonObject
        assertNull(memoryReplyContext(turn, job(result = invalidRef), 3))
        val duplicateRefs = Json.parseToJsonElement(
            """{"version":1,"kind":"answer","reply":"Answer","source_ids":["caption-101","caption-101"],"questions":["More?"],"proposal":null}""").jsonObject
        assertNull(memoryReplyContext(turn, job(result = duplicateRefs), 3))
        val invalidQuestion = Json.parseToJsonElement(
            """{"version":1,"kind":"answer","reply":"Answer","source_ids":[],"questions":["bad\u0007question"],"proposal":null}""").jsonObject
        assertNull(memoryReplyContext(turn, job(result = invalidQuestion), 3))
        val oversizedQuestion = Json.parseToJsonElement(
            """{"version":1,"kind":"answer","reply":"Answer","source_ids":[],"questions":["qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"],"proposal":null}""").jsonObject
        assertNull(memoryReplyContext(turn, job(result = oversizedQuestion), 3))
    }

    private fun wav(frames: Int): ByteArray {
        val data = frames * 2
        val bytes = ByteArray(44 + data)
        val b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        b.put("RIFF".toByteArray()); b.putInt(bytes.size - 8); b.put("WAVEfmt ".toByteArray())
        b.putInt(16); b.putShort(1); b.putShort(1); b.putInt(16000); b.putInt(32000)
        b.putShort(2); b.putShort(16); b.put("data".toByteArray()); b.putInt(data)
        return bytes
    }

    private fun wavWithAncillaryChunk(frames: Int): ByteArray {
        val base = wav(frames)
        val extra = byteArrayOf('J'.code.toByte(), 'U'.code.toByte(), 'N'.code.toByte(), 'K'.code.toByte(),
            2, 0, 0, 0, 7, 8)
        return ByteArray(base.size + extra.size).also { out ->
            base.copyInto(out, 0, 0, 12)
            extra.copyInto(out, 12)
            base.copyInto(out, 12 + extra.size, 12)
            ByteBuffer.wrap(out).order(ByteOrder.LITTLE_ENDIAN).putInt(4, out.size - 8)
        }
    }
}
