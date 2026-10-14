# A fluid voice and viewing experience

## Goal and delivery boundary

拾光助手 should feel like a companion who understands the current conversation
and the memories on screen. Voice, text, source cards and readers belong to one
journey. Personal preferences belong to the account; a family story remains a
shared, permission-scoped source.

This design follows the approved foreground Start → listen → reply → listen
experience with visible Pause/End. The current implementation is half duplex:
the microphone is off during recognition, requests and playback. Source changes
in this round are local; delivered v57 and its physical-family acceptance remain
separate. No provider, live schema, worker or TV change is part of this slice.

## Build in this order

| Stage | Experience | Acceptance gate |
|---|---|---|
| Contextual actions, this slice | Search stories, then say “读第二个故事” or “打开第一个故事” | Current displayed ordering, fresh source, no recovered action, cancellation and visible target |
| Continuous reading | “继续” advances bounded chapter segments; progress and source remain visible | Exact chapter/source revisions, one playback owner, resume rules and interruption tests |
| Quicker conversation | Faster end-of-turn and first audible reply with truthful preparation feedback | Measure capture end, ASR completion, turn completion, TTS readiness and actual first playback separately |
| Speaking interruptions | Talk to interrupt; assistant stops and acknowledges the new turn | Qualified echo cancellation, VAD, cancellation/late-result tests and human listening on target devices |
| Grounded storytelling | Connect related photos and contributions, explain evidence and propose a coherent narrative | Current sources, editable drafts, author attribution and family quality review |

End-of-turn timing and interruptions are distinct engineering problems. OpenAI's
[Realtime conversation guide](https://developers.openai.com/api/docs/guides/realtime-conversations)
describes cancelling interrupted output; its
[VAD guide](https://developers.openai.com/api/docs/guides/realtime-vad) describes
speech and semantic turn detection. These are interaction references. PhotoHouse
continues to use replaceable Windows-local speech and language services.

Latency targets should be set after observing the existing service pipeline.
Animations never stand in for real microphone or playback confirmation. Show a
short reason when an operation is slow, and retain an explicit way to stop.

## Conversation and visual presentation

Keep a short spoken response and a useful visual result together. A request such
as “找我们那次野餐的照片” should lead to a focused set of media/story cards,
then make the next choice easy. After selection, keep the title, relevant media,
saved source and actual listening/preparing/speaking state visible. Avoid a wall
of configuration, receipts and repeated buttons in the primary conversation;
diagnostic details belong behind a secondary control.

The next understanding stage should support followups such as “那天还有什么”,
“把刚才那段讲短一点” and “接着讲”. A replaceable local language adapter can
propose a typed action against authorized conversation context. The backend
must resolve its references and validate the action. Uncertain identity, dates
or relationships need clarification and evidence; a polished narrative must not
invent family facts or silently overwrite anyone's original contribution.

Personalization should use explicitly chosen language, voice pace, reply length
and reading position. Offer an easy way to change/reset preferences. Distinguish
private conversation continuity from shared family stories and contributions.
Changing account/library ends the current voice session; anonymous TV visibility
does not establish an authenticated assistant identity.

## Contextual story actions

While current saved-memory cards are displayed, support complete commands:

- “读第一篇回忆”, “请朗读第二个故事的开篇”, “read the second story”.
- “打开第三本回忆录”, “查看第2段回忆”, “open the first saved memory”.
- “读这个故事” or “打开这个故事” selects a sole displayed item. With several
  items, ask which one and keep their order for the next answer.

The read action says it reads the **opening**. It uses the existing 240-code-point
and 600-byte speech bound; it must not imply a whole story has been read. Full
chapters are the next stage. No command substring, negation or appended mutation
is interpreted as authority. Unsupported wording follows the existing assistant
path. This deterministic grammar establishes the contract; a later language
adapter can propose the same typed actions without gaining authority over IDs.

A fresh action identifies its target visibly. Outside the active voice session,
a typed command requires an explicit Open/Read button. Within the approved voice
session, an open action ends voice before reader navigation. A read action keeps
the microphone off and may listen again only after actual successful playback.
Pause, End, Stop, backgrounding, source/scope change or playback failure invalidate
the operation and cannot restart listening through a late callback.

## Wire, privacy and compatibility

The optional protected probe is:
`GET /assistant/workspace/v1/saved-memory-action-capabilities?library_id=...`.
It returns exactly `{version: 1, available: <boolean>}` and checks current readers.
Reading audio additionally requires the separate opening-reading capability.

New clients negotiate the exact ordered list
`["saved_memory_cards_v1", "saved_memory_actions_v1"]`. Older clients retain
`["saved_memory_cards_v1"]` and receive no action extension. Existing request
recovery occurs before negotiation and never creates an action.

A newly completed `memory_cards` result may add:

```json
"memory_action": {"type": "read_opening", "ordinal": 1}
```

`type` is exactly `open` or `read_opening`; `ordinal` is a zero-based index in
that result's current nonempty cohort, never an asset ID. No other action keys
are accepted. The new completed turn owns the cohort and becomes the parent for
its existing protected reader/speech route. Clients bind its account, library,
thread, request and revision; source resolution remains server-owned.

All displayed references are revalidated, including unselected entries. A stale
parent cannot borrow a later list. Ambiguous or out-of-range action requests
return the current whole cohort and a choice prompt without an action. Missing
context asks for a search. Source changes fail closed.

Only generic replies and opaque source references enter private conversation
storage. Source excerpts and action metadata are transient. History and recovery
have no actionable source hydration or automatic playback/navigation. Recordings
keep the existing transient-audio policy; this feature adds no database schema.

## Product acceptance journey

1. Search two generated stories; verify visible numbered cards.
2. Start voice; say “读第二个故事”. Check the second card is the spoken source,
   preparation precedes actual Speaking, and listening starts only after it ends.
3. During preparation and speech, separately try Pause/End and Stop. Verify no
   late audio or microphone restart. Inject an async playback error as well.
4. Ask “读这个故事” with two cards. Check the choice prompt retains both cards;
   answer “读第二个故事” without searching again.
5. Say “打开第一个故事”. Verify the current protected reader and ended voice.
6. Type the same requests outside voice. Confirm no autoplay/navigation until a
   deliberate button action.
7. Reopen old history and recover a lost response. Neither may act automatically.
8. Repeat in Chinese/English at 150% text on phone and desktop; then separately
   validate real phone microphone, local ASR/TTS, family permissions and listening
   comfort. Synthetic tests and renders do not establish physical acceptance.
