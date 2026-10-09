package dev.photohouse.home

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect

/** App-domain contract; a transport must bind both revisions to its verified server contract. */
data class DiscoverySnapshot(val revision: Int, val catalogRevision: Int, val libraryId: String,
    val libraryTitle: String, val options: DiscoveryOptions, val nextPages: Map<DiscoveryField, Int> = emptyMap(),
    val binding: String? = null, val facetTotals: Map<DiscoveryField, Int> = emptyMap(),
    val facetLastIds: Map<DiscoveryField, Int> = emptyMap(),
    val tagQuery: String? = null, val tagMatches: Set<String> = emptySet())
interface DiscoveryGateway {
    val calendarEnabled:Boolean get()=false
    suspend fun calendar(snapshot:DiscoverySnapshot,request:CalendarRequest):CalendarPage=throw HomeFailure(HomeError.INVALID)
    fun calendarCovers(snapshot:DiscoverySnapshot,page:CalendarPage):HomeApi=throw HomeFailure(HomeError.INVALID)
    suspend fun load(): DiscoverySnapshot
    suspend fun more(snapshot: DiscoverySnapshot, field: DiscoveryField): DiscoverySnapshot
    suspend fun findTags(snapshot: DiscoverySnapshot, query: String, selected: Set<String>): DiscoverySnapshot = throw HomeFailure(HomeError.INVALID)
    fun results(snapshot: DiscoverySnapshot, draft: DiscoveryDraft): HomeApi
}
data class DiscoveryState(val snapshot: DiscoverySnapshot? = null, val loading: Boolean = false,
    val problem: HomeError? = null, val calendar:CalendarState=CalendarState(), val query: DiscoveryDraft? = null, val results: HomeStore? = null)

/** Owns metadata and an isolated result gallery. A failed search never falls back to all photos. */
class DiscoveryController(private val gateway: DiscoveryGateway, private val browse: HomeStore,
    private val scope: CoroutineScope, private val now: () -> Long = { System.nanoTime() / 1_000_000 }) {
    private val mutable = MutableStateFlow(DiscoveryState())
    val state = mutable.asStateFlow()
    private var job: Job? = null
    private var generation = 0L
    private var active = false
    private var notBefore = 0L
    private var calendarJob:Job?=null
    private var calendarGeneration=0L
    val calendarEnabled get()=gateway.calendarEnabled
    private fun clearCalendar() { calendarGeneration++;calendarJob?.cancel();state.value.calendar.covers?.background();mutable.value=state.value.copy(calendar=CalendarState()) }
    fun calendar(request:CalendarRequest=CalendarRequest()) {
        val snapshot=state.value.snapshot ?: return
        if(!active || state.value.loading || !gateway.calendarEnabled || !request.valid()) return
        clearCalendar();val g=calendarGeneration
        if(now()<notBefore) { mutable.value=state.value.copy(calendar=CalendarState(request=request,problem=HomeError.BUSY));return }
        mutable.value=state.value.copy(calendar=CalendarState(request=request,loading=true))
        calendarJob=scope.launch {
            try {
                val page=gateway.calendar(snapshot,request)
                if(!active || g!=calendarGeneration) return@launch
                val covers=HomeStore(gateway.calendarCovers(snapshot,page),scope)
                covers.foreground()
                mutable.value=state.value.copy(calendar=CalendarState(request=request,page=page,covers=covers))
                covers.state.collect { cover ->
                    val error=cover.problem
                    if(active && g==calendarGeneration && error in setOf(HomeError.DENIED,HomeError.CHANGED,HomeError.INVALID,HomeError.TLS)) {
                        background();browse.failDiscovery(HomeFailure(error!!));mutable.value=DiscoveryState(problem=error)
                    }
                }
            } catch(e:CancellationException) { throw e } catch(e:HomeFailure) {
                if(!active || g!=calendarGeneration) return@launch
                if(e.kind in setOf(HomeError.DENIED,HomeError.CHANGED,HomeError.INVALID,HomeError.TLS)) {
                    background();browse.failDiscovery(e);mutable.value=DiscoveryState(problem=e.kind)
                } else {
                    if(e.kind==HomeError.BUSY) notBefore=maxOf(notBefore,now()+e.retryAfterMillis.coerceIn(0,Long.MAX_VALUE-now()))
                    mutable.value=state.value.copy(calendar=CalendarState(request=request,problem=e.kind))
                }
            }
        }
    }
    fun open() {
        active = true
        val previous = state.value.snapshot
        load {
            val fresh = gateway.load()
            // Revalidate first; retain later pages only under the identical server metadata binding.
            if (previous?.binding != null && previous.binding == fresh.binding &&
                previous.revision == fresh.revision && previous.catalogRevision == fresh.catalogRevision &&
                previous.libraryId == fresh.libraryId && previous.facetTotals == fresh.facetTotals && previous.tagQuery == fresh.tagQuery)
                fresh.copy(options = fresh.options.copy(people = previous.options.people, tags = previous.options.tags,
                    places = previous.options.places), nextPages = previous.nextPages, facetLastIds = previous.facetLastIds, tagMatches = previous.tagMatches)
            else if (previous?.binding != null && previous.binding == fresh.binding && fresh.tagQuery != null) {
                val selected=state.value.query?.tags.orEmpty()
                fresh.copy(options=fresh.options.copy(tags=(fresh.options.tags + previous.options.tags.filter { it.id in selected }).distinctBy { it.id }))
            } else fresh
        }
    }
    fun more(field: DiscoveryField) {
        val snapshot = state.value.snapshot ?: return
        if (!active || state.value.loading || field !in snapshot.nextPages) return
        load(keepSnapshot = true) { gateway.more(snapshot, field) }
    }
    fun findTags(query: String, selected: Set<String>) {
        val snapshot=state.value.snapshot ?: return
        val text=query.trim()
        if (!active || state.value.loading || snapshot.tagQuery == null || text.toByteArray(Charsets.UTF_8).size > 128 || text.any { it < ' ' } || selected.size > 20) return
        load(keepSnapshot=true) { gateway.findTags(snapshot,text,selected.toSet()) }
    }
    private fun load(keepSnapshot: Boolean = false, request: suspend () -> DiscoverySnapshot) {
        clearCalendar()
        job?.cancel(); val g = ++generation
        if (now() < notBefore) { mutable.value = state.value.copy(loading = false, problem = HomeError.BUSY); return }
        mutable.value = state.value.copy(snapshot = if (keepSnapshot) state.value.snapshot else null, loading = true, problem = null)
        job = scope.launch {
            try {
                val snapshot = request()
                if (!active || generation != g) return@launch
                val library = browse.state.value.feed?.id
                if (library != null && library != snapshot.libraryId) throw HomeFailure(HomeError.INVALID)
                mutable.value = state.value.copy(snapshot = snapshot, loading = false, problem = null)
            } catch (e: CancellationException) { throw e }
            catch (e: HomeFailure) {
                if (!active || generation != g) return@launch
                if (e.kind == HomeError.BUSY) notBefore = maxOf(notBefore, now() + e.retryAfterMillis.coerceIn(0, Long.MAX_VALUE - now()))
                if (e.kind in setOf(HomeError.DENIED, HomeError.CHANGED, HomeError.INVALID, HomeError.TLS)) {
                    state.value.results?.background(); browse.failDiscovery(e)
                    mutable.value = DiscoveryState(problem = e.kind)
                } else mutable.value = state.value.copy(snapshot = null, loading = false, problem = e.kind)
            }
        }
    }
    fun search(draft: DiscoveryDraft) {
        val s = state.value; val snapshot = s.snapshot ?: return
        if (!active || s.loading || s.problem != null || draft.issue(snapshot.options) != null) return
        val query = draft.normalized()
        val api = gateway.results(snapshot, query)
        clearCalendar()
        job?.cancel(); generation++; active = false
        s.results?.background()
        val result = HomeStore(api, scope)
        result.foreground()
        mutable.value = state.value.copy(query = query, results = result)
    }
    fun close() { clearCalendar(); active = false; generation++; job?.cancel(); mutable.value = state.value.copy(loading = false) }
    fun clearResults() {
        close(); state.value.results?.background()
        mutable.value = state.value.copy(query = null, results = null)
        browse.loadPage(1)
    }
    fun invalidateResults(error: HomeError) {
        if (error !in setOf(HomeError.DENIED, HomeError.INVALID, HomeError.TLS)) return
        background(); browse.failDiscovery(HomeFailure(error))
    }
    fun background() {
        close(); state.value.results?.background(); mutable.value = DiscoveryState()
    }
}
