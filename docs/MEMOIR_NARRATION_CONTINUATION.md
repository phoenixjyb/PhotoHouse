# Read the next memoir chapter aloud

After a chapter finishes, Web and phone can offer **Read next chapter aloud /
继续朗读下一章**. The reader remains at the completed chapter until the user
chooses that action. The action selects and narrates only the adjacent chapter
inside the currently loaded story. It never crosses a story boundary or starts
listening, submits a conversation, opens an original recording or invokes a model.

## A single deliberate attempt

Phone source `92b1285` captures the account, access generation, library, reader,
book revision, ordered child revisions, story revision and both adjacent chapter
IDs before navigating. It verifies the source before changing chapter and the
destination before speech can start. The ordinary explicit chapter-navigation
path records the new reading location. Preview loading does not prevent this
speech action; pending metadata or unfinished private work does.

The transient speech request also binds the complete destination wording and
language. It is consumed before checking eligibility, recording priority and
foreground lifecycle. A refused attempt cannot start later when recording ends
or the app returns to the foreground. The user can choose Read aloud again.
Requests are not persisted. A one-shot start cannot replace a paused session;
explicit Resume retains its bounded speech chunk.

Completion means the current local speech adapter reported the end of every
chunk. A cancelled, paused, failed, replaced or stale utterance does not reveal
the next action. Stop, manual navigation, account/library/revision changes and
backgrounding invalidate the old completion. The final chapter has no next
narration action even when the book contains another story.

Web source `ce2467c` likewise binds its action to the attached reader, book and
ordered child revisions, current story/chapter, exact prose and current speech
run. Starting the next chapter remains inside the explicit click handler, so
the browser retains that user action. Recording or an unfinished dictation
helper refuses it. There is no retry or background narration.

## Qualification

The phone's 90-test memoir-store cohort includes valid adjacency, bookmarks,
replacement scope, unfinished work and forged source/target chapter refusal.
Eighteen generic narration simulator tests cover one-shot consumption, paused
chunk preservation, recording conflict, lifecycle, completion and stale callbacks.
Three memoir narration journeys cover English/Chinese at 150% text, explicit
advancement, stopping, late callbacks, final-chapter boundaries and a recording
conflict. Two existing continuity journeys also passed after the reader integration;
those are reruns, not additional distinct continuity cases. Both new narration
renders were inspected.

The complete phone/TV source profile passed JVM checks, lint and debug builds
at `92b1285`; its inventory contains 945 tests with no failures or skips.
Unaffected tasks were up to date. The Web change passed 24 focused checkpoint
groups and the complete 19-suite profile at `ce2467c`, with inspected English
and Chinese 390 px/150% controls.

All audio checks above use synthetic speech adapters and generated content.
They establish neither installed voice availability nor audible quality. Signed
phone delivery, served Web files, installed-provider checks and a family
listening walkthrough remain separate gates. See [development evidence](DEVELOPMENT.md)
and [memoir reading continuity](PHONE_MEMOIR_READING_CONTINUITY.md).
