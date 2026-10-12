# Private conversation navigation

This source slice makes owned conversations distinguishable and older text
readable. It does not activate Windows storage or providers, change retention,
accept assistant replies from a client, or replay historical actions.

## Labels

Clients opt into labels with `GET /assistant/workspace/v1/threads` and query
`library_id` plus `include_labels=true`. Without the opt-in, the existing strict
thread shape is unchanged. An opted-in thread adds nullable `label`: the first
unexpired user question, whitespace collapsed and shortened to at most 64 Unicode
code points (including an ellipsis). Empty conversations have null labels.

Labels are computed from the current account/library's unexpired exchanges.
They are plain display text, not model instructions or HTML, and add no retained
copy or database column. They disappear when their source expires or is deleted.
The default label is a localized new-conversation/date/count presentation.

Capabilities add optional `thread_labels` and `history_paging` booleans. They
reflect a healthy owned store, independently of discovery/model availability.
Clients retain compatibility when these fields are absent. History access needs
`available` and `threads`; sending/voice additionally needs `server_owned_turns`.
A unavailable search engine must not hide previously saved conversation text.

## Older text

`GET /assistant/workspace/v1/threads/{thread_id}/history` requires exactly:

- `library_id`: current authenticated library membership;
- `before_revision`: canonical positive integer, exclusive older cursor;
- `snapshot_revision`: canonical nonnegative integer matching the owned thread's
  current revision. The cursor must be no greater than the snapshot revision.

The response is a strict object:

```json
{
  "version": 1,
  "thread_id": "11111111-1111-4111-8111-111111111111",
  "snapshot_revision": 25,
  "before_revision": 6,
  "exchanges": [],
  "has_older_exchanges": false,
  "next_before_revision": null
}
```

A page contains up to 20 complete exchange projections in increasing revision
order, all strictly older than `before_revision`. It preserves full saved text;
card entries remain non-actionable type/count placeholders. A bounded UTF-8 JSON
budget may return fewer rows rather than truncate text. If more rows exist,
`next_before_revision` equals the oldest returned revision; otherwise it is null.
No empty page can advertise another cursor. All replies fit the existing 256 KiB
client limit. The latest detail projection receives the same byte-budget guard.

Account/library/expiry ownership, thread revision and page rows are read under
one database snapshot. A revision mismatch returns 409 and requires explicit
refresh; the client must not append a mixed snapshot or resend a turn. Missing
or foreign threads return the same 404. Membership is checked again before a
response is exposed. No history lookup invokes discovery or model inference.

## Client behavior

An explicit “查看更早消息” action reads one page. It prepends validated text to
the selected thread only when account/library/generation, thread, revision and
cursor still match. Duplicate/out-of-order IDs or revisions, inconsistent cursors,
unknown fields and oversized pages are rejected. At most the store's existing
200 exchanges are held. Account/background changes clear every page buffer.

History never changes trusted search context, the current result, reply receipts,
or foreground voice consent. Reading, paging and returning to a conversation
never speak, navigate or listen automatically. “继续聊天” and the separate voice
button remain explicit activation actions. After a concurrent turn, older text
requires an explicit reload at the new revision. An unsent draft is preserved.

## Acceptance

Verify owned and foreign scopes, expired source labels, Unicode/HTML labels,
multiple pages, byte-budget boundaries, revision changes and cancellation/stale
callbacks. Render Web and phone controls at narrow widths and large text. Keep
source/JVM/browser/simulator evidence separate from Windows and family use.
