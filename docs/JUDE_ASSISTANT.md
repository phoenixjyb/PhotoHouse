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

## October 30 candidate behavior

These improvements are implemented locally and await Windows deployment. They
are not instructions to assume that the currently served page already has them.

A conversational search should retain the understood conditions between turns:
“找去年九月份的照片” selects the previous calendar year's September and images;
“只看视频” changes only media type; “改成十月份” changes only the month. Unsupported
conditions still need clarification. Empty results are a valid answer and must
not cause the service to silently discard a requested condition.

The candidate agent carries recent exchanges in the signed-in library's server
conversation. It rechecks ownership and revision for every new request. This
provides continuity with the same local model; it does not make the model an
unrestricted autonomous assistant or a source of access permissions.

When optional automatic story refinement is deployed and enabled, a saved story
can queue a proposal bound to that exact revision. An existing story can also be
submitted explicitly. The reader distinguishes queued, processing, deferred,
failed and ready-for-review states. A ready proposal appears beside the original;
the owner decides whether to adopt it. Original contributions/audio remain
available. A changed story revision or access scope invalidates a stale proposal;
request retries do not create duplicate jobs.

The requested household story is the intended live demonstration, not an already
completed example. The current voice has also not yet been replaced by the
prepared natural bilingual TTS candidate.

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
