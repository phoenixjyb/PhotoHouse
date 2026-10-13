# Phone v56 and saved-memory followup candidate

Status: built locally and qualified on Windows; not signed, not published, and
not deployed.
The served API/Web and phone OTA remain the separately verified v55 release.

## Fixed identity

Source: `043c9386621a9ccc9bc74a7f868733bc0f725d53`.
Phone `dev.photohouse.connected`: version 56 / `0.56-memory-followups`.

| Artifact | SHA-256 | Bytes |
|---|---|---|
| 195-file API/Web source ZIP | `695acbd6a8cb3dedd970a790e44b85138ae270a7e0d2c48673c464168d9625f3` | 3,404,539 |
| Unsigned phone APK | `ed8488585a523fad76eafc058f24dffc5dcaa6a064f55286e1336339b4f6b2d0` | 11,510,949 |

The private production profile is reused unchanged. All seventeen embedded
BuildConfig fields (fourteen booleans and three routing strings) match that
profile. Package/version, clean source pin and unsigned state were inspected
with Android Build Tools. The original shared mark pixels match exactly;
optimized resource names required content-based image lookup.

## Changes and checks

[Saved-memory followups](../../../docs/ASSISTANT_SAVED_MEMORY_FOLLOWUPS.md)
add original-excerpt and chapter-outline requests over the current displayed
cohort. Typed and foreground voice turns bind the latest fresh completed parent;
localized suggested questions only populate a draft after ending voice.

- Assistant security: 180 tests, one external-adapter skip. Web controller:
  59 checks. Generated browser journey: thirteen checkpoints.
- Portable qualification: six checks. The fixed extracted 195-file package
  separately passed eleven synthetic scenario groups, including search →
  overview → outline → reader → inert recovery. No provider or live data used.
- Immutable package closure/import/synthetic-a0 tests: six checks. Profile
  dispatcher tests: thirteen checks. Current source ledger verifies.
- Android focused JVM: 57 store/HTTPS/voice checks; fifteen earlier wire checks
  are a separate overlapping cohort. Release build and release lint passed.
- At the fixed source pin, empty-origin QA/test builds passed. Four direct
  emulator cases passed again after final label polish and version reservation.
  Chinese/English 150% captures were inspected. No physical phone was installed.

## Delivery gates

The approved offline operation staged this exact archive in fresh private Windows
candidate directories and passed native qualification: 195 source files and
11 synthetic scenario groups. The child was bounded to five minutes, 2 GiB,
eight processes and an 8 GiB free-RAM admission floor. No real database,
listener, model/provider, worker, service/task change or publication occurred.

An initial SSH handshake reset happened before any Windows command. Read-only
absence reconciliation and a shared connection allowed the staged operation to
complete. Large read-only parser payloads later needed explicit input framing;
the first EOF-based transport timed out. No maintenance operation was replayed.
All eight exact API controller scripts then parsed natively without staging.

The prepared API/Web switch/rollback plan passed thirteen local controller
checks. Phone signing/publication preparation passed twenty-two synthetic
controller checks and pins the exact new API entry/config, so it refuses phone
publication before the fixed API switch succeeds. A separate complete-operation
authority request covers service fencing, fresh stopped-writer backup, guarded
API switch/recovery, original-certificate signing and HTTPS OTA readback. That
live operation is not yet executed in this record.

Keep schema `a0c9d2e4f817`, original media, models, ASR/TTS/OCR and TV unchanged.
The later backend opening-speech foundation is outside this fixed candidate.
Physical foreground voice, source reader and owner/member acceptance remain open.

## Test after delivery

1. Update the phone and select a library containing saved stories/memoirs.
2. In 拾光助手, search a distinctive saved title/text word using “找故事 …”
   or “找回忆录 …”.
3. Continue by typing or speaking “介绍这些回忆”, then “第一段回忆有哪些章节”.
   Compare the excerpt/outline with the explicitly opened saved reader.
4. Tap a suggested question: voice must end and the question must appear as a
   draft, without sending until you confirm.
5. Change library or reopen old history: previous result actions and voice
   progression must not resume. A changed source requires a fresh search.
