# Phone story reading continuity

After a fresh authorized story read, PhotoHouse can offer **Continue reading /
继续阅读** at the last explicitly selected chapter and moment. The reader starts
at the first chapter until the user chooses Continue. **Start over / 从头阅读**
removes only this story's saved location and returns to its beginning.

## Private local storage

The phone stores at most twelve location records per account, newest first. A
record contains only the account, library, story ID and revision, chapter ID and
asset ID. It contains no story words, original notes, recordings, passwords,
session token or endpoint. Identifiers still have privacy value: records are
AES-256-GCM encrypted with an Android Keystore key in app-private no-backup
storage. Origin and account bind both the filename and authenticated encryption.

Strict versioned decoding rejects an entire malformed, oversized, duplicate or
foreign-scope record. Corrupt or unsupported encrypted records yield no location
and receive best-effort deletion. Atomic writes preserve the preceding record
if a write fails. Storage failures leave ordinary story reading available.

## Authorization and user actions

Opening a story checks the current protected detail before loading a location.
The account, library, story ID, exact revision, chapter and asset must all match.
A changed revision or missing moment invalidates the saved location; the app does
not guess a replacement. Automatic preview loading never writes a location.
Only explicit chapter/frame navigation records a location.

Continue and Start over are unavailable while private input, recording,
recognition review or chapter-link changes are unfinished. They change only
reading selection and protected previews. Original media, video playback,
narration, microphone capture, source writes and commands remain separate
explicit actions. Backgrounding retains the disk record; logout, session expiry
and a current access denial clear only the captured current account. A late old
request cannot clear a replacement account's records.

## Local evidence

Source commit `7b3e68d` includes six strict codec tests, twenty-three reader-store
tests and strengthened current/stale saved-editor denial cases. Five generated
API 36 instrumentation tests passed real Keystore encryption, account/origin
isolation, bounded history, corrupt data and unsupported encrypted versions.
Bilingual 150% reader tests verify explicit Continue, the exact selected moment,
Start over and no original/video/open-media calls. Render checks and subsequent
phone voice regression results are recorded in the current development record.

These are source checkout and generated emulator checks. They do not publish a
signed phone APK or establish household/device acceptance. Web and TV reading
storage are unchanged by this slice.
