# Voice retrieval and playback evidence

## Explicit asset numbers

The assistant accepts commands such as `打开编号101`, `查找编号101`,
`open asset id 101` and `find photo number 101`. The number must be explicit;
an ordinary result ordinal still refers to the current displayed list.

An exact lookup runs inside the same bounded, authorized discovery snapshot as
search. It can find a library asset beyond the first result page. Hidden assets,
other libraries and absent numbers receive the same clarification. A client
supplied ID never grants access. Membership or source changes invalidate the
context before opening, recovery or speech.

The result retains the v1 envelope and context shape: a singleton card, empty
filters and an opaque fingerprint binding the number to the current discovery
snapshot. This is an internal lookup operation, not a public discovery facet.
An explicit find returns a card; an explicit open returns a fresh `open_asset`
effect. Durable GET or duplicate POST recovery returns the card without replaying
navigation. A voice session ends before opening its result.

## ASR failures

The protected transcription route returns a bounded `{error, detail}` envelope.
Only these safe categories are retained; upstream bodies are never exposed.

| Code | HTTP | Evidence required |
| --- | --- | --- |
| `speech_no_input` | 422 | Successful provider response with empty recognized text |
| `speech_busy` | 503 | Provider explicitly returned HTTP 429 |
| `speech_timeout` | 504 | Provider transport raised a timeout |
| `speech_invalid_response` | 502 | Successful response was malformed, wrong type or oversized |
| `speech_unavailable` | 503 | Unknown provider/transport failure or other unsuccessful status |

Phone and Web show localized recovery guidance. A continuous session pauses;
empty or failed recognition never becomes a broad search or an automatic retry.
Existing drafts remain available. The request journal records the code and stages
for 30 days. Audio remains transient. These categories do not retroactively
identify the cause of an older generic error.

## Separate playback reporting

Successful speech responses can advertise
`X-PhotoHouse-Playback-Tracking: enabled`. Clients without the header do not
attempt the new operation. A synthesis receipt saying `succeeded`, or the old
client outcome `displayed`, proves waveform delivery/handling rather than that
playback finished.

Clients report to `POST /assistant/v1/receipts/{request_id}/playback` with
`{library_id, outcome}` where outcome is `completed`, `failed` or `cancelled`.
The response is `{version: 1, request_id, playback_outcome}`. The endpoint requires
current library membership, the owning account, and a succeeded speech receipt.
Browser cookie requests also require the normal origin and CSRF protections.

Only the player's actual end callback reports `completed`. Playback error reports
`failed`; stopping an owned playback reports `cancelled`. Account/library changes,
old generations and detached callbacks cannot report completion for a new scope.
The first terminal event wins; repeating it is idempotent and a contradictory
event conflicts. Events are stored alongside the speech request as
`client_playback_completed`, `client_playback_failed` or
`client_playback_cancelled`, and expire with it. The existing receipt envelope,
client outcome enum and journal schema stay compatible with older clients.

Reporting is best effort. Missing reports are unknown, never inferred success.
A completed player callback is client evidence, not proof that the user heard or
understood the audio. Native ASR/TTS service checks, generated browser/JVM tests
and real device listening remain separate acceptance steps.

## Release acceptance

1. Check exact-number retrieval beyond page one, hidden/cross-library refusal,
   stale source refusal and navigation-free recovery.
2. Check all five ASR classes and that neither provider details nor audio enter
   the journal.
3. Check both manual and continuous playback, Pause/End, errors, late callbacks
   and servers without the reporting header.
4. Qualify the pinned Windows source candidate and matching unsigned phone APK.
   Live switching, signing and OTA publication require release authority.
5. After delivery, test a known accessible number, an unavailable number, an ASR
   failure and an audible reply on the real phone and Web UI.
