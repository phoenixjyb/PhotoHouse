# Edition-bound original-source inspection, version 1

Source contract for an explicit reader action. This does not activate C2, run a
model, intake audio, change retention or alter the database schema. Both
`memory_editions_enabled` and `memory_originals_enabled` gate these reads, with
ordinary library/book/child-media authentication first. Reading needs neither
editorial permission nor a retained private AI job.

## Routes

All are protected HTTPS GET routes below
`/memory-community/v1/books/{book_id}/editions/{edition_id}`:

- `/sources?library=...&page=1`: metadata pages of 16; no source words/audio.
- `/sources/{source_id}?library=...`: explicitly load current original material.
- `/sources/{source_id}/audio?library=...`: explicitly load an original recording.

Book and edition are canonical UUIDs. A source ID is a bounded ASCII identifier
matching `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`. It is a selector, never authority or a
model-supplied original identity. Only IDs in the freshly rebuilt, verified
full server prompt closure of this current saved edition may be read, including
uncited prompt inputs. Unknown/foreign sources are denied. Every request checks
membership, every current child and asset, saved/current revisions, complete
source fingerprint, normalized source rows and stored manuscript validity in
one read transaction. A stale edition never exposes its originals through this
interface. Do not resolve a model citation directly into an unrestricted table
lookup or the existing unbound story audio route.

## List JSON

Exactly these keys:

```json
{
  "version": 1,
  "book_id": "canonical UUID",
  "edition_id": "canonical UUID",
  "book_revision": "positive canonical decimal string",
  "state": "current",
  "page": 1,
  "page_size": 16,
  "has_more": false,
  "items": [
    {"source_id": "server source ID", "origin": "caption", "kind": "ai", "asset_id": "positive decimal string"}
  ]
}
```

Origins: `contribution_text`, `contribution_audio`, `asset_note`, `caption`,
`book_introduction`, `story_chapter`. Kinds: `family`, `transcript`, `ai`, `editorial`. Asset IDs
are null for contributions/introduction/saved editorial chapters. Page is a positive integer up to
100000. Sources preserve the server closure order; IDs are unique, at most 96
over the entire closure. Lists contain no text, byline, original URL or bytes.
When state is `source_changed` or `source_invalidated`, items are empty and
`has_more=false`.

## Detail JSON

Exactly these envelope keys:

```json
{
  "version": 1,
  "book_id": "canonical UUID",
  "edition_id": "canonical UUID",
  "book_revision": "positive canonical decimal string",
  "source_id": "server source ID",
  "state": "current",
  "source": {
    "origin": "contribution_audio",
    "kind": "transcript",
    "asset_id": null,
    "story_id": "owning canonical child-story UUID",
    "byline": null,
    "original_text": null,
    "original_truncated": false,
    "transcript": "Current ASR-derived transcript",
    "transcript_truncated": false,
    "prompt_excerpt": "The exact excerpt in the fresh verified prompt closure",
    "audio_available": true
  }
}
```

`story_id` is populated only for contributions or `story_chapter` and must be
one of the current book children. `asset_id` is populated only for caption/asset-note sources.
`byline` is null or bounded at 256 UTF-8 bytes. Each text/excerpt is bounded at
8192 UTF-8 bytes, with strict Unicode and no control characters other than LF
and TAB. A bounded original/transcript prefix uses its explicit truncation
flag; it must not masquerade as a complete original. Null text always has a
false truncation flag. Title/polished prose/tags/account IDs are not returned.

Text contribution, asset note, caption, introduction and saved child chapter
expose current stored text as `original_text`; audio contribution exposes only its ready current
transcript and an audio-availability flag. The client labels AI captions and
ASR transcripts as derived material, separately from a family original or
editorial direction. `story_chapter` is current saved editorial narration under
`editorial-{child_uuid}-chapter-[1-6]`, not an independent family account or an
asset-family note. `prompt_excerpt` is the exact current server excerpt,
not an assertion that the entire original was supplied to the model. This is
fresh source inspection, not a new historical text snapshot in an edition.

For `source_changed` or `source_invalidated`, `source=null`. A failed read has
no cached fallback. `book_revision` always identifies the immutable selected edition receipt,
including changed/invalidated responses; it is not replaced by the latest book
revision. A current response additionally passed fresh book revision equality.
Existing detail/save/capability wire contracts are unchanged.

## Original audio and client lifetime

Audio requires the same fresh edition/source binding as text, accepted and
consented contribution ownership, and the originals gate. Load only after an
explicit request. Return bounded valid PCM16 mono 16 kHz WAV (up to 30 seconds /
2 MiB) after checking stored original SHA-256 and payload validity; no ASR/TTS,
model call, disk cache or alternate route. Changed/invalidated editions return a
bounded conflict, with no bytes. Responses are `Cache-Control: no-store`.

Clients clear prior source text before fresh catalog/detail requests and
source/edition/page changes. Stop/revoke previous audio before every audio request.
A bound current transcript may remain visible while its explicit original-audio
request is pending; there is no prior-audio fallback. Denial/conflict,
account/library/book/child revision change, close or backgrounding clear both
source text and audio. Fence late results by the same scope and a source-request epoch.
Display explicit loading/unavailable/changed states. Opening a chapter, list,
reference disclosure or source card must not fetch a recording or start audio.
Do not use this UI to change an editor draft, IME composition, pending save body
or uncertain mutation identity.

## Acceptance boundaries

Temporary-database service/HTTP checks cover all six origins, uncited prompt
sources, foreign selectors, viewer reads, expired jobs, revoked membership or
child media, changed/invalidated editions, original feature gates, bounded text,
malformed audio/hash and no legacy route fallbacks. Web/phone fixtures separately
cover manual source load, raw/derived labels, source failure, cancellation and
late-scope fencing while preserving private editing state. Synthetic audio does
not establish real-device listening or provider quality. Physical erasure and
native paired restore qualification remain separate gates before C2 activation.
