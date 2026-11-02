# Using Jude / 小贾

Jude is the private assistant inside the PhotoHouse Web workspace. It works in
the signed-in account's current library. The [October 29 delivery](RELEASE_2026-10-29.md)
includes the new Web UI and a real server speech → Search → reply-audio result;
physical microphone/speaker and native phone/TV acceptance remain separate.

## Find photos

1. Sign in and select the intended library. Open the assistant workspace.
2. Type a request, or explicitly start foreground voice interaction. Review the
   interpreted conditions and returned cards; unsupported conditions can require
   clarification rather than silently widening the search.
3. Continue within the visible conversation. Opening a result is a distinct user
   action. Membership, library, conversation and revision checks still apply.

The model-backed `agent_media_search_v1` lane has three typed read-only tools.
It cannot run shell commands, write SQL, change permissions or automatically save
or publish a story. Existing story reading, draft editing and playback actions
have their own contracts; they are not generic agent powers.

## Voice interaction

- **Start / 开始** grants the visible foreground session permission to alternate
  listening, requesting a read-only result and playing its reply.
- **Pause / 暂停** and **End / 结束** remain available. The microphone is off while
  reply audio plays. The next capture depends on actual playback completion and
  a still-valid foreground session.
- Account/library changes, hidden pages, interruption and uncertain request state
  fence late results and pause the flow. Resume explicitly when requested.
- Outside that opted-in session, recording, inserting a transcript and sending
  the request are separate actions. Typed requests remain an alternative when
  microphone permissions or local speech services are unavailable.

This is half-duplex local speech interaction, not unrestricted background
listening or a cloud Realtime connection. The measured server demonstration took
28.688 seconds; that is one result, not a latency guarantee for every device/query.

## Recover a completed recognition request

If the page appears stuck after recognition, use the current request's server
receipt lookup. Do not repeatedly submit the recording or invent a new request
ID for an uncertain operation.

A successful, current-scope recognition receipt can restore its transcript into a
**review** state. Recovery leaves the microphone off and does not automatically
send a Search request. Use the transcript action to insert the wording, review
it, then Send. An existing typed draft is preserved. The submitted turn retains
the original ASR parent request ID, and reply audio has a separate linked receipt.

For an uncertain already-sent Search, recover the same request with GET instead
of starting another model action. A stale account/library/conversation receipt
cannot restore an active microphone or execute an action. Stored history and
returned cards do not bypass fresh authorization.

### Search context conflict (HTTP 409)

In the current client source, a context conflict hides stale active result cards
and reply audio while retaining the pending turn and text draft. The UI gives
guidance for the invalidated context and offers explicit Recover and Abandon
actions; it does not resend automatically. Recovery remains subject to current
server authorization and context checks. Token rotation invalidates the old
result context and receipts, so a fresh Search is required for a new context.
The focused client CJS and syntax checks and synthetic ASGI/Chromium case passed
with screenshot review. This is local source-preview evidence, not Windows
installation or family/device acceptance.

## Search conversation context and current qualification

The October 30 compact chat layout and bounded conversation projection were
deployed from `daa7e14`. That dated rollout does not establish acceptance for
the current Search follow-up contract.

The later R10 native attempt made two real model inferences. The first Search
reached the model; the natural-language follow-up in turn two returned a
clarification instead of fulfilling the requested refinement. The attempt was
refused, so it is not a two-turn native pass or a new live acceptance. The
profile, configuration and provider checks passed, as did native cleanup. This
result is limited to that follow-up path; it does not mean all incumbent Search
behavior failed, and existing basic Search evidence remains separate. The
latest permitted start for a 2,700-second live rollout was 22:45 UTC. That time
expired before qualification, so no live rollout was admitted; no full live
check or operation ran.

The intended follow-up behavior retains supported conditions. For example,
“找去年九月份的照片” selects the previous calendar year's September and images;
“只看视频” changes only media type. For “改成十月份”, the intended behavior
retains the prior year only when it is unambiguous; an ambiguous year requires
clarification. Explicit dates override that context. Unsupported conditions
still need clarification. Empty results must not cause the service to silently
discard a requested condition. The ordinary same-session follow-up path remains
unqualified after the R10 refusal.

Search result context and its protected continuation/recovery receipts are bound
to the authenticated login-token/session identity. Token rotation deliberately
invalidates the prior context: reuse with the new token returns HTTP 409 and
requires a fresh search. Result context is not carried between login sessions.
The 20 focused source tests exercise qualification-helper session-rotation
timing; they do not test application authentication behavior or establish live
token-rotation behavior. See [Search v2](ASSISTANT_JOINT_SEARCH_V2.md#contract-and-compatibility)
for the context binding and source checks.

A local reproduction confirmed that `Refine the last search to videos only`
returns clarification marked `unsupported_negation`, while `only videos` and
`只看视频` are accepted. The isolated parser fix is now implemented in source;
67 focused tests covering 169 subtests passed. This is source-only evidence and
does not establish deployment or native acceptance: the R10 follow-up was
refused, so there is no two-turn native pass or new live rollout. The
reproduction establishes the phrase discrepancy, not a broader cause.
The deployed assistant carries recent exchanges in the signed-in library's
server conversation and rechecks ownership and revision for each request.
Continuity comes from app-managed, authorized retained history; the model does
not have self-memory or an unconstrained agent loop.

When optional automatic story refinement is deployed and enabled, a saved story
can queue a proposal bound to that exact revision. An existing story can also be
submitted explicitly. The reader distinguishes queued, processing, deferred,
failed and ready-for-review states. A ready proposal appears beside the original;
the owner decides whether to adopt it. Original contributions/audio remain
available. A changed story revision or access scope invalidates a stale proposal;
request retries do not create duplicate jobs.

Story refinement grounds public canonical names and authorized family context
before generation. Private names come from the current authorized library
catalog and account-scoped kinship graph. For currently selected photos, only
manual, reviewed face-to-person assignments can supply an identity spelling;
raw detections and unreviewed or ambiguous assignments do not. A mapping can
help spell a mentioned name, but it does not establish who attended an event.
Selected captions and family notes retain their provenance and access limits;
the recipe starts no new vision job and scans no unselected media.

Each proposal is tied to its story revision, access scope and name-context
fingerprint. A change to those inputs fences stale work. A busy context read
defers validation; a completed result is retained privately and revalidated
without generating again. Originals and audio remain unchanged, and every
proposal needs review before adoption.

The story and assistant model roles, shared runtime bounds, native qualification
and current rollout status are in the [technical role and privacy contract](STORY_GROUNDING_AND_CLOUD_PROOFREADING.md).
The new roles and name-grounding/cloud-preview UI are not live. Search and
grouping remain on their existing paths. Optional cloud proofreading is off and
unconfigured by default; it requires an exact preview and explicit per-send
consent, has no background send, and returns an unsaved review suggestion.

The current voice has not been replaced by this story change. Natural bilingual
voice deployment remains a separate feature.

## Privacy and review

Assistant request metadata, recognized text and private conversation exchanges
have the documented 30-day retention. Transient assistant recordings are not
saved as family memories. Original family contributions and their retained audio
use a different explicit save/consent path. Generated wording is a proposal;
selected-source story drafts remain unsaved and `needs_review` until adoption.

Broader search relevance, long oral-history intake, general agent workflows and
family/device experience remain [roadmap](ROADMAP.md) work. See
[architecture](ARCHITECTURE.md), [feature status](FEATURES.md),
[foreground voice controls](VOICE_SESSION_SPOKEN_CONTROLS.md) and
[private workspace](PRIVATE_ASSISTANT_TURNS_V1.md) for the detailed contracts.
