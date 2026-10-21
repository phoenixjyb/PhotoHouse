# Household inference admission contract

PH-C0 defines one process-local admission owner for optional PhotoHouse model
work. The internal [admission component](../server/backend/app/access/inference_admission.py)
is included in the source-only API runtime package. With an explicitly injected
async selected-story provider, the app constructs one nonqueued gate and draft
owner during its lifespan. The default app constructs neither; no HTTP profile,
worker, database, provider discovery or live configuration is changed. PH-A1 v1
remains nonqueued and keeps its existing independent supervisor.

The [selected-source draft owner](SELECTED_SOURCE_STORY_DRAFT_CONTRACT.md#implemented-internal-operation-owner)
adds process-local retry/expiry/session ownership and explicit cleanup proof.
Its [app lifecycle](../server/backend/app/access/selected_story_lifecycle.py)
retains the shared instance in `app.state.inference_admission`, closes it at
shutdown and never replaces a closed or quarantined owner on app reuse. The
protected prepare/cancel API has a separate default-off opt-in and uses
that same owner; it adds no waiting or save authority. Other runtime consumers
below remain independent until their native integration is qualified. This
does not establish GPU exclusion across processes.

## Ownership and API

Construct one `InferenceAdmission` for one application event loop, and share
that instance among participating profile owners. It admits at most one
execution and four waiting operations, with at most one waiting operation per
authenticated account across libraries. A caller can lower the waiting count
or deadline; ceilings are four and 20 seconds. Waiting is global FIFO among
eligible distinct request owners. Idle conversations hold no permit.

`AdmissionIdentity` contains only host-validated account/library/request IDs,
profile and the canonical request digest. The digest must include the complete
immutable request meaning, including thread/selection/revisions as appropriate
to that profile. Neither the identity nor the scheduler is authentication.
Store no source words, credentials, selected-source snapshot or model prompt in
the scheduler. Each profile owner must authorize before acquiring and again
after promotion, then resolve and bind its current source snapshot.

`await acquire(identity, wait=True)` returns a unique `AdmissionPermit`.
`wait=False` refuses occupied capacity immediately. Both modes preserve FIFO;
a fresh call cannot jump waiting work. Bounds, duplicate/conflicting identity,
expiry, closure and quarantine produce fixed internal `AdmissionError.reason`
values, not new wire enums. They contain no request/account data.

The application operation owner must register and look up its durable or
transient request before calling acquire. A matching duplicate joins that
owner's outcome; it must not execute acquire a second time. The primitive
rejects `duplicate_owned` rather than give two callers the same execution
permit; a changed digest/profile for the same scoped request conflicts. It
retains no completed-result cache and does not replace application receipts.

The owner calls `permit.finish(reconciled=True)` only after its own protected
work and resources have settled. Finishing twice cannot release someone else's
permit. Canceling an admitted owner is not reconciliation and never releases
its permit automatically. `finish(reconciled=False)` quarantines the scheduler,
fails queued waiters and retains the active permit until the owner settles it.
Later settlement does not clear quarantine. No reset/resume bypass is exposed;
replacement requires the separate native reconciliation/lifespan design.

`close()` rejects waiting/fresh admission and keeps active ownership intact.
It neither kills a provider nor cancels an admitted operation. The application
lifespan owner performs invalidation, cleanup and exact-result recovery. The
count-only `state()` is developer evidence, not a family-facing status API.

## Waiting and cancellation

The absolute waiting deadline starts once on first enqueue. Duplicate checks,
unrelated releases or promotion do not reset it. Overdue entries cannot be
promoted even if a timer callback was delayed. Waiting acquires no database
transaction, workspace lease or generation resource. The admitted owner's
profile starts its own execution deadline; a waiting deadline is not a promise
of end-to-end response time.

Canceling an acquire task removes that waiting entry. If cancellation races
with promotion before the acquire returns, the primitive reclaims the unused
permit and promotes the next eligible waiter. This is safe because it never
starts provider work, and the caller may not start work before acquire returns.
After acquire returns, cleanup belongs to that caller even if it is canceled.

An HTTP navigation/disconnect must not cancel the operation-owner task merely
because it was awaiting a permit. A future handler detaches its waiter from
that owner, as PH-A1 already does for accepted work. A true user cancel requires
a separately authenticated, correlated operation and client contract. No new
public cancellation, queued acknowledgement or GET state is introduced here.

The primitive keeps only active/waiting identity state. A canceled, expired or
reconciled operation frees its identity slot. Safe retry after loss/restart is
therefore the application owner's responsibility: reconcile durable execution
first, or treat a lost volatile PH-A4 preparation as a new reviewed proposal.
Do not interpret a scheduler refusal or identity removal as proof that a saved
mutation never happened.

## Integration prerequisites

Before connecting a new profile, define its existing/negotiated response mapping,
request registry, detach/cancel rules, source revalidation and owner-to-permit
handoff. Waiting must not add `queued` to strict existing response grammars.
For an assistant workspace profile, reserve its execution lease only after
admission; PH-A4 does not acquire a workspace lease merely to share capacity.
The saved-story job's durable state/300-second lease remains a different contract.

An event-loop-local component is not a cross-process GPU lock. Inventory actual
consumers below and connect a qualified resource owner before activating
overlapping API and worker inference. An already-running saved-story worker
retains its capacity; new optional work waits/refuses within its own bounds.
Calling two independent scheduler instances does not share capacity. Source
tests prove one-instance behavior only; native provider-stop, crash/restart and
cross-worker exclusion remain unqualified.

## Current source consumer inventory

This is a source audit at the PH-P1 revision, not an inventory of running
household processes. Provider endpoints, model residency and host ownership
still need native verification.

| Consumer | Existing owner and scheduling scope | Shared-capacity consequence |
| --- | --- | --- |
| PH-A1 | [AgentSupervisor](../server/backend/app/access/assistant_agent.py), one app-process lane and owned cleanup | No cross-process model slot |
| Internal selected-source drafts | [DraftOperations](../server/backend/app/access/selected_story_operations.py), injected shared scheduler, exact retries and retained cleanup | App-owned process-local instance on explicit provider injection; logout/revocation/shutdown fencing, with a [default-off async adapter](SELECTED_SOURCE_STORY_LOCAL.md) requiring separate native ownership proof; the [default-off process owner](SELECTED_SOURCE_STORY_NATIVE_OWNER.md) has synthetic cleanup/quarantine evidence, with provider binding still unqualified |
| Saved narrative/companion | [process_job](../server/backend/app/access/memory_processing.py) and [worker](../server/scripts/run_memory_worker.py), durable per-job 300-second lease | Distinct worker jobs may call inference concurrently; a job lease is not global admission |
| Story titles | [title_suggestions](../server/backend/app/access/story_workspace.py), per-app `threading.Lock` | Does not coordinate with saved jobs or another API process |
| Approved face/image/video vector work | [image worker kernel_lock](../server/scripts/run_approved_image_embed_worker.py), [face lock](../server/scripts/run_approved_face_worker.py), [video worker](../server/scripts/run_approved_video_embed_worker.py), OS file lock at the same database-derived path | Cross-process coordination exists for participating approved media workers; it does not include narrative, assistant or caption HTTP providers |
| Released caption work | [released worker](../server/scripts/run_released_caption_worker.py), serial task children with Windows Job bounds | Bounds the owned child, not the independent HTTP model server or other invocations |
| ASR and contribution polishing | [local annotation adapters](../server/backend/app/access/annotation_local.py), per-request/item timeout | Direct HTTP calls; no shared model slot established by source |
| Semantic text provider | [provider app](../server/backend/app/access/semantic_provider_transport.py), per-process executor/busy flag | Local provider-process exclusion, not global GPU ownership |
| OCR | No OCR-named application worker/provider identified in the inspected source | Check separately managed native components before declaring it absent |

[Model binding](../server/backend/app/access/model_binding.py) projects settings;
its resource declarations do not enforce runtime capacity. The reusable OS
lock for approved vision work cannot simply be claimed as an Ollama/model-wide
lock. Connecting this component to provider users requires a specific
cross-process coordination and stop/reconciliation design, with forced overlap
tests for an already-running saved-story job and a new assistant/draft request.
The existing [authentication admission](../server/backend/app/access/admission.py)
guards pre-KDF login/registration with a durable database slot. It is a
different resource boundary and must not be repurposed as model admission.

## Source acceptance

The CPU suite must exercise FIFO across accounts/profiles, four-total and
one-per-account waiting bounds, fail-fast mode, duplicate versus conflict,
expiration and canceled-waiter removal, cancellation at promotion, admitted
cancellation retaining ownership, stale double release, closure and sticky
cleanup quarantine. Tests must not call models or infer native GPU capacity.
The component does not schedule user conversations, implement a job queue or
make a nonlocal model local.
