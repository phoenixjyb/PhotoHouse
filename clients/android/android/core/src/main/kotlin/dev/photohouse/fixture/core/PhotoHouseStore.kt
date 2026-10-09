package dev.photohouse.fixture.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Local states, not server error codes. Server detail strings never select UI behavior. */
enum class Notice { INVALID_INVITATION, DENIED, CLOSED, UNAVAILABLE, RATE_LIMITED, INVALID_RESPONSE, LOCAL_LOGOUT, EXPIRED, NO_FIXTURE }
data class Problem(val notice: Notice, val retryAtMillis: Long = 0)
data class PhotoState(
    val generation: Long = 0, val session: Session? = null, val library: String? = null,
    val gallery: Gallery? = null, val detail: Detail? = null, val captions: Captions? = null,
    val previews: Map<String, ByteArray> = emptyMap(), val busy: Boolean = false,
    val covered: Boolean = false, val problem: Problem? = null,
)
data class RequestScope(val generation: Long, val accountId: String?, val library: String?)

/** Confined to the caller's UI dispatcher. Tests use a single runBlocking dispatcher.
 * No saved-state handle, file store, cookie store, HTTP client, player or disk image cache.
 */
class PhotoHouseStore(
    private val repository: FixtureRepository,
    private val scope: CoroutineScope,
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val mutable = MutableStateFlow(PhotoState())
    val state = mutable.asStateFlow()
    private var token: SessionToken? = null
    private var sessionExpiry = 0L
    private var identity: Session? = null
    private var sessionCase = "approved"
    private val jobs = mutableSetOf<Job>()
    private var retry: (() -> Unit)? = null
    val hasToken get() = token != null
    val cacheEntries get() = state.value.previews.size

    private fun ticket() = RequestScope(state.value.generation, identity?.account_id, state.value.library)
    private fun current(t: RequestScope) = t == ticket()
    private fun invalidate(keepSession: Boolean, covered: Boolean = false) {
        jobs.toList().forEach { it.cancel() }
        jobs.clear()
        retry = null
        if (!keepSession) { token = null; identity = null; sessionExpiry = 0 }
        mutable.value = PhotoState(
            generation = state.value.generation + 1,
            session = if (covered) null else identity, covered = covered,
        )
    }
    private fun request(block: suspend (RequestScope) -> Unit) {
        val t = ticket()
        val job = scope.launch {
            try { block(t) }
            catch (e: CancellationException) { throw e }
            catch (_: Exception) {
                if (current(t)) mutable.value = state.value.copy(busy = false, problem = Problem(Notice.INVALID_RESPONSE))
            }
        }
        jobs += job
        job.invokeOnCompletion { jobs.remove(job) }
    }
    private fun sessionUsable(): Boolean {
        if (token == null || state.value.covered) return false
        if (now() >= sessionExpiry) { lockExpired(); return false }
        return true
    }
    private fun allowed() = sessionUsable() &&
        identity?.memberships?.any { it.library_id == state.value.library && it.available } == true

    fun signIn(invited: Boolean = false, invalidInvitation: Boolean = false, profile: String = "approved", admission: String? = null) {
        invalidate(keepSession = false)
        val input = if (invited) DemoInputs.register().password else DemoInputs.login().password
        check(Contract.passwordLengthValid(input))
        sessionCase = if (invited && !invalidInvitation) "invited-viewer" else profile
        mutable.value = state.value.copy(busy = true)
        request { t ->
            val response = repository.response(admission ?: if (invited) {
                if (invalidInvitation) "invalid-invitation" else "invited-registration"
            } else "login")
            if (!current(t)) return@request
            if (response.status !in 200..299) {
                mutable.value = state.value.copy(busy = false, problem = if (invalidInvitation)
                    Problem(Notice.INVALID_INVITATION) else problem(response.status))
                retry = { signIn(invited, invalidInvitation, profile) }
                return@request
            }
            val result = Contract.body<SessionToken>(response)
            require(result.token_type == "Bearer" && result.expires_in == 86400L)
            val sessionResponse = repository.response(sessionCase)
            if (!current(t)) return@request
            if (sessionResponse.status != 200) {
                mutable.value = state.value.copy(busy = false, problem = problem(sessionResponse.status))
                retry = { signIn(invited, invalidInvitation, "approved") }
                return@request
            }
            identity = Contract.body(sessionResponse)
            token = result
            sessionExpiry = now() + result.expires_in * 1000
            mutable.value = state.value.copy(session = identity, busy = false)
        }
    }

    fun selectLibrary(library: String) {
        if (!sessionUsable()) return
        invalidate(keepSession = true)
        if (identity?.memberships?.none { it.library_id == library && it.available } != false) {
            mutable.value = state.value.copy(problem = Problem(Notice.DENIED)); return
        }
        mutable.value = state.value.copy(library = library)
        // No family-b gallery exists in the frozen pack: don't relabel family-a content.
        if (library != "family-a") {
            mutable.value = state.value.copy(problem = Problem(Notice.NO_FIXTURE)); return
        }
        loadGallery()
    }

    fun libraries() { if (sessionUsable()) invalidate(keepSession = true) }

    fun loadGallery(caseId: String = "gallery", missingPreview: Boolean = false, delayed: Boolean = false) {
        if (!allowed()) return
        val library = state.value.library!!
        // A new read invalidates detail/caption/media callbacks as well as earlier pages.
        invalidate(keepSession = true)
        mutable.value = state.value.copy(library = library, busy = true)
        request { t ->
            if (delayed) kotlinx.coroutines.delay(3000)
            val response = repository.response(caseId)
            if (!current(t)) return@request
            if (response.status != 200) { handleReadFailure(response.status, t); return@request }
            val page = Contract.body<Gallery>(response)
            require(page.library_id == t.library)
            val deduplicated = page.copy(items = page.items.distinctBy { it.id })
            val images = mutableMapOf<String, ByteArray>()
            for (asset in deduplicated.items.take(100)) {
                val preview = repository.response(if (missingPreview) "missing-thumbnail" else "thumbnail")
                if (!current(t)) return@request
                if (preview.status == 200) repository.thumbnail(asset.thumbnail_url)?.let { images[asset.id] = it }
                else if (preview.status != 404) { handleReadFailure(preview.status, t); return@request }
            }
            mutable.value = state.value.copy(gallery = deduplicated, previews = images, busy = false)
        }
    }

    fun openAsset(asset: Asset, denied: Boolean = false, recheck: String = sessionCase, missingCaptions: Boolean = false) {
        if (!allowed()) return
        val library = state.value.library!!
        invalidate(keepSession = true)
        mutable.value = state.value.copy(library = library, busy = true)
        request { t ->
            val response = repository.response(if (denied) "foreign-asset" else if (asset.id == "101") "detail" else "video-metadata-only")
            if (!current(t)) return@request
            if (response.status != 200) { handleReadFailure(response.status, t, recheck); return@request }
            val detail = Contract.body<Detail>(response)
            require(detail.library_id == t.library && detail.asset.id == asset.id)
            val captionsResponse = repository.response(if (missingCaptions) "captions-missing" else if (asset.id == "101") "captions-bilingual" else "captions-untrusted-text")
            if (!current(t)) return@request
            if (captionsResponse.status != 200) { handleReadFailure(captionsResponse.status, t); return@request }
            val captions = Contract.body<Captions>(captionsResponse)
            require(captions.library_id == t.library && captions.asset_id == asset.id)
            // Metadata-only video never invokes originalGet or creates a native player.
            val preview = repository.response("thumbnail")
            if (!current(t)) return@request
            if (preview.status != 200 && preview.status != 404) { handleReadFailure(preview.status, t); return@request }
            val bytes = if (preview.status == 200) repository.thumbnail(detail.asset.thumbnail_url) else null
            mutable.value = state.value.copy(detail = detail, captions = captions, busy = false,
                previews = if (bytes == null) emptyMap() else mapOf(asset.id to bytes))
        }
    }

    private suspend fun handleReadFailure(status: Int, t: RequestScope, recheck: String = sessionCase) {
        if (!current(t)) return
        // Hide affected private content before the single session check.
        mutable.value = state.value.copy(gallery = null, detail = null, captions = null,
            previews = emptyMap(), busy = status == 401, problem = problem(status))
        if (status == 401) {
            val checked = repository.response(recheck)
            if (!current(t)) return
            if (checked.status == 401) { lockExpired(); return }
            if (checked.status != 200) {
                invalidate(keepSession = true, covered = true)
                mutable.value = state.value.copy(problem = problem(checked.status))
                retry = { foreground() }
                return
            }
            val refreshed = Contract.body<Session>(checked)
            require(refreshed.account_id == identity?.account_id)
            identity = refreshed
            invalidate(keepSession = true)
            mutable.value = state.value.copy(problem = Problem(Notice.DENIED))
        } else {
            mutable.value = state.value.copy(busy = false)
            if (status == 429 || status >= 500) retry = { loadGallery() }
        }
    }

    fun acceptDemoInvitation() {
        if (!sessionUsable()) return
        invalidate(keepSession = true)
        mutable.value = state.value.copy(busy = true)
        request { t ->
            val response = repository.response("accept-second-library")
            if (!current(t)) return@request
            if (response.status != 200) { handleReadFailure(response.status, t); return@request }
            require(Contract.body<Ok>(response).ok)
            val refreshed = repository.response("two-libraries")
            if (!current(t)) return@request
            if (refreshed.status != 200) { handleReadFailure(refreshed.status, t); return@request }
            val session = Contract.body<Session>(refreshed)
            // The second-library fixture belongs only to the returning demo account.
            require(session.account_id == identity?.account_id)
            identity = session
            sessionCase = "two-libraries"
            mutable.value = state.value.copy(session = session, busy = false)
        }
    }

    fun background() { invalidate(keepSession = true, covered = true) }
    fun foreground(recheck: String = sessionCase) {
        if (!state.value.covered) return
        if (token == null) { invalidate(keepSession = false); return }
        if (now() >= sessionExpiry) { lockExpired(); return }
        invalidate(keepSession = true, covered = true)
        mutable.value = state.value.copy(busy = true)
        request { t ->
            val response = repository.response(recheck)
            if (!current(t)) return@request
            if (response.status == 401) { lockExpired(); return@request }
            if (response.status != 200) {
                mutable.value = state.value.copy(busy = false, problem = problem(response.status))
                retry = { foreground(sessionCase) }; return@request
            }
            val session = Contract.body<Session>(response)
            require(session.account_id == identity?.account_id)
            identity = session
            mutable.value = state.value.copy(session = session, covered = false, busy = false)
        }
    }
    private fun lockExpired() {
        invalidate(keepSession = false)
        mutable.value = state.value.copy(problem = Problem(Notice.EXPIRED))
    }
    fun logout(serverUnavailable: Boolean = false) {
        invalidate(keepSession = false)
        mutable.value = state.value.copy(problem = Problem(Notice.LOCAL_LOGOUT))
        // A synthetic acknowledgement is never described as server revocation.
        request { repository.response(if (serverUnavailable) "unavailable" else "logout") }
    }
    fun retry() {
        if (now() < (state.value.problem?.retryAtMillis ?: 0)) return
        val action = retry ?: return
        retry = null
        action()
    }
    fun canRetry(at: Long = now()) = retry != null && at >= (state.value.problem?.retryAtMillis ?: 0)

    private fun problem(status: Int, retryAfter: String? = null) = when (status) {
        401 -> Problem(Notice.DENIED)
        403 -> Problem(Notice.CLOSED)
        429 -> Problem(Notice.RATE_LIMITED, now() + retryDelayMillis(retryAfter))
        in 500..599 -> Problem(Notice.UNAVAILABLE)
        else -> Problem(Notice.INVALID_RESPONSE)
    }
    companion object {
        // The frozen 429 fixture has no headers. Default is a local demo cooldown.
        // Keep Retry-After parsing ready for injected tests; no transport is implied.
        fun retryDelayMillis(value: String?, nowMillis: Long = System.currentTimeMillis()): Long {
            val seconds = value?.toLongOrNull()
            if (seconds != null) return seconds.coerceIn(0, 86400) * 1000
            val date = runCatching { java.time.ZonedDateTime.parse(value, java.time.format.DateTimeFormatter.RFC_1123_DATE_TIME).toInstant().toEpochMilli() }.getOrNull()
            return if (date == null) 5000 else (date - nowMillis).coerceIn(0, 86400000)
        }
    }
}
