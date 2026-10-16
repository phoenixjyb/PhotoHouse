# Spoken controls for the foreground assistant

October 16 source increment; not included in the published phone v66 APK or
claimed live on Windows. Web and phone recognize a small set of complete spoken
controls during an explicitly started foreground voice session.

## Interaction

While **Listening / 正在聆听**, say **暂停** or **pause** to pause, or
**结束语音** or **stop listening** to end. The recognized command stops locally
before any search/chat turn or reply-speech request. It starts no further
capture. Pause leaves a visible Resume button; resuming requires a tap. End
returns to the explicit Start action. An unrelated unsent composer draft stays
intact.

This uses the existing protected ASR request. Recognition must finish before a
spoken control can take effect. During reply preparation or playback the
microphone is off: use the visible Pause/End buttons. This adds no overlapping
microphone/speaker mode, wake word, background listening or spoken resume.

The exact command vocabulary is:

| Action | Chinese | English |
| --- | --- | --- |
| Pause | 暂停, 暂停聆听, 暂停语音 | pause, pause listening, pause voice chat, pause voice search, stop |
| End | 结束, 结束语音, 结束对话, 停止聆听 | end voice chat, end voice search, stop listening |

Only surrounding whitespace, ASCII letter case and trailing `. ! ? 。 ！ ？`
punctuation are normalized. There is no fuzzy or substring matching. Quoted
words, negation, internal punctuation and extra words remain ordinary requests:
“不要暂停，找最近的照片”, “pause the video” and “please pause” are not local
controls. Manual one-shot dictation always retains these words for review.

## Ownership and data

Commands require the exact active transcription attempt and current foreground
account/library/session generation. A delayed End from an earlier capture
cannot stop a newly resumed session. Existing transcript size/Unicode checks,
Pause/End cancellation, capability loss, lifecycle and scope fences still apply.
Only the voice session's exact transcript is consumed; it is not retained as the
parent of a later assistant request.

There is no new server data endpoint, schema, command log or audio retention.
The existing ASR request/receipt and its configured troubleshooting retention
continue to apply; recognizing a local control does not erase server records.
Recordings keep their existing transient treatment. The new public Web static
asset is included in both complete staging packages and source-only UI overlays.

## Qualification and next work

Focused JVM checks cover exact controls, near misses, validation order,
actual driver stopping without a turn/TTS/recapture, explicit resume, stale ASR
and manual dictation. The generated Web voice journey covers the same local
control boundaries, retained drafts, normal search after negation and manual
transcript review. Chinese/English 150% layouts are checked separately from
provider and physical listening quality.

Saved-section continuation remains a separate feature. A later voice-owned
continuation must retain the exact current result, card, source revision,
completed segment and segment count, and request only one next segment after
actual successful playback. Current voice opening playback and manual segmented
playback have different owners. Do not treat a new voice session as permission
to reuse old progress, advance chapters or restart recovered speech. See
[segmented reading](ASSISTANT_SEGMENT_READING.md) and [the roadmap](ROADMAP.md).
