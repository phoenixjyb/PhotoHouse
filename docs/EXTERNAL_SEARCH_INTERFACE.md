# External search interface

The [in-process reader](../server/backend/app/access/external_search.py) can
search a reviewed library and retrieve metadata through the existing protected
discovery service. The generated proof supplies a host-authenticated client
identity and an explicit library scope. MCP transport, OAuth, user consent and
production activation remain open.

## What the local reader supports

A trusted host constructs an `ExternalSearchSession` for one authenticated
client, one library and a current host session, with an independent expiry.
The host can revoke the reader without changing the member's app session. Each
operation checks that the reader still accepts the client and the member
still has access. Expiration and revocation close that reader permanently.

`search_media` accepts recorded date and media filters and optional caption
matching against a reviewed index. It returns up to 20 items per page, with an
opaque reference, kind and recorded capture date. The response reports the
result total and whether the reviewed index covers the catalog. An unsupported
filter returns a refusal. `get_media_detail` rechecks the exact current search
binding before returning that item's safe metadata. A continuation sends the
opaque cursor alone.

A reader retains up to 128 recent references and 16 cursors for its current
search. A successful fresh search clears the previous handles. Current
membership, source and index changes can invalidate them earlier. The two read
methods keep their HTTP, OAuth and client credentials outside this interface.
Generated authorization tests exercise this adapter without a network listener.

## Initial contract

Start with two read-only operations for one explicitly selected library:

1. `search_media(query, filters, page_size, cursor?)` returns a bounded page of
   current matching media references, safe display metadata, total/continuation
   state, and coverage or unavailable-field information. Use the existing
   reviewed structured filters and the negotiated search profile; do not add
   arbitrary SQL, provider methods, identity resolution, or implicit semantic
   model calls to this first slice.
2. `get_media_detail(media_ref)` returns a small allowlisted current-source
   projection for one result. It reauthorizes the caller and rechecks that the
   referenced asset is still active and in the granted library. It does not
   return an original file, filesystem path, unrestricted database row, or
   unbounded caption/transcript.

The external `media_ref` and continuation cursor should be opaque, non-authority
handles bound server-side to the authenticated principal, library, grant,
search binding, and expiry. A caller cannot turn a guessed asset ID into a
reference or use a handle from another account, library, session, or query.
Keep page size bounded and reject stale or mismatched continuation state; do not
silently continue against a changed index.

Reviewed people, events, and saved stories are later additions only after each
has an explicit read projection and authorization contract. Private notes,
story prose, transcripts, and audio are separate data classes and remain out of
the initial response. An eventual scope for private text must be independently
opted into and consented to; audio/original bytes require their existing media
capability and a separate retrieval design.

## Reuse and authorization boundary

Reuse the current domain path rather than creating a parallel search engine:

- `AccessService` and `DiscoveryRuntime.authorize/call` perform current
  session, library-membership, and capability checks before discovery reads.
- `DiscoveryReads.search` and the explicit `SearchRuntime` provide reviewed
  filters, source/index snapshot bindings, bounded paging, and source-change
  refusal. `SearchRuntime` is currently used by the local assistant path.
- `AgentTools` demonstrates run-scoped opaque handles, bounded projections,
  exact selector validation, and current-source revalidation. It is an internal
  local tool facade; its tool names and payloads are not an external protocol.
- `AccessService.asset_metadata` is internal and includes a storage path. Never
  expose it directly. The detail operation needs a safe DTO assembled through
  the authorized domain path.

The external adapter must have no direct database/provider access of its own.
It accepts only fixed operation names and validated fields, calls the domain
facade with the authenticated host principal and the explicitly granted
library, and returns generic authorization errors without SQL, paths, tokens,
provider exceptions, or private request text. Ordinary search grants must not
imply `media.original.read`, write, curation, member-management, or deletion
capabilities. Preserve source originals; this interface has no mutation method.

## Grant, session, library, and source lifecycle

The eventual integration must be off by default and require an explicit owner
or member opt-in for a named external client and named library. The user-facing
grant must state that this first scope permits metadata search and current
detail only. A client cannot choose or infer another library through account,
phone, person, or asset identifiers.

Use the existing host identity and authorization checks on every operation.
The current `AccessService` rejects expired or revoked sessions and unavailable
or revoked memberships. An external grant must also have its own narrow,
expiring authorization boundary and revocation path; it must not turn a
long-lived host session token into a third-party credential. The concrete OAuth
grant/token mechanism, persistence, consent UI, and revocation endpoint are
future implementation decisions and are deliberately unspecified here.

Revoking the external grant, host session, or library membership must deny the
next search and detail request, including a request presenting an old cursor or
media reference. On source withdrawal, deletion, remapping, or relevant source
revision change, detail must refuse or return not-found without stale metadata;
the client must search again to obtain current references. A cursor or media
reference is never a durable grant and never preserves access after revocation.
Current asset-withdrawal code is an internal tested contract; no HTTP withdrawal
route or physical-erasure flow is enabled by this proposal.

## Privacy and response limits

- Return only fields needed to identify and browse a result: opaque reference,
  media kind, safe date, and a clipped/redacted caption excerpt only when the
  caller's grant and response policy permit it.
- Do not return raw storage paths, full originals, session/grant tokens,
  internal bindings, raw person/account identifiers, embeddings, private notes,
  transcripts, or audio in the initial contract.
- Enforce request, page, and serialized-response limits; use no-store privacy
  headers; reject malformed, duplicate, unknown, or overlong fields.
- Reauthorize and revalidate on every operation. A prior search response is not
  authority to fetch a source later.
- Log operation outcome and stable error category only. Avoid logging query
  text, captions, media bytes, credentials, or returned private content.

## Generated acceptance matrix

These cases define the remaining external-transport acceptance. The local
reader exercises the protected domain path with generated data. A named external
client still needs a verified consent and connection flow.

| Case | Required future behavior | Existing generated evidence |
|---|---|---|
| Explicit opt-in and `library.read` grant | Default disabled; opted-in client can search only the named library | `test_phone_discovery_http.py`: `test_facets_and_search_string_ids_and_coverage`; candidate runtime requires explicit factory configuration, but external opt-in is unimplemented |
| Missing, expired, or revoked host session | Deny before provider/index access with a generic response | `test_phone_discovery_http.py`: `test_missing_foreign_expired_revoked_denied_before_provider_or_bad_body` |
| Unknown, pending, expired, or revoked membership | Deny without disclosing discovery data | `test_phone_discovery_http.py`: `test_unknown_library_and_membership_states` |
| Cross-library or cross-principal cursor/reference | Deny; handles cannot be replayed under another scope | `test_assistant_agent_tools.py`: `test_selector_is_exact_run_scoped_and_revalidates_source_binding`; the local reader binds its own references and cursors to the named client and current search |
| Expired or revoked external grant / missing external scope | Deny search and detail on every request | `test_external_search.py` checks independent reader expiry and revocation, including during a read. OAuth grant issuance remains open |
| Stale page cursor or changed source/index | Refuse continuation and require a fresh search | `test_phone_discovery_http.py`: `test_changed_binding_fingerprint_and_session`, `test_paginated_search_fingerprint_normalization`; `test_phone_discovery.py`: `test_paging_binding_and_fingerprint_prevent_mixed_results` |
| Source withdrawn between search and detail | Return no stale metadata or media; require fresh search | `test_asset_tombstones.py` and `test_upload_original_deletion_journal.py` cover internal tombstone/source guards; the in-process reader refuses metadata after a source change |
| Detail request with guessed or foreign asset ID | Deny without resolving identity or crossing library scope | `test_assistant_agent_tools.py`: `test_dispatch_rejects_unreviewed_names_and_nonempty_search_arguments`; the in-process detail method refuses guessed IDs and other readers' references |
| Path, token, SQL, provider error, or excessive response | Redact and bound output; return generic error | `test_phone_discovery_http.py`: `test_service_errors_generic_busy_and_budget`, `test_body_limits_and_strict_envelope` |
| Attempted write, original fetch, note/audio access | Reject as unsupported or missing capability; preserve originals | `test_original_deletions.py` and `test_asset_tombstones.py` validate internal deletion guards; external transport must have no such operation |

## Checks performed for this design

On generated fixtures only, the focused local checks passed:

- `test_external_search.py` checks protected paging and detail, safe metadata,
  changed sources, foreign handles, ignored-filter prevention, current host
  authorization and independent reader expiry and revocation.
- `test_assistant_agent_tools.py`: 7 tests, including exact run-scoped handles,
  current-source invalidation, and rejection of unreviewed tool names.
- `test_phone_discovery_http.py`: 18 tests, including session/membership denial,
  paging bindings, body/response bounds, and generic failures.
- `test_original_deletions.py`: 14 tests, covering the generated deletion-journal
  lifecycle and refusal cases.
- `test_asset_tombstones.py`: 14 tests, covering generated tombstone binding,
  refusal, retry, and replay behavior.

These checks cover the local reader and discovery prerequisites. External
transport, consent, OAuth/token issuance and client interoperability remain
future integration work.
