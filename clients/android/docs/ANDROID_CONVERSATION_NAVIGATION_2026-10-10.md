# Returning to a story or memoir conversation

The phone keeps the last selected conversation for a saved story or memoir in
the current process. Reopening the reader fetches a fresh protected directory
and fresh messages, then shows “已回到上次选择的对话。” only if restoration
succeeded. The composer is empty. Recording, transcript insertion, creating a
conversation and sending a message remain explicit actions.

## Scope and interruption

The bounded hint contains an ID and account/library/membership/target revisions,
with ordered child story revisions for a memoir. At most 16 hints are kept;
there is no disk persistence of these hints or of unsent text, audio or replies.
A missing conversation falls back to the current authorized directory. Changed
membership or target revisions cannot reuse an old selection.

Backgrounding clears the reader's private content. Foregrounding checks the
session again before retaining a hint for the same available library. Logout,
account changes and current access denial clear hints. A delayed denial from
an older reader cannot close its replacement. Fresh turn reads pass a reader
guard through the repository's denial callback as well as the store response
checks.

The existing pending-reply check reads status; it does not resend the original
message. A failed history read cannot show a restored notice. Existing unsent
draft, recording and pending-submit controls still apply when explicitly
switching between conversations inside an open reader.

## Local qualification

The October 9–10 source cohort passed 610 live-core JVM tests, with no failures
or errors. It includes fresh restoration, missing IDs, pending-job read without
resubmission, history failure, changed scope and revisions, memoir child order,
background revalidation, current access denial and delayed stale denial. These
focused cases overlap the full count and are not added to it.

Use the existing JDK 17, Android SDK and Gradle 8.10.2 installation:

```sh
/path/to/gradle-8.10.2/bin/gradle \
  --offline --no-daemon --max-workers=2 -PphotohousePhoneUiQa=true \
  :live-core:test :connected:compileDebugKotlin \
  :connected:compileDebugAndroidTestKotlin :connected:lintDebug \
  :connected:assembleDebug :connected:assembleDebugAndroidTest
```

Phone debug and Android-test Kotlin compilation, lint, QA APK and instrumentation
assembly passed. Five API 36 emulator tests passed: a localized notice check and
four story/memoir reopening journeys in Chinese and English at 150% text. They
create and select a thread explicitly, leave through the unsent-draft confirmation,
reopen from fresh reads, verify the empty composer and no automatic ASR/send, and
capture the restored reader. All four reader captures were visually inspected.
The draft was inserted through the fixture store, so keyboard interaction is not
qualified by these journeys.

The first run exposed incorrect fixture navigation; a later run was rejected
because an Android system error dialog obscured the screen. The final run used
the same existing AVD, cold booted with hardware graphics and two CPU cores,
without saving a snapshot. Failed runs were retained separately; their assertions
were not weakened.

The QA application ID is separate from the family app. Its generated fixtures
need no household server, account, recording or model. Emulator results and
render inspection are recorded separately in [development evidence](../../../docs/DEVELOPMENT.md).
This source candidate is phone version 46, `0.46-conversation-continuity`.
It has no production signature, Windows OTA publication or physical-phone
acceptance result.
