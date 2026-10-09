# Chat about the current memoir chapter

## Source scope

This source increment adds explicit discussion of the chapter currently open in the memoir reader. It was developed after an earlier client package; package contents and installed behavior must be checked separately.

An existing memoir conversation offers “聊聊正在阅读的篇章” / “Discuss this
chapter”. Choosing it fills a bounded, editable question naming the current
story and chapter. It requests source-based discussion and a question for the
family, preserving uncertainty. It never creates a conversation, sends a turn,
fetches extra context, saves a story, records audio or starts speech playback.
The user reviews the question and explicitly sends it through the existing
protected conversation path.

The captured identity includes account/generation, library, reader scope, book
and child revisions, chapter ID/index and selected conversation. Selection
rechecks the visible authorized reader and loaded turns. Closed/loading readers,
changed chapter/story/thread and forged snapshots are refused. Core and UI guards
preserve typed input, active IME composition, rejected oversized input, unfinished
voice review, pending retries and active replies. The thread draft and focus
request are updated together. Only metadata enters the question; chapter prose
and source recordings are not copied into the composer.

## Checks on October 6

- 58 `MemoryCommunityStoreTest` tests plus two pure question-boundary tests passed.
  Five new store cases cover explicit send, chapter/account changes, typed input,
  uncertain retry, missing/running thread and unreviewed voice preservation.
- Two focused emulator journeys passed in Chinese and English at 150% font size
  on the reused API 36 emulator. They cover editable insertion, typed-input
  protection, chapter changes within the same thread and explicit sending.
- `:connected:lintDebug` passed. Build origins were empty and real-network feature
  flags retained their default-off values. Synthetic injected repositories were
  used; no family service or recording was involved.
- A subsequent keyboard-layout increment keeps the dialog within its resized
  window, applies readable system-bar contrast, and temporarily hides the fixed
  chapter footer while the keyboard is visible. The focused composer is brought
  fully into the scroll viewport, including its label; hiding the keyboard restores
  chapter navigation. The owning dialog restores its original window flags on exit.
- Both bilingual keyboard journeys passed again at 150% text size, together with
  debug lint. Full-display keyboard screenshots were inspected in both languages:
  the shelf heading, close button and complete input frame remain visible. The
  long editable question scrolls inside its field. The emulator hardware-keyboard
  setting is restored after each test. Earlier attempts exposed real layout issues
  and intermittent software-keyboard visibility; the final run checks visible IME
  state and complete input-frame bounds rather than only test-node existence.

The existing memoir form, voice-instruction and whole-memoir review flows then
passed as one six-flow Chinese/English regression run (86.309 seconds, no failures
or skips). The whole-memoir flow now checks both the selected checkbox semantics
and stored editorial-context choice immediately after touch, before requesting a
plan. Earlier failed captures showed the option unchecked; a capture immediately
after touch also preceded visual recomposition. The final test records successful
screenshots after the checked/state assertions, and failure-only screenshots when
those assertions fail. That capture-order-only adjustment passed a final isolated
Chinese flow (43.728-second suite). No assertion was weakened or blind sleep added.

The first emulator run failed only its last assertion, which incorrectly expected
an action to remain disabled after the synthetic server returned a completed
reply. The corrected check verifies the empty composer is reusable and no second
message was sent. The final two-flow run passed.

Commands, run from `android/` with JDK 17:

```sh
./gradlew --offline --no-daemon --max-workers=2 :live-core:test \
  --tests dev.photohouse.connected.core.MemoryCommunityStoreTest \
  --tests dev.photohouse.connected.core.MemoryBookChapterDiscussionTest \
  -PphotohouseOrigin= -PphotohousePhoneHomeOrigin= -PphotohousePhoneHomeLanAddress=
ANDROID_SERIAL=<emulator-serial> ./gradlew --offline --no-daemon --max-workers=2 \
  :connected:connectedDebugAndroidTest :connected:lintDebug \
  '-Pandroid.testInstrumentationRunnerArguments.class=dev.photohouse.connected.MemoryCommunityUiTest#currentMemoirChapterQuestionWaitsForExplicitSendChinese,dev.photohouse.connected.MemoryCommunityUiTest#currentMemoirChapterQuestionWaitsForExplicitSendEnglish' \
  -PphotohouseOrigin= -PphotohousePhoneHomeOrigin= -PphotohousePhoneHomeLanAddress=
```

## Delivery boundary

No signed APK, OTA publication, physical-device install or Windows deployment
was performed for this increment. Server model quality and actual family use
remain separate evidence. The live phone feed remains v43.

## Evidence boundary

The source revision and its focused checks are recorded as source-repository evidence. They do not qualify this curated candidate until its checks are run against the candidate tree. Emulator or browser fixture results remain test evidence; they do not establish live-service, signed-package, physical-device or family acceptance. No live database migration, model/provider run, service deployment, package signing or publication is authorized by this source note.
