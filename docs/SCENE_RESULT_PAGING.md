# Browse more scene-search results

This source increment adds protected result-page navigation to the private Web
conversation. It is a source candidate; it does not enable semantic serving, deploy an API
or publish an Android app.

## User flow

After an explicit scene search, Next and Previous replace the visible photos in
groups of at most 20. The view shows the current range, total and global rank.
Similarity remains an approximate ordering, not a match probability or textual
evidence. Coverage and omission explanations stay visible on later pages.

Each explicit page request may encode the scene description again. There is no
prefetch or automatic retry. The original conversation turn is not resubmitted,
and reading history or restoring its saved first page does not encode again.
The original unseen ranking tail was not saved: the first continuation verifies
the saved first 20 and establishes a new complete-ranking consistency digest.
Later pages refuse if that ordering or its raw score bits change.

Page cards are temporary and do not become a new conversation scope. Return to
the first results before sending another ordinary or scene request, recording a
new voice question or asking for narration. The return checks the saved result
against current access and source without encoding. Unsaved wording is kept.
This prevents an instruction such as “the second photo” from silently referring
to a different page. A photo can still be opened through its explicit card.

Closing or reopening the conversation and switching account/library clear page
state. A changed source, request, revision, membership, runtime or capability
withholds unconfirmed cards. An uncertain page request is not a durable turn
receipt; retry only through an explicit page action.

## Separate continuation contract

The existing v4 turn, context, result and history response shapes are unchanged.
Older servers without the optional page capability keep the disclosed first-20
limit. A disabled semantic capability cannot execute page requests.

The optional authenticated capability GET is
`/assistant/workspace/v1/scene-page-capabilities?library_id=...`, with closed
response `{version: 1, available: boolean, page_size: 20}`.

An explicit continuation POST uses
`/assistant/workspace/v1/threads/{thread_id}/requests/{request_id}/scene-pages`
and search version 4. Its closed body contains `version: 1`, `library_id`,
`expected_revision`, `page`, and an optional `ranking_sha256` consistency digest.
It accepts no query, filters, vectors, scores or replacement scope from the
browser. A first page-2 request establishes the digest; other continuation pages
require it. Page size stays 20 and the page selector is bounded by the stored
result total.

The server reads the latest retained request across every status in one
read-only workspace snapshot. It must be the selected live, completed scene
request at the current thread revision. A newer pending, failed, interrupted or
expired request blocks an older result. The validated stored summary supplies
the description, reviewed scope, binding, fingerprint and first-page prefix.
The same source identity is checked again after inference.

The separate closed page response binds its thread, request, revision, page,
total, source binding, query fingerprint, ranking digest, cards and semantic
coverage metadata. It does not replace the durable first-page context. Complete
vector/source/policy checks, current authorization and owner restrictions,
request-wide cancellation/deadline and row/byte/response budgets remain active.
Serving flags and the captured runtime identities are checked again immediately
before accepting the response. No new database schema, ranking cache or durable
exchange is introduced.

## Acceptance boundaries

Focused acceptance includes generated three-page ordering, first-page parity,
rank-bit and vector/source mutation refusals, latest-request/revision races,
membership and runtime changes, cancellation during provider and final readback,
strict request/response shapes, older-server/OFF behavior and late UI replies.
English and Chinese page controls require rendered narrow-screen and large-text
checks. Passing existing first-page browser tests alone does not qualify the
new navigation.

Local generated checks passed 12 API tests / 14 subtests, 32 controller tests,
20 existing scene tests / 12 subtests and 12 combined browser checkpoints. The
browser fixture contains 46 eligible and 65 omitted synthetic images and uses a
mock encoder. Its bilingual page navigation and omission notices were inspected
at 390px and 150% text. These overlapping cohorts are not a new full-suite run.

These are source and generated-fixture checks. Installed devices, representative
multilingual relevance, production coverage and omissions, runtime rollout and
rollback, activation and family experience remain separate gates. See the
[functional acceptance matrix](SEARCH_FUNCTIONAL_ACCEPTANCE.md),
[scene-search contract](ASSISTANT_SCENE_SEARCH.md) and
[current project status](PROJECT_STATUS.md).
