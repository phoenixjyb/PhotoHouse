# Protected story workspace: additive native contract

Version: `1-preview-title-create` (additive to `1-preview-title`). Upstream
backend source: `f282472a29d291a8b7ffae1cf6c6ccddd07dc15a`.
This separate contract covers temporary grouped drafts, title suggestions and explicit creation.
It does not change the frozen protected-native single-asset story contract or
claim a deployed service, phone screen or enabled Ollama provider.

## Scope and transport

Use the authenticated protected HTTPS origin, current account/library scope,
existing bearer/cookie policy, CSRF for browser writes, and `no-store`. Query
fields are exactly `library`. Native clients must not invent a legacy or LAN
fallback. Unknown/duplicate fields, malformed Unicode, noncanonical IDs, foreign
or deleted media and revoked memberships are rejected. 401 is access failure,
400/413 invalid or oversized input, 409 stale references and 503 unavailable/busy.
Do not silently retry inference or turn an unconfirmed save into a new mutation.

## Selected-media preview

`POST /story-workspace/preview?library=<id>` accepts JSON with four string fields:
`asset_ids` (comma-separated ordered IDs), `theme`, `language`, `title`.
There must be 1–24 distinct positive canonical signed-64-bit asset IDs; no leading
zero aliases. Themes: `everyday`, `trip`, `growing_up`, `birthday`, `grandparents`,
`year_in_review`. Language: `zh` or `en`. Title may be empty and is at most 160
code points; the server supplies a neutral provisional title. Control characters
below U+0020 are rejected. Request budget: 4096 bytes.

Exact response fields: `version` (integer 1), `library_id`, `selection_revision`
(64 lowercase hex), `state` (`draft`), `saved` (false), `items`, `title`, `theme`,
`language`, `generator` (`evidence_outline`), `needs_review` (true), `chapters`,
`questions`. Response budget: 256 KiB. Items retain the exact selected order.

An item has exactly `id`, `kind` (`image`/`video`), `width`, `height`,
`duration_sec`, `taken_at`, `thumbnail_url`, `date_hint`, `evidence`. Nullable
positive dimensions, nullable finite nonnegative duration, and nullable capture
date follow the saved-memory reader bounds. Thumbnail URLs are protected relative
`/assets/<id>/thumbnail?library=<encoded library>` paths, with no alternate origin,
credentials or path traversal. Date hints are either null or exactly `value` and
`source` (`filename`/`received`); they do not establish an event date.

Up to three references per item: a `family-<uuid>` family note has exact `id`,
`source` (`family`), `title`, `text`, `revision` (positive integer); a
`caption-<positive signed-64-bit ID>` observation has exact `id`, `source`
(`family`/`ai`), empty `title`, `text`. Text is limited to 1800 UTF-8 bytes and
1800 code points, retaining CRLF/other source characters except NUL. Source labels
must remain distinct from verified family facts and edited narration.

Each chapter has exactly `id`, `title`, `narration`, `asset_ids`, `evidence_ids`.
Chapter IDs are `chapter-1` onward, at most six; consecutive groups contain at
most four assets in the exact input order, cover every selected asset once, and
reference only that chapter's item evidence. Titles: 160 code points. Narration:
6000 code points and 6000 UTF-8 bytes, permitting newline/tab but no NUL. Questions:
at most three, at most 1000 code points each. No database mutation or provider call
occurs during preview. Family source text is never silently copied into narration.

## Title assistance

`GET /story-workspace/title-capabilities?library=<id>` returns exactly
`{"version":1,"enabled":false,"max_suggestions":3,"needs_review":true}`.
Absent/disabled capability hides the optional control and leaves manual editing
available. A capability response establishes availability, not model quality.

`POST /story-workspace/title-suggestions?library=<id>` accepts exactly five string
fields: `asset_ids`, `theme`, `language`, `selection_revision`, `chapters`.
`chapters` is serialized JSON `[{"id":"chapter-1","narration":"edited words"}]`
in current outline order. Narration remains exact and is at most 6000 UTF-8 bytes
per chapter, with newline/tab allowed. Request budget: 64 KiB.

Exact response fields: `version` (integer 1), `selection_revision` (unchanged),
`titles`, `needs_review` (true). There are 0–3 distinct candidates, each exactly
`text` and `source_ids`. A title is nonblank, single-line, at most 160 Unicode code
points and 640 UTF-8 bytes, with no C0/C1 controls or U+2028/U+2029. Each candidate
has a nonempty unique citation list drawn from nonblank item references and
nonblank current chapter drafts (`draft-chapter-1` etc.). The server uses bounded
1800-byte source excerpts and rejects context beyond its 64 KiB budget.

Bind a request/result to account, library, selected order/source revision and exact
edited narration/title. Account/selection changes, local edits, pending mutation,
composition or stale references invalidate results. Show readable source labels
and optional excerpts; use opaque IDs for validation only. A title is adopted
explicitly and remains editable. Suggestions are transient, do not save/publish,
and do not substitute for one retained event-level text/audio contribution.

## Native delivery boundary

The phone implementation includes ordered group selection, scoped creation
state, an HTTPS adapter, explicit save/retry, and whole-story or chapter
contributions. The existing saved-story reader and original-source lifecycle
remain in place. The normal runtime does not configure the title adapter; live
provider qualification and delivery need separate evidence and authority.

## Reproduce synthetic contract evidence

`examples.json` contains only generated ASGI responses and synthetic family text.
It includes an image/video selection, filename date provenance, exact CRLF source
text, capability off/on and a fixed adapter suggestion. This is not model output
qualification or real family data. Ordinary offline JVM tests load this fixture.
To replay it against this curated monorepo, run from the candidate checkout with
its installed source-test environment:

```sh
python3 clients/android/scripts/verify-story-workspace-contract.py
cd clients/android/android
./gradlew --offline --no-daemon --max-workers=2 :live-core:test --tests '*ProtectedStoryWorkspace*Test*'
```

`--record` is coordinator-only fixture maintenance. No listener, external sockets,
model files, production data or runtime operation is used.

## Explicit grouped-story creation

`POST /memory-stories?library=<id>` takes exactly eight string fields: `title`,
`theme`, `language`, `asset_ids`, `chapters`, `selection_revision`, `revision`,
`mutation_id`. `revision` is exactly `"0"`; mutation ID is a canonical UUID.
The actor is taken from the authenticated session, never from a client author.
Only owners and contributors can create; viewers are denied. Request budget is
384 KiB. Title is nonblank, at most 160 code points. Chapters are serialized JSON
with the same five fields as preview, current selected order and current citations;
chapter titles are nonblank (160 code points/640 bytes), narration at most 6000
UTF-8 bytes. Preview source revision must still match every selected item.

Success is the exact existing saved-story detail shape: server-generated UUID,
positive string revision, integer created/updated times, `can_edit`, `saved:true`,
`state:draft`, `generator:family_edited_outline`, `needs_review:true`, current
selection revision, title/theme/language/items/chapters/questions and integer
`version:1`. Server response budget is 256 KiB. The create transport/decoder enforces this
limit; the existing saved-reader decoder retains its historical 3 MiB client cap.

A reviewed save freezes the complete body in process memory. Lost response retry
uses the same body and mutation ID. Same-body retry returns the current saved
story, potentially a later revision after another edit; it need not echo the old
prose or snapshot hash. Reusing the ID with different body returns 409. Parent
media and membership are rechecked on every retry. A native client may reject a
later response whose selection changed; it must keep that result uncertain and
must not automatically create another story. No durable client cache or automatic
retry is permitted. Close/discard can abandon a local draft, but cannot undo a
request which may already have reached the server.

The synthetic replay includes viewer denial, initial creation, identical retry,
retry after a later edit and conflicting mutation reuse. It uses fixed generated
identities and disposable storage only. This contract does not enable a phone UI,
publish an APK, or change a Windows feature flag.
