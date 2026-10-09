# Phone story chapter directory

Source base: `e1a462e`, branch `codex/phone-v29-candidate-20260929`.

The saved-story reader now offers a collapsed chapter directory beneath its
read-aloud controls. Readers can open the directory, see complete chapter titles,
identify the current chapter and jump directly to another chapter. The directory
uses the reader's scrolling body, so long titles and many chapters do not consume
the fixed navigation area. Opening it scrolls the reading body to the directory.

A chapter jump uses the existing authorized story and chapter-selection callback.
It closes the directory after selection and resets the reading body to its start
instead of retaining the previous chapter's scroll offset. Selection is disabled
while chapter frames are loading; the callback rechecks the current account,
library and story.
Directory visibility and scroll state are scoped to account, library, story and
revision. Returning to the shelf and reopening a story starts with it collapsed.
Existing previous/next navigation and read-aloud behavior remain available.

## Checks

- Two synthetic emulator journeys passed: Chinese and English at 150% font scale.
- Both journeys checked full long titles, selected-chapter semantics, jumps in
  both directions, no extra story-detail request and reset on reopening.
- The combined run also included five dictation journeys: seven tests, zero
  failures, errors or skips. `:connected:lintDebug` passed.
- Full-screen Chinese and English captures were inspected for wrapping, visible
  navigation controls and the selected chapter's contrast.
- After adding the chapter-scroll reset, the same two directory journeys passed
  again, asserting the selected title was visible without scrolling the test to it.

These checks used the existing Android emulator and synthetic media/account data.
They do not establish physical-device, live-service or family acceptance. This
change belongs to the next source release; the frozen v42 artifact is unchanged.
