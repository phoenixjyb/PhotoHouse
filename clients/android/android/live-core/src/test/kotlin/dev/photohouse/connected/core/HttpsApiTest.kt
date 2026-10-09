package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.*
import okhttp3.tls.*
import org.junit.Assert.*
import org.junit.Test
import java.net.InetAddress
import java.util.concurrent.TimeUnit

class HttpsApiTest {
    private val password = "synthetic-password-only"
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
    private val asset = Asset("1", "image", null, null, null, null, "/assets/1/thumbnail?library=family")
    private val session = """{"account_id":"synthetic-account","phone_login":"+12025550123","memberships":[]}"""
    private class TlsFixture(hostname: String = "localhost") : AutoCloseable {
        val certificate = HeldCertificate.Builder().addSubjectAlternativeName(hostname).build()
        val server = MockWebServer().apply {
            useHttps(HandshakeCertificates.Builder().heldCertificate(certificate).build().sslSocketFactory(), false)
            start(InetAddress.getByName("127.0.0.1"), 0)
        }
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(certificate.certificate).build()
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
        val origin = TrustedOrigin.parse("https://localhost:${server.port}")
        val api = HttpsPhotoHouseApi(origin, client)
        override fun close() { server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll() }
    }
    private fun json(body: String) = MockResponse().setHeader("Content-Type", "application/json").setBody(body)
    private suspend fun failure(block: suspend () -> Unit): ApiFailure {
        try { block() } catch (e: ApiFailure) { return e }
        throw AssertionError("Expected a classified failure")
    }
    private fun range(body: String = "abcd", header: String = "bytes 0-3/10") = MockResponse().setResponseCode(206)
        .setHeader("Content-Type", "video/mp4").setHeader("Content-Range", header).setBody(body)
    @Test fun galleryDateHintsAreLabeledAndOlderServersKeepWorking() = runBlocking {
        val legacy = """{"library_id":"family","page":1,"page_size":50,"total":1,"originals_allowed":false,"items":[{"id":"1","kind":"image","width":null,"height":null,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/1/thumbnail?library=family"}]}"""
        val withHint = legacy.replace("\"thumbnail_url\"", "\"date_hint\":{\"value\":\"2024-05-12\",\"source\":\"filename\"},\"thumbnail_url\"")
        TlsFixture().use { f ->
            val api = HttpsPhotoHouseApi(f.origin, f.client, dateHintsEnabled = true)
            f.server.enqueue(json("{} ").setResponseCode(400))
            f.server.enqueue(json(legacy))
            f.server.enqueue(json(legacy))
            assertNull(api.gallery(token, "family", 1).items.single().date_hint)
            assertEquals("1", f.server.takeRequest().requestUrl!!.queryParameter("date_hints"))
            assertNull(f.server.takeRequest().requestUrl!!.queryParameter("date_hints"))
            api.gallery(token, "family", 1)
            assertNull(f.server.takeRequest().requestUrl!!.queryParameter("date_hints"))
        }
        TlsFixture().use { f ->
            val api = HttpsPhotoHouseApi(f.origin, f.client, dateHintsEnabled = true)
            f.server.enqueue(json(withHint))
            val result = api.gallery(token, "family", 1).items.single()
            assertEquals(DateHint("2024-05-12", "filename"), result.date_hint)
            assertNull(result.taken_at)
            assertEquals("1", f.server.takeRequest().requestUrl!!.queryParameter("date_hints"))
        }
    }
    @Test fun savedMemoryStoriesUseProtectedNoStoreGetAndStrictDetailScope() = runBlocking {
        TlsFixture().use { f ->
            val api = HttpsPhotoHouseApi(f.origin, f.client, protectedNativeV2Enabled = true)
            val storyId = "11111111-1111-1111-1111-111111111111"
            val summary = """{"id":"$storyId","title":"Garden day","theme":"everyday","language":"zh","revision":"3","cover_asset_id":"1","item_count":1,"chapter_count":1,"updated_at":1720000000,"can_edit":false}"""
            f.server.enqueue(json("""{"library_id":"family","page":1,"page_size":8,"has_more":false,"can_create":false,"items":[$summary]}"""))
            assertEquals(storyId, api.savedMemoryStories(token, "family", 1).items.single().id)
            val list = f.server.takeRequest()
            assertEquals("GET", list.method)
            assertEquals("/memory-stories?library=family&page=1", list.path)
            assertEquals(token.header(), list.getHeader("Authorization"))
            assertEquals("no-store", list.getHeader("Cache-Control"))

            f.server.enqueue(json("""{"library_id":"family","page":2,"page_size":8,"has_more":false,"can_create":false,"items":[${summary.replace("everyday", "trip") }]}"""))
            assertEquals("trip", api.savedMemoryStories(token, "family", 2, "trip").items.single().theme)
            assertEquals("/memory-stories?library=family&page=2&theme=trip", f.server.takeRequest().path)
            assertThrows(IllegalArgumentException::class.java) {
                runBlocking { api.savedMemoryStories(token, "family", 1, "unknown") }
            }

            val item = """{"id":"1","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/1/thumbnail?library=family","date_hint":null,"evidence":[]}"""
            val chapter = """{"id":"chapter-1","title":"Garden","narration":"A quiet day.","asset_ids":["1"],"evidence_ids":[]}"""
            val body = """{"version":1,"library_id":"family","id":"$storyId","revision":"3","created_at":1710000000,"updated_at":1720000000,"can_edit":false,"saved":true,"state":"draft","generator":"family_edited_outline","needs_review":true,"selection_revision":"${"a".repeat(64)}","title":"Garden day","theme":"everyday","language":"zh","items":[$item],"chapters":[$chapter],"questions":[]}"""
            f.server.enqueue(json(body))
            assertEquals("1", api.savedMemoryStory(token, "family", storyId, 3).items.single().asset.id)
            val detail = f.server.takeRequest()
            assertEquals("GET", detail.method)
            assertEquals("/memory-stories/$storyId?library=family", detail.path)
            assertEquals(token.header(), detail.getHeader("Authorization"))

            f.server.enqueue(json(body.replace("\"library_id\":\"family\"", "\"library_id\":\"other\"", false)))
            assertEquals(FailureKind.INVALID_RESPONSE, failure { api.savedMemoryStory(token, "family", storyId, 3) }.kind)
            assertEquals("GET", f.server.takeRequest().method)
        }
    }

    @Test fun savedStoryContributionReadsUseCurrentRevisionAndExplicitProtectedDetailRoute() = runBlocking {
        TlsFixture().use { f ->
            val api = HttpsPhotoHouseApi(f.origin, f.client, protectedNativeV2Enabled = true)
            val storyId = "11111111-1111-1111-1111-111111111111"
            val contributionId = "33333333-3333-3333-3333-333333333333"
            f.server.enqueue(json("""{"version":1,"id":"$storyId","library_id":"family","revision":"4","chapters":[{"id":"chapter-1","contribution_ids":["$contributionId"]}]}"""))
            val refs = api.savedMemoryStoryContributionReferences(token, "family", storyId, 4, listOf("chapter-1"))
            assertEquals(4L, refs.revision)
            assertEquals(listOf(contributionId), refs.chapters.single().contributionIds)
            val refsRequest = f.server.takeRequest()
            assertEquals("GET", refsRequest.method)
            assertEquals("/memory-stories/$storyId/contribution-refs?library=family&revision=4", refsRequest.path)
            assertEquals(token.header(), refsRequest.getHeader("Authorization"))
            assertEquals("no-store", refsRequest.getHeader("Cache-Control"))

            f.server.enqueue(json("""{"version":1,"id":"$contributionId","story_id":"$storyId","author_id":"22222222-2222-2222-2222-222222222222","kind":"text","language":"zh","byline":"家人","sha256":"${"a".repeat(64)}","duration_ms":null,"chapter_id":"chapter-1","base_story_revision":"2","state":"accepted","created_at":1720000000,"text":"家人原话","processing_consent":true,"can_review":false,"can_delete":false,"derivation":null}"""))
            val detail = api.savedMemoryContributionDetail(token, "family", storyId, contributionId)
            assertEquals("家人原话", detail.receipt.contribution.text)
            val detailRequest = f.server.takeRequest()
            assertEquals("GET", detailRequest.method)
            assertEquals("/memory-community/v1/stories/$storyId/contributions/$contributionId?library=family", detailRequest.path)
            assertEquals(token.header(), detailRequest.getHeader("Authorization"))
            assertEquals("no-store", detailRequest.getHeader("Cache-Control"))

            f.server.enqueue(json("{} ").setResponseCode(503))
            assertEquals(503, failure { api.savedMemoryStoryContributionReferences(token, "family", storyId, 4, listOf("chapter-1")) }.status)
        }
    }
    @Test fun memoirEditorialSourceCatalogUsesMetadataOnlyProtectedRouteAndActualChapterList() = runBlocking {
        TlsFixture().use { f ->
            val api = HttpsMemoryCommunityApi(f.origin, f.client)
            val storyId = "11111111-1111-4111-8111-111111111111"
            val contributionId = "33333333-3333-4333-8333-333333333333"
            f.server.enqueue(json("""{"version":1,"id":"$storyId","library_id":"family","revision":"4","chapters":[{"id":"chapter-1","contribution_ids":["$contributionId"]}]}"""))
            val refs = api.getBookEditorialSourceReferences(token, "family", storyId, 4)
            assertEquals(listOf("chapter-1"), refs.chapters.map { it.chapterId })
            assertEquals(listOf(contributionId), refs.chapters.single().contributionIds)
            val request = f.server.takeRequest()
            assertEquals("GET", request.method)
            assertEquals("/memory-stories/$storyId/contribution-refs?library=family&revision=4", request.path)
            assertEquals(token.header(), request.getHeader("Authorization"))
            assertEquals("no-store", request.getHeader("Cache-Control"))
            f.server.enqueue(json("""{"version":1,"id":"$storyId","library_id":"family","revision":"4","chapters":[{"id":"chapter-1","contribution_ids":[]}]}"""))
            assertEquals(FailureKind.INVALID_RESPONSE, failure { api.getBookEditorialSourceReferences(token, "other", storyId, 4) }.kind)
            f.server.takeRequest()
            Unit
        }
    }
    @Test fun savedStoryContributionLinkSaveUsesOptInPutAndCarriesFrozenRevisionFields() = runBlocking {
        TlsFixture().use { f ->
            val api = HttpsPhotoHouseApi(f.origin, f.client, protectedNativeV2Enabled = true)
            val storyId = "11111111-1111-1111-1111-111111111111"
            val mutationId = "55555555-5555-5555-5555-555555555555"
            val groups = """[{"chapter_id":"chapter-1","contribution_ids":[]},{"chapter_id":"chapter-2","contribution_ids":[]}]"""
            val mutation = SavedMemoryStoryContributionReferencesMutation(storyId, 4, "a".repeat(64),
                "Garden day", "everyday", "zh",
                listOf(SavedMemoryStoryChapter("chapter-1", "Garden", "A quiet day.", listOf("1"), emptyList()),
                    SavedMemoryStoryChapter("chapter-2", "Afternoon", "We kept walking.", listOf("2"), listOf("caption-2"))),
                groups, mutationId)
            f.server.enqueue(json("""{"version":1,"library_id":"family","id":"$storyId","revision":"5","created_at":1,"updated_at":2,"can_edit":true,"saved":true,"state":"draft","generator":"family_edited_outline","needs_review":true,"selection_revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","title":"Garden day","theme":"everyday","language":"zh","items":[{"id":"1","kind":"image","width":1,"height":1,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/1/thumbnail?library=family","date_hint":null,"evidence":[]}],"chapters":[{"id":"chapter-1","title":"Garden","narration":"A quiet day.","asset_ids":["1"],"evidence_ids":[]}],"questions":[]}"""))
            val result = api.saveMemoryStoryContributionReferences(token, "family", mutation)
            assertEquals(5L, result.revision)
            val request = f.server.takeRequest()
            assertEquals("PUT", request.method)
            assertEquals("/memory-stories/$storyId?library=family&contribution_refs=1", request.path)
            assertEquals(token.header(), request.getHeader("Authorization"))
            assertEquals("no-store", request.getHeader("Cache-Control"))
            val body = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
            assertEquals(setOf("title", "theme", "language", "asset_ids", "chapters", "selection_revision",
                "revision", "mutation_id", "contribution_refs"), body.keys)
            assertTrue(body.values.all { it is JsonPrimitive && it.jsonPrimitive.isString })
            assertEquals("4", body.getValue("revision").jsonPrimitive.content)
            assertEquals(mutationId, body.getValue("mutation_id").jsonPrimitive.content)
            assertEquals("1,2", body.getValue("asset_ids").jsonPrimitive.content)
            val embeddedChapters = Json.parseToJsonElement(body.getValue("chapters").jsonPrimitive.content).jsonArray
            assertEquals(listOf("chapter-1", "chapter-2"), embeddedChapters.map { it.jsonObject.getValue("id").jsonPrimitive.content })
            val refs = Json.parseToJsonElement(body.getValue("contribution_refs").jsonPrimitive.content).jsonArray
            assertEquals(embeddedChapters.map { it.jsonObject.getValue("id").jsonPrimitive.content },
                refs.map { it.jsonObject.getValue("chapter_id").jsonPrimitive.content })
            assertEquals(listOf("1", "2"), embeddedChapters.flatMap { chapter ->
                chapter.jsonObject.getValue("asset_ids").jsonArray.map { it.jsonPrimitive.content }
            })
            assertEquals(groups, body.getValue("contribution_refs").jsonPrimitive.content)
        }
    }

    @Test fun resumableSessionUsesExactRoutesOffsetsAndChunkHash() = runBlocking {
        TlsFixture().use { f ->
            val api = HttpsPhotoHouseApi(f.origin, f.client, protectedNativeV2Enabled = true, uploadEnabled = true)
            val id = "a".repeat(32); val uploading = "{\"upload_id\":\"$id\",\"bytes\":4,\"offset\":0,\"chunk_bytes\":4194304,\"state\":\"uploading\",\"asset_id\":null}"
            f.server.enqueue(json(uploading).setResponseCode(201)); f.server.enqueue(json(uploading)); f.server.enqueue(json(uploading).setResponseCode(200)); f.server.enqueue(json("{\"upload_id\":\"$id\",\"bytes\":4,\"offset\":4,\"chunk_bytes\":4194304,\"state\":\"complete\",\"asset_id\":\"901\"}")); f.server.enqueue(json("{\"upload_id\":\"$id\",\"bytes\":4,\"offset\":4,\"chunk_bytes\":4194304,\"state\":\"cancelled\",\"asset_id\":null}"))
            val request = UploadSessionRequest("1".repeat(32), "2".repeat(32), "a.jpg", 4, "3".repeat(64), UploadKind.IMAGE, "family-a")
            api.createUploadSession(token, request)
            val createRequest = f.server.takeRequest()
            assertEquals("/upload-sessions", createRequest.requestUrl!!.encodedPath)
            assertEquals("family-a", Json.parseToJsonElement(createRequest.body.readUtf8()).jsonObject.getValue("destination_library_id").jsonPrimitive.content)
            api.uploadSession(token, id); assertEquals("GET", f.server.takeRequest().method)
            api.uploadChunk(token, id, 0, byteArrayOf(1, 2, 3, 4), "4".repeat(64)); val chunkRequest = f.server.takeRequest(); assertEquals("PUT", chunkRequest.method); assertEquals("0", chunkRequest.getHeader("Upload-Offset")); assertEquals("4".repeat(64), chunkRequest.getHeader("X-Chunk-SHA256"))
            api.completeUploadSession(token, id); assertEquals("/upload-sessions/$id/complete", f.server.takeRequest().requestUrl!!.encodedPath)
            api.cancelUploadSession(token, id); assertEquals("DELETE", f.server.takeRequest().method)
        }
    }

    @Test fun textAnnotationUsesExactAuthenticatedContractAndReadsScopedOriginals() = runBlocking {
        TlsFixture().use { f ->
            val api = HttpsPhotoHouseApi(f.origin, f.client, protectedNativeV2Enabled = true, uploadEnabled = true)
            val batch = "a".repeat(32)
            val item = """{"id":"annotation-1","scope":"item","asset_id":"42","batch":"$batch","library_id":"family-a","author_id":"member-1","kind":"text","original_text":"garden dinner","audio_url":null,"mime":null,"duration_ms":null,"sha256":null,"language":"en","local_processing_consent":"no","created_at":1720000000,"derivation":{"revision":1,"state":"held","transcript":null,"polished_text":null,"provider":null,"model":null,"error_code":null},"tags":[]}"""
            f.server.enqueue(json(item).setResponseCode(201))
            val request = UploadTextAnnotationRequest(batch, "42", "en", "no", "123e4567-e89b-12d3-a456-426614174000", "garden dinner")
            val posted = api.postUploadTextAnnotation(token, "family-a", request)
            assertEquals("garden dinner", posted.originalText)
            val post = f.server.takeRequest()
            assertEquals("POST", post.method)
            assertEquals("/upload-annotations/text?library=family-a", post.path)
            assertEquals("Bearer " + "T".repeat(43), post.getHeader("Authorization"))
            assertEquals(setOf("batch", "asset_id", "language", "consent", "mutation_id", "text"), Json.parseToJsonElement(post.body.readUtf8()).jsonObject.keys)
            f.server.enqueue(json("""{"library_id":"family-a","asset_id":"42","batch":"$batch","page":1,"page_size":20,"total":1,"items":[$item]}"""))
            val read = api.uploadAnnotations(token, "family-a", "42")
            assertEquals("garden dinner", read.items.single().originalText)
            assertEquals("held", read.items.single().derivation.state)
            val get = f.server.takeRequest()
            assertEquals("GET", get.method)
            assertEquals("/upload-annotations?library=family-a&asset_id=42&page=1", get.path)
        }
    }
    @Test fun audioAnnotationPostsWavWithScopedHeadersAndChecksReceipt() = runBlocking {
        TlsFixture().use { f ->
            val api = HttpsPhotoHouseApi(f.origin, f.client, protectedNativeV2Enabled = true, uploadEnabled = true)
            val wav = syntheticAnnotationWav()
            val batch = "a".repeat(32)
            val mutation = "123e4567-e89b-12d3-a456-426614174000"
            val request = UploadAudioAnnotationRequest(batch, "42", "en", "yes", mutation, wav)
            val info = UploadAnnotationsWire.audioInfo(request)
            fun item(sha: String) = """{"id":"annotation-audio","scope":"item","asset_id":"42","batch":"$batch","library_id":"family-a","author_id":"member-1","kind":"audio","original_text":null,"audio_url":"/upload-annotations/annotation-audio/audio?library=family-a&asset_id=42","mime":"audio/wav","duration_ms":${info.durationMs},"sha256":"$sha","language":"en","local_processing_consent":"yes","created_at":1720000000,"derivation":{"revision":1,"state":"waiting","transcript":null,"polished_text":null,"provider":null,"model":null,"error_code":null},"tags":[]}"""
            f.server.enqueue(json(item(info.sha256)).setResponseCode(201))
            assertEquals(info.sha256, api.postUploadAudioAnnotation(token, "family-a", request).sha256)
            val post = f.server.takeRequest()
            assertEquals("POST", post.method)
            assertEquals("/upload-annotations/audio?library=family-a", post.path)
            assertEquals("audio/wav", post.getHeader("Content-Type"))
            assertEquals("Bearer " + "T".repeat(43), post.getHeader("Authorization"))
            assertEquals(batch, post.getHeader("X-Annotation-Batch"))
            assertEquals("42", post.getHeader("X-Annotation-Asset-Id"))
            assertEquals(mutation, post.getHeader("X-Annotation-Mutation-Id"))
            assertArrayEquals(wav, post.body.readByteArray())
            f.server.enqueue(json(item("0".repeat(64))).setResponseCode(201))
            assertEquals(FailureKind.INVALID_RESPONSE,
                failure { api.postUploadAudioAnnotation(token, "family-a", request) }.kind)
        }
    }
    @Test fun originalAnnotationAudioUsesOnlyAuthenticatedScopedNoStoreGet() = runBlocking {
        TlsFixture().use { f ->
            val api = HttpsPhotoHouseApi(f.origin, f.client, protectedNativeV2Enabled = true, uploadEnabled = true)
            val wav = syntheticAnnotationWav()
            val batch = "a".repeat(32)
            val info = UploadAnnotationsWire.audioInfo(UploadAudioAnnotationRequest(batch, "42", "en", "yes",
                "123e4567-e89b-12d3-a456-426614174000", wav))
            val item = """{"id":"annotation-audio","scope":"item","asset_id":"42","batch":"$batch","library_id":"family-a","author_id":"member-1","kind":"audio","original_text":null,"audio_url":"/upload-annotations/annotation-audio/audio?library=family-a&asset_id=42","mime":"audio/wav","duration_ms":${info.durationMs},"sha256":"${info.sha256}","language":"en","local_processing_consent":"yes","created_at":1720000000,"derivation":{"revision":1,"state":"waiting","transcript":null,"polished_text":null,"provider":null,"model":null,"error_code":null},"tags":[]}"""
            val annotation = UploadAnnotationsWire.parseItem(item.toByteArray())
            f.server.enqueue(MockResponse().setHeader("Content-Type", "audio/wav")
                .setHeader("Cache-Control", "private, no-store").setBody(okio.Buffer().write(wav)))

            assertArrayEquals(wav, api.uploadAnnotationAudio(token, "family-a", annotation))
            val request = f.server.takeRequest()
            assertEquals("GET", request.method)
            assertEquals("/upload-annotations/annotation-audio/audio?library=family-a&asset_id=42", request.path)
            assertEquals("Bearer ${"T".repeat(43)}", request.getHeader("Authorization"))
            assertEquals("audio/wav", request.getHeader("Accept"))
            assertEquals("no-store", request.getHeader("Cache-Control"))
            assertEquals("identity", request.getHeader("Accept-Encoding"))
            assertNull(request.getHeader("Cookie"))
        }
    }

    @Test fun originalAnnotationAudioRejectsAlteredReferenceAndMismatchedBytes() = runBlocking {
        TlsFixture().use { f ->
            val api = HttpsPhotoHouseApi(f.origin, f.client, protectedNativeV2Enabled = true, uploadEnabled = true)
            val wav = syntheticAnnotationWav()
            val batch = "a".repeat(32)
            val info = UploadAnnotationsWire.audioInfo(UploadAudioAnnotationRequest(batch, "42", "en", "yes",
                "123e4567-e89b-12d3-a456-426614174000", wav))
            val item = """{"id":"annotation-audio","scope":"item","asset_id":"42","batch":"$batch","library_id":"family-a","author_id":"member-1","kind":"audio","original_text":null,"audio_url":"/upload-annotations/annotation-audio/audio?library=family-a&asset_id=42","mime":"audio/wav","duration_ms":${info.durationMs},"sha256":"${info.sha256}","language":"en","local_processing_consent":"yes","created_at":1720000000,"derivation":{"revision":1,"state":"waiting","transcript":null,"polished_text":null,"provider":null,"model":null,"error_code":null},"tags":[]}"""
            val annotation = UploadAnnotationsWire.parseItem(item.toByteArray())
            val altered = annotation.copy(audioUrl = "https://public.invalid/${annotation.id}.wav")
            assertEquals(FailureKind.INVALID_INPUT, failure { api.uploadAnnotationAudio(token, "family-a", altered) }.kind)
            assertEquals(0, f.server.requestCount)

            f.server.enqueue(MockResponse().setHeader("Content-Type", "audio/wav")
                .setHeader("Cache-Control", "no-store").setBody(okio.Buffer().write(wav.copyOf().also { it[50] = (it[50].toInt() xor 1).toByte() })))
            assertEquals(FailureKind.INVALID_RESPONSE, failure { api.uploadAnnotationAudio(token, "family-a", annotation) }.kind)
        }
    }

    @Test fun originalAnnotationAudioRejectsWrongContentTypeOversizeAndRedirects() = runBlocking {
        TlsFixture().use { f ->
            val api = HttpsPhotoHouseApi(f.origin, f.client, protectedNativeV2Enabled = true, uploadEnabled = true)
            val wav = syntheticAnnotationWav()
            val batch = "a".repeat(32)
            val info = UploadAnnotationsWire.audioInfo(UploadAudioAnnotationRequest(batch, "42", "en", "yes",
                "123e4567-e89b-12d3-a456-426614174000", wav))
            val item = """{"id":"annotation-audio","scope":"item","asset_id":"42","batch":"$batch","library_id":"family-a","author_id":"member-1","kind":"audio","original_text":null,"audio_url":"/upload-annotations/annotation-audio/audio?library=family-a&asset_id=42","mime":"audio/wav","duration_ms":${info.durationMs},"sha256":"${info.sha256}","language":"en","local_processing_consent":"yes","created_at":1720000000,"derivation":{"revision":1,"state":"waiting","transcript":null,"polished_text":null,"provider":null,"model":null,"error_code":null},"tags":[]}"""
            val annotation = UploadAnnotationsWire.parseItem(item.toByteArray())
            for (response in listOf(
                MockResponse().setHeader("Content-Type", "application/octet-stream").setBody(okio.Buffer().write(wav)),
                MockResponse().setHeader("Content-Type", "audio/wav").setBody(okio.Buffer().write(wav)),
                MockResponse().setHeader("Content-Type", "audio/wav").setHeader("Content-Length", UploadAnnotationsWire.MAX_AUDIO_BYTES + 1),
                MockResponse().setResponseCode(302).setHeader("Location", "https://public.invalid/audio.wav"),
            )) {
                f.server.enqueue(response)
                assertTrue(failure { api.uploadAnnotationAudio(token, "family-a", annotation) }.kind in
                    setOf(FailureKind.INVALID_RESPONSE, FailureKind.TOO_LARGE, FailureKind.HTTP))
            }
            assertEquals(4, f.server.requestCount)
        }
    }
    @Test fun preparedBrowseSendsOnlyTheOptInScopedFilter() = runBlocking {
        TlsFixture().use { f ->
            val disabled = HttpsPhotoHouseApi(f.origin, f.client, protectedNativeV2Enabled = true, mediaFilterEnabled = true)
            assertTrue(runCatching { disabled.gallery(token, "family", 1, GalleryMedia.PREPARED_VIDEOS) }.isFailure)
            assertEquals(0, f.server.requestCount)
            val api = HttpsPhotoHouseApi(f.origin, f.client, protectedNativeV2Enabled = true,
                mediaFilterEnabled = true, preparedVideoEnabled = true, preparedBrowseEnabled = true)
            f.server.enqueue(json("""{"library_id":"family","page":1,"page_size":50,"total":0,"originals_allowed":false,"items":[]}"""))
            assertEquals(0, api.gallery(token, "family", 1, GalleryMedia.PREPARED_VIDEOS).total)
            val request = f.server.takeRequest()
            assertEquals("prepared_video", request.requestUrl!!.queryParameter("media"))
            assertEquals("family", request.requestUrl!!.queryParameter("library"))
            assertEquals("Bearer " + "T".repeat(43), request.getHeader("Authorization"))
            assertEquals(1, f.server.requestCount)
        }
    }

    @Test fun absentRetryAfterAllowsTransientReadRecoveryButRetainsRateLimitDefault() = runBlocking {
        TlsFixture().use { f ->
            for (status in listOf(502, 503, 504, 429)) {
                f.server.enqueue(MockResponse().setResponseCode(status))
                val error = failure { f.api.session(token) }
                assertEquals(if (status == 429) 5000L else 0L, error.retryAfterMillis)
            }
            f.server.enqueue(MockResponse().setResponseCode(503).setHeader("Retry-After", "invalid"))
            assertEquals(5000L, failure { f.api.session(token) }.retryAfterMillis)
            assertEquals(5, f.server.requestCount) // the transport itself never retries requests
        }
    }

    @Test fun optimizedPhotoUsesProtectedDisplayRouteAndNeverOriginalFallback() = runBlocking {
        TlsFixture().use { f ->
            val api = HttpsPhotoHouseApi(f.origin, f.client, photoDeliveryEnabled = true)
            f.server.enqueue(MockResponse().setHeader("Content-Type", "image/jpeg").setBody("synthetic"))
            assertEquals("synthetic", api.displayPhoto(token, "family", "1").toString(Charsets.UTF_8))
            val request = f.server.takeRequest()
            assertEquals("/assets/1/display?library=family", request.path)
            assertEquals("Bearer " + "T".repeat(43), request.getHeader("Authorization"))
            f.server.enqueue(MockResponse().setResponseCode(503))
            assertEquals(503, failure { api.displayPhoto(token, "family", "1") }.status)
            assertEquals(2, f.server.requestCount)
        }
    }

    @Test fun videoRangesAuthenticateEverySeekWithStrictSameOriginHeaders() = runBlocking {
        TlsFixture().use { f ->
            f.server.enqueue(range()); f.server.enqueue(range("ij", "bytes 8-9/10"))
            assertEquals(10L, f.api.videoRange(token, "family", "1", 0, 4).total)
            assertEquals("ij", f.api.videoRange(token, "family", "1", 8, 4).bytes.toString(Charsets.UTF_8))
            for (expected in listOf("bytes=0-3", "bytes=8-11")) {
                val request = f.server.takeRequest()
                assertEquals("/assets/1/media?library=family", request.path)
                assertEquals(expected, request.getHeader("Range"))
                assertEquals("identity", request.getHeader("Accept-Encoding"))
                assertEquals("no-store", request.getHeader("Cache-Control"))
                assertEquals(1, request.headers.values("Authorization").size)
                assertNull(request.getHeader("Cookie")); assertNull(request.getHeader("If-Range"))
            }
            for (start in listOf(-1L, HttpsPhotoHouseApi.VIDEO_FILE_LIMIT, Long.MAX_VALUE))
                assertTrue(runCatching { f.api.videoRange(token, "family", "1", start, 4) }.isFailure)
            assertTrue(runCatching { f.api.videoRange(token, "family", "1", 0, 262145) }.isFailure)
            assertEquals(2, f.server.requestCount)
        }
    }
    @Test fun videoRejectsIgnoredMalformedCompressedOversizedAndTruncatedRanges() = runBlocking {
        TlsFixture().use { f ->
            val invalid = listOf(range().setResponseCode(200), range().removeHeader("Content-Range"),
                range(header = "bytes 1-4/10"), range(header = "bytes 0-4/10"), range(header = "bytes 0-3/*"),
                range(header = "bytes 0-3/0"), range(header = "bytes 0-3/99999999999999999999"),
                range().setHeader("Content-Encoding", "gzip"), range().setHeader("Content-Type", "text/html"),
                range("abc"), range("abcde").setChunkedBody("abcde", 1))
            for (response in invalid) {
                f.server.enqueue(response)
                assertTrue(failure { f.api.videoRange(token, "family", "1", 0, 4) }.kind in setOf(FailureKind.INVALID_RESPONSE, FailureKind.TOO_LARGE))
            }
            f.server.enqueue(range(header = "bytes 0-3/${HttpsPhotoHouseApi.VIDEO_FILE_LIMIT + 1}"))
            assertEquals(FailureKind.TOO_LARGE, failure { f.api.videoRange(token, "family", "1", 0, 4) }.kind)
            f.server.enqueue(range().setHeader("Content-Length", 5))
            assertEquals(FailureKind.TOO_LARGE, failure { f.api.videoRange(token, "family", "1", 0, 4) }.kind)
        }
    }
    @Test fun multiGigabyteSeeksUseLongOffsetsWithoutDownloadingTheFile() = runBlocking {
        TlsFixture().use { f ->
            val total = 8193114694L
            for (start in listOf(0L, 4294967296L, total - 4)) {
                f.server.enqueue(range("abcd", "bytes $start-${start + 3}/$total"))
                val result = f.api.videoRange(token, "family", "1", start, 4)
                assertEquals(total, result.total); assertEquals(start, result.start)
                assertEquals(4, result.bytes.size)
                val request = f.server.takeRequest()
                assertEquals("bytes=$start-${start + 3}", request.getHeader("Range"))
                assertEquals(1, request.headers.values("Authorization").size)
            }
            assertEquals(3, f.server.requestCount)
        }
    }
    @Test fun videoDenialRateLimitRedirectAndCancellationHaveNoAutomaticRetry() = runBlocking {
        TlsFixture().use { f ->
            for (status in listOf(401, 403, 404, 416, 429, 503, 302)) {
                f.server.enqueue(MockResponse().setResponseCode(status).setHeader("Retry-After", "7").setHeader("Location", "https://other.invalid/video"))
                val error = failure { f.api.videoRange(token, "family", "1", 0, 4) }
                assertEquals(status, error.status)
                if (status == 429) assertEquals(7000L, error.retryAfterMillis)
                assertNotNull(f.server.takeRequest(5, TimeUnit.SECONDS))
            }
            assertEquals(7, f.server.requestCount)
            f.server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            val job = launch(Dispatchers.IO) { f.api.videoRange(token, "family", "1", 0, 4) }
            assertNotNull(f.server.takeRequest(5, TimeUnit.SECONDS)); withTimeout(2000) { job.cancelAndJoin() }
        }
    }
    @Test fun originalUsesFixedAuthenticatedNoStoreRouteAndAcceptsExactBudget() = runBlocking {
        TlsFixture().use { f ->
            f.server.enqueue(MockResponse().setHeader("Content-Type", "image/jpeg").setBody("x".repeat(HttpsPhotoHouseApi.ORIGINAL_LIMIT)))
            assertEquals(HttpsPhotoHouseApi.ORIGINAL_LIMIT, f.api.originalPhoto(token, "family", "1").size)
            val request = f.server.takeRequest()
            assertEquals("/assets/1/media?library=family", request.path); assertEquals("GET", request.method)
            assertEquals(listOf("Bearer ${"T".repeat(43)}"), request.headers.values("Authorization"))
            assertEquals("no-store", request.getHeader("Cache-Control"))
            assertEquals("image/jpeg, image/png, image/webp", request.getHeader("Accept"))
            assertNull(request.getHeader("Range")); assertNull(request.getHeader("Cookie"))
            assertTrue(runCatching { f.api.originalPhoto(token, "family", "../collect") }.isFailure)
            assertEquals(1, f.server.requestCount)
        }
    }
    @Test fun originalRejectsKnownAndUnknownOversizeAndIncompleteOrNonImageBodies() = runBlocking {
        TlsFixture().use { f ->
            f.server.enqueue(MockResponse().setBody("x").setHeader("Content-Type", "image/png")
                .setHeader("Content-Length", HttpsPhotoHouseApi.ORIGINAL_LIMIT + 1))
            assertEquals(FailureKind.TOO_LARGE, failure { f.api.originalPhoto(token, "family", "1") }.kind)
            f.server.enqueue(MockResponse().setHeader("Content-Type", "image/png")
                .setChunkedBody("x".repeat(HttpsPhotoHouseApi.ORIGINAL_LIMIT + 1), 8192))
            assertEquals(FailureKind.TOO_LARGE, failure { f.api.originalPhoto(token, "family", "1") }.kind)
            for (response in listOf(
                MockResponse().setResponseCode(206).setHeader("Content-Type", "image/png").setBody("partial"),
                MockResponse().setHeader("Content-Type", "image/svg+xml").setBody("<svg/>"),
                MockResponse().setHeader("Content-Type", "video/mp4").setBody("not a photo"),
                MockResponse().setHeader("Content-Type", "image/png").setBody(""))) {
                f.server.enqueue(response)
                assertEquals(FailureKind.INVALID_RESPONSE, failure { f.api.originalPhoto(token, "family", "1") }.kind)
            }
        }
    }
    @Test fun originalDenialAndRedirectAreNeverFollowedOrRetried() = runBlocking {
        TlsFixture().use { f ->
            for (status in listOf(401, 403, 404, 302)) {
                f.server.enqueue(MockResponse().setResponseCode(status).setHeader("Location", "https://other.invalid/collect"))
                assertEquals(status, failure { f.api.originalPhoto(token, "family", "1") }.status)
            }
            assertEquals(4, f.server.requestCount)
            f.server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            val task = launch(Dispatchers.Default) { f.api.originalPhoto(token, "family", "1"); fail("Cancelled original returned") }
            repeat(5) { assertNotNull(f.server.takeRequest(5, TimeUnit.SECONDS)) }
            withTimeout(2000) { task.cancelAndJoin() }; assertTrue(task.isCancelled)
        }
    }
    @Test fun nativeLoginAndRegistrationSendExactFieldsWithoutAmbientCredentials() = runBlocking {
        TlsFixture().use { f ->
            repeat(2) { f.server.enqueue(json("""{"expires_in":86400,"access_token":"${"T".repeat(43)}","token_type":"Bearer"}""").setHeader("Set-Cookie", "ambient=never")) }
            f.api.login("+1 (202) 555-0123", password)
            f.api.register("+12025550123", password, "synthetic-invitation")
            val login = f.server.takeRequest()
            assertEquals("POST", login.method); assertEquals("/auth/login", login.path)
            val body = Wire.json.parseToJsonElement(login.body.readUtf8()).jsonObject
            assertEquals(setOf("phone", "password", "transport"), body.keys)
            assertEquals("native", body.getValue("transport").jsonPrimitive.content)
            assertEquals("+12025550123", body.getValue("phone").jsonPrimitive.content)
            val register = f.server.takeRequest()
            assertEquals("/auth/register", register.path)
            assertEquals(setOf("phone", "password", "code", "transport"), Wire.json.parseToJsonElement(register.body.readUtf8()).jsonObject.keys)
            for (request in listOf(login, register)) for (header in listOf("Authorization", "Cookie", "Origin")) assertNull(request.getHeader(header))
        }
    }
    @Test fun protectedSessionUsesOneHeaderAndDoesNotPersistCookie() = runBlocking {
        TlsFixture().use { f ->
            repeat(2) { f.server.enqueue(json(session).setHeader("Set-Cookie", "secret=discard")) }
            repeat(2) { assertEquals("synthetic-account", f.api.session(token).account_id) }
            repeat(2) {
                val request = f.server.takeRequest()
                assertEquals(listOf("Bearer ${"T".repeat(43)}"), request.headers.values("Authorization"))
                assertEquals("/auth/session", request.path); assertNull(request.getHeader("Cookie"))
                assertEquals("no-store", request.getHeader("Cache-Control"))
            }
        }
    }
    @Test fun frozenBrowsingAndMutationResponsesUseExactScopedRoutes() = runBlocking {
        val cases = Wire.json.parseToJsonElement(javaClass.getResource("/fixtures.json")!!.readText()).jsonObject.getValue("cases").jsonArray
        fun body(id: String) = cases.single { it.jsonObject.getValue("id").jsonPrimitive.content == id }.jsonObject.getValue("body").toString()
        TlsFixture().use { f ->
            for (id in listOf("gallery", "detail", "captions-bilingual", "accept-second-library", "logout")) f.server.enqueue(json(body(id)))
            assertEquals(2, f.api.gallery(token, "family-a", 1).items.size)
            assertEquals("101", f.api.detail(token, "family-a", "101").asset.id)
            assertEquals("Synthetic hillside. 合成山景。", f.api.captions(token, "family-a", "101").items.single().text)
            f.api.acceptInvitation(token, "synthetic-invitation"); f.api.logout(token)
            for (path in listOf("/assets?library=family-a&page=1&page_size=50", "/assets/detail/101?library=family-a", "/assets/101/captions?library=family-a")) {
                val request = f.server.takeRequest(); assertEquals(path, request.path); assertEquals("GET", request.method)
            }
            val accept = f.server.takeRequest(); assertEquals("/auth/invitations/accept", accept.path); assertEquals("POST", accept.method)
            assertEquals("""{"code":"synthetic-invitation"}""", accept.body.readUtf8())
            val logout = f.server.takeRequest(); assertEquals("/auth/logout", logout.path); assertEquals("POST", logout.method); assertEquals("{}", logout.body.readUtf8())
        }
    }
    @Test fun redirectsNeverFollowEvenOnSameOrigin() = runBlocking {
        TlsFixture().use { f ->
            f.server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "/collect"))
            assertEquals(302, failure { f.api.session(token) }.status)
            assertEquals(1, f.server.requestCount)
        }
    }
    @Test fun platformTrustRejectsSelfSignedServerAndHostnameValidationRemainsEnabled() = runBlocking {
        TlsFixture().use { f ->
            assertEquals(FailureKind.TLS, failure { HttpsPhotoHouseApi(f.origin).session(token) }.kind)
            assertEquals(0, f.server.requestCount)
        }
        TlsFixture("wrong.invalid").use { f ->
            assertEquals(FailureKind.TLS, failure { f.api.session(token) }.kind)
            assertEquals(0, f.server.requestCount)
        }
    }
    @Test fun statusesDoNotDependOnErrorBodyAndNeverAutoRetry() = runBlocking {
        TlsFixture().use { f ->
            for (status in listOf(401, 403, 422, 429, 503)) {
                f.server.enqueue(MockResponse().setResponseCode(status).setHeader("Retry-After", "7").setBody("private diagnostic deliberately not parsed"))
                val error = failure { f.api.session(token) }
                assertEquals(status, error.status)
                assertEquals(if (status == 429 || status in 502..504) 7000L else 0L, error.retryAfterMillis)
                assertFalse(error.toString().contains("private diagnostic"))
            }
            assertEquals(5, f.server.requestCount)
        }
    }
    @Test fun boundedStreamingAndStrictJsonRejectMalformedResponses() = runBlocking {
        TlsFixture().use { f ->
            f.server.enqueue(json(" ".repeat(HttpsPhotoHouseApi.JSON_LIMIT + 1)).setChunkedBody(" ".repeat(HttpsPhotoHouseApi.JSON_LIMIT + 1), 8192))
            assertEquals(FailureKind.TOO_LARGE, failure { f.api.session(token) }.kind)
            f.server.enqueue(json(session.dropLast(1) + ",\"unexpected\":true}"))
            assertEquals(FailureKind.INVALID_RESPONSE, failure { f.api.session(token) }.kind)
            f.server.enqueue(MockResponse().setHeader("Content-Type", "text/html").setBody(session))
            assertEquals(FailureKind.INVALID_RESPONSE, failure { f.api.session(token) }.kind)
        }
    }
    @Test fun missingThumbnailIsPlaceholderWithNoOriginalFallback() = runBlocking {
        TlsFixture().use { f ->
            f.server.enqueue(MockResponse().setResponseCode(404))
            assertNull(f.api.thumbnail(token, "family", asset))
            assertEquals("/assets/1/thumbnail?library=family", f.server.takeRequest().path)
            assertEquals(1, f.server.requestCount)
        }
    }
    @Test fun arbitraryThumbnailUrlsNeverSendBearer() = runBlocking {
        TlsFixture().use { f ->
            for (url in listOf("https://other.invalid/collect", "//other.invalid/collect", "/assets/1/media?library=family", "/assets/1/thumbnail?library=other", "/assets/2/thumbnail?library=family")) {
                try { f.api.thumbnail(token, "family", asset.copy(thumbnail_url = url)); fail("Accepted $url") } catch (_: IllegalArgumentException) { }
            }
            assertEquals(0, f.server.requestCount)
        }
    }
    @Test fun thumbnailMimeAndStreamingSizeAreBounded() = runBlocking {
        TlsFixture().use { f ->
            f.server.enqueue(MockResponse().setHeader("Content-Type", "image/svg+xml").setBody("<svg/>"))
            assertEquals(FailureKind.INVALID_RESPONSE, failure { f.api.thumbnail(token, "family", asset) }.kind)
            f.server.enqueue(MockResponse().setHeader("Content-Type", "image/png").setChunkedBody("x".repeat(HttpsPhotoHouseApi.IMAGE_LIMIT + 1), 8192))
            assertEquals(FailureKind.TOO_LARGE, failure { f.api.thumbnail(token, "family", asset) }.kind)
        }
    }
    @Test fun cancelStopsOutstandingTransport() = runBlocking {
        TlsFixture().use { f ->
            f.server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            val task = launch(Dispatchers.Default) { f.api.session(token); fail("Cancelled request returned") }
            assertNotNull(f.server.takeRequest(5, TimeUnit.SECONDS))
            withTimeout(2000) { task.cancelAndJoin() }
            assertTrue(task.isCancelled); assertEquals(1, f.server.requestCount)
        }
    }
    @Test fun requestLimitsRejectOversizedInvitationBeforeNetwork() = runBlocking {
        TlsFixture().use { f ->
            assertEquals(FailureKind.INVALID_INPUT, failure { f.api.register("+12025550123", password, "x".repeat(3000)) }.kind)
            assertEquals(0, f.server.requestCount)
        }
    }
    @Test fun uploadHistoryUsesProtectedBearerAndStrictPageContract() = runBlocking {
        TlsFixture().use { f ->
            val api = HttpsPhotoHouseApi(f.origin, f.client, protectedNativeV2Enabled = true, uploadEnabled = true)
            f.server.enqueue(json("""{"page":1,"page_size":10,"total":1,"items":[{"asset_id":"901","created_at":1760000000,"bytes":1234,"kind":"image","state":"available","library_id":"family"}]}"""))
            val page = api.uploadHistory(token, 1)
            assertEquals("901", page.items.single().assetId)
            val request = f.server.takeRequest()
            assertEquals("/uploads?page=1", request.path)
            assertEquals("Bearer " + "T".repeat(43), request.getHeader("Authorization"))
            for (status in listOf(403, 404, 503)) {
                f.server.enqueue(MockResponse().setResponseCode(status))
                assertEquals(status, failure { api.uploadHistory(token, 1) }.status)
            }
        }
    }
    @Test fun originAdmissionAndOpaqueTokenValidation() {
        for (origin in listOf("http://localhost", "https://u:p@example.invalid", "https://example.invalid/path", "https://example.invalid?x=1", "https://example.invalid#x", " https://example.invalid", "https://example.invalid\\path")) {
            assertTrue(runCatching { TrustedOrigin.parse(origin) }.isFailure)
        }
        assertEquals("+12025550123", Admission.phone("+1 (202) 555-0123"))
        assertTrue(runCatching { Admission.phone("12025550123") }.isFailure)
        Admission.password("😀".repeat(15))
        assertTrue(runCatching { Admission.password("😀".repeat(14)) }.isFailure)
        assertTrue(runCatching { Bearer.from(SessionToken(86400, "F".repeat(43), "Bearer")) }.isFailure)
        assertFalse(token.toString().contains("T".repeat(43)))
        assertEquals(9000L, retryAfterMillis("9"))
        assertEquals(5000L, retryAfterMillis("invalid"))
        assertEquals(1000L, retryAfterMillis("Thu, 01 Jan 1970 00:00:01 GMT", 0))
    }
}
