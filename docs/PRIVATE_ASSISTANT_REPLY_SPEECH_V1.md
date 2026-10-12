# Protected private reply speech

This optional source feature reads an already completed, owned assistant reply.
It keeps the existing result-count speech endpoint and has no family-content
mutation, new model selection, or implicit Windows activation.

## Contract

A default-off runtime flag `assistant_reply_speech_enabled` requires the existing
local TTS adapter, healthy assistant journal and healthy private workspace.
Workspace capabilities add optional `reply_speech` (absent means false).

`POST /assistant/workspace/v1/threads/{thread_id}/requests/{turn_id}/speech`
accepts exactly `{library_id, expected_revision}`. Headers must contain a new
canonical `X-PhotoHouse-Request-Id` and `X-PhotoHouse-Parent-Request-Id` equal to
`turn_id`. The speech ID differs from the turn ID. No caller text, context,
language, cards, paths or action inputs are accepted.

The server requires current membership, an owned unexpired completed turn, and
the same current thread revision. It revalidates any saved result context against
the current source binding. The parent journal record must be a successful turn
owned by that account/library. The server reads the persisted reply and derives
Chinese/English voice selection from it. It refuses empty, open-action or longer
than 600 UTF-8 byte replies without truncating the on-screen text.

The existing journal admits each speech request ID once. Repeating the same ID
never reruns synthesis or returns cached audio. A separately requested explicit
read may use a new ID; the server does not infer microphone consent from an ID.
The client alone owns foreground Start/Pause/End and explicit reading controls.
Journal entries contain processing status/parent linkage, without another copy
of reply text or raw audio. Audio remains transient, bounded by the existing
2 MiB/30-second WAV contract. Membership and the current thread revision are
checked again before returning audio. Failures preserve visible text and pause.

## Voice UX

Saved story/memoir results have an additional optional speech-capability probe.
Their matching exchange references are source-validated before and after TTS,
with one drift guard across the whole reference set. Only the generic persisted
reply is synthesized. Missing speech capability leaves cards readable; replay
never creates a speech source. See [saved-memory cards](ASSISTANT_SAVED_MEMORY_CARDS_V1.md).

Only a fresh completed response in an explicitly started private voice session
can automatically request speech. A recovered/replayed response pauses for
review and never automatically synthesizes, plays, navigates or listens again.

Results (including no matches) and clarification replies can speak, then listen
again after actual playback completion. Unsupported requests speak their help
text, then pause for review; they execute no mutation. Over-limit replies remain
fully visible and pause without requesting speech. When the new capability is
off, the existing result-count behavior remains available for nonempty results.

A fresh private media-open response may open its exact server-selected asset
from the validated current result set. Unique item IDs, effect membership and
server context authorization are retained. The session ends before opening the
viewer; a recovered effect is never executed. Ordinary v1 behavior is retained.

## Qualification

Use invented data and a fake TTS adapter for source/transport/controller/browser
and simulator checks: ownership, parent linkage, duplicate speech IDs, revision
and membership changes, limit/type/framing errors, source drift, cancellation,
actual-playback gating and recovery suppression. Native provider pronunciation,
Windows resource behavior, served routes and family-device acceptance require
separate evidence and delivery authority.
