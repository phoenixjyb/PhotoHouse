package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull
import java.util.UUID

/** Reader identity used only by the owner; it is never copied into public state. */
data class MemoryBookNarrativeScope(
    val accountId: String,
    val credential: Bearer,
    val library: String,
    val generation: Long,
    val bookId: String,
    val bookRevision: Long,
    val children: List<EditorialChild>,
    val scopeId: Long,
)

enum class MemoryBookNarrativeStatus {
    IDLE, CHECKING_PLAN, PLAN_READY, SMALLER_SCOPE, VIEW_ONLY, PLAN_FAILED,
    QUEUING, RETRY_REQUIRED, QUEUED, RUNNING, REVIEW_READY, DRAFT_FAILED,
    DRAFT_STALE, DRAFT_CANCELLED,
}

enum class MemoryBookNarrativeFailure {
    NETWORK, TLS, SERVICE_UNAVAILABLE, RATE_LIMITED, SCOPE_CHANGED, TOO_LARGE,
    INVALID_RESPONSE, INVALID_REQUEST, UNKNOWN,
}

enum class MemoryBookNarrativeForm(val instruction: String?) {
    EXISTING(null),
    CHRONICLE("按已有时间线整理为忠实纪事。保留不同家人的说法，未知日期先提问，不编造事件。"),
    ESSAY("把已有回忆整理成温暖的家庭散文。保留真实讲述与不确定之处，不补写没有来源的经历。"),
    LONG_MEMOIR("把已有篇章连成有开篇、衔接和回望的长篇回忆录。保留原篇章顺序与家人的不同声音，不编造对白、人物或事件。"),
}

data class MemoryBookNarrativeChapter(
    val id: String,
    val storyId: String,
    val storyTitle: String,
    val storyRevision: Long,
    val chapterId: String,
    val chapterTitle: String,
    val narration: String,
    /** Counts only. Opaque source references are validated then discarded. */
    val citationCount: Int,
)

data class MemoryBookNarrativeProposal(
    val title: String,
    val chapters: List<MemoryBookNarrativeChapter>,
    val questions: List<String>,
    val needsReview: Boolean = true,
)

data class MemoryBookNarrativeStoreState(
    val instructions: String = "",
    val editorialContext: Boolean = false,
    val plan: MemoryBookPlan? = null,
    val pendingRequest: MemoryNarrativeRequest? = null,
    val job: MemoryJob? = null,
    val proposal: MemoryBookNarrativeProposal? = null,
    val busy: Boolean = false,
    val status: MemoryBookNarrativeStatus = MemoryBookNarrativeStatus.IDLE,
    val failure: MemoryBookNarrativeFailure? = null,
    val hasUnfinishedInput: Boolean = false,
    val form: MemoryBookNarrativeForm = MemoryBookNarrativeForm.EXISTING,
)

/**
 * One-book, review-only narrative workflow. It does not apply generated text to the
 * book or its child stories. Callers own this coordinator and must call [clear]
 * whenever their memoir chat/reader epoch changes.
 */
class MemoryBookNarrativeStore(
    private val repository: MemoryCommunityRepository,
    private val scope: CoroutineScope,
    private val currentScope: () -> MemoryBookNarrativeScope?,
) {
    private data class Fence(
        val accountId: String,
        val credential: Bearer,
        val library: String,
        val generation: Long,
        val bookId: String,
        val bookRevision: Long,
        val children: List<EditorialChild>,
        val scopeId: Long,
    )

    private data class FrozenRequest(
        val fence: Fence,
        val request: MemoryNarrativeRequest,
        val plan: MemoryBookPlan,
    )

    private val mutableState = MutableStateFlow(MemoryBookNarrativeStoreState())
    val state: StateFlow<MemoryBookNarrativeStoreState> = mutableState.asStateFlow()

    private var generation = 0L
    private var operationJob: Job? = null
    private var operationKind: MemoryBookNarrativeStatus? = null
    private var boundFence: Fence? = null
    private var checkedPlanFence: Fence? = null
    private var checkedPlanEditorial: Boolean? = null
    private var frozenRequest: FrozenRequest? = null

    /** Updates transient instructions. Text is UTF-8 bounded and never persisted. */
    @Synchronized
    fun updateInstructions(text: String): Boolean {
        if (!ensureBoundScope() || controlsFrozen()) return false
        if (combinedInstructions(mutableState.value.form, text) == null) return false
        frozenRequest = null
        val plan = mutableState.value.plan
        val activeFence = boundFence
        val eligible = plan != null && activeFence != null && checkedPlanFence == activeFence &&
            checkedPlanEditorial == mutableState.value.editorialContext &&
            planMatchesScope(plan, activeFence, mutableState.value.editorialContext)
        mutableState.value = mutableState.value.copy(instructions = text, failure = null,
            hasUnfinishedInput = hasInput(text, mutableState.value.form), pendingRequest = null, job = null, proposal = null,
            status = when {
                plan?.whole?.state == "smaller_scope_required" -> MemoryBookNarrativeStatus.SMALLER_SCOPE
                eligible && (!plan!!.canEdit || !plan.whole.canDraft) -> MemoryBookNarrativeStatus.VIEW_ONLY
                eligible -> MemoryBookNarrativeStatus.PLAN_READY
                else -> MemoryBookNarrativeStatus.IDLE
            })
        return true
    }

    /** Selects a local request form without probing a plan, queueing a job or contacting a provider. */
    @Synchronized
    fun chooseForm(form: MemoryBookNarrativeForm): Boolean {
        if (!ensureBoundScope() || controlsFrozen()) return false
        val current = mutableState.value
        if (current.form == form) return true
        if (combinedInstructions(form, current.instructions) == null) return false
        frozenRequest = null
        val activeFence = boundFence
        val plan = current.plan
        val eligible = plan != null && activeFence != null && checkedPlanFence == activeFence &&
            checkedPlanEditorial == current.editorialContext && planMatchesScope(plan, activeFence, current.editorialContext)
        mutableState.value = current.copy(
            form = form,
            failure = null,
            pendingRequest = null,
            job = null,
            proposal = null,
            status = when {
                plan?.whole?.state == "smaller_scope_required" -> MemoryBookNarrativeStatus.SMALLER_SCOPE
                eligible && (!plan!!.canEdit || !plan.whole.canDraft) -> MemoryBookNarrativeStatus.VIEW_ONLY
                eligible -> MemoryBookNarrativeStatus.PLAN_READY
                else -> MemoryBookNarrativeStatus.IDLE
            },
            hasUnfinishedInput = hasInput(current.instructions, form),
        )
        return true
    }

    /** Changes the opt-in choice and invalidates any plan checked for the old choice. */
    @Synchronized
    fun chooseEditorialContext(selected: Boolean): Boolean {
        if (!ensureBoundScope() || controlsFrozen()) return false
        if (mutableState.value.editorialContext == selected) return true
        cancelPlanCheck()
        checkedPlanFence = null
        checkedPlanEditorial = null
        frozenRequest = null
        mutableState.value = mutableState.value.copy(
            editorialContext = selected,
            plan = null,
            proposal = null,
            pendingRequest = null,
            job = null,
            failure = null,
            status = MemoryBookNarrativeStatus.IDLE,
            hasUnfinishedInput = hasInput(mutableState.value.instructions, mutableState.value.form),
        )
        return true
    }

    /** Explicitly reads the current saved plan; it never queues a generation job. */
    suspend fun checkPlan(): Boolean {
        val fence = beginOperation(MemoryBookNarrativeStatus.CHECKING_PLAN) ?: return false
        val ticket = generation
        val editorial = state.value.editorialContext
        synchronized(this) {
            frozenRequest = null
            mutableState.value = state.value.copy(
                job = null,
                proposal = null,
                pendingRequest = null,
                hasUnfinishedInput = hasInput(state.value.instructions, state.value.form),
            )
        }
        return try {
            val plan = repository.bookPlan(fence.bookId, fence.bookRevision, editorialContext = editorial) {
                stillCurrent(fence, ticket)
            }
            currentCoroutineContext().ensureActive()
            if (!stillCurrent(fence, ticket)) return false
            if (!planMatchesScope(plan, fence, editorial)) invalidResponse()
            synchronized(this) {
                if (ticket != generation) return false
                checkedPlanFence = fence
                checkedPlanEditorial = editorial
                val status = when {
                    plan.whole.state == "smaller_scope_required" -> MemoryBookNarrativeStatus.SMALLER_SCOPE
                    !plan.canEdit || !plan.whole.canDraft -> MemoryBookNarrativeStatus.VIEW_ONLY
                    else -> MemoryBookNarrativeStatus.PLAN_READY
                }
                mutableState.value = mutableState.value.copy(plan = plan, status = status, failure = null)
            }
            true
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (failure: ApiFailure) {
            if (!stillCurrent(fence, ticket)) return false
            val mapped = safeFailure(failure)
            if (failure.status in setOf(401, 403)) {
                clear()
            } else synchronized(this) {
                mutableState.value = mutableState.value.copy(
                    plan = null,
                    status = if (failure.status == 422) MemoryBookNarrativeStatus.SMALLER_SCOPE
                    else MemoryBookNarrativeStatus.PLAN_FAILED,
                    failure = mapped,
                )
            }
            false
        } catch (_: Exception) {
            if (!stillCurrent(fence, ticket)) return false
            synchronized(this) {
                mutableState.value = mutableState.value.copy(
                    plan = null, status = MemoryBookNarrativeStatus.PLAN_FAILED,
                    failure = MemoryBookNarrativeFailure.UNKNOWN,
                )
            }
            false
        } finally {
            finishOperation(ticket)
        }
    }

    /** Starts one explicit book draft request after an eligible plan has been reviewed. */
    suspend fun queue(): Boolean {
        val fence = currentFenceForPlan() ?: return false
        if (controlsFrozen() || state.value.job != null) return false
        val plan = state.value.plan ?: return false
        if (!queueEligible(plan, fence, state.value.editorialContext)) {
            synchronized(this) {
                mutableState.value = mutableState.value.copy(
                    status = when {
                        plan.whole.state == "smaller_scope_required" -> MemoryBookNarrativeStatus.SMALLER_SCOPE
                        else -> MemoryBookNarrativeStatus.VIEW_ONLY
                    },
                    failure = null,
                )
            }
            return false
        }
        val request = synchronized(this) {
            val current = state.value
            if (fence != boundFence || controlsFrozen() || current.job != null || current.plan != plan ||
                !queueEligible(plan, fence, current.editorialContext)) return false
            val fullInstructions = combinedInstructions(current.form, current.instructions) ?: return false
            val frozen = MemoryNarrativeRequest(
                targetType = "book",
                targetId = fence.bookId,
                revision = fence.bookRevision,
                instructions = fullInstructions,
                editorialContext = current.editorialContext,
            )
            frozenRequest = FrozenRequest(fence, frozen, plan)
            mutableState.value = mutableState.value.copy(
                pendingRequest = frozen, proposal = null, busy = true,
                status = MemoryBookNarrativeStatus.QUEUING, failure = null,
                hasUnfinishedInput = true,
            )
            frozen
        }
        return submitFrozenRequest(fence, request, plan)
    }

    /** Retries the exact request and mutation ID after an uncertain submission. */
    suspend fun retry(): Boolean {
        val frozen = synchronized(this) {
            frozenRequest?.takeIf { state.value.pendingRequest == it.request &&
                state.value.status == MemoryBookNarrativeStatus.RETRY_REQUIRED }
        } ?: return false
        if (!sameCurrent(frozen.fence)) return false
        synchronized(this) {
            if (state.value.busy || state.value.pendingRequest != frozen.request) return false
            mutableState.value = state.value.copy(busy = true, status = MemoryBookNarrativeStatus.QUEUING,
                failure = null)
        }
        return submitFrozenRequest(frozen.fence, frozen.request, frozen.plan)
    }

    /** Checks a known job only after the caller explicitly asks. */
    suspend fun refresh(): Boolean {
        val frozen = synchronized(this) { frozenRequest } ?: return false
        val prior = state.value.job ?: return false
        if (!sameCurrent(frozen.fence) || state.value.busy) return false
        val operation = beginOperation(MemoryBookNarrativeStatus.RUNNING, allowJob = true) ?: return false
        val ticket = generation
        return try {
            val updated = repository.job(prior.id) { stillCurrent(operation, ticket) }
            currentCoroutineContext().ensureActive()
            if (!stillCurrent(operation, ticket)) return false
            if (!validJob(updated, prior.id, frozen.request)) invalidResponse()
            synchronized(this) {
                if (ticket != generation) return false
                applyJobResult(updated, frozen)
            }
            true
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (failure: ApiFailure) {
            if (!stillCurrent(operation, ticket)) return false
            if (failure.status in setOf(401, 403)) clear() else synchronized(this) {
                mutableState.value = state.value.copy(status = MemoryBookNarrativeStatus.DRAFT_FAILED,
                    failure = safeFailure(failure))
            }
            false
        } catch (_: Exception) {
            if (!stillCurrent(operation, ticket)) return false
            synchronized(this) {
                mutableState.value = state.value.copy(status = MemoryBookNarrativeStatus.DRAFT_FAILED,
                    failure = MemoryBookNarrativeFailure.UNKNOWN)
            }
            false
        } finally {
            finishOperation(ticket)
        }
    }

    /** Explicitly cancels only the currently retained queued/running job. */
    suspend fun cancelKnownJob(): Boolean {
        val frozen = synchronized(this) { frozenRequest } ?: return false
        val prior = state.value.job ?: return false
        if (prior.state !in ACTIVE_JOB_STATES || !sameCurrent(frozen.fence)) return false
        val operation = beginOperation(MemoryBookNarrativeStatus.RUNNING, allowJob = true) ?: return false
        val ticket = generation
        return try {
            val updated = repository.cancelJob(prior.id)
            currentCoroutineContext().ensureActive()
            if (!stillCurrent(operation, ticket)) return false
            if (!validJob(updated, prior.id, frozen.request)) invalidResponse()
            synchronized(this) {
                if (ticket != generation) return false
                applyJobResult(updated, frozen)
            }
            true
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (failure: ApiFailure) {
            if (!stillCurrent(operation, ticket)) return false
            if (failure.status in setOf(401, 403)) clear() else synchronized(this) {
                mutableState.value = state.value.copy(status = MemoryBookNarrativeStatus.DRAFT_FAILED,
                    failure = safeFailure(failure))
            }
            false
        } catch (_: Exception) {
            if (!stillCurrent(operation, ticket)) return false
            synchronized(this) {
                mutableState.value = state.value.copy(status = MemoryBookNarrativeStatus.DRAFT_FAILED,
                    failure = MemoryBookNarrativeFailure.UNKNOWN)
            }
            false
        } finally {
            finishOperation(ticket)
        }
    }

    /** Clears all private state and invalidates/cancels late local continuations. */
    @Synchronized
    fun clear() {
        generation++
        operationJob?.cancel()
        operationJob = null
        operationKind = null
        boundFence = null
        checkedPlanFence = null
        checkedPlanEditorial = null
        frozenRequest = null
        mutableState.value = MemoryBookNarrativeStoreState()
    }

    private suspend fun submitFrozenRequest(
        fence: Fence,
        request: MemoryNarrativeRequest,
        plan: MemoryBookPlan,
    ): Boolean {
        val callerJob = currentCoroutineContextJob()
        val operationFence = synchronized(this) {
            if (frozenRequest?.request != request || !sameCurrent(fence)) return false
            operationJob = callerJob
            operationKind = MemoryBookNarrativeStatus.QUEUING
            fence
        }
        val ticket = generation
        try {
            val job = repository.queueNarrative(request)
            currentCoroutineContext().ensureActive()
            if (!stillCurrent(operationFence, ticket)) return false
            if (!validJob(job, null, request)) invalidResponse()
            synchronized(this) {
                if (ticket != generation) return false
                applyJobResult(job, FrozenRequest(fence, request, plan))
            }
            return true
        } catch (cancelled: CancellationException) {
            if (stillCurrent(operationFence, ticket)) synchronized(this) {
                mutableState.value = state.value.copy(pendingRequest = request, busy = false,
                    status = MemoryBookNarrativeStatus.RETRY_REQUIRED, failure = MemoryBookNarrativeFailure.UNKNOWN,
                    hasUnfinishedInput = true)
            }
            throw cancelled
        } catch (failure: ApiFailure) {
            if (!stillCurrent(operationFence, ticket)) return false
            if (failure.status in setOf(401, 403)) {
                clear()
            } else if (failure.status in setOf(409, 422)) {
                rejectDefiniteQueueFailure(failure)
            } else synchronized(this) {
                mutableState.value = state.value.copy(
                    pendingRequest = request,
                    busy = false,
                    status = MemoryBookNarrativeStatus.RETRY_REQUIRED,
                    failure = safeFailure(failure),
                )
            }
            return false
        } catch (_: Exception) {
            if (!stillCurrent(operationFence, ticket)) return false
            synchronized(this) {
                mutableState.value = state.value.copy(
                    pendingRequest = request,
                    busy = false,
                    status = MemoryBookNarrativeStatus.RETRY_REQUIRED,
                    failure = MemoryBookNarrativeFailure.UNKNOWN,
                )
            }
            return false
        } finally {
            finishOperation(ticket)
        }
    }

    @Synchronized
    private fun rejectDefiniteQueueFailure(failure: ApiFailure) {
        frozenRequest = null
        checkedPlanFence = null
        checkedPlanEditorial = null
        mutableState.value = state.value.copy(
            plan = null,
            pendingRequest = null,
            job = null,
            proposal = null,
            busy = false,
            status = if (failure.status == 409) MemoryBookNarrativeStatus.DRAFT_STALE
                else MemoryBookNarrativeStatus.SMALLER_SCOPE,
            failure = if (failure.status == 409) MemoryBookNarrativeFailure.SCOPE_CHANGED
                else MemoryBookNarrativeFailure.TOO_LARGE,
            hasUnfinishedInput = hasInput(state.value.instructions, state.value.form),
        )
    }

    private suspend fun beginOperation(
        status: MemoryBookNarrativeStatus,
        allowJob: Boolean = false,
    ): Fence? {
        val fence = synchronized(this) {
            if (scope.coroutineContext[Job]?.isActive == false || state.value.busy ||
                controlsFrozen() && !allowJob) return null
            captureFence() ?: return null
        }
        val callerJob = currentCoroutineContextJob()
        synchronized(this) {
            if (state.value.busy || !sameCurrent(fence)) return null
            operationJob = callerJob
            operationKind = status
            mutableState.value = state.value.copy(busy = true, status = status, failure = null)
        }
        return fence
    }

    private suspend fun currentCoroutineContextJob(): Job? = currentCoroutineContext()[Job]

    @Synchronized
    private fun finishOperation(ticket: Long) {
        if (ticket != generation) return
        operationJob = null
        operationKind = null
        if (mutableState.value.busy) mutableState.value = mutableState.value.copy(busy = false)
    }

    @Synchronized
    private fun currentFenceForPlan(): Fence? {
        if (!ensureBoundScope() || controlsFrozen()) return null
        val fence = boundFence ?: return null
        if (checkedPlanFence != fence || checkedPlanEditorial != state.value.editorialContext) return null
        val plan = state.value.plan ?: return null
        if (!planMatchesScope(plan, fence, state.value.editorialContext)) return null
        return fence
    }

    @Synchronized
    private fun ensureBoundScope(): Boolean {
        val actual = validFence(currentScope()) ?: return false.also { invalidateIfBoundScopeIsMissing() }
        val existing = boundFence
        if (existing != null && existing != actual) {
            invalidateState()
        }
        if (boundFence == null) boundFence = actual
        return boundFence == actual
    }

    @Synchronized
    private fun captureFence(): Fence? {
        if (!ensureBoundScope()) return null
        return boundFence
    }

    @Synchronized
    private fun stillCurrent(fence: Fence, ticket: Long): Boolean {
        if (ticket != generation || scope.coroutineContext[Job]?.isActive == false) return false
        val actual = validFence(currentScope())
        if (actual == null || actual != fence) {
            invalidateState()
            return false
        }
        return boundFence == fence
    }

    @Synchronized
    private fun sameCurrent(fence: Fence): Boolean {
        val actual = validFence(currentScope())
        if (actual == null || actual != fence) {
            if (boundFence != null) invalidateState()
            return false
        }
        if (boundFence == null) boundFence = fence
        return boundFence == fence
    }

    @Synchronized
    private fun invalidateIfBoundScopeIsMissing() {
        if (boundFence != null) invalidateState()
    }

    @Synchronized
    private fun invalidateState() {
        generation++
        operationJob?.cancel()
        operationJob = null
        operationKind = null
        boundFence = null
        checkedPlanFence = null
        checkedPlanEditorial = null
        frozenRequest = null
        mutableState.value = MemoryBookNarrativeStoreState()
    }

    private fun validFence(value: MemoryBookNarrativeScope?): Fence? {
        value ?: return null
        if (value.accountId.isBlank() || value.accountId.length > 256 ||
            !PhoneDiscoveryWire.validLibrary(value.library) || value.generation < 0 ||
            value.scopeId < 0 || value.bookRevision <= 0 || !canonicalUuid(value.bookId) ||
            value.children.isEmpty() || value.children.size > MAX_CHAPTERS ||
            value.children.map { it.storyId }.distinct().size != value.children.size ||
            value.children.any { !canonicalUuid(it.storyId) || !positiveRevision(it.revision) }) return null
        return Fence(value.accountId, value.credential, value.library, value.generation, value.bookId,
            value.bookRevision, value.children.toList(), value.scopeId)
    }

    private fun planMatchesScope(plan: MemoryBookPlan, fence: Fence, editorial: Boolean): Boolean {
        if (plan.targetType != "book" || plan.targetId != fence.bookId || plan.revision != fence.bookRevision ||
            plan.kind != "saved_structure_plan" || plan.generated || plan.queued || !plan.needsReview ||
            plan.contextProfile != if (editorial) EDITORIAL_CONTEXT_PROFILE else null) return false
        val children = plan.sections.map { EditorialChild(it.id, it.revision.toString()) }
        return children == fence.children && plan.sections.all { it.chapters.isNotEmpty() } &&
            plan.chapterCount == plan.sections.sumOf { it.chapters.size } &&
            (plan.whole.state != "within_limits" || plan.chapterCount <= MAX_CHAPTERS)
    }

    private fun queueEligible(plan: MemoryBookPlan, fence: Fence, editorial: Boolean): Boolean =
        checkedPlanFence == fence && checkedPlanEditorial == editorial && planMatchesScope(plan, fence, editorial) &&
            plan.whole.state == "within_limits" && plan.canEdit && plan.whole.canDraft

    private fun controlsFrozen(): Boolean = state.value.busy || state.value.pendingRequest != null ||
        state.value.job?.state in ACTIVE_JOB_STATES

    private fun cancelPlanCheck() {
        if (operationKind == MemoryBookNarrativeStatus.CHECKING_PLAN) {
            generation++
            operationJob?.cancel()
            operationJob = null
            operationKind = null
            mutableState.value = mutableState.value.copy(busy = false)
        }
    }

    private fun applyJobResult(job: MemoryJob, frozen: FrozenRequest) {
        val parsed = when (job.state) {
            "ready" -> parseReview(job.result ?: invalidResponse(), frozen.plan)
            else -> null
        }
        val status = when (job.state) {
            "queued" -> MemoryBookNarrativeStatus.QUEUED
            "running" -> MemoryBookNarrativeStatus.RUNNING
            "ready" -> MemoryBookNarrativeStatus.REVIEW_READY
            "stale" -> MemoryBookNarrativeStatus.DRAFT_STALE
            "cancelled" -> MemoryBookNarrativeStatus.DRAFT_CANCELLED
            "failed" -> MemoryBookNarrativeStatus.DRAFT_FAILED
            else -> invalidResponse()
        }
        this.frozenRequest = frozen
        if (job.state == "stale") {
            checkedPlanFence = null
            checkedPlanEditorial = null
        }
        mutableState.value = state.value.copy(
            pendingRequest = null,
            job = job,
            proposal = parsed,
            busy = true,
            status = status,
            failure = if (job.state == "stale") MemoryBookNarrativeFailure.SCOPE_CHANGED else null,
            hasUnfinishedInput = false,
        )
    }

    private fun validJob(job: MemoryJob, expectedId: String?, request: MemoryNarrativeRequest): Boolean =
        canonicalUuid(job.id) && (expectedId == null || job.id == expectedId) &&
            job.kind == "narrative" && job.baseRevision == request.revision && job.needsReview &&
            job.state in JOB_STATES

    private fun parseReview(result: JsonObject, plan: MemoryBookPlan): MemoryBookNarrativeProposal {
        val outputBytes = try { ProtectedMemoryCommunityWire.strictUtf8(result.toString()) }
            catch (_: Exception) { invalidResponse() }
        val withinOutputLimit = try { outputBytes.size <= MAX_OUTPUT_BYTES } finally { outputBytes.fill(0) }
        if (!withinOutputLimit || result.keys != setOf("version", "title", "chapters", "questions", "needs_review"))
            invalidResponse()
        if (int(result["version"], 1, 1) != 1 || boolean(result["needs_review"]) != true) invalidResponse()
        val title = text(result["title"], 512, allowBlank = true)
        val chapters = result["chapters"] as? JsonArray ?: invalidResponse()
        val expected = plan.sections.flatMap { section ->
            section.chapters.map { chapter ->
                Triple(section, chapter, "${section.id}-${chapter.id}")
            }
        }
        if (expected.isEmpty() || expected.size > MAX_CHAPTERS || chapters.size != expected.size) invalidResponse()
        var totalSources = 0
        val mapped = chapters.mapIndexed { index, element ->
            val raw = element as? JsonObject ?: invalidResponse()
            if (raw.keys != setOf("id", "narration", "source_ids")) invalidResponse()
            val id = text(raw["id"], 128)
            val (section, chapter, expectedId) = expected[index]
            if (id != expectedId) invalidResponse()
            val narration = text(raw["narration"], 6000, allowBlank = true)
            val refs = raw["source_ids"] as? JsonArray ?: invalidResponse()
            totalSources += refs.size
            if (refs.size > MAX_SOURCES || totalSources > MAX_SOURCES) invalidResponse()
            val ids = refs.map { text(it, 128) }
            if (ids.distinct().size != ids.size || ids.any { !it.matches(OPAQUE_ID) }) invalidResponse()
            MemoryBookNarrativeChapter(expectedId, section.id, section.title, section.revision,
                chapter.id, chapter.title, narration, ids.size)
        }
        val questionsJson = result["questions"] as? JsonArray ?: invalidResponse()
        if (questionsJson.size > 6) invalidResponse()
        val questions = questionsJson.map { text(it, 512) }
        return MemoryBookNarrativeProposal(title, mapped, questions)
    }

    private fun safeFailure(failure: ApiFailure): MemoryBookNarrativeFailure = when {
        failure.kind == FailureKind.OFFLINE -> MemoryBookNarrativeFailure.NETWORK
        failure.kind == FailureKind.TLS -> MemoryBookNarrativeFailure.TLS
        failure.kind == FailureKind.INVALID_RESPONSE -> MemoryBookNarrativeFailure.INVALID_RESPONSE
        failure.kind == FailureKind.INVALID_INPUT -> MemoryBookNarrativeFailure.INVALID_REQUEST
        failure.status == 409 -> MemoryBookNarrativeFailure.SCOPE_CHANGED
        failure.status == 422 -> MemoryBookNarrativeFailure.TOO_LARGE
        failure.status == 429 -> MemoryBookNarrativeFailure.RATE_LIMITED
        failure.status == 503 -> MemoryBookNarrativeFailure.SERVICE_UNAVAILABLE
        failure.kind == FailureKind.HTTP -> MemoryBookNarrativeFailure.SERVICE_UNAVAILABLE
        else -> MemoryBookNarrativeFailure.UNKNOWN
    }

    private fun invalidResponse(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)

    private fun int(value: JsonElement?, min: Int, max: Int): Int {
        val primitive = value as? JsonPrimitive ?: invalidResponse()
        if (primitive.isString) invalidResponse()
        val parsed = primitive.intOrNull ?: invalidResponse()
        if (parsed !in min..max) invalidResponse()
        return parsed
    }

    private fun boolean(value: JsonElement?): Boolean {
        val primitive = value as? JsonPrimitive ?: invalidResponse()
        if (primitive.isString) invalidResponse()
        return primitive.booleanOrNull ?: invalidResponse()
    }

    private fun text(value: JsonElement?, maxBytes: Int, allowBlank: Boolean = false): String {
        val primitive = value as? JsonPrimitive ?: invalidResponse()
        if (!primitive.isString) invalidResponse()
        val text = primitive.content
        val encoded = try { ProtectedMemoryCommunityWire.strictUtf8(text) } catch (_: Exception) { invalidResponse() }
        val size = encoded.size
        encoded.fill(0)
        if (size > maxBytes || !allowBlank && text.isBlank() || invalidText(text)) invalidResponse()
        return text
    }

    private fun invalidText(value: String): Boolean =
        value.any { it == '\u0000' || it.isISOControl() && it !in "\n\t" }

    private fun canonicalUuid(value: String): Boolean = runCatching {
        UUID.fromString(value).toString() == value
    }.getOrDefault(false)

    private fun positiveRevision(value: String): Boolean =
        value.matches(Regex("[1-9][0-9]{0,18}")) && value.toLongOrNull() != null

    private fun hasInput(instructions: String, form: MemoryBookNarrativeForm): Boolean =
        instructions.isNotEmpty() || form != MemoryBookNarrativeForm.EXISTING

    /** Builds and bounds the one existing wire field; EXISTING leaves user text byte-for-byte unchanged. */
    private fun combinedInstructions(form: MemoryBookNarrativeForm, instructions: String): String? {
        val modelInstruction = form.instruction
        val combined = when {
            modelInstruction == null -> instructions
            instructions.isEmpty() -> modelInstruction
            else -> "$instructions\n$modelInstruction"
        }
        val bytes = try { ProtectedMemoryCommunityWire.strictUtf8(combined) } catch (_: Exception) { return null }
        val valid = try { bytes.size <= MAX_INSTRUCTIONS_BYTES && !invalidText(combined) } finally { bytes.fill(0) }
        return combined.takeIf { valid }
    }

    companion object {
        private const val MAX_INSTRUCTIONS_BYTES = 4096
        private const val MAX_OUTPUT_BYTES = 64 * 1024
        private const val MAX_CHAPTERS = 24
        private const val MAX_SOURCES = 96
        private const val EDITORIAL_CONTEXT_PROFILE = "memoir_editorial_v1"
        private val JOB_STATES = setOf("queued", "running", "ready", "failed", "cancelled", "stale")
        private val ACTIVE_JOB_STATES = setOf("queued", "running")
        private val OPAQUE_ID = Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    }
}
