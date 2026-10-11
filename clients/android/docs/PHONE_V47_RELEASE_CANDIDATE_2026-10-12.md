# Phone v47 memoir composition source candidate

Version 47 (`0.47-family-memoir-composer`) reserves a new phone release identity
for the current monorepo source. Its version change is pinned at `a4507e3`.
The installed/published v46 remains a separate release.

## User-facing source changes

- Create a memoir from 1–24 current, readable saved stories; review their order
  and an optional opening, then explicitly save.
- Dictate an introduction with separate Record, Stop, transcript review, Add
  and Save actions. Edits typed during transcription are retained. Overflow
  leaves both texts available; audio stays transient.
- Browse a visual memoir shelf with bounded protected covers, a local fallback,
  opening excerpts and explicit reading controls.
- Read a saved memoir opening with explicit local Read, Pause, Resume and Stop;
  preserve the current chapter and reading position.
- Continue a full conversation without deleting the old history or automatically
  sending retained words into the new thread.
- Preserve current chapter/reader and unsent drafts; ignore detached controls and
  obsolete authorization responses.

The [composer contract](../../../docs/PHONE_MEMOIR_COMPOSITION.md),
[voice contract](../../../docs/MEMOIR_INTRODUCTION_DICTATION.md),
[opening narration](../../../docs/MEMOIR_INTRODUCTION_NARRATION.md) and
[development evidence](../../../docs/DEVELOPMENT.md) separate focused core tests,
complete source profiles and generated emulator journeys. The source-change
ledger records exact paths and hashes. The complete final Android profile is
recorded after source integration; earlier runs retain their own revisions.

## Delivery gates

This is an unconfigured public-source candidate. The source profile supplies
no household endpoint, release signer or deployment setting. A distributable
APK still needs a reviewed private build profile, compatible served feature
capabilities, a newly pinned unsigned release artifact, signing authorization,
signature/version/hash readback, HTTPS OTA publication and phone walkthrough.
Passing debug builds or simulator flows does not establish these gates.

No signing, OTA publication, Windows operation or physical-device installation
is part of this source candidate. TV's version and access configuration are
unchanged.


## Family walkthrough after delivery

Run this only after the compatible private release and served capabilities are
verified. Use a generated or deliberately selected family test story; do not
infer availability from this public source build.

1. Open saved stories, choose Create memoir and select readable stories. Confirm
   their order, opening text and language before Save.
2. Record an opening, Stop, review and edit recognized words. Type additional
   opening words while transcription is pending; Add should retain them.
   Discard should retain typed words. Neither action should save the book.
3. Save once, open the returned memoir, close and reopen it. Confirm the exact
   ordered stories and saved introduction remain. Check covers or their fallback.
4. Choose Read introduction aloud. Check the saved language, Pause, Resume and
   Stop. Navigate to a chapter while reading: opening speech should stop without
   restarting or advancing the chapter. Return and start it explicitly again.
5. Record another memory while reading, then finish or discard it. Speech must
   stop and remain stopped until a new explicit Read action. Background or logout
   should also stop speech; return should not start it automatically.
6. Repeat at enlarged system text size and in both interface languages. A member
   should see only authorized stories; a revoked account must not reuse old cards,
   sources, audio or editor controls. Preserve any unsent draft before logout.

Record installed version, served source, feature capabilities, interface/book
language, installed local voice and the step that failed. Family content should
remain private; use asset IDs and status rather than copying narration into
public issues. Listening quality is a human check separate from fake-voice tests.


## Frozen local package evidence

Client source qualification at `263439c` passed all 19 Web suites and the
complete Android JVM/lint/debug profile with unchanged snapshots. Nine generated
phone opening/reader instrumentation cases passed, with both enlarged language
renders inspected. The frozen public v47 unsigned release build passed in 30s:
10,058,085 bytes, SHA-256
`5e38f059d25bed72edc53a46f487e3aa0a31f169cae7589b594a12f7d84202e8`.
It has empty origins, all optional capabilities disabled and no signature.
This artifact qualifies compilation and version identity only; private release
configuration and publication remain the delivery gates listed above.


Generic release lint passed separately in 29s. Native `aapt2` package inspection
also reports `dev.photohouse.connected` and version 47. These checks add no
private build configuration or signing evidence. The prepared Web overlay and
remaining cross-client operations are in the [local handoff](../../../docs/LOCAL_CANDIDATE_2026-10-12.md).
