# PhotoHouse household AI development plan

PhotoHouse should help a small family find memories, clarify what they mean,
and prepare stories from evidence they choose. Several members may interact
with the assistant at the same time. Conversation privacy, useful responses
and graceful waiting matter more than maximizing model throughput.

This October 20 revision replaces the original engineering guide's fixed
three-tool **product** ceiling and Codex-first adapter sequence for PhotoHouse.
It keeps the guide's application authority, local inference, source preservation
and separate deployment gates. The original downloaded guide is retained as a
reference; its unrelated learning-project sections are outside this plan.
The implemented [PH-A1 v1 seam](LOCAL_AGENT_RUNTIME.md), its three domain tools,
wire profile, budgets and tests remain unchanged. New profiles below are
development contracts to complete, not enabled capabilities.

## Household operating model

The expected workload is modest overall, with overlapping independent family
conversations rather than every member generating at once. Do not turn this
into an account-count limit or assume a daily request quota. Test a few dozen
open client sessions and several overlapping AI submissions separately from
the number of model calls that the host can execute simultaneously.

Use the existing application, authenticated accounts/libraries, workspace store
and receipt/recovery paths. Keep one application owner for optional assistant
work in the initial implementation. Each account/library/thread has separate
context, result handles, revisions and authorization checks. A room or family
relationship does not grant access to another member's private thread or an
unconfigured TV audience.

An open conversation consumes no generation slot while its member is reading,
editing or answering a clarification. Release model resources after each
bounded turn; retain conversational state in the application. Browsing,
deterministic search and authorized result recovery must remain available while
optional inference is busy or unavailable. Existing storage/authorization
failures still receive their truthful errors.

Start with one admitted optional generation at a time, shared across the new
assistant profiles. This is an initial admission setting to measure, not a
one-user architecture or a claimed GPU capacity limit. Evaluate two concurrent
generations only if native memory, latency, output quality and competing-worker
measurements justify it. No horizontal scaling, distributed queue, second
conversation database or agent delegation is needed for the initial household
design.
Model/provider processes must use the qualified local backend without cloud
fallback. Literal localhost routing is insufficient evidence. Keep household
prompts, media, source words and drafts out of telemetry and public diagnostics;
qualify retention and outbound destinations for each selected component.

## Capabilities follow workflows

Every profile gets a versioned exact list of domain operations, argument and
result schemas, authorized sources/effects, deadlines and invocation limits.
The list may grow or shrink with a reviewed user task. Three names is not an
enduring target; an unrestricted operation is not safe merely because it is
the only tool.

| Workflow | Useful model work | Application authority | Development status |
| --- | --- | --- | --- |
| PH-A1 media-search v1 | Exercise the existing search and outcome selection seam | Canonical interpretation, clarification, scope, results and final receipt | Implemented default off; retain as regression/integration fixture |
| Find and recollect, later profile | Propose typed conditions, identify ambiguity, suggest explicit refinements | Validate person/date/media/exclusion conditions and execute protected queries | Define a separate proposal contract before implementation; do not change v1 silently |
| Selected-source story preparation | Draft ordered narration and questions using an explicit source snapshot | Resolve source identity, validate citations/current revisions and return a review-only proposal | First product-value candidate; [PH-A4 contract](SELECTED_SOURCE_STORY_DRAFT_CONTRACT.md) |
| Review and save | Help explain proposed wording and uncertainty | Existing explicit author review, permissions, revision checks and idempotent Save | Preserve existing save/adoption flows; no autonomous save/share/publish tool |

The search v1 model cannot rewrite the query, author a clarification or produce
a different final result. Its integration checks cannot establish better
language understanding or fewer user actions. Keep deterministic search as the
baseline. Reliable exclusion and clarification behavior remain prerequisites
for any richer retrieval profile; a new model must not reinterpret an
unsupported exclusion as a positive clue or silently broaden the search.

For story preparation, first compare against the existing
[saved-story drafting journey](AI_STORY_COMPLETION.md). It already has explicit
job submission, proposal review/adoption and saved-context recovery contracts.
PH-A4's selected-source, unsaved first-draft operation is a distinct gap to
justify, not permission to duplicate that worker, job queue or save flow. Reuse
the narrative validator/provider boundary and authorized source services. A
single structured generation may complete this task without any agent loop.
The existing durable jobs require a saved story/book and a positive base
revision; an unsaved PH-A4 target cannot be inserted into that lifecycle.
Sharing its worker would need an explicit immutable-snapshot adapter returning
ephemeral output without mutating a saved story or adopting durable job receipts.

## Runtime helpers and enforcement

Review both the model-visible interface and actual executable capabilities.
They are separate assertions. Extra presentation increases prompt/selection
cost and needs justification; it is not automatically proof of a private read.

| Capability class | Initial policy | Evidence required |
| --- | --- | --- |
| Workflow domain operations | Exact versioned allowlist with application checks at every call | Forced wrong-name/argument/scope/revision cases, valid calls and current-source disclosure |
| Local planning/bookkeeping helpers | Eligible for individual review if bounded and needed | Prove no extra file/network reads, writes, subprocesses, delegation or private retention; count work against the run budget |
| Clarification helpers | Produce an application-owned pending question and end the current turn | Persist/recover the question under its original scope; no indefinitely waiting child or held model slot while a human answers |
| Generic MCP resources | Deny by default; a later source-read operation must use explicit scoped references and a bounded schema | Force enumeration/read attempts, cross-server/reference attempts and stale/revoked access; no implicit arbitrary resource access |
| Shell, patch, filesystem, browser/network, deployment and delegation | Outside the initial product profiles | Denied dispatch or demonstrably unreachable registration; hidden definitions and prompts alone are insufficient |

Unknown helpers remain denied or make that runtime ineligible until classified.
A helper that starts another agent, retains private state or reads resources is
not pure bookkeeping. Any future delegated work must inherit scope and a shared
budget; delegation is not required by the household workload.

The [recorded Codex probe](LOCAL_AGENT_QUALIFICATION.md) still fails its original
three-tool policy. Its forced resource request reached the fixture and was
denied; no family-data disclosure was exercised. This policy revision neither
turns that record into a pass nor proves Codex unsuitable. A candidate needs new
profile-specific visibility, forced-dispatch, local-backend, retention and
native-lifecycle evidence. Keep runtime choice open. Implement a custom loop
only if the needed workflow and measured integration cost justify it.

## Shared inference admission and overlapping requests

PH-A1 currently has one nonqueued process lane. PH-A4 separately proposed one
generation lane. Before enabling both, give their new inference work one shared
application admission owner, with per-profile budgets. Independent locks must
not permit both profiles to over-admit the same provider. Identical request IDs
join their existing owner; conflicting request digests remain conflicts.

Several active conversations need understandable waiting behavior. The proposed
interactive scheduling target is one active generation and at most four waiting
turns across accounts, with at most one waiting turn per account. Waiting expires
after at most 20 seconds. These are initial bounded test settings, not measured
capacity or existing API behavior. Use fair ordering among accounts, never an
unbounded queue, background resubmission or automatic retry storm. An already
owned duplicate consumes no additional waiting slot.
The 20 seconds bounds admission waiting, not end-to-end completion. A long
running draft can cause waiting requests to expire; preserving input and
reporting that outcome is essential. Do not promise four fast model responses
from one execution slot.

Complete a separately negotiated waiting/recovery contract before adding that
scheduler. Current v1 does not gain a queued wire state or different admission
semantics. The contract must specify:

- Waiting owns only bounded request identity, expected revisions and source
  references in the application, not copied source words or a cached authorized
  source snapshot. It holds no database transaction, generation slot or workspace
  lease. Waiting time is included in reported elapsed time and has a fixed deadline.
- Validate permission before admission to waiting, then reauthorize and compare
  expected revisions/source choices when promoted. Resolve the immutable source
  snapshot only then, and revalidate before returning output. For profiles that
  actually reserve assistant workspace turns, start that lease only after
  admission to execution. PH-A4's ephemeral operation does not acquire a
  workspace lease merely by sharing generation admission. Waiting never renews
  an existing lease, query interpretation or source snapshot.
- Look up durable execution/replay and transient waiting ownership before fresh
  admission checks. Duplicate waiters join; an incompatible request conflicts.
  A completed receipt is recovered even if new admission is disabled.
- Distinguish a volatile waiting acknowledgement from a durable accepted
  execution. Define GET/retry/expiry semantics and client capability negotiation;
  an API restart cannot promise that an in-memory waiting turn survived. Retain
  the member's input/selection and require deliberate resubmission when the
  original outcome has been reconciled.
- Scope loss, logout, changed sources or an explicit authenticated cancellation
  invalidate waiting work. Navigation/disconnect detaches a waiter; it is not
  a cancellation command. Define any true cancel operation separately. Retain
  ownership of already admitted work through finalization
  and cleanup; uncertainty quarantines the shared lane, rather than bypassing it
  through another profile. A confirmed commit is not rolled back by cancellation.
- On full/expired/unavailable admission, use the negotiated supported response
  and retain the member's input/selection. Keep ordinary browsing/search available.
  Long story preparation should reuse the existing job path where appropriate,
  with its own durable semantics; an unsaved PH-A4 target cannot use those jobs
  without a new lifecycle contract. Do not wrap a durable job in a second queue.

The new source contract must define the actual supported wire vocabulary and
single ownership handoff before coding waiting. Four queued turns is not four
new reservations. Existing 60-second work/10-second cleanup proposals remain
separate from the 20-second wait. A workspace profile must fit its execution
lease after acquisition. The existing narrative worker's provider timeouts and
300-second durable job lease are different contracts, not substitutes for these
deadlines. Report queue wait, inference and cleanup separately.

This application owner is not cross-process GPU coordination. Inventory actual
narrative/title/companion workers and caption/face/OCR/transcription consumers
before selecting a provider admission mechanism. Reuse a verified shared
resource policy where available, or explicitly coordinate/refuse conflicting
work. Separate workers and existing durable jobs do not inherit an in-memory
API semaphore. Shared-server capacity and effective model-stop signals remain
native qualification gates, including when a process is killed or restarted.

## Evaluation for a small household

These are proposed synthetic cases, not load-test results or production limits.
Use independent fictional accounts, libraries and threads. Keep per-account
observations; aggregate averages cannot hide disclosure or starvation.

| Cohort | Proposed check |
| --- | --- |
| 1, 4, 12 and 32 open client sessions | Ordinary browse/search/recovery remains usable and authorization/context stay isolated; an idle session does not reserve inference |
| 2 and 4 overlapping AI submissions | Exercise actual admission, fair waiting/promotion or current v1 busy behavior; no accidental parallel execution beyond the configured provider limit |
| 8 simultaneous submissions | Saturation case: bounded waiting/refusal, preserved input, no hidden background work or automatic retries |
| Same request from two clients | Join/recover one execution and one original interpretation, without consuming another slot |
| Permission/source changes while waiting and running | Reject promotion/disclosure or fence the late result; never rebase a draft to new sources |
| Long draft overlaps short search/clarification | Ordinary browsing, deterministic search and existing playback remain available; measure waiting and fairness, do not assume model preemption is safe |
| Existing durable saved-story generation overlaps PH-A4/assistant submission | The already-running job retains its owned capacity; new optional work waits/refuses within its negotiated bounds. Verify the admission policy reaches the separate worker/provider; an API lock alone cannot establish this. Include title/companion consumers when they share that capacity. |
| Distinct requests from one account | Enforce one waiting turn for that account without dropping an existing request or treating different IDs/digests as duplicates |
| Provider fault, unknown stop and API restart | Keep retained durable receipts recoverable; bound/expire waiting and refuse new inference until resource reconciliation |

Record cold/warm provider times, queue wait, end-to-end latency, completion,
refusal/expiry rates, per-account wait, errors and peak RAM/VRAM. Before native
testing, freeze the desired normal-path responsiveness and successful-overlap
thresholds for the exact workflow; do not invent a throughput claim from the
session count. The existing [PH-U0 search comparison](LOCAL_AGENT_ACCEPTANCE.md)
remains a fixed baseline/oracle. Add a separate story comparison: manual versus
existing saved-story drafting versus selected-source preparation, when each is
implemented. Include review/edit time and all failed/unavailable attempts.
Source/citation eligibility is not proof that generated statements are true;
human review and factual quality remain separate acceptance criteria.
One-process fixtures establish application-owner behavior only. The
cross-worker/provider overlap case needs native evidence before capacity is
qualified; a synthetic occupancy signal is not proof of shared GPU admission.

## Revised implementation order

| Step | Deliverable | Completion boundary |
| --- | --- | --- |
| PH-P1 workflow and household scope | This plan, source reuse map and separate capability/helper policy | Plan only; no runtime control is relaxed |
| PH-P2 story comparison and exact capability contract | Freeze representative EN/ZH/mixed source bundles, manual/existing-flow baselines, benefit thresholds and exact draft profile | Copy-ready service/client delta; clarify the unsaved-first-draft gap before duplicating code |
| PH-C0 shared admission and waiting contract | Inventory provider consumers; define ownership, bounded waiting, versioned recovery and restart behavior | Contract plus generated overlap tests before a new queued profile is shipped |
| PH-A0 per chosen candidate | Qualify the exact direct provider or coordinator, effective local model/server, helpers if any, resource admission, retention and native stop/restart | Reproducible scoped evidence; original Codex failure retained |
| PH-A4 source implementation | Reuse or extend the authorized story/narrative boundary with immutable sources, injected fixtures and shared admission | Default-off synthetic application checks; no provider installation or household deployment |
| PH-A2 only where useful | Add a replaceable coordinating runtime if a workflow demonstrably needs multiple domain operations | Exact profile-specific capability/runtime qualification; no required Codex/MCP rewrite for one structured draft |
| PH-A3 one client journey | Selected sources, prepare/wait, inspect/edit, review, explicit save and recover | Useful measured benefit plus matching native provider and independent family/device acceptance |
| Later retrieval improvement | Typed intent/clarification proposals with exclusion-preserving validation | Separate relevance and regression gates; no silent semantic-search activation |

The [PH-P2 acceptance contract](SELECTED_SOURCE_STORY_ACCEPTANCE.md) now freezes
six story comparison cases, adoption thresholds and the next provider input
delta. The [PH-C0 contract](HOUSEHOLD_INFERENCE_ADMISSION.md) records current
consumer ownership and a tested admission primitive. The optional PH-A4 app
lifecycle now constructs one nonqueued gate; other profile owners, provider-wide
coordination and a public waiting protocol remain separate integration work. Neither comparison has model/UX
measurements yet. The narrative-only bundle version 3 and isolated authorized
snapshot core are implemented with synthetic checks. The isolated PH-A4
operation owner now adds exact retries, fixed expiry and injected shared
admission. Optional app startup/shutdown, logout and membership revocation
wiring now retain that owner and its shared gate. The protected prepare/cancel
HTTP v1 routes now have a separate default-off opt-in and synthetic-provider
coverage. Client integration, native stop proof and cross-process resource
coordination remain separate; no native provider is installed or selected.

PH-C0 integration and candidate qualification can proceed alongside fixture work.
The first source implementation can remain synthetic while native host access
is unavailable. Shipping or activating it cannot. Existing upload, indexing,
worker-recovery and process-safe household connection workstreams retain their
owners and priorities. Deployment, model installation, service control and
publication remain separate operations.
