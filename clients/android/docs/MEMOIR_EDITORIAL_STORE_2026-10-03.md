# Android memoir editorial store

Started October 3, reviewed October 4, 2026. This is an in-memory Android source slice for the optional
editorial API. It does not alter the legacy memoir API or enable the backend
feature.

## Store behavior

`MemoryBookEditorialStore` snapshots token/session/library/book/revision, ordered
children, and eligible source identities for each operation. It copies draft and
response collections at its boundary. Changing account/session/library/book
clears the old draft; changing revision, child order/revisions, or source
eligibility invalidates in-flight work and preserves same-book edits in conflict
state. Late responses cannot restore cleared or superseded state.

Each explicit save creates one mutation ID and freezes the mutation. A pending
save blocks another submission. Offline, TLS, malformed-response, and unknown
exceptions, cancellation, and HTTP 5xx leave the frozen request in
`SAVE_UNCERTAIN`; newer edits remain separate, and save/load/discard cannot erase
the unresolved request. The caller must invoke `retryUncertainSave()` explicitly,
which sends the same mutation and serialized payload. Acknowledgements advance
the base revision without replacing edits made while the request was pending.
Local mutation validation errors are known to precede the API call, clear the
frozen request, and leave the draft repairable. Conflicts retain the draft.
404/503 reads map to unavailable through the existing repository. An unavailable
save is not an acknowledgement and retains the exact uncertain request; 401/403 clear the
draft, server data, request, and context.

A `source_changed` save response is a conflict without a current editable server
basis. It preserves the local draft but requires a caller-refreshed book context;
the caller must explicitly handle or discard the old draft before a read can
adopt the refreshed basis. A fresh
`source_changed` read stays in conflict until the caller explicitly invokes
`acceptCurrentServerBasis()` after review. Empty and source-changed reads seed
blank adjacent transitions from the validated ordered children. A 409 drops the
stale server snapshot. Cancelling a reload preserves newer draft edits.

`applyReviewedDraft()` permits an explicit rebase only after a current server
basis has been loaded. It validates every citation, adjacent story and byte
budget before adopting user-reviewed text, without sending a request or creating
a mutation UUID. Invalid sources leave the retained draft untouched; a 409 with
no refreshed basis cannot use this path.

The public state is intended for later Compose integration. `discardDraft()` is
an explicit caller action; it cannot discard an unresolved mutation and retains
conflict when no current server snapshot exists. A dirty explicit load keeps
local changes and reports a conflict rather than silently rebasing citations.

## Evidence

- Base: `codex/phone-v29-candidate-20260929` at
  `9251363343e4a1fa1cfc4b549ef53ccf690c8e95`.
- Changed paths: `android/live-core/src/main/kotlin/dev/photohouse/connected/core/MemoryBookEditorialStore.kt`,
  `android/live-core/src/test/kotlin/dev/photohouse/connected/core/MemoryBookEditorialStoreTest.kt`,
  and this document.
- `cd android && ./gradlew :live-core:test --tests dev.photohouse.connected.core.MemoryBookEditorialStoreTest`:
  passed after owner review, 23 tests, 0 failures, 0 skipped.
- `git diff --check`: passed.
- Tests use only synthetic local API responses. No APK, live API, Windows
  runtime, device, signing, or family interaction was exercised. Compose
  integration and full Android/API delivery remain separate work.
