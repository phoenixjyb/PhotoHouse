# Continue a memoir on the phone

Opening a memoir can offer **Continue last read / 继续上次阅读** or
**Start from the beginning / 从头阅读**. Opening the book never chooses the
saved location automatically. Continue returns to the exact child story,
chapter, preview page and selected photo or video; opening its original media
and starting narration remain separate actions.

## Exact location, fresh access

A location binds the account, library, book ID and revision, child story ID and
revision, chapter ID and asset ID. Before offering it, the phone rereads the
protected book and its ordered children, then the matching child story. This
validation fetches metadata, not previews, originals or audio. Continue performs
fresh parent and child reads again before navigating.

A changed book or story revision, missing chapter or missing moment removes the
pointer rather than guessing a replacement. A definite invalid/404/409 child
response also removes it. A transient read failure hides the offer and retains
the pointer for a later fresh check. Every completion, including failures,
checks the current session and reader before changing state or stored records.

Only deliberate story, chapter, preview-page and frame navigation records a
location. Automatic thumbnail loading does not. Start over removes only this
account/library/book pointer and opens the first story without immediately
recreating it. Failed local storage leaves ordinary reading available.

## Private storage and unfinished work

At most twelve memoir locations per account are retained, newest first, in a
strict versioned record bounded to 16 KiB. Records contain identifiers and
revision metadata only: no memoir prose, original notes, audio or credentials.
They are AES-256-GCM encrypted in Android's private no-backup directory using a
Keystore key. Origin, account and the fixed memoir domain authenticate each
record; story bookmarks use a separate domain. The existing story envelope is
preserved for compatibility. Malformed or unauthenticated records yield no
location and receive best-effort deletion; atomic writes retain the prior file
if writing fails.

Backgrounding preserves locations. Logout, expiry and a current access denial
clear the matching account's records. A delayed response from an old account
cannot clear the replacement account or mount its book.

Continue and Start over refuse unfinished conversation text, recognition review,
recording, source audio inspection, editorial changes/conflicts, pending
generation and edition work. These controls cannot submit text, save a story,
invoke a model, open originals, start video or turn on the microphone.

## Qualification and delivery

Source `c3e2706` passed an extended 124-test core cohort across album selection,
the codec, memoir store and existing saved-story store. The earlier 108-test
cohort overlaps this result. New cases cover process recreation, exact
asset restoration, storage failure and delayed old-account errors. Two generated
API 36 journeys pass in Chinese and English at 150% text size, including explicit
Continue and Start over with no original/video calls. Both offer renders were
visually inspected. Full source and real-Keystore qualification are recorded in
[the development record](DEVELOPMENT.md).

These are local source and simulator results. A new signed phone APK, OTA
publication, compatible installed service and family reading walkthrough remain
separate delivery gates. Web and TV storage are unchanged by this feature.
