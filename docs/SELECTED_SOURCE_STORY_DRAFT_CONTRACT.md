# Selected-source story draft contract

This contract defines a bounded, review-only operation for preparing a story
from media and source evidence the author selected. The end-to-end PH-A4 service
now has a default-off prepare/cancel API, authorized snapshot core, narrative
input and app/session operation owner. Its [optional Web editor](SELECTED_SOURCE_STORY_UI.md)
now adds a default-off source journey; native-provider and family/device
qualification remain separate. It leaves story ownership,
current source authorization, revision checks and explicit save in PhotoHouse.
The current application facts below were checked against
[`story_workspace.py`](../server/backend/app/access/story_workspace.py),
[`memory_stories.py`](../server/backend/app/access/memory_stories.py),
[`memory_narrative.py`](../server/backend/app/access/memory_narrative.py), and
the [chapter source-choice contract](CHAPTER_SOURCE_CHOICES.md).

The preparation boundary is an application-owned service. It may be called by
a later qualified coordinator, but its request and result contracts do not
depend on PH-A1's media-search tools, final-selector format, or runtime. The
service receives only an explicit authorized snapshot and returns an ephemeral
proposal. It has no save, publish, source-search or authorization-changing
operation.
The revised [household plan](LOCAL_AGENT_DEVELOPMENT_PLAN.md) makes this a first
product-value candidate alongside the existing saved-story drafting path. It
does not require a general agent loop or PH-A1's three-tool ceiling. Reconcile
shared provider admission and the story-specific baseline before implementation.
The [PH-P2 acceptance contract](SELECTED_SOURCE_STORY_ACCEPTANCE.md) freezes that
comparison and specifies the required internal draft-bundle variant. The
[PH-C0 admission contract](HOUSEHOLD_INFERENCE_ADMISSION.md) defines the process-local
capacity primitive; this HTTP profile adds no application waiting queue.

## Existing source and save behavior

`POST /story-workspace/preview?library=…` accepts selected `asset_ids`,
`theme`, `language` and `title`. It reauthorizes the library and each selected
asset, returns current item evidence and a `selection_revision`, and derives a
bounded outline. It does not generate narrative prose or save a story.
`POST /story-workspace/related-media?library=…` returns a small page of media
sharing selected assets' recorded capture day; a suggestion is not selected
until the author explicitly adds it and obtains a new preview.

The optional `GET /story-workspace/source-capabilities?library=…` reports
`chapter_sources_v1`. In that profile, the author opts into
`source_policy: "chapter_sources_v1"` and chooses `evidence_ids` per chapter;
empty choices are valid. The current title-suggestion path can validate these
choices and rechecks the selection after inference, but it proposes titles,
not narrative drafts. The current narrative validator can validate ordered
chapter prose and chapter-level source IDs against a supplied bundle; that
validation establishes eligible provenance pointers, not factual entailment.

Saved stories use `POST /memory-stories?library=…&source_review=1` for create
and `PUT /memory-stories/{story_id}?library=…&source_review=1` for edit. The
closed save body includes `title`, `theme`, `language`, ordered `asset_ids`,
`chapters` as a JSON-encoded string, `selection_revision`, `revision`,
`mutation_id`, and `source_policy`. `asset_ids` is the current
comma-separated string form accepted by `_selection`. Each chapter in the
decoded array carries `id`, `title`, `narration`, `asset_ids` and
`evidence_ids`. The route accepts a 384 KiB request body and existing story
responses are bounded at 256 KiB. Saves reauthorize and compare current
selection and story revisions. A `mutation_id` is recorded with the request
digest: retry the exact same body and mutation ID after an unknown response;
reuse of that ID with a different body conflicts. A matching retry can return
the story's newer current revision if a later family edit has occurred.

Saved content stores editorial text, selected media and evidence IDs, with
source digests for current-reference filtering. It does not copy source words
into the saved revision. Reads hydrate current authorized evidence. Keep
family-authored wording, accepted contributions, transcripts, AI captions and
generated prose visibly and structurally distinct. A source byline belongs to
its source; generated wording must never inherit it.

## Proposed request and immutable snapshot

The proposed internal operation accepts a strict versioned request. The
authenticated account and library come from the application boundary, never
from model output. Source and media IDs below are references to resolve inside
the current authorized library, not bearer capabilities.

~~~json
{
  "version": 1,
  "request_id": "22222222-2222-4222-8222-222222222222",
  "target": {"story_id": null, "base_revision": "0"},
  "selection": {
    "asset_ids": ["17000017", "23000023"],
    "selection_revision": "<64 lowercase hex characters>",
    "source_policy": "chapter_sources_v1",
    "chapters": [
      {"id": "chapter-1", "title": "Preparing the bed", "asset_ids": ["17000017"], "evidence_ids": ["family-synthetic-note-4"]},
      {"id": "chapter-2", "title": "Watering the plants", "asset_ids": ["23000023"], "evidence_ids": ["caption-synthetic-8"]}
    ]
  },
  "theme": "everyday",
  "language": "en",
  "title": "A day in the garden",
  "author_direction": "Keep the wording gentle and brief."
}
~~~

All IDs and text in this example are synthetic. A request has one to six
ordered chapters; each chapter has one to four selected media items and no
more than twelve distinct evidence IDs. Flattened chapter media must exactly
equal the selected media in the same order. Evidence IDs must belong to the
current selected items for that chapter. Empty evidence lists are allowed and
mean that the chapter receives no picture-linked evidence. `source_policy` is
required for this reviewed workflow. These limits align with the existing
story/source contracts; the service must reuse current validators where their
meaning matches.

Each chapter's required `title` comes from the current editable preview outline,
including any author edits. `build_outline` supplies the initial wording.
Capture that exact title in the request and snapshot, and copy it unchanged to
the client draft. The narrative adapter has no chapter-title output field and
cannot invent or replace those titles. Each is nonblank, at most 160 Unicode
scalar values and 512 UTF-8 bytes, compatible with the narrative bundle and save
contracts.

`author_direction` is a required string, empty when unused, and limited to
8,192 UTF-8 bytes to match the existing narrative bundle's `instructions`
bound. It can guide style or focus only; it cannot add evidence, authority or
actions.

Bind `request_id` to a canonical digest of the authenticated account, library,
target story/base revision, ordered media, source policy, chapter partitions,
chapter titles and evidence IDs, language, theme, title, and any bounded author
direction.
Within that scope, an identical ID and digest joins the active operation or
recovers its retained ephemeral result. Reusing the ID with a different digest
returns a conflict; it never changes the operation's source snapshot. After an
ephemeral result has expired, the same ID may start a new preparation only
after the same request digest and current source snapshot are revalidated. The
new prose is not guaranteed to match the earlier run. Surface it as a new
proposal, assign a new `draft_id`, and require full review again.

PH-A4 proposes one process-wide, nonqueued application admission lane across
accounts and libraries, held for one generation at a time. The proposed
end-to-end generation deadline is 60 seconds from admission, covering snapshot
resolution, adapter work, post-generation revalidation and response assembly.
No request may wait in an application queue. On timeout, cancellation or scope
invalidation, revoke the operation capability and fence all late output. Keep
strong ownership of the operation and its child resources until they stop or
are reconciled; do not release the lane while cleanup is uncertain. If a child
cannot be confirmed stopped, mark the optional lane unavailable for new work.
These bounds are implemented in the default-off selected-source operation
owner; they do not qualify a native runtime or govern nonparticipating workers.
The household revision requires this generation slot to share ownership with
other optional assistant profiles rather than use an independent lock. Its
future bounded waiting profile needs a separate negotiated contract and starts
no workspace lease while waiting. Until that contract is implemented, the v1
nonqueued behavior and this generation deadline remain unchanged; an existing
saved-story job keeps its own established queue/lease semantics.

The server resolves the request into an immutable `SourceSnapshot` before
preparation. The proposed request envelope is capped at 32 KiB; it contains
source references, not caller-supplied copies of source text. The validated
narrative bundle is separately capped at the current `MAX_BUNDLE_BYTES` of
64 KiB, with no more than 96 distinct source records. Each source text is at
most 8,192 UTF-8 bytes, each author/byline at most 256 bytes, and the aggregate
selected source-text budget is proposed at 48 KiB to leave room for metadata
and instructions inside that bundle. Current preview evidence is already
projected to at most 1,800 UTF-8 bytes per item source. Reject over-budget
requests before invoking a model or coordinator.

~~~json
{
  "version": 1,
  "request_id": "22222222-2222-4222-8222-222222222222",
  "library_id": "synthetic-library",
  "target": {"story_id": null, "base_revision": "0"},
  "selection_revision": "<64 lowercase hex characters>",
  "source_policy": "chapter_sources_v1",
  "media": [
    {"asset_id": "17000017", "kind": "image", "recorded_at": "2024-05-12", "stack_id": null},
    {"asset_id": "23000023", "kind": "video", "recorded_at": "2024-05-12", "stack_id": null}
  ],
  "chapters": [
    {
      "id": "chapter-1",
      "title": "Preparing the bed",
      "asset_ids": ["17000017"],
      "sources": [
        {"source_id": "family-synthetic-note-4", "selected_asset_ids": ["17000017"], "source_kind": "family_note", "source_revision": 3, "source_digest": "<sha256>", "byline": "Synthetic Aunt", "text": "We planted beans together."}
      ]
    },
    {
      "id": "chapter-2",
      "title": "Watering the plants",
      "asset_ids": ["23000023"],
      "sources": [
        {"source_id": "caption-synthetic-8", "selected_asset_ids": ["23000023"], "source_kind": "ai_caption", "source_revision": null, "source_digest": "<sha256>", "byline": null, "text": "A green watering can beside the raised bed."}
      ]
    }
  ]
}
~~~

This is a proposed normalized operation snapshot, not the current preview wire
shape. The current preview exposes family evidence and AI or family-edited
captions; it does not expose transcripts as selected evidence. PH-A4 v1 may
consume only evidence actually returned by the current authorized source
service. Use `source_kind: "family_note"` for a family note and
`source_kind: "ai_caption"` or `"family_edited_caption"` for captions, based on
the current record. An accepted contribution or transcript can enter a later
version only through a separately reviewed authorized source contract that
preserves its original attribution and derived-text status. `source_revision`
is nullable because not every evidence type exposes a revision.
`source_digest` is a server-computed digest of the canonical current source
descriptor, never a model-supplied value. `selected_asset_ids` records where a
canonical source is eligible for this chapter; it is not a replacement for its
original `origin_asset_id` or byline when those exist. Keep original note text
and byline on the host; send only the selected, bounded snapshot to the approved
preparation adapter.

For a stack selection, the snapshot must enumerate every media member actually
selected for the story, preserving its ordered member asset IDs and its own
current evidence. A cover or representative asset is only a display choice.
Do not silently expand a cover into unreviewed members, collapse members to
the cover, or treat the cover's source evidence as evidence for its siblings.
If the existing selection UI cannot express and confirm that member set, PH-A4
must remain unavailable for that stack until the user selects the members.

Before provider work starts, the application verifies membership, source
eligibility, exact selection order, chapter partitions, source policy and
selection revision. It takes this snapshot in a bounded read operation, then
releases the database transaction before model or coordinator I/O. Before
returning any draft, it reacquires current authorized state and compares the
selection revision, ordered media, chapter source choices and source digests.
Any difference yields a conflict and discards the generated output. Do not
refresh the snapshot automatically and apply old prose to new sources.

### Implemented internal snapshot core

[`selected_story_snapshot.py`](../server/backend/app/access/selected_story_snapshot.py)
implements `validate_request`, `resolve_snapshot` and `revalidate_snapshot`.
Resolution uses the current `AccessRuntime` connection factory and one owned
read transaction. It requires `story.write`; an existing target also requires
the saved-story edit rule and exact base revision. Every selected media item and
each chapter's explicit evidence choices are checked through `collect_items`.
No source text, byline, digest or media metadata is accepted from the caller.

The group profile remains the runtime's existing explicit setting. With it on,
the existing shared-note resolver checks all group members and source origins.
With it off, only current direct sources are eligible. Original note bylines
are resolved in that same authorized transaction in either profile. Canonical
shared notes are deduplicated in the provider bundle; chapter snapshot records
retain their distinct eligible `selected_asset_ids`. A caption retains its
derived source kind and its own media origin, with no invented byline.

The process-local `SourceSnapshot` stores immutable canonical JSON bytes and
keeps source text out of its representation. Its accessors return detached
copies. The reference-only request is capped at 32 KiB, the deduplicated narrative
bundle at 64 KiB, and the host snapshot at 384 KiB; this last bound accommodates
one shared source displayed in several chapters without increasing the 48 KiB
deduplicated selected-text budget. The host allocates a fresh operation UUID
separate from the client request ID. Only explicit asset IDs are resolved;
`stack_id: null` means no stack expansion was performed, not a claim that an
asset has no stack relationships.

The request digest binds the authenticated account, library and canonical
request, including target, chapter titles, source choices and author direction.
Source digests cover the current bounded preview evidence descriptor and the
resolved origin, kind, revision and exact byline. They identify the selected
projection, not full original records or factual entailment. Caption records
expose no source revision; an edit that restores the identical current descriptor
cannot be distinguished from unchanged content. Revalidation opens a fresh
transaction, checks the same account and current permissions, then compares
membership state, target revision, selection and source descriptors. It returns
no replacement snapshot on a conflict. The existing selection revision also
includes unchosen current evidence and group dependencies, so changes to those
can conservatively invalidate preparation without sending them to the model.

The [synthetic snapshot tests](../server/tests/security/test_selected_story_snapshot.py)
exercise these checks without model, network or household data. This core is
included in the source-only API runtime package for the optional operation
owner. No DB writes, HTTP route, operation registry, retry recovery, expiry,
admission or generation are implemented in the snapshot core itself. The
operation owner resolves after admission and calls revalidation after provider
work before assembling a review result. Current token validity and account
binding do not replace operation/session lifecycle fencing on logout, account
switch, cancellation or a newer generation. Existing Save remains the final
write authority.

## Proposed draft and citation result

The preparation adapter's strict narrative output should reuse the existing
`validate_narrative` result grammar: `version`, `title`, ordered `chapters`
with `id`, `narration` and `source_ids`, `questions`, and
`needs_review: true`. Its source bundle uses the closed PH-P2 v3 input variant,
reusing chapter/content rules while preserving each source's original kind.
The host validates this output against the exact selected
chapter evidence IDs, then enriches it into the client result below. The model
echoes only supplied chapter IDs and selected source IDs in that closed output
grammar; the host validates and resolves those references. Its unsaved input
uses the PH-P2 bundle version 3, now supported only by the narrative validator
and provider path. The internal snapshot core constructs and authorizes this
input; an injected operation owner assembles the result below. The public
transport, native provider and client integration remain separate. The model cannot mint or
change identities, supply chapter titles, author citation metadata, choose
chapter media, or set revisions, expiry or review state. This keeps the current
validator useful while making the returned citation record server-derived.

Use these compatible limits, with PH-A4's story-specific bounds where they
are narrower: one to six chapters; no more than 24 selected media items; one
to four media items per chapter; no more than twelve selected source IDs per
chapter and 96 source records in the validated bundle; source text at most
8,192 UTF-8 bytes and author/byline at most 256 bytes; title at most 160
Unicode scalar values and 512 UTF-8 bytes; chapter title at most 160 scalar
values and 512 bytes; narration at most 6,000 UTF-8 bytes; no more than six
questions, each at most 512 bytes. The narrative bundle and validated model
output each remain at the current 64 KiB limit. The underlying provider response
reader is capped at 128 KiB. The enriched client result is capped at 256 KiB,
matching the existing workspace response bound. The separately proposed
request envelope remains capped at 32 KiB and total source text at 48 KiB.
These bounds are checked on UTF-8 bytes where the current validators do so;
the additional Unicode-character caps keep saved-story content within its
current contract.

The strict client result is an ephemeral proposal. Its source binding is
copied from the server snapshot, never generated by the adapter.

~~~json
{
  "version": 1,
  "request_id": "22222222-2222-4222-8222-222222222222",
  "draft_id": "33333333-3333-4333-8333-333333333333",
  "state": "needs_review",
  "expires_at": "<server-generated timestamp>",
  "selection_revision": "<64 lowercase hex characters>",
  "source_policy": "chapter_sources_v1",
  "title": "Planting beans together",
  "chapters": [
    {
      "id": "chapter-1",
      "title": "Preparing the bed",
      "narration": "We planted beans together.",
      "asset_ids": ["17000017"],
      "citations": [
        {
          "source_id": "family-synthetic-note-4",
          "selected_asset_ids": ["17000017"],
          "source_kind": "family_note",
          "source_revision": 3,
          "source_digest": "<sha256>",
          "byline": "Synthetic Aunt"
        }
      ]
    },
    {
      "id": "chapter-2",
      "title": "Watering the plants",
      "narration": "A green watering can stood beside the raised bed.",
      "asset_ids": ["23000023"],
      "citations": [
        {
          "source_id": "caption-synthetic-8",
          "selected_asset_ids": ["23000023"],
          "source_kind": "ai_caption",
          "source_revision": null,
          "source_digest": "<sha256>",
          "byline": null
        }
      ]
    }
  ],
  "questions": [],
  "needs_review": true
}
~~~

Every nonblank narration chapter must cite one or more source IDs selected for
that chapter and validated against its chapter media. A citation is an
eligibility/provenance link, not proof that every sentence is entailed. The UI
must let the author inspect the cited source and edit or remove generated
wording. A selected source can support more than one chapter without copying
or changing its original identity and byline. Keep authored wording distinct
from transcripts and generated narration in both the snapshot and review UI.
Never present a transcript as the speaker's authored words or generated prose
as source-authored wording.

Reject extra or missing fields, duplicate chapter/source IDs, reordered or
unknown chapters, references not in the immutable snapshot, citations attached
to the wrong media, incomplete chapters, oversized text, unsafe control
characters, stale digests, and any result that does not require review. Do not
let the adapter write `selection_revision`, source identity, revision, byline,
review state, save state or expiry. Validate its `source_ids` with the existing
narrative validator, then build citation objects from the immutable source
snapshot and check their media/source-kind binding on the host.

## Review binding, save and unknown outcomes

The review screen binds one proposal to the current account and library,
`draft_id`, target story and base revision, `selection_revision`, ordered media
and chapter layout, source-policy choice, per-chapter evidence IDs, title,
chapter titles and narration, and citation set. The client computes or stores a
canonical review fingerprint over those exact values. Any edit, source-choice
change, chapter/media rearrangement, scope change or source refresh clears the
review confirmation and requires a fresh review. This binding is a UI integrity
fence; it is not server authorization or a new permission.

After an explicit Save action, the client constructs the existing reviewed
save body from the approved proposal: copy the author-approved title and text,
the exact ordered chapter `asset_ids`, the selected evidence IDs, current
`selection_revision`, `source_policy: "chapter_sources_v1"`, and a fresh
`mutation_id`. For a new story, send `revision: "0"`; for an edit, bind the
existing story ID and current base revision. Do not include source words,
transcripts, citations as copied prose, model prompts, or provider diagnostics
in saved content.

The server's existing save transaction remains the final authority: it checks
`story.write`, current media and source availability, selection revision,
story revision and evidence eligibility. A stale source or revision returns a
conflict and preserves the local draft for reload/review. It must never
silently replace the selected evidence or save a prior proposal against a new
snapshot.

If the save response is lost or ambiguous, freeze the exact request body and
`mutation_id`; retry that exact pair or reconcile with the saved-story read
path. Do not mint a new mutation ID until the prior outcome is known. A
same-ID/same-body replay is the existing idempotent path. Same ID with a
different body is a conflict. If a matching replay returns a newer story
revision, show that current version and do not overwrite it with the stale
editor payload.

## Expiry, recovery and privacy

The prepared prose is volatile and is not an application record. The internal
owner sets `expires_at` once, 30 minutes after the result is issued; a future
client must honor this same bound.
This is a fixed absolute lifetime, not a sliding idle timer. At expiration,
clear the proposal and its review binding; a user can explicitly save an
ordinary local draft if that capability is already available. PH-A4 does not
add server draft persistence, background resume, conversation history or a
new recovery endpoint. If the response is lost before display, retrying the
same request ID may re-run preparation only after revalidating the identical
request and source snapshot; generation has no durable side effect and is not
guaranteed to reproduce the earlier prose. Treat a regenerated result as a
new proposal requiring full review. If the request is still running, join that
operation rather than start a duplicate. An app restart may require the user
to start preparation again.

Source words stay within the authorized application snapshot and the
specifically approved local preparation boundary. No source text, family
identity, private media, draft, prompt or citation is written to logs, Git,
analytics, shared runtime threads or an external service. Runtime qualification
must separately inspect provider, coordinator, crash and diagnostic retention.
The result sent to the client includes citation metadata and generated text,
not a copied source corpus. Clearing the ephemeral draft does not delete or
change originals, sources or saved stories.

### Implemented internal operation owner

[`selected_story_operations.py`](../server/backend/app/access/selected_story_operations.py)
implements `DraftOperations` with injected protected `SelectedStorySources`,
an asynchronous provider and the application's shared `InferenceAdmission`.
The optional app lifecycle constructs it only after explicit async provider
injection; the default app has no owner. It is included in the source-only API
runtime package. No model runner, new database write, saved-story job,
background restart recovery or native
capacity claim is added by that owner. Its default-off HTTP transport is defined
below.

The default household bounds are one admitted generation, no application
waiting, 60 seconds of work from permit grant, ten seconds to confirm cleanup,
16 active/retained proposal slots and 128 request identity records. At most
16 owned database reads may be outstanding, including detached authentication
and cached-result reads. Conversations at rest hold no permit. An occupied
shared lane returns a fixed internal busy error; this profile never bypasses
other profiles' admission or enables the primitive's optional waiting mode.

`prepare(token, library, request)` authorizes `story.write` before registering
or looking up the account/library/request identity. Exact active retries join
one owner; cancelling a response waiter detaches it. A changed request digest
conflicts. Every retained-result delivery reauthenticates the current session
and revalidates the source snapshot. No await separates the final scope checks
from returning a detached result. Futures retain notification only, with no
prose or exception traceback. Citation fields and chapter titles come from the
host snapshot; the provider supplies only the validated narrative grammar.

The result's UTC expiry and monotonic deadline are fixed at issue; a read never
extends them. Timer callbacks and lookup/delivery checks discard expired prose
and source snapshots. A compact digest/session/source-fingerprint tombstone
remains for 24 hours after the latest accepted execution. No active owner,
unexpired result or protected tombstone is evicted to admit new work; capacity
exhaustion refuses registration. The existing request can run again after
result expiry only with the exact request digest and freshly resolved matching
source/authorization fingerprints. It receives a new `draft_id` and needs full
review. Busy work that never started a provider may retry the same ID; provider
failure and explicit cancellation remain terminal for that ID. These are not
automatic model retries. After the bounded identity lifetime, or process
restart, old request identity is no longer remembered.

The provider contract is `async prepare(bundle, scope)` and
`async stop_and_reconcile(scope) -> bool`. The scope carries a host operation
ID matching the draft bundle, a fixed deadline and a cooperative cancellation
check. Exact `True` from cleanup is required on success as well as failure and
must certify that **all native work for the scope has stopped**. A cancelled
Python task, finished HTTP response or `asyncio.to_thread` wrapper is not that
proof. The optional [async local adapter](SELECTED_SOURCE_STORY_LOCAL.md) reuses the
narrative prompt/schema through a bounded async HTTP path. It requires an
explicit injected native work owner, including on completed HTTP responses;
no synchronous thread wrapper or native owner is installed by default.

`cancel(token, library, request_id)` requires current matching account/session
authority. Trusted `invalidate_session(token)` and `close()` fence output and
drop retained words before awaiting cleanup. The session hook is not a public
unauthenticated endpoint. Its invalidated session hashes are bounded at 1,024;
exhaustion closes this owner instead of reviving an invalidated session. A
controller must cancel an older operation when a newer intent replaces it in
the same editor; the service does not infer that independent conversations
should cancel each other. Current database validity remains authoritative.

Source reads run in owned shielded thread tasks; their transactions must settle
before a permit is released. Native or thread cleanup that is false, exceptional
or overdue quarantines the shared scheduler and retains the permit. Late
successful settlement can release the permit but cannot clear quarantine or
publish late prose. `reconcile()` retries owned stop proof without resetting
the scheduler. `close()` returns false while resources remain unresolved and
never closes a scheduler shared with other profile owners. The lifespan owner
must retain this object and its tasks until settlement; replacement after
native reconciliation remains a separate integration decision.

The [operation tests](../server/tests/security/test_selected_story_operations.py)
use synthetic providers and source snapshots, and the
[authentication tests](../server/tests/security/test_selected_story_operation_auth.py)
exercise real protected SQLite policy without a model or password KDF. These
checks establish process-local contracts, not provider privacy, GPU exclusion
across processes, real cancellation or household client acceptance.


### App and session integration

[`create_app`](../server/backend/app/main.py) accepts the explicit
`selected_story_provider` injection. It requires an exact protected
`AccessRuntime`, collaboration opt-in and async `prepare`/`stop_and_reconcile`
methods. There is no settings/environment fallback or installed native adapter.
The app's memory-group flag is copied into its protected source runtime, matching
existing workspace source resolution. The separate `selected_story_drafts_enabled`
flag controls HTTP preparation and cancellation; provider injection alone leaves
those routes unavailable. The separate `selected_story_ui_enabled` flag controls
the optional Web preparation controls. No native provider is activated, and
saved-memory generation flags and PH-A1 remain independent.

[`SelectedStoryLifecycle`](../server/backend/app/access/selected_story_lifecycle.py)
constructs one `DraftOperations` at startup and owns one `InferenceAdmission`
with zero waiting slots. They are retained as `app.state.selected_story_operations`
and `app.state.inference_admission`. Startup failure also closes them. Shutdown
synchronously fences all draft output and closes admission before awaiting
shielded cleanup. The app retains unresolved operation, native stop and access
mutation tasks; `shutdown_clean` is false when the bounded wait cannot prove
settlement. It never reports successful native shutdown or constructs a fresh
gate to bypass quarantine. An enabled app object supports one lifetime; reuse
must fail closed rather than reset ownership.

The existing authenticated logout route uses an owned access-mutation task.
Before the database write starts, a temporary session barrier drops retained
prose, fences matching operations and blocks that session's new/delivering
work until revocation settles. Disconnecting the response does not cancel the
write or remove this barrier. Unknown logout tokens do not accumulate permanent
invalidation hashes. At most 16 access mutations/barriers are in flight. A
failed write releases the temporary barrier but cannot revive fenced proposals;
a later request must pass current database policy. The existing web CSRF and
native bearer rules still apply.

Successful revision-bound membership revocation fences only the affected
account/library after the authorized commit. Denied or conflicting revocation
requests cannot cancel another member's work. Existing final authorization and
source revalidation remain required. Account switch uses logout plus the new
session's ordinary authorization; independent sessions and conversations do not
cancel each other. The optional Web editor fences newer intents and clears its volatile proposal
on scope changes; other clients remain separate integrations.

The [lifecycle tests](../server/tests/security/test_selected_story_lifecycle.py)
use generated SQLite accounts/sessions and injected synthetic providers. They
qualify local app/session ownership only, not an installed provider, Windows
runtime, physical device or household usability. Package checks separately
verify extracted source dependency closure; building an archive does not deploy it.


## Protected HTTP v1

The [transport](../server/backend/app/access/selected_story_transport.py) is
registered in the explicit closed boundary and route capability inventory.
`create_app(selected_story_drafts_enabled=True, selected_story_provider=...)`
requires both a boolean opt-in and an explicit async provider; the default is
false. Collaboration opt-in, a protected access runtime and a started app
lifecycle are also required. No settings/environment fallback or native adapter
is selected. This source implementation is tested with synthetic providers;
native qualification is required before household activation.

Preparation and cancellation are POST requests with exactly one `library` query
parameter. The optional Web editor also negotiates its independent UI opt-in
through `GET /story-workspace/drafts/capabilities?library=...`; this read requires
current library membership and grants no preparation or save authority.
No token, prompt, source text, request ID or extra query parameter is accepted
in the URL. Existing reviewed HTTPS/Host/Origin/Fetch-Metadata checks, explicit
native bearer or web cookie credentials, and same-origin cookie CSRF apply.
Responses use the existing private no-store headers. Wrong methods and
unreviewed/shadowing handlers remain denied by the closed boundary.

| Path | Request | Successful response |
| --- | --- | --- |
| `/story-workspace/drafts/prepare?library=...` | The exact nested version-1 reference-only request above, streamed UTF-8 JSON capped at 32 KiB | HTTP 200 with the host-assembled `needs_review` result and its fixed expiry |
| `/story-workspace/drafts/cancel?library=...` | Exactly `{"version":1,"request_id":"<canonical lowercase UUID>"}`, capped at 512 bytes | HTTP 200 with `{"version":1,"request_id":"...","matched":true}` or `matched:false` |

Require `application/json`, reject content encoding, duplicate keys at every
object depth, non-object envelopes, nonfinite constants, malformed UTF-8, and
missing/extra/version-invalid fields. The raw streamed cap applies even without
Content-Length, and a supplied length must match the captured bytes. Media,
evidence, account, session, saved-target ownership and current revision checks
remain in the protected operation/source services before provider work and on
result delivery. The API accepts no caller-supplied source corpus or provider
configuration, and never saves a story.

Prepare waits for the bounded operation outcome; it creates no polling resource,
background durable job or waiting queue. The 60-second work deadline starts at
admission; an error response may additionally wait up to ten seconds for bounded
cleanup. A successful proposal must still meet the work deadline. A disconnected response waiter detaches
without cancelling the owned generation. A same-ID/same-body retry joins or
recovers the result after fresh authorization; a changed body conflicts. Busy
before provider work permits a later exact retry, but this is not an instruction
to retry model failures automatically. After fixed result expiry, an exact retry
requires a matching fresh snapshot and returns a new draft ID for full review.

Cancel requires current `story.write` and the exact account/library/request and
session binding. `matched:true` acknowledges that a registered matching
operation's output was fenced, including retained prose; it is **not** proof
that native work stopped or that inference admission has been released.
Repeated matched cancellation is safe. `matched:false` means no operation was
registered under that authorized identity at the lookup instant. It creates no
cancellation tombstone and cannot fence a prepare that registers later. A future
client must invalidate its own logical intent immediately, ignore stale
responses and reconcile/repeat cancellation if its first prepare is still
unresolved. Never interpret either response as permission to expose a late
proposal or start work outside shared admission.

Operation errors have fixed bodies `{"detail":"...","code":"..."}` with no
provider exception, prompt, source words, source/snapshot hash or internal ID.
Existing transport-level malformed-request/credential failures retain their
ordinary fixed `detail` response and HTTP status.

| HTTP status | Operation code | Client meaning |
| --- | --- | --- |
| 400 | `draft_invalid_request` | Reject the invalid reference/cancel envelope; do not invoke inference |
| 401 | `draft_access_denied` | Current account/session/library write authority is unavailable |
| 409 | `draft_conflict` | The request meaning or selected source/target state changed |
| 409 | `draft_scope_changed` | The session, operation or review scope is no longer valid |
| 409 | `draft_cancelled` | This request identity was cancelled and is terminal |
| 429 | `draft_busy` | Shared inference/read capacity is occupied; `Retry-After: 2` is advisory for an explicit exact retry |
| 429 | `draft_capacity` | Bounded request/result registry is full; no identity is silently evicted and no automatic retry is requested |
| 503 | `draft_unavailable` | HTTP opt-in/lifecycle/provider cleanup health is unavailable; no fallback provider or fresh gate is created |
| 504 | `draft_timed_out` | The bounded operation deadline elapsed; late prose remains fenced |

The [HTTP tests](../server/tests/security/test_selected_story_transport.py)
cover the protected application flow with synthetic providers and generated
SQLite data. They do not establish a deployed endpoint, native cancellation,
model quality, physical voice interaction or family/device acceptance.

## Acceptance cases and dependencies

Default-off PH-A4 source work requires a frozen benefit comparison, exact
request/result and runtime boundary, and client review path under the revised
household plan. It may use injected synthetic providers before a native host is
available. Exact local provider, resource, retention and native lifecycle
qualification are required before household inference or client activation;
isolated qualification canaries need their own authorized scope. A source
fixture does not establish those gates. Essential synthetic acceptance cases are:

| Case | Expected behavior |
| --- | --- |
| Exact selected sources | Draft uses only the selected current media and per-chapter evidence; every nonblank chapter has valid citations. |
| Empty source choice | A chapter with no selected evidence receives no picture-linked evidence. The system asks for sources or leaves its narration blank; it does not silently use all available evidence. |
| Source text injection | Instructions embedded in a note, transcript or caption cannot add tools, sources, people, media or save authority. |
| Mixed source kinds | Family note and AI or family-edited caption remain distinguishable in PH-A4 v1. If a later source contract admits accepted contributions or transcripts, their authored/derived status and original byline remain distinct. |
| Stack member coverage | Each explicitly selected member is represented with its own evidence. Cover-only input cannot cite or imply unselected siblings. |
| Drift during generation | Change, withdrawal, deletion, membership or source revision while preparation is pending; return conflict and no draft. |
| Stale review | Change a source choice, chapter partition, title or wording after review; the old confirmation cannot authorize Save. |
| Lost save response | Retry the frozen body and mutation ID; create/update occurs at most once and current revision is reconciled. |
| Conflicting mutation | Reuse the mutation ID with changed text or selection; show conflict and preserve the local proposal. |
| Expiry and scope change | Expired or account/library-switched proposal is cleared and cannot be saved into a new scope. |
| Invalid adapter output | Reject missing/extra fields, unsupported citations, omissions, duplicates, oversized content and claims of saved/published state. |

Dependencies remain separate: refreshed source review; PH-A0 qualification of
the exact local runtime and retention behavior; a separately reviewed
story-specific benefit threshold; the existing or explicitly designed client
draft/review path; and source, runtime, native-host and family acceptance. PH-A1
is an application seam and does not qualify the model or make PH-A4 available.
PH-A4 does not require shipping the PH-A3 search experience first, but it must
not bypass any enabled application boundary. No model installation, source
deployment, service restart, publication or family-device acceptance follows
from this proposal.
