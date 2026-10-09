# Phone reviewed memoir edition editor and reader

## Scope

This source increment wires the optional edition coordinator into ConnectedStore
and the whole-memoir reader. It follows prior protocol/coordinator increment and
consumes the separately gated C2 backend contract. The default-off capability
must be enabled by a separately qualified backend before a family can save.

A ready whole-book suggestion offers **审阅并保存整本回忆录**. Opening explicitly
checks capability and fetches the private proposal; job completion never adopts
it. The panel edits a title and one chapter at a time, displays the parent story,
chapter position, citation count and unresolved questions. Chinese is the
existing default; English is also localized. Original stories and recordings
are separate from the reviewed edition.

Each edit or IME composition clears the explicit review checkbox. Oversized or
invalid local input remains visible and prevents confirming/saving the last
accepted text. It also requires discard confirmation before leaving. Chapter
identities, source references and questions remain bound to the proposal.

Only the review checkbox followed by **明确保存这个版本** sends the save. Uncertain
saves freeze the body/mutation and disable editing, regeneration, chat submission
and conflicting book-basis updates. An explicit retry sends identical content.
Closing the book during an uncertain save offers retry/stay instead of discarding
the retry identity. A known conflict permits a confirmed discard and fresh check.
Ordinary dirty edits require a discard decision. Scope clearing on logout,
library/account changes or reader invalidation fences late results and drops
transient protected data.

The receipt contains no prose. **重新读取已保存版本** clears previous text before
fetching current authorization and source state. A changed/invalidated source or
failed read leaves prior prose hidden. A current manuscript supports chapter
navigation and explicit read-aloud. Nothing starts playback or recording itself.

## Delivery boundary and next work

The editor has no durable local draft store or new HTTP route. Signing, OTA,
backend schema migration/activation, provider quality and physical-family use remain
separate gates. The previously released phone package does not contain this increment.
The [independent family edition shelf](ANDROID_SAVED_MEMOIR_EDITION_SHELF_2026-10-07.md)
now has a separate source increment. Full source-detail inspection and complete
backend purge coverage remain outstanding.

## Qualification (October 7)

- Focused JVM scopes: **65 tests**, no failures/skips (7 edition coordinator,
  58 community/ConnectedStore integration). The coordinator's new rejection case
  prevents saving the last accepted text or leaving without a discard decision.
- Six combined bilingual 150% emulator journeys passed: edition editing/retry/read,
  existing whole-memoir suggestion and current-chapter conversation/keyboard.
  After the final title-height and invalid-input disclosure protection, the two
  edition journeys passed again with the software keyboard explicitly shown.
  These are six distinct journeys, with two final reruns, not eight unique tests.
- The final edition journeys exercise 24-chapter scope/navigation, no automatic
  adoption, review invalidation, oversized input, kept dirty edits, identical
  explicit retry, frozen controls/exit, fresh read and source invalidation.
  Save/review/navigation controls fit the reader's width. Rendered Chinese and
  English keyboard, review and saved-reading screenshots were inspected.
- Debug lint passed: 0 errors, 5 warnings. A composition-time StateFlow read found
  during qualification was fixed to observe the flow with collectAsState.

Checks reused JDK 17, the existing offline Gradle cache and the reused synthetic Android emulator; all
configured service origins were empty. The Android API was a synthetic fixture,
including the source invalidation and lost receipt; no real source was deleted,
no provider/model ran and no live service or family data was contacted. The
software-keyboard preference was restored after each test. This is source and
emulator evidence, not native C2, signed-package or physical-device acceptance.

## Public candidate source checks (October 7)

On the curated candidate, `:connected:compileDebugKotlin` and
`:connected:lintDebug` passed. Lint reported six warnings and one informational
issue, with no errors. An offline `:live-core:test` run filtered to
`MemoryBookEditionStoreTest` and `MemoryCommunityStoreTest` passed 65 tests
(7 and 58 respectively), with no failures or skips. The Gradle run used JDK 17
and empty service-origin properties. It did not run an emulator or build, sign
or publish an APK. These candidate checks are separate from the source-revision
emulator evidence above.
