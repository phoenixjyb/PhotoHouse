# Memoir citation originals on the phone

October 5, 2026. Source base `a4583c147192dc0cda3d5b0a3f57285b0974cc1e`,
branch `codex/phone-v29-candidate-20260929`.

The memoir arrangement panel now offers **查看原始回忆 / Inspect original**
separately from each citation checkbox. It does not select or save a reference.
The inspector distinguishes original wording or recording from derived
transcripts and polished text. Missing processing results remain explicit.
An audio contribution needs a separate **Load original recording**, then
**Play original recording** action through the existing reader audio coordinator.
Playback yields to recording. Inspecting text never fetches audio.

Only current catalog identities are inspected. Acceptance binds the account,
credential, library, book/revision, ordered child snapshots, reader/session
generation and request ticket. Contribution identity, accepted state, processing
consent, compatible chapter and base revision `1..current child revision` must
match. This permits an original written before later story revisions.
Protected denial closes the memoir through the existing access-failure path;
deleted sources become unavailable. Scope changes, catalog refresh, editor
collapse, dismissal and lifecycle pause/stop clear detail and close audio.
Late responses cannot restore the old inspector; response audio bytes are wiped.
Editorial drafts and frozen mutation retries keep their existing behavior.

## Evidence

- Final filtered `:live-core:test` run: **111 tests**, zero skipped, failures or
  errors: source inspection **9**, editorial integration **5**, connected store
  **97**. Tests include held replies across child/book refresh, catalog removal,
  account/library invalidation and stale audio wiping.
- Two focused synthetic emulator journeys passed on existing API 36 emulator
  5558 at 150% text: original/derived text inspection without selection, and
  explicit audio loading/playback with recording ownership. The text journey
  was repeated in English after the header width correction and passed.
- Root inspected Chinese text/audio and final English 150% renders. The English
  title and Close control have separate space. These are generated fixtures,
  not household records or physical microphone/playback acceptance.

No API/wire/shared schema or version change was made. There was no release build,
signing, OTA publication, installed physical-device check or live endpoint test.
The frozen unsigned v41 remains SHA-256
`88e6f9adae2c9257d9507c22694d9ce3c5ee5483ef639161e3fcf48cb4e543bc`
and does **not** contain this source inspector. Manual memoir arrangement still
needs the separately qualified/enabled b1 server and a later signed phone release.
