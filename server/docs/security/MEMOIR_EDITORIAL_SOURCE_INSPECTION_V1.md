# Memoir editorial source inspection v1

Source/UI candidate, October 5, 2026. The memoir editor can inspect an eligible
family contribution while choosing citations. Inspection is separate from
selecting a citation, editing memoir prose, saving, or generating anything.

## Eligibility and display

The inspector is available only for a source in the current authorized memoir
catalog that is accepted and records processing consent. It binds the selected
account and library, memoir and ordered story revisions, editorial generation,
and current catalog entry. The contribution-detail request is sent only after
the user selects **Inspect source**.

Original text is labeled as family wording. For audio, the original recording is
identified separately. A transcript and polished text are shown only as derived
content and labeled accordingly; a missing, pending, or failed derivation is
reported as such. Reading a source does not change its citation checkbox or
memoir draft.

Audio bytes are fetched only after a second explicit **Load audio player
explicitly** action. The browser creates a native player with controls, without
autoplay or eager preload. The response must be bounded mono 16 kHz PCM16 WAV,
within the existing 30-second and 2 MiB limits, and its SHA-256 must match the
accepted contribution detail before an object URL is created. A successful load
is idempotent. Inactive or capture-owned players are paused. Inspection cleanup
aborts outstanding reads, removes players and revokes their object URLs.

If the account, library, lock state, memoir/story revision, catalog membership,
editor visibility, or document visibility changes, the inspector clears its
content and fences late detail/audio responses. A failed or denied source read
does not leave previously inspected text visible or substitute another source.

## Local source evidence

The implementation is in `backend/app/ui/access/memory-community.js`; responsive
presentation is in `backend/app/ui/access/styles.css`. The synthetic browser
bridge and Chromium journey are
`tests/security/memory_book_editorial_browser_bridge.py` and
`tests/security/test_memory_book_editorial_browser.cjs`.

The local synthetic browser journey covers default-off fallback, eligible
inspection, separation of original and derived text, explicit and idempotent
audio loading, URL cleanup, stale-play pausing, 404/403 clearing, held-response
fencing across source/book/account/background changes, save/retry behavior,
conflicts, and deleted-source invalidation. Chinese and English mobile views
were rendered at 390 px with 150% zoom; an English desktop view was rendered at
1280 px. These are source-level synthetic UI results. They do not establish
Windows installation, live service behavior, physical-device acceptance, or
provider/model acceptance.

Run receipt and screenshots are retained in the local artifact directory
Private local qualification artifacts are intentionally excluded from this public source export.
