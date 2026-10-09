# Story reader navigation

The Web and phone readers keep a selected media frame inside a selected story
chapter. Selection changes the current preview; it does not start video,
narration, microphone capture, story saving or a model request.

## Web filmstrip

Each chapter shows protected preview thumbnails with visible frame numbers and
a video marker. Controls have at least 44 px targets, localized position labels,
selected semantics and a live current-frame notice. A failed thumbnail leaves
its frame selectable. The existing outline groups up to 24 selected media into
chapters of at most four frames; this change preserves that contract.

Clicking or using arrow keys reveals the selected control inside the horizontal
strip. It does not scroll the page or reader dialog. Language changes preserve
focus and strip position. Detached controls are bound to their rendered draft,
chapter and access generation, so they cannot act on a replacement reader.
Late preview errors and detached video controls likewise recheck the current
reader and DOM attachment before changing the stage or opening media.
Signing out clears the controls and live position notice.

## Phone reader

The selected frame is bound to current account, library, access generation,
story revision, chapter identity and ordered eligible media. A changed scope or
media cohort resets selection to the first current frame. Preview bytes are
shown only for a current story item. Explicit frame, chapter and open-media
callbacks recheck the current reader before acting.

The strip exposes selected semantics and a localized position label. Chapter
count has its own line; equally sized Previous/Next buttons retain 48 dp
minimum targets at enlarged text. This avoids placing three competing labels
in one narrow row.

## Evidence and delivery

Generated browser journeys cover keyboard navigation, narrow bilingual renders,
one/two-frame chapters, failed thumbnails, detached controls and logout. Phone
instrumentation uses generated adapters on an API 36 emulator; its source and
render results remain separate from a signed APK, OTA, installed phone or TV.
See [development evidence](DEVELOPMENT.md) for the exact checks.

This reader work does not change the TV application or its anonymous LAN access
policy. Original playback, contribution review and story/memoir conversation
controls retain their existing explicit actions.
