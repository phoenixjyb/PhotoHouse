package dev.photohouse.home

import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.serialization.json.*
import okhttp3.OkHttpClient
import okhttp3.Call
import okhttp3.Callback
import okhttp3.ConnectionSpec
import okhttp3.Request
import okhttp3.Response
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import java.nio.charset.CodingErrorAction
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

const val UPDATE_APK_MAX_BYTES = 160L * 1024 * 1024

data class UpdateOffer internal constructor(
    val channel: String,
    val packageName: String,
    val versionCode: Long,
    val versionName: String,
    val bytes: Long,
    val sha256: String,
    val apkPath: String,
    val signingCertSha256: String,
)

object UpdateWire {
    fun parse(bytes: ByteArray, origin: HomeOrigin, channel: String, packageName: String,
              installedVersionCode: Long, installedSignerSha256: String): UpdateOffer {
        fun bad(): Nothing = throw HomeFailure(HomeError.INVALID)
        if (channel !in setOf("phone", "tv") || bytes.size > 16 * 1024) bad()
        val text = runCatching {
            Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(java.nio.ByteBuffer.wrap(bytes)).toString()
        }.getOrElse { bad() }
        val root = runCatching { Json.parseToJsonElement(text).jsonObject }.getOrElse { bad() }
        if (hasDuplicateObjectKeys(text)) bad()
        if (root.keys != setOf("schema_version", "channel", "package_name", "version_code", "version_name", "bytes", "sha256", "apk_url", "signing_cert_sha256")) bad()
        fun string(key: String, max: Int): String {
            val p = root[key] as? JsonPrimitive ?: bad()
            if (!p.isString || p.content.isEmpty() || p.content.toByteArray().size > max || p.content.any { it.code < 0x20 }) bad()
            return p.content
        }
        fun number(key: String, low: Long, high: Long): Long {
            val p = root[key] as? JsonPrimitive ?: bad()
            if (p.isString || !p.content.matches(Regex("0|[1-9][0-9]*"))) bad()
            return p.content.toLongOrNull()?.takeIf { it in low..high } ?: bad()
        }
        if (number("schema_version", 1, 1) != 1L) bad()
        if (string("channel", 8) != channel || string("package_name", 160) != packageName) bad()
        val version = number("version_code", 1, Int.MAX_VALUE.toLong())
        if (version <= installedVersionCode) bad()
        val versionName = string("version_name", 80)
        if (!versionName.matches(Regex("[A-Za-z0-9][A-Za-z0-9._+ -]{0,79}"))) bad()
        val length = number("bytes", 1, UPDATE_APK_MAX_BYTES)
        val hash = string("sha256", 64)
        val cert = string("signing_cert_sha256", 64)
        if (!hash.matches(Regex("[a-f0-9]{64}")) || !cert.matches(Regex("[a-f0-9]{64}")) || cert != installedSignerSha256) bad()
        val expectedPath = "/updates/v1/$channel/$hash.apk"
        val rawUrl = string("apk_url", 512)
        val url = origin.url.resolve(rawUrl) ?: bad()
        if (url.scheme != "https" || url.host != origin.url.host || url.port != origin.url.port ||
            url.encodedPath != expectedPath || url.query != null || url.fragment != null || url.username.isNotEmpty() || url.password.isNotEmpty()) bad()
        if (rawUrl != expectedPath) bad()
        return UpdateOffer(channel, packageName, version, versionName, length, hash, expectedPath, cert)
    }

    /** kotlinx.serialization's JsonObject keeps the last duplicate key, so reject duplicates before using it. */
    private fun hasDuplicateObjectKeys(text: String): Boolean {
        class Scanner {
            var i = 0
            var duplicate = false
            private fun ws() { while (i < text.length && text[i].isWhitespace()) i++ }
            private fun string(): String {
                val start = i++
                while (i < text.length) {
                    when (text[i++]) {
                        '\\' -> i++
                        '"' -> return Json.parseToJsonElement(text.substring(start, i)).jsonPrimitive.content
                    }
                }
                return ""
            }
            fun value(depth: Int = 0) {
                ws(); if (i >= text.length || depth > 64) return
                when (text[i]) {
                    '{' -> {
                        i++; ws(); val seen = HashSet<String>()
                        if (i < text.length && text[i] == '}') { i++; return }
                        while (i < text.length) {
                            ws(); if (i >= text.length || text[i] != '"') return
                            val key = string(); if (!seen.add(key)) duplicate = true
                            ws(); if (i < text.length) i++ // colon; syntax was already checked by Json
                            value(depth + 1); ws()
                            if (i < text.length && text[i] == ',') { i++; continue }
                            if (i < text.length) i++
                            return
                        }
                    }
                    '[' -> {
                        i++; ws(); if (i < text.length && text[i] == ']') { i++; return }
                        while (i < text.length) {
                            value(depth + 1); ws()
                            if (i < text.length && text[i] == ',') { i++; continue }
                            if (i < text.length) i++
                            return
                        }
                    }
                    '"' -> string()
                    else -> while (i < text.length && text[i] !in ",]} \t\r\n") i++
                }
            }
        }
        return Scanner().run { value(); duplicate }
    }
}

/** OTA requests use their configured HTTPS origin and strict no-redirect policy. */
class HttpsUpdateClient internal constructor(private val origin: HomeOrigin, client: OkHttpClient) {
    constructor(origin: HomeOrigin) : this(origin, OkHttpClient())
    constructor(origin: HomeOrigin, address: HomeLanAddress) : this(origin, homeLanClient(origin, address))
    private val client = client.newBuilder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).cookieJar(okhttp3.CookieJar.NO_COOKIES)
        .authenticator(okhttp3.Authenticator.NONE).proxyAuthenticator(okhttp3.Authenticator.NONE)
        .connectionSpecs(listOf(ConnectionSpec.MODERN_TLS))
        .cache(null).connectTimeout(10, TimeUnit.SECONDS).readTimeout(20, TimeUnit.SECONDS)
        .callTimeout(180, TimeUnit.SECONDS).build()

    private suspend fun <T> execute(request: Request, consume: (Response) -> T): T = suspendCancellableCoroutine { continuation ->
        val call = client.newCall(request)
        continuation.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (continuation.isActive) continuation.resumeWithException(e)
            }
            override fun onResponse(call: Call, response: Response) {
                try {
                    val value = response.use(consume)
                    if (continuation.isActive) continuation.resume(value)
                } catch (e: Exception) {
                    if (continuation.isActive) continuation.resumeWithException(e)
                }
            }
        })
    }

    suspend fun check(channel: String, packageName: String, installedVersionCode: Long,
                      installedSignerSha256: String): UpdateOffer {
        require(channel in setOf("phone", "tv"))
        val path = "/updates/v1/$channel"
        val request = Request.Builder().url(requireNotNull(origin.url.resolve(path)))
            .header("Accept", "application/json").header("Accept-Encoding", "identity")
            .header("Cache-Control", "no-store").build()
        return execute(request) { response ->
            if (response.code != 200 || response.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() != "application/json" ||
                response.header("Content-Encoding")?.lowercase() !in listOf(null, "identity")) throw HomeFailure(HomeError.INVALID)
            val body = response.body ?: throw HomeFailure(HomeError.INVALID)
            if (body.contentLength() !in -1..16384) throw HomeFailure(HomeError.INVALID)
            val raw = body.byteStream().use { input ->
                val out = ByteArray(16385); var count = 0
                while (true) { val n = input.read(out, count, out.size - count); if (n < 0) break; count += n; if (count > 16384) throw HomeFailure(HomeError.INVALID) }
                out.copyOf(count)
            }
            if (!response.header("Cache-Control").orEmpty().split(',').any { it.trim().equals("no-store", true) }) throw HomeFailure(HomeError.INVALID)
            UpdateWire.parse(raw, origin, channel, packageName, installedVersionCode, installedSignerSha256)
        }
    }

    suspend fun download(offer: UpdateOffer, destination: File): File {
        require(offer.channel in setOf("phone", "tv") && offer.bytes in 1..UPDATE_APK_MAX_BYTES)
        require(offer.sha256.matches(Regex("[a-f0-9]{64}")) && offer.apkPath == "/updates/v1/${offer.channel}/${offer.sha256}.apk")
        val request = Request.Builder().url(requireNotNull(origin.url.resolve(offer.apkPath)))
            .header("Accept", "application/vnd.android.package-archive")
            .header("Accept-Encoding", "identity").header("Cache-Control", "no-store").build()
        val temp = File(destination.parentFile ?: error("destination parent missing"), destination.name + ".part")
        try {
            execute(request) { response ->
                if (response.code != 200 || response.header("Content-Encoding")?.lowercase() !in listOf(null, "identity")) throw HomeFailure(HomeError.INVALID)
                val body = response.body ?: throw HomeFailure(HomeError.INVALID)
                if (body.contentLength() >= 0 && body.contentLength() != offer.bytes) throw HomeFailure(HomeError.INVALID)
                val digest = MessageDigest.getInstance("SHA-256")
                var count = 0L
                temp.outputStream().buffered().use { output ->
                    body.byteStream().use { input ->
                        val buffer = ByteArray(32 * 1024)
                        while (true) {
                            val n = input.read(buffer); if (n < 0) break
                            count += n
                            if (count > offer.bytes || count > UPDATE_APK_MAX_BYTES) throw HomeFailure(HomeError.INVALID)
                            digest.update(buffer, 0, n); output.write(buffer, 0, n)
                        }
                    }
                }
                if (count != offer.bytes || digest.digest().joinToString("") { "%02x".format(it) } != offer.sha256) throw HomeFailure(HomeError.INVALID)
            }
            if (!temp.renameTo(destination)) throw IOException("Could not save update")
        } catch (e: Exception) {
            temp.delete(); destination.delete(); throw e
        }
        return destination
    }
}
