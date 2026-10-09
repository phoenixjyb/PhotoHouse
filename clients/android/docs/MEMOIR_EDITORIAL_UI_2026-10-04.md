# Android memoir editorial UI integration

October 4, 2026. The owner book reader now contains a closed-by-default
**编排回忆册** panel. Opening it explicitly loads contribution-reference metadata
for the ordered child stories and then negotiates the optional editorial route.
The metadata request uses the protected contribution-reference endpoint and
returns chapter and contribution IDs only. It does not fetch chapter text or
audio. Older `MemoryCommunityApi` and `MemoryBookEditorialApi` adapters remain
compatible; an unsupported source catalog or editorial endpoint leaves the
legacy memoir reader available.

The panel lets the owner select introduction citations and write text with
citations between adjacent stories. It shows source labels from story titles,
chapter positions, and contribution order; it never displays raw contribution
UUIDs. Each transition folds independently. Save, conflict refresh, reviewed
rebase, discard, and uncertain retry are explicit actions. The exit warning
offers a later check when the server may already have accepted a frozen save;
leaving clears local state and does not cancel or replay the request.

On acknowledgement, the selected book and shelf summary advance together to
the returned revision. The editorial store retains a newer draft if one was
entered during the request. Revision-bound memoir chat context is refreshed
without clearing local composer drafts. Save and explicit conflict refresh are
blocked while chat work is actively sending, pending, recording, or
transcribing. A fresh conflict refresh loads the latest book and source
eligibility before asking the editorial store for the current basis.

## Evidence

- Source catalog decoder and HTTPS adapter tests verify actual ordered chapter
  counts (including a one-chapter story), revision/library binding, and the
  protected metadata-only route.
- `MemoryBookEditorialIntegrationTest` exercises explicit-open/no-prefetch,
  catalog failure, owner edit/save acknowledgement, exact uncertain retry,
  revision-coherent shelf update, conflict refresh with draft retention, and
  scope clear.
- `MemoryBookEditorialUiTest` checks source selection, adjacent transition
  text, unavailable/conflict/uncertain controls, and the uncertain-save exit
  warning at 100% and 150% font scales. It saves synthetic screenshots to
  `Pictures/PhotoHouseEditorialUi` on an emulator.
- 70 focused core/HTTPS tests passed: five controller integration, 23 draft-store,
  seven wire-contract and 35 HTTPS adapter tests. An additional 143 existing
  community/controller tests passed. The denied-read/metadata/save cases verify
  that a 403 immediately clears the reader, source catalog and draft.
- Debug and Android-test APKs built and installed on the existing emulator. All
  four instrumentation tests passed. One uses the real controller and dialog
  against a synthetic adapter: select sources, type a transition, guard an
  unsaved exit, simulate an accepted save with a lost acknowledgement, retry the
  identical request, close and reopen. The synthetic server persists once and
  the reopened text and references match.
- Final synthetic panel screenshots were inspected at 100% and 150% font scale,
  including the reopened real-controller reader. Text wraps without overlapping
  controls; long sections scroll and fold. These are generated fixtures, not
  household media or an installed Samsung acceptance check.

## Delivery boundary

This change is source and emulator qualified. No release version was advanced,
release APK signed, OTA published or Windows task changed. The optional b1
service still needs native Windows offline qualification and separate migration /
enablement authority before a family can use this editor. Existing readers
continue to work when the optional endpoint is unavailable. AI narrative
processing and original audio editing are separate follow-up work.

## Reproduce the focused checks

From `android/`, with JDK 17 and the Android SDK available:

```sh
./gradlew :live-core:test --tests '*MemoryBookEditorialIntegrationTest' \
  --tests '*MemoryBookEditorialStoreTest' --tests '*MemoryBookEditorialTest' \
  --tests '*HttpsApiTest'
./gradlew :live-core:test --tests '*MemoryCommunityStoreTest' --tests '*ConnectedStoreTest'
./gradlew :connected:assembleDebug :connected:assembleDebugAndroidTest
```

Install those two debug APKs on an emulator, then run
`dev.photohouse.connected.MemoryBookEditorialUiTest` through
`androidx.test.runner.AndroidJUnitRunner`. The test adapters use synthetic
identities and data without a household service connection.
