# Android memoir editorial core

October 3, 2026. This is a source-qualified optional client contract, not a
published feature or a change to the unchanged legacy memoir response.

## Optional interface and transport

`MemoryBookEditorialApi` is separate from `MemoryCommunityApi`; existing clients
and test fakes keep their legacy interface. `HttpsMemoryCommunityApi` implements
both. GET and PUT use `/memory-community/v1/books/{id}/editorial` with the selected
`library` query and the authenticated configured HTTPS origin. The existing
transport disables redirects, cookies, retries and disk caching. The repository
maps only 404/503 to unavailable; authorization failures propagate.

The encoder binds canonical UUIDs, positive decimal revisions, ordered current
children and eligible source identities supplied by an authorized caller. Sources
include story/revision, chapter and original contribution identity. Introduction
references may use any current child; transitions use only their adjacent pair.
Budgets are 24 children, 12 references per section, 96 references per memoir,
6,000 UTF-8 bytes per transition, 128 UTF-8 bytes per chapter ID and 64 KiB per
mutation. Duplicate JSON keys, duplicate references, unknown keys and malformed
UTF-8 are refused. Python whitespace semantics are mirrored for empty transitions.

Responses bind the expected book/revision/ordered children and use the bounded
512 KiB transport envelope. `current` validates every section; `empty` and
`source_changed` contain no returned references or transition text. These states
must not imply that a new citation still uses a deleted or edited source.

## Checks and next integration

406 live-core tests passed, including six new editorial tests. Root review added
the 96-reference accepted / 97-reference rejected boundary and reran the six
focused tests. The phone debug Kotlin compilation passed; no APK was generated
or published for this change, and no device/editor interaction was tested.

The backend source has the default-off b1 sidecar contract. Live availability must
be negotiated; a client protocol does not enable its database or routes.

Next: integrate account/library/generation-bound editor state; preserve the exact
serialized mutation and ID after uncertain saves; provide explicit retry and
conflict refresh while retaining drafts. Connect the editor and reader citations,
then exercise save/reopen, source deletion, child edits, denied access and absent
service with synthetic API and 150% emulator journeys. Do not automatically resend
or expose stale source text. Signing, OTA, live migration and family acceptance
remain separate delivery gates.
