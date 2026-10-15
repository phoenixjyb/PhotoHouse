# Title from a chapter opening

Delivered for new Web/phone stories in the [October 15 v64 release](../clients/android/docs/PHONE_V64_RELEASE_2026-10-15.md).
Provider-backed title suggestions keep their separate, default-off qualification
gate.

## Experience

After typing chapter words or explicitly adding a reviewed transcript, a compact
card offers **用章节开头做标题 / Title from a chapter opening**. It identifies
the chapter and shows the exact candidate. **用作标题 / Use as title** updates
the title field only. A custom title remains until that explicit action; the
chapter text remains unchanged. The title remains editable and saving the story
is a separate action. This does not request a model or save anything remotely.

The card uses the first nonblank chapter narration explicitly authored in this
draft. Outline scaffolding, source captions and linked contributions do not
become authored text merely by opening the editor. A deliberately adopted title
is stored as authored when the user separately saves a private device draft.
Existing saved-story editing does not offer this shortcut.

## Deterministic extraction and guards

Use the first nonblank CR/LF line, trimmed at its edges. Take its first sentence
through `。！？!?`; a period ends a sentence only before whitespace or the end
of the line, preserving decimal points. Offer only a complete nonblank title of
at most 80 Unicode code points and 640 UTF-8 bytes. Do not truncate, rewrite or
skip an overlong opening in favor of a later chapter. Reject control characters,
Unicode line separators, bidi controls and malformed surrogate sequences;
ordinary emoji and valid joined emoji remain intact.

A displayed action is bound to its current editor, account/library, selected
frames, chapter wording and title. Stale actions cannot replace newer work.
Recording/transcript review, IME composition, pending saves, source refresh and
editor/scope changes fence adoption. Typed text and explicitly inserted reviewed
voice text follow the same authored-text path. A transcript is not an original
audio attachment or proof of factual accuracy.

## Qualification

Focused browser journeys exercise the actual protected ASGI application with
synthetic SQLite data and no listening server/model. They cover provider-off
adoption, literal text, retained custom titles, stale controls, IME, Unicode,
English/Chinese large text, unfinished recording and encrypted private-draft
reload/resume. Kotlin store tests cover scaffolding exclusion, first-authored
selection, snapshot guards and reviewed voice insertion/private persistence.
The QA emulator journey exercises the visible button and private draft save.

Local results: 13 title-browser checkpoints, 30 full workspace checkpoints,
seven encrypted-draft browser groups and all 40 `StoryWorkspaceStoreTest` cases
passed. QA APK and instrumentation builds passed. Bilingual Web controls were
rendered at 390 px with 150% text and inspected for wrapping and action size.
The explicit QA-emulator button/private-save case also passed with Chinese/English
150% text. Its generated renders were inspected; the candidate, source chapter
and adoption action remain readable and reachable. These are synthetic fixtures,
not family/device acceptance.

Hosted CI, signed APK publication and Windows service delivery passed for v64.
Family use remains a separate gate. This increment changes no protected API route, database
schema, provider activation, recording retention or permissions.
