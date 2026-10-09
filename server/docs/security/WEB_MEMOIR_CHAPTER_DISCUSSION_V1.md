# Discuss the current memoir chapter v1

The whole-memoir conversation composer provides an explicit “Discuss the chapter
you are reading” action after the user has opened a conversation. It prepares a
question in an empty editable message, using the currently loaded story title,
chapter title and chapter number. The question asks what the existing sources
say and suggests asking the family about missing information without inventing
experiences. It is not an assistant answer or a generated narrative.

The reader supplies only the book/story IDs and revisions, chapter ID and two
titles. It provides no narration, transcript, contribution, recording or token.
The getter is available only for the exact open memoir reader, current account
and library, visible loaded pane, and a child matching the saved book revision.
Loading, contents and closed-reader states do not supply a chapter context.
Closing the reader removes its getter.

The composer requires an exact current book and listed child revision, chapter
1–6, bounded titles and the current rendered conversation. It checks this again
after obtaining context. Its shared insertion guard preserves text, Chinese IME
composition, recording/transcription, a pending transcript, an uncertain send,
conversation operations and pending chat work. Old buttons, changed libraries,
hidden documents and closed readers cannot obtain a reading context.

The button does not fetch a story, change the chat target, create a conversation,
submit a turn, run a model, save the story or start/stop narration. It obtains the
latest reading context at the explicit click, so navigation does not require
replacing an active composer. The user edits and sends through the existing
controls. Actual source authorization is rechecked by the existing backend
submission and worker boundaries when that later submission occurs.

The UI harness covers revision, account/library scope, title bounds, unexpected context
fields, existing drafts, detached renders, changed library, hidden document and
closed-reader refusal. The synthetic protected-browser journey covers current
chapter navigation, whole-memoir thread continuity, no automatic turn/audio
request, unavailable context and Chinese/English display with enlarged text.
Live ASR, local browser voice availability, provider interpretation and family
acceptance remain separate qualifications.
