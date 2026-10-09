# Android memoir draft directory

`MemoryBookNarrativeDirectory` is a compact, optional table of contents for a
reviewable memoir proposal. It starts collapsed and is keyed by the caller's
scope key, so a different book revision or narrative job gets a fresh collapsed
directory. When expanded, each row shows its chapter number, the complete story
title, and the complete chapter title. The selected row has a visible current
marker and radio selection semantics. Titles wrap instead of being shortened.

Selecting a row invokes only the supplied local `onSelect(index)` callback and
collapses the directory. Opening or closing the directory has no callback. The
component does not load original stories, save, queue, chat, record, or speak.
The parent owns proposal selection, scrolling the selected draft back into view,
and stopping read-aloud when the chapter identity changes. The proposal reader
is separate from saved memoir content.

The server and core store cap a proposal at 24 chapters, and each saved story
plan section supports at most six chapters. A valid maximum-size synthetic UI
fixture therefore uses four stories with six chapters each. Do not create a
12-chapter section or relax the store validation to accommodate a UI test.

## Local qualification (October 6)

The integration owner inspected the complete 24-chapter Chinese and English
directory and the selected final chapter at 150% text on the reused API 36
emulator. Full titles wrap, direct selection returns to the proposal, and
changing chapters stops the previous read-aloud. When AI review is expanded,
saved-story navigation stays beside the saved original rather than obscuring
the proposal with a second sticky chapter counter.

The final two synthetic memoir journeys and debug lint passed. They check the
valid four-story/six-chapter fixture, current selection semantics, direct jumps,
read-aloud cancellation, original-story reading, and unchanged job/plan/save
counts. Earlier failed fixture and accessibility-window attempts are retained
as evidence; only the final unmasked captures were accepted. Screenshot capture
rejects active Android system-error dialogs instead of treating a masked screen
as a visual pass.

This is source and emulator evidence. It does not qualify a signed APK, Windows
provider, deployed service, real microphone, or family-device experience.
