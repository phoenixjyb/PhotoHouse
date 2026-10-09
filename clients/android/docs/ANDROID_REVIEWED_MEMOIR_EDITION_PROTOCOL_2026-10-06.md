# Phone reviewed memoir edition protocol

## Source and compatibility

This optional Android source increment follows the current-chapter discussion
and keyboard-layout changes. It consumes the separately gated backend edition
contract at schema revision `c2e6b8a1d490`. It does not change the frozen
fixture manifest, iOS contract or existing memory-community DTOs. The existing
HTTPS adapter implements a new optional `MemoryBookEditionApi` seam; old fakes
and adapters remain source compatible.

Five routes under the protected memoir endpoint cover capability, private
proposal, explicit save, paged receipts and fresh reading. Authentication uses
the configured trusted HTTPS origin, bearer headers, no redirects, cookies,
cache or automatic connection retry. The edition POST has the exact
`application/json` content type required by the C2 intake; existing routes keep
their previous content type. Bodies are bounded to 128 KiB and response streams
use the existing bounded, wiped-buffer transport.

The new wire decoder checks exact fields/types, canonical UUIDs/revisions,
digests, ordered child/chapter scope, explicit review and 64 KiB manuscript size.
Constructed DTOs receive the same checks before freezing a request. Invalid
Unicode cannot silently become replacement text. Editing title and narration
retains the proposal's chapter identities, citations and review questions.
`needs_review` keeps the AI-draft identity; it does not substitute for the
independent `reviewed` confirmation.

## Ephemeral repository behavior

The repository admits requests only after a capability check for this scope/book.
An older missing/unavailable capability route disables the feature; save failures
are propagated instead of being disguised as optional absence. Family readers
can read while `can_save=false`. Generation is not a repository prerequisite.

An explicitly reviewed save freezes one immutable body and mutation. Retries are
explicit calls with that same object, including when a prior committed edition
has since been invalidated. The receipt remains content-free. The pending object's
printed representation omits prose and credentials; no local draft persistence,
automatic POST, model invocation or recording is introduced.

Each result rechecks token identity, library, generation and the owner's current
reader callback. Late results and stale denials cannot affect a new session. Owned
response bytes are wiped after successful or failed decoding. Current/changed/
invalidated detail states are distinct; only a valid current detail may contain
prose. Metadata lists contain no manuscript.

## Checks and delivery gate

The focused source run passed 22 tests: seven wire tests, six repository tests and
nine existing/new HTTPS adapter tests. They cover explicit review, malformed
Unicode, aggregate escaped-JSON limits, forged/reordered children and citations,
lost/malformed save receipts with identical retry, invalidation, scope changes,
current/stale denials, reader-only access and the actual TLS POST content type.
JDK 17 and the existing offline Gradle cache were reused with all build origins
empty; no private service or device was involved.

The adopted-manuscript coordinator and Compose editor/reader are a subsequent
increment. This protocol did not update the previously signed phone release; no new APK, OTA publication,
physical install, runtime switch or C2 activation was performed. Other source
purge coverage and native journal restore/worker qualification still gate backend
activation.

## Subsequent editor coordinator

A separate source coordinator now implements process-memory title/chapter editing,
review invalidation after edits or IME composition, explicit save, frozen uncertain
retry, confirmed discard and fresh read with prior prose cleared first. Its six
focused tests passed with the seven wire and six repository tests (19 total,
no failures/skips). Late results after scope clearing cannot refill the editor;
changed book/child identity rejects further edits. At that commit it was not yet
wired into ConnectedStore or Compose. The subsequent
[editor/reader integration](ANDROID_REVIEWED_MEMOIR_EDITION_UI_2026-10-07.md)
adds the optional phone surface. The independent edition-list reader remains
outstanding; protocol/coordinator evidence alone does not qualify the UI.
