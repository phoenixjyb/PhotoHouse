# Web memoir narrative forms v1

## Scope

The memoir reader's **Draft suggestions** panel offers an optional form choice for owners who can edit a memoir. It is a local draft control. It does not change the selected book, saved memoir, story text, conversation, profile, API route, or request schema. Story readers and read-only memoir viewers do not receive this control.

The compact disclosure starts with **EXISTING** selected. Leaving this choice unchanged preserves the existing request instructions exactly. Selecting a form only changes local panel state; a narrative job starts only after the user explicitly submits **Create a reviewable suggestion**.

## Form choices

| Choice | Instruction appended when the user submits |
| --- | --- |
| EXISTING | No additional instruction |
| CHRONICLE | 按已有时间线整理为忠实纪事。保留不同家人的说法，未知日期先提问，不编造事件。 |
| ESSAY | 把已有回忆整理成温暖的家庭散文。保留真实讲述与不确定之处，不补写没有来源的经历。 |
| LONG_MEMOIR | 把已有篇章连成有开篇、衔接和回望的长篇回忆录。保留原篇章顺序与家人的不同声音，不编造对白、人物或事件。 |

When the existing instruction field is nonempty, the selected recipe follows it on a single new line. The same combined text is sent through the existing `instructions` field; no form identifier or additional API field is introduced.

## Validation and lifecycle

The full frozen instruction, including the selected recipe and any explicitly inserted voice transcript, must be well formed and fit the existing 4096-byte UTF-8 limit. Invalid text and overflow are rejected without truncating either part or changing the selected form. Voice transcripts remain separate and editable until the user explicitly inserts them into the instruction field. Insertion validates the base text, transcript, and selected recipe together before consuming the transcript. Capture, transcription, and insertion do not create a job.

An uncertain job retry reuses its original mutation ID, target and revision, base instructions, form, final instructions, and editorial-context choice. A definite 409 or 422 clears that retry state while keeping the local instruction draft and selected form. Existing memoir-context recheck requirements still apply after a context conflict.

The selected form is unsent reader state: leaving prompts before discarding it. It resets on reader target/revision, account/library, logout, or suspension changes. Same-reader rerenders and language changes preserve it. It is not sent to chat or to a family's original contribution.

## Limits

A form is an instruction to the existing narrative drafting service, not a guarantee that generated wording follows every constraint. The resulting suggestion remains reviewable and does not modify saved prose until the user takes the separate adoption action. Model adherence and family acceptance require review of the actual suggestion.

## Local verification on 2026-10-06

JavaScript syntax and the UI contract harness passed. The protected synthetic
browser suite passed 18 checks with no page errors or external requests.
English and Chinese forms were rendered at a 390-pixel viewport and 150% text;
all four English choices fit and submit remains reachable. The integration
owner inspected the final English memoir and Chinese chronicle displays.
The harness also verifies acknowledged form-only drafts clear the exit guard,
a later local edit survives acknowledgement of an uncertain retry, and a
definite 422 retains the full draft and form while clearing frozen retry state.
These are source and synthetic browser checks; this change has not been
deployed to Windows and does not prove actual model adherence.
