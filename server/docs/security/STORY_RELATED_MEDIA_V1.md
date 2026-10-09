# Protected story related-media candidates v1

`POST /story-workspace/related-media?library=<id>` is an authenticated,
read-only candidate lookup for the grouped-story editor. It suggests active
photos and videos from the same library whose recorded capture calendar day
matches one of the selected seed assets. Every result is only a candidate and
requires review; a shared day does not establish that media belongs to one
activity.

The exact request body contains two string fields:

```json
{"asset_ids":"101,102","before_id":""}
```

`asset_ids` is an ordered, comma-separated list of 1–24 distinct canonical
positive decimal IDs. `before_id` is empty on the first page or a canonical
positive decimal ID returned as `next_before_id`. Unknown, duplicate or
non-string fields are rejected. The request is limited to 4096 bytes.

The exact response shape is:

```json
{
  "version": 1,
  "library_id": "family-a",
  "seed_asset_ids": ["101", "102"],
  "recorded_days": ["2026-01-01", "2026-01-02"],
  "needs_review": true,
  "has_more": false,
  "next_before_id": null,
  "items": []
}
```

Each item has the ordinary protected asset fields (`id`, `kind`, `width`,
`height`, `duration_sec`, `taken_at`, `thumbnail_url`) plus
`match_reason: "same_recorded_capture_day"`. Items are ordered by descending
asset ID. Responses contain at most 20 items and inspect no more than 80
candidate rows plus one lookahead row per request. The next cursor is the last
inspected ID, including when invalid date rows were skipped. An empty `recorded_days`
list yields an empty result without examining candidates. Responses are at most
256 KiB and use the existing no-store, CSRF and closed-boundary controls.

Only `assets.taken_at` is considered. It must be a valid ISO calendar date or
ISO datetime; an offset is accepted, but the written calendar day is preserved
instead of converting to UTC. Candidate values are validated in full after the
bounded prefix query. A malformed timestamp never becomes a match. Filename
and upload-receipt hints are neither queried nor returned. The route reads only
catalog metadata after `library.read` authorization, validates every seed as an
active image or video mapped to that library before returning candidate data,
and excludes the seed IDs. It does not read pixels, embeddings, paths, captions,
or story prose and performs no writes, inference, indexing or scheduling.

## Web editor and acceptance

The Web editor exposes a collapsed “同一天的更多瞬间” panel. Lookup is explicit;
no candidates are fetched merely by opening the editor. Each candidate requires
“加入故事”. Inclusion preserves the selected order, observes the 24-item limit,
and uses the ordinary preview to reload current evidence. Changing a selection
with edited chapter text uses the existing discard confirmation. Lookup failure
preserves the draft. Membership/library changes, selection changes, closing the
editor and logout invalidate delayed responses and clear candidate media.

The candidate list scrolls within a bounded height. Chinese and English layouts
were rendered and inspected at 390px with 150% text. The actual-ASGI browser
journey passed seven checks over generated assets, covering keyset pagination,
photo/video inclusion, filename-date exclusion, malformed foreign-library
responses and malformed full timestamps, transient failure, stale selection/logout responses and the selection
limit. The existing story-workspace browser regression also passed ten checks.
Focused route/workspace/closed-application checks passed 38 tests and
27 subtests. These Web checks are local source acceptance; the route and picker
are absent from the deployed f282472 API and phone v45. No model or media
mutation is introduced.

## Android phone editor

The phone source uses the same protected request/response contract. Opening its
collapsed panel makes no request. Lookup and each “加入故事” are explicit;
adding a candidate appends to the ordered selection within the 24-item limit.
Pages replace the previous candidate page rather than accumulating an unbounded
list. A failed page can be explicitly retried with its original cursor.

The decoder rejects mismatched libraries/seeds, invalid full capture timestamps,
duplicate JSON keys, foreign preview routes and nonadvancing cursors. Candidate
preview storage is separate from ordinary selection previews. Membership,
library, selection and editor changes invalidate delayed responses and zero
candidate buffers. Read the [Android evidence note](../../../clients/android/docs/ANDROID_RELATED_MOMENTS_2026-10-09.md)
for source and synthetic UI checks. Deployment of the route and signing/OTA
publication of a matching client remain separate delivery gates.
