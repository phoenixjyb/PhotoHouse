# V3 description clarification continuations

When a v3 refinement has a valid current result context but needs more scene
detail, the server asks for one quoted caption or scene clue. The person, date,
media, and existing description filters remain bound to that result context.
The user can answer with one quoted phrase, such as `“red coat”` or
`"red coat"`. The server sends that clue through the existing single-clue
planner and search path.

The continuation is private server state. It stores the original initiating
query, the entity binding, a digest of the exact prior result context, and its
creation time. The continuation is valid for 15 minutes and is tied to the
immediately preceding thread revision. The digest covers the library, source
binding, result fingerprint, filters, visible item IDs, total, and search
version. The stored thread context is checked against this digest before an
answer is resolved.

Only one bounded quoted phrase is accepted. Surrounding instructions, multiple
quotes, actions, dates, reviewed person names, and conflicting edits do not
change the search. An invalid answer keeps the same pending object and does not
extend its expiry. A successful search clears it. Starting a new search also
cancels it. Expired or stale continuations cannot be reinterpreted as a broader
search.

The wire response and history shape remain unchanged. The original request and
answer text remain separate user inputs; the server does not rewrite either
record. Request recovery reads the stored result and does not run the planner
again. Date clarification state continues to use its existing date-only schema
and behavior.
