package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import okhttp3.OkHttpClient
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test
import java.io.BufferedReader
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.PosixFilePermissions
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Opt-in tests against the actual protected backend; no canned HTTP responses. */
class BackendIntegrationTest {
    private val member = "+12025550102"
    private val invited = "+12025550103"
    private val password = "Synthetic family passphrase!"

    private class Backend : AutoCloseable {
        private val directory = Files.createTempDirectory("photohouse-android-tls-")
        private val readerExecutor = Executors.newSingleThreadExecutor()
        private lateinit var process: Process
        private lateinit var reader: BufferedReader
        private lateinit var client: OkHttpClient
        lateinit var api: HttpsPhotoHouseApi
            private set
        init {
            try {
                Files.writeString(directory.resolve("synthetic-test-only"), "ephemeral test storage only")
                val certificate = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
                val pem = directory.resolve("certificate.pem")
                val key = directory.resolve("key.pem")
                Files.writeString(pem, certificate.certificatePem())
                Files.writeString(key, certificate.privateKeyPkcs8Pem())
                Files.setPosixFilePermissions(key, PosixFilePermissions.fromString("rw-------"))
                val builder = ProcessBuilder(requireNotNull(System.getenv("PHOTOHOUSE_TEST_PYTHON")), "-I", "-B",
                    requireNotNull(System.getenv("PHOTOHOUSE_TEST_SERVER")), "--source", requireNotNull(System.getenv("PHOTOHOUSE_TEST_BACKEND")),
                    "--certificate", pem.toString(), "--key", key.toString())
                    .directory(directory.toFile()).redirectError(directory.resolve("server-error.log").toFile())
                builder.environment().clear()
                // Isolated Python receives no backend/runtime/proxy/credential environment.
                builder.environment()["PATH"] = "/usr/bin:/bin"
                process = builder.start()
                reader = process.inputStream.bufferedReader()
                val ready = readReply()
                check(ready.getValue("ready").jsonPrimitive.boolean)
                val port = ready.getValue("port").jsonPrimitive.int
                require(port in 1..65535)
                val trust = HandshakeCertificates.Builder().addTrustedCertificate(certificate.certificate).build()
                client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
                api = HttpsPhotoHouseApi(TrustedOrigin.parse("https://localhost:$port"), client)
            } catch (e: Exception) { close(); throw IllegalStateException("Synthetic backend setup failed; no deployment was attempted", e) }
        }
        private fun readReply(): JsonObject {
            return readerExecutor.submit<JsonObject> {
                val line = StringBuilder()
                while (true) {
                    val c = reader.read()
                    check(c >= 0) { "Synthetic backend ended before replying" }
                    if (c == '\n'.code) break
                    check(line.length < 4096) { "Oversized synthetic control reply" }
                    line.append(c.toChar())
                }
                Wire.json.parseToJsonElement(line.toString()).jsonObject
            }.get(30, TimeUnit.SECONDS)
        }
        fun control(command: String): JsonObject {
            require(command.matches(Regex("[a-z-]+")))
            process.outputStream.write("{\"command\":\"$command\"}\n".toByteArray())
            process.outputStream.flush()
            return readReply().also { check(it.getValue("ok").jsonPrimitive.boolean) }
        }
        override fun close() {
            if (::process.isInitialized) {
                runCatching { process.outputStream.close() } // EOF requests orderly cleanup.
                if (!process.waitFor(5, TimeUnit.SECONDS)) {
                    process.destroy()
                    if (!process.waitFor(2, TimeUnit.SECONDS)) process.destroyForcibly().waitFor()
                }
            }
            if (::reader.isInitialized) reader.close()
            readerExecutor.shutdownNow()
            if (::client.isInitialized) { client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll() }
            Files.walk(directory).use { paths -> paths.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
            check(!Files.exists(directory)) { "Synthetic storage was not cleaned up" }
        }
    }
    private suspend fun failure(block: suspend () -> Unit): ApiFailure {
        try { block() } catch (e: ApiFailure) { return e }
        throw AssertionError("Expected backend denial")
    }
    @Test fun realVideoRangesSeekAndReauthorizeAfterOriginalPermissionRevocation() = runBlocking {
        Backend().use { backend ->
            backend.control("use-synthetic-video")
            val api = backend.api; val token = Bearer.from(api.login(member, password))
            assertEquals("video", api.detail(token, "family-a", "102").asset.kind)
            assertEquals(401, failure { api.videoRange(token, "family-a", "102", 0, 32) }.status)
            backend.control("allow-originals")
            val first = api.videoRange(token, "family-a", "102", 0, 32)
            assertEquals("ftyp", first.bytes.copyOfRange(4, 8).toString(Charsets.US_ASCII))
            assertTrue(first.total > HttpsPhotoHouseApi.VIDEO_CHUNK_LIMIT)
            val tail = api.videoRange(token, "family-a", "102", first.total - 10, 32)
            assertEquals(10, tail.bytes.size); assertEquals(first.total, tail.total)
            assertEquals(401, failure { api.videoRange(token, "family-b", "102", 0, 32) }.status)
            val errors = mutableListOf<Exception>()
            val reader = VideoReader({ start, length -> api.videoRange(token, "family-a", "102", start, length) }, Long.MAX_VALUE, { 0 }) { errors += it }
            reader.use {
                assertEquals(first.total, it.size())
                assertEquals(262144, it.readAt(0, ByteArray(262144), 0, 262144))
                backend.control("deny-originals")
                assertTrue(runCatching { it.readAt(300000, ByteArray(16), 0, 16) }.isFailure)
                assertTrue(it.isClosed); assertEquals(401, (errors.single() as ApiFailure).status)
                assertTrue(api.session(token).memberships.single().available)
            }
        }
    }
    @Test fun realLoginBrowsingThumbnailAndAcknowledgedLogout() = runBlocking {
        Backend().use { backend ->
            val api = backend.api
            val token = Bearer.from(api.login(member, password))
            val session = api.session(token)
            assertEquals(member, session.phone_login)
            assertEquals(listOf("family-a"), session.memberships.filter { it.available }.map { it.library_id })
            val gallery = api.gallery(token, "family-a", 1)
            assertEquals(listOf("102", "101"), gallery.items.map { it.id }); assertFalse(gallery.originals_allowed)
            assertTrue(api.gallery(token, "family-a", 2).items.isEmpty())
            val detail = api.detail(token, "family-a", "101")
            assertEquals("101", detail.asset.id)
            assertEquals("<b>Synthetic 原文</b>", api.captions(token, "family-a", "101").items.single().text)
            val image = requireNotNull(api.thumbnail(token, "family-a", detail.asset))
            assertTrue(image.size in 1..HttpsPhotoHouseApi.IMAGE_LIMIT)
            assertEquals(0xff, image[0].toInt() and 0xff); assertEquals(0xd8, image[1].toInt() and 0xff)
            assertEquals(401, failure { api.originalPhoto(token, "family-a", "101") }.status)
            backend.control("allow-originals")
            assertTrue(api.detail(token, "family-a", "101").originals_allowed)
            val original = api.originalPhoto(token, "family-a", "101")
            assertTrue(original.isNotEmpty()); assertEquals(0xff, original[0].toInt() and 0xff)
            assertEquals(401, failure { api.originalPhoto(token, "family-b", "201") }.status)
            backend.control("deny-originals")
            assertEquals(401, failure { api.originalPhoto(token, "family-a", "101") }.status)
            api.logout(token)
            assertEquals(401, failure { api.session(token) }.status)
        }
    }
    @Test fun realInvitedRegistrationAndSecondLibraryAcceptance() = runBlocking {
        Backend().use { backend ->
            val api = backend.api
            assertEquals(401, failure { api.register(invited, password, "invalid-synthetic-code") }.status)
            val code = backend.control("invite-new").getValue("code").jsonPrimitive.content
            val token = Bearer.from(api.register(invited, password, code))
            val first = api.session(token).memberships.single()
            assertEquals("viewer", first.role); assertEquals("family-a", first.library_id); assertEquals(0, first.originals)
            assertEquals(401, failure { api.gallery(token, "family-b", 1) }.status)
            val secondCode = backend.control("invite-second-library").getValue("code").jsonPrimitive.content
            api.acceptInvitation(token, secondCode)
            assertEquals(setOf("family-a", "family-b"), api.session(token).memberships.filter { it.available }.map { it.library_id }.toSet())
            assertEquals(listOf("201"), api.gallery(token, "family-b", 1).items.map { it.id })
        }
    }
    @Test fun foreignDeletedUnmappedAndMissingReadsAreUniformDenials() = runBlocking {
        Backend().use { backend ->
            val api = backend.api; val token = Bearer.from(api.login(member, password))
            for (id in listOf("103", "201", "999", "123456")) {
                assertEquals(401, failure { api.detail(token, "family-a", id) }.status)
                assertEquals(401, failure { api.captions(token, "family-a", id) }.status)
            }
            assertEquals(member, api.session(token).phone_login)
            assertEquals(401, failure { api.gallery(token, "family-b", 1) }.status)
        }
    }
    @Test fun missingPreviewAndUnavailableStorageRemainDistinct() = runBlocking {
        Backend().use { backend ->
            val api = backend.api; val token = Bearer.from(api.login(member, password))
            val asset = api.detail(token, "family-a", "101").asset
            backend.control("remove-thumbnail")
            assertNull(api.thumbnail(token, "family-a", asset))
            backend.control("storage-unavailable")
            assertEquals(503, failure { api.session(token) }.status)
            assertEquals(503, failure { api.gallery(token, "family-a", 1) }.status)
        }
    }
    @OptIn(DelicateCoroutinesApi::class, ExperimentalCoroutinesApi::class)
    @Test fun realMembershipRevocationAndSessionExpiryClearConnectedState() {
        newSingleThreadContext("synthetic-ui").use { dispatcher -> runBlocking(dispatcher) {
            Backend().use { backend ->
                val scope = CoroutineScope(SupervisorJob() + dispatcher)
                try {
                    val store = ConnectedStore(backend.api, scope)
                    suspend fun settle() { withTimeout(10000) { while (store.state.value.busy) delay(10) } }
                    store.authenticate(member, password); settle(); assertNotNull(store.state.value.session)
                    store.selectLibrary("family-a"); settle(); assertTrue(store.cachedBytes > 0)
                    val first = store.state.value.gallery!!.items.first()
                    store.openAsset(first); settle()
                    assertEquals("102", store.state.value.detail?.asset?.id)
                    store.adjacentPhoto(1); settle()
                    assertEquals("101", store.state.value.detail?.asset?.id)
                    assertEquals("<b>Synthetic 原文</b>", store.state.value.captions?.items?.single()?.text)
                    store.backToPhotos(); settle(); assertEquals(1, store.state.value.gallery?.page)
                    backend.control("allow-originals")
                    store.openAsset(first); settle()
                    store.openOriginalPhoto(); settle()
                    assertTrue(store.state.value.originalPhoto?.isNotEmpty() == true)
                    store.closeOriginalPhoto(); assertNull(store.state.value.originalPhoto)
                    backend.control("deny-originals")
                    store.openOriginalPhoto(); settle()
                    assertNull(store.state.value.originalPhoto); assertNull(store.state.value.detail)
                    assertTrue(store.hasSession)
                    store.selectLibrary("family-a"); settle(); store.openAsset(first); settle()
                    backend.control("revoke-member")
                    store.adjacentPhoto(1); settle()
                    assertTrue(store.hasSession); assertNull(store.state.value.gallery); assertEquals(0, store.cachedBytes)
                    assertNull(store.state.value.detail); assertNull(store.state.value.photoNavigation)
                    assertFalse(store.state.value.session!!.memberships.single().available)
                    store.background(); assertTrue(store.state.value.covered); assertNull(store.state.value.session)
                    backend.control("expire-sessions")
                    store.foreground(); settle()
                    assertFalse(store.hasSession); assertEquals(Message.SESSION_ENDED, store.state.value.problem?.message)
                } finally { scope.cancel() }
            }
        } }
    }
    @Test fun actualAdmissionCooldownIsExposedAndExpiresOnServerClock() = runBlocking {
        Backend().use { backend ->
            repeat(6) { assertEquals(401, failure { backend.api.login(member, "Incorrect synthetic password") }.status) }
            val limited = failure { backend.api.login(member, password) }
            assertEquals(429, limited.status); assertTrue(limited.retryAfterMillis > 0)
            backend.control("advance-admission-window")
            val token = Bearer.from(backend.api.login(member, password))
            assertEquals(member, backend.api.session(token).phone_login)
        }
    }
}
