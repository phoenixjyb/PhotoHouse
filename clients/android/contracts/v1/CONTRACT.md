# PhotoHouse native browsing contract 1.0.0-fixture.1

Source: backend `87a60b475b37b1d6873cd977bcb6e7254472da7e`. OpenAPI is a hand-authored
consumer subset checked against source and synthetic ASGI responses. No server URL
or live account is configured. The version identifies the fixture wire format and
the manifest pins this source snapshot; the backend
has no version-negotiation endpoint/header. Platform sessions consume it unchanged.

## Identity and membership

- The owner manually sends a short-lived, single-use invitation bound to the new
  user's phone login. New-account registration requires phone, password, code and
  `transport: "native"`; success creates the account **and approved viewer membership
  in that invited library**. No open signup, first-signup owner or automatic legacy
  library grant. Invalid invitation fails; it is not a pending-registration success.
- Phone is an unverified login label, not proof of phone possession. Use an explicit
  country code. Backend accepts common ASCII spaces/parentheses/hyphens and returns
  canonical `phone_login`. Returning login uses phone/password. No SMS or WeChat/OIDC.
- Internal `account_id` is opaque. Do not use phone as an object key. Password length
  is 15–128 characters; never persist or log it. Count Unicode characters consistently
  across platforms (code points, not Swift grapheme clusters or UTF-16 code units).
- Native login/register success contains `access_token`, `token_type: "Bearer"`,
  `expires_in: 86400`. This is an opaque revocable session, **not JWT**; there is no
  refresh credential or refresh endpoint. First fixture shells keep it in memory
  only and restart signed out. Secure persistent sign-in is a later reviewed slice.
- Protected requests send exactly one `Authorization: Bearer …`; never cookies,
  Origin, query credentials or an invented API-key header. Actual integration requires
  an explicitly trusted HTTPS origin with normal certificate validation. Never follow
  a cross-origin redirect or forward a token to an arbitrary returned image URL.
- After sign-in, fetch `/auth/session`. Only memberships with `available=true` permit
  selecting a library and requesting media. `status=approved` alone is insufficient:
  the library can be closed or membership expired. `requested`, `rejected`, `revoked`
  and empty memberships are read-only UI states. There is no request-approval endpoint.
- Existing signed-in accounts can accept a code through `/auth/invitations/accept`,
  then refetch session. Owner invitation creation/review remains in the web UI in this
  first mobile slice. No admin, bootstrap or recovery controls belong in the app.

## Fields that differ from the initial design proposal

| Topic | Actual frozen wire behavior |
| --- | --- |
| Membership | `library_id`, `status`, `role`, numeric `revision`, nullable epoch-seconds `expires_at`, integer `originals` 0/1, boolean `available`. Use 64-bit decoding for revision. |
| Asset IDs | Positive int64 decimal **strings**. Do not coerce through floating point. |
| Gallery | `/assets?library=…&page=1&page_size=50`; page 1–100000, size 1–100, scoped `total` and `originals_allowed`. Offset pages ordered by date then ID; no cursor/snapshot guarantee. Deduplicate appended IDs and refresh safely. |
| Detail | `/assets/detail/{asset_id}?library=…`; contains `asset` and `originals_allowed`. |
| Asset | `id`, `kind` image/video/other, nullable width/height/duration_sec/taken_at, relative `thumbnail_url`. No file path, title, GPS, asset revision or full-resolution preview URL. |
| Dates | Nullable source strings; may lack a timezone. Preserve unknown timezone and tolerate date-only/legacy formats. Never invent UTC or exact capture time. |
| Captions | Separate `/assets/{asset_id}/captions?library=…`; up to 20 items, `has_more`. Each item has string ID, plain `text`, `truncated`, `user_edited`, nullable created/updated timestamps. No language tag, translation map, provider ID, request ID or structured bilingual segments. |
| Errors | Generally `{"detail":"…"}` with HTTP status; no stable error-code field. Use local localized messages keyed by status/operation, not English-string parsing. Framework malformed-media-path 422 has a different validation body; do not require one universal error DTO. |

UI language (system/English/Simplified Chinese) is independent of captions. Render
caption text literally, including bilingual text and markup-like strings. Do not
regex-split translations, execute HTML or claim translation availability. A caption
language setting may be deferred until a structured backend contract exists.

The complete encoded UTF-8 caption JSON response, including the envelope and JSON
escaping, is at most 524288 bytes (512 KiB). It contains an ordered prefix of up to
20 whole rows. `has_more=true` means rows were omitted by either the row or byte
limit. `truncated` independently marks a stored caption whose text exceeds 8192
Unicode code points; it does not indicate omitted rows. Exact-budget responses are
allowed. There is no caption cursor or pagination route to retrieve omitted rows.
This aggregate budget applies to captions; it is not a new limit on every endpoint.

## Media and lifecycle

Thumbnails are authenticated cached derivatives, default size 256, allowed 64–1024.
Missing cached media returns 404 and triggers a placeholder, never provider work or
an original-media fallback. Original `/assets/{asset_id}/media?library=…` requires
separate original permission even for video playback. Honor `originals_allowed` in
the UI; it is not a replacement for server authorization. GET/HEAD and single Range
are supported. An If-Range request currently returns full 200. No automatic 304 bypass.
HEAD carries no body, including errors. Exact media statuses are in OpenAPI; real
native video/range/cache behavior remains a later integration/device gate.

Fixture image loading maps known synthetic thumbnail paths to the bundled PNGs in
`client-scenarios.json`. Never fetch those paths or use the fixture access token on
any network. The PNGs are rasterized from the included original SVG shapes, without people or
private content. Both platforms can load the PNGs using native image APIs.
The video case is metadata/unavailable-state evidence only: no playable video fixture
or native player acceptance is delivered here. Binary ASGI cases verify bytes/ranges
on a tiny generated JPEG; those byte lengths are not product constraints.

On logout, lock private UI immediately, increment the session generation, cancel
requests/player work and discard tokens/images/navigation. An unavailable server
must not undo local logout; do not claim server revocation succeeded. Library/account/
server changes also advance generation and clear private state. Late callbacks from
an older generation cannot repopulate UI. Cover private content in the app switcher;
returning to foreground revalidates session before uncovering content. No persistent
photo cache, offline album, credential log or reusable public-media URL in v1.

401 can mean session failure **or object/library denial**. Stop the affected read,
clear that private view and recheck session once; do not loop retries or identify a
foreign object's existence. If session is also 401, lock/sign out. A 403 indicates
transport/closed-boundary denial; no legacy fallback. Honor 429 Retry-After with a
bounded retry UI. Treat 503/offline as unavailable, distinct from revoked access.

## Fixture use and verification

`fixtures.json` contains pinned ASGI response cases. UUIDs are normalized to invented
IDs and returned tokens replaced with inert `F` characters. The source databases
are temporary and deleted. No actual password or invitation code is stored here.
`client-scenarios.json` adds UI-only transitions and local image mapping, explicitly
separate from server evidence. The fixture adapter may use visibly labeled demo
inputs; no demo bypass may exist in a production network adapter.

Both apps must parse these files and test approved/invalid-invitation/empty/requested/
rejected/revoked/expired/foreign/error states, generation races and private cache
cleanup. Fixture tests do not prove server authorization, deployed TLS or device
behavior. All unsupported operations remain unavailable in the initial app shell.
