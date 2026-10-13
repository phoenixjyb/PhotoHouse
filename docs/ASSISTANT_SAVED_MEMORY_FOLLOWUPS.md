# Conversational followups over saved memories

Status: implemented in local backend, Web and phone source; phone v56 identity
is reserved. Published API/Web and phone v55 contain search and reader handoff,
not this later followup feature. Delivery and family acceptance remain separate.

## User experience

First search current saved text, such as “找故事 野餐” or “找回忆录 夏天”.
While those fresh results remain displayed, type or say one of these requests:

| Request | Result |
|---|---|
| 介绍这些回忆 / introduce these memories | Original excerpts for the displayed cohort |
| 第二段回忆讲了什么 / what is the second saved memory about | Original excerpt for the selected displayed item |
| 第2段回忆有哪些章节 / what chapters does the second saved memory have | Current chapter titles for that item |
| 有哪些章节 / what chapters does it have | Chapter outline when exactly one item is displayed |

Chinese spoken ordinals 一 through 十二 and numerical ordinals are accepted;
English first through twelfth and numerical ordinal suffixes are accepted.
Commands match the complete documented phrase after trailing spoken punctuation
is removed. Extra mutation instructions do not match a read-only followup.
Ambiguous requests and out-of-range numbers ask the user to refine or search again.

Cards show their ordinals, the saved-source cue, and localized suggested questions.
Suggestions insert a draft after ending foreground voice. The user explicitly
sends the draft. Ordinary typed and foreground voice turns also use the fresh
result anchor; tapping a suggestion is not required. Start/Pause/End and scope or
foreground interruption keep their existing behavior. Reader opening is explicit.

This is a bounded source-grounded reading feature. It does not generate new story
prose. Excerpts preserve original code points and are clipped at the existing
240-code-point card limit. Chapter outlines may also be clipped; the explicit
reader contains the complete source. TTS speaks the generic reply, not titles,
excerpts or chapter text automatically.

## Wire and authorization

A separate optional probe returns exactly `{version: 1, available: <boolean>}`:
`GET /assistant/workspace/v1/saved-memory-followup-capabilities?library_id=...`.
It requires existing saved-card, workspace and current authorized reader health;
base/card/reader/speech capability response shapes remain unchanged.

A new opted-in turn may include this exact optional field:

```json
{
  "library_id": "example-library",
  "request_id": "11111111-1111-4111-8111-111111111111",
  "expected_revision": 3,
  "text": "第二段回忆讲了什么",
  "accepts": ["saved_memory_cards_v1"],
  "memory_parent": {
    "request_id": "22222222-2222-4222-8222-222222222222",
    "revision": 3
  }
}
```

The parent revision must equal `expected_revision` and be positive. The client
sends only the latest fresh, completed, non-recovered displayed card result from
the current account/library/thread and foreground generation. History, recovery,
media results and clarification do not supply a parent. Client card IDs,
excerpts, digests and result context are never sent as authority.

The server loads the owned latest completed parent and its canonical typed
references, resolves current authorized readers, validates source digests,
checks database commit drift, then rechecks the parent before completing the
new turn. Missing/foreign sources stay hidden (404), stale sources or parents
conflict (409), and unavailable or malformed current storage fails closed (503).
A fresh unrelated search ignores a well-formed parent semantically. Existing
owned request recovery occurs before new negotiation and never rehydrates cards;
changing negotiation or a parent on replay cannot create fresh actions.

The response uses the existing `memory_cards_v1` grammar. All displayed IDs stay
in their original order, including when only one item's excerpt changes to its
outline. `total` is this displayed cohort's count and `has_more` is false. It is
not a new complete-corpus count; there is no followup paging or hidden expansion.
Explicit reader GETs revalidate the new completed request and current source.

Older closed APIs can return 403 for this unknown optional route. For this probe
alone, clients recheck the existing base capability using the same authenticated
scope. A strictly parsed base 200 means followups are unavailable; actual base
401/403 still clears private state. No blanket access-denial fallback applies.
Missing, disabled or malformed optional probes do not add `memory_parent`.

## Persistence and qualification

Original saved text/audio retains its existing ownership and retention. Source
wording is transient in fresh cards. Private replies persist only generic
mode/count/ordinal text and existing reference digests, with the existing 30-day
assistant retention. No source text is copied into private reply/context, no
new schema or retention is introduced, and no model/provider is invoked.

Tests cover exact commands, parent ownership/latest revision, invalid references,
source changes, hidden access, storage failure, generic-only recovery, no source
mutation, typed/voice chaining and older-server fallback. Generated Web and
Chinese/English 150% phone renders are separate from physical microphone/speaker
and family acceptance. Portable synthetic qualification also exercises search →
overview → outline → explicit reader → inert recovery, without live data or providers.
