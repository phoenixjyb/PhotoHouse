# Whole memoir plan and suggestion review on the phone

The selected memoir now offers a separate, initially collapsed “整理整本回忆册”
entry. It works before opening an individual story. The user writes arrangement
instructions, optionally includes the saved opening and transitions, checks the
available chapters, then explicitly asks for a draft. Checking never queues a
job. Confirmation hides the input keyboard so the status and review are readable.

A ready suggestion is shown one chapter at a time with its original story/chapter
labels, citation count and questions. Previous/next controls, explicit local
read-aloud and opening the original story support review. Uncited passages have
an honest warning. No proposed text is applied or saved into a child story.
Instructions are retained through an acknowledged editorial revision, while the
old plan, context selection and remote proposal are invalidated.

A network-uncertain request retries the exact mutation, text and context choice.
Definite 409/422 rejection drops that retry state, keeps the instructions and
requires an explicit fresh plan check. Oversized or view-only plans cannot queue.
Account, library, book, child revision and reader changes fence delayed responses.
Closing/back/media navigation warns about unsent instructions, active recording,
transcription and pending work. Choosing to stay preserves the current input.

## Local evidence

- 10 synthetic coordinator checks, 51 community/store integration checks, and
  six editorial integration checks passed in focused JVM runs.
- Three API 36 emulator flows passed: Chinese/English at 150% text for the whole
  plan → request → chapter review → original story path, plus active-recording
  exit protection. The two rendering flows passed again after fixture titles
  were aligned with their saved stories.
- Debug lint passed. Final full-screen captures were inspected with keyboard
  hidden and controls reachable; synthetic family content only.

This is next-release source. It does not alter the frozen v42 release candidate,
qualify native model prose, enable Windows processing, publish an APK or establish
physical phone/family acceptance. See [the core contract](ANDROID_WHOLE_MEMOIR_DRAFT_CORE_2026-10-06.md).
