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
- Continue a full conversation without deleting the old history or automatically
  sending retained words into the new thread.
- Preserve current chapter/reader and unsent drafts; ignore detached controls and
  obsolete authorization responses.

The [composer contract](../../../docs/PHONE_MEMOIR_COMPOSITION.md),
[voice contract](../../../docs/MEMOIR_INTRODUCTION_DICTATION.md) and
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
