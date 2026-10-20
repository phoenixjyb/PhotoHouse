# Selected-source story draft contract

This contract defines a bounded, review-only operation for preparing a story
from media and source evidence the author selected. It is a proposal for PH-A4,
not an existing endpoint or runtime capability. It leaves story ownership,
current source authorization, revision checks and explicit save in PhotoHouse.
The current application facts below were checked against
[`story_workspace.py`](../server/backend/app/access/story_workspace.py),
[`memory_stories.py`](../server/backend/app/access/memory_stories.py),
[`memory_narrative.py`](../server/backend/app/access/memory_narrative.py), and
the [chapter source-choice contract](CHAPTER_SOURCE_CHOICES.md).

The preparation boundary is an application-owned service. It may be called by
a later qualified coordinator, but its request and result contracts do not
depend on PH-A1's media-search tools, final-selector format, or runtime. The
service receives only an explicit authorized snapshot and returns an ephemeral
proposal. It has no save, publish, source-search or authorization-changing
operation.

## Existing source and save behavior

`POST /story-workspace/preview?library=…` accepts selected `asset_ids`,
`theme`, `language` and `title`. It reauthorizes the library and each selected
asset, returns current item evidence and a `selection_revision`, and derives a
bounded outline. It does not generate narrative prose or save a story.
`POST /story-workspace/related-media?library=…` returns a small page of media
sharing selected assets' recorded capture day; a suggestion is not selected
until the author explicitly adds it and obtains a new preview.

The optional `GET /story-workspace/source-capabilities?library=…` reports
`chapter_sources_v1`. In that profile, the author opts into
`source_policy: "chapter_sources_v1"` and chooses `evidence_ids` per chapter;
empty choices are valid. The current title-suggestion path can validate these
choices and rechecks the selection after inference, but it proposes titles,
not narrative drafts. The current narrative validator can validate ordered
chapter prose and chapter-level source IDs against a supplied bundle; that
validation establishes eligible provenance pointers, not factual entailment.

Saved stories use `POST /memory-stories?library=…&source_review=1` for create
and `PUT /memory-stories/{story_id}?library=…&source_review=1` for edit. The
closed save body includes `title`, `theme`, `language`, ordered `asset_ids`,
`chapters` as a JSON-encoded string, `selection_revision`, `revision`,
`mutation_id`, and `source_policy`. `asset_ids` is the current
comma-separated string form accepted by `_selection`. Each chapter in the
decoded array carries `id`, `title`, `narration`, `asset_ids` and
`evidence_ids`. The route accepts a 384 KiB request body and existing story
responses are bounded at 256 KiB. Saves reauthorize and compare current
selection and story revisions. A `mutation_id` is recorded with the request
digest: retry the exact same body and mutation ID after an unknown response;
reuse of that ID with a different body conflicts. A matching retry can return
the story's newer current revision if a later family edit has occurred.

Saved content stores editorial text, selected media and evidence IDs, with
source digests for current-reference filtering. It does not copy source words
into the saved revision. Reads hydrate current authorized evidence. Keep
family-authored wording, accepted contributions, transcripts, AI captions and
generated prose visibly and structurally distinct. A source byline belongs to
its source; generated wording must never inherit it.

## Proposed request and immutable snapshot

The proposed internal operation accepts a strict versioned request. The
authenticated account and library come from the application boundary, never
from model output. Source and media IDs below are references to resolve inside
the current authorized library, not bearer capabilities.

~~~json
{
  "version": 1,
  "request_id": "22222222-2222-4222-8222-222222222222",
  "target": {"story_id": null, "base_revision": "0"},
  "selection": {
    "asset_ids": ["17000017", "23000023"],
    "selection_revision": "<64 lowercase hex characters>",
    "source_policy": "chapter_sources_v1",
    "chapters": [
      {"id": "chapter-1", "asset_ids": ["17000017"], "evidence_ids": ["family-synthetic-note-4"]},
      {"id": "chapter-2", "asset_ids": ["23000023"], "evidence_ids": ["caption-synthetic-8"]}
    ]
  },
  "theme": "everyday",
  "language": "en",
  "title": "A day in the garden",
  "author_direction": "Keep the wording gentle and brief."
}
~~~

All IDs and text in this example are synthetic. A request has one to six
ordered chapters; each chapter has one to four selected media items and no
more than twelve distinct evidence IDs. Flattened chapter media must exactly
equal the selected media in the same order. Evidence IDs must belong to the
current selected items for that chapter. Empty evidence lists are allowed and
mean that the chapter receives no picture-linked evidence. `source_policy` is
required for this reviewed workflow. These limits align with the existing
story/source contracts; the service must reuse current validators where their
meaning matches.

`author_direction` is a required string, empty when unused, and limited to
8,192 UTF-8 bytes to match the existing narrative bundle's `instructions`
bound. It can guide style or focus only; it cannot add evidence, authority or
actions.

Bind `request_id` to a canonical digest of the authenticated account, library,
target story/base revision, ordered media, source policy, chapter partitions
and evidence IDs, language, theme, title, and any bounded author direction.
Within that scope, an identical ID and digest joins the active operation or
recovers its retained ephemeral result. Reusing the ID with a different digest
returns a conflict; it never changes the operation's source snapshot. After an
ephemeral result has expired, the same ID may start a new preparation only
after the same request digest and current source snapshot are revalidated. The
new prose is not guaranteed to match the earlier run. Surface it as a new
proposal, assign a new `draft_id`, and require full review again.

PH-A4 proposes one process-wide, nonqueued application admission lane across
accounts and libraries, held for one generation at a time. The proposed
end-to-end generation deadline is 60 seconds from admission, covering snapshot
resolution, adapter work, post-generation revalidation and response assembly.
No request may wait in an application queue. On timeout, cancellation or scope
invalidation, revoke the operation capability and fence all late output. Keep
strong ownership of the operation and its child resources until they stop or
are reconciled; do not release the lane while cleanup is uncertain. If a child
cannot be confirmed stopped, mark the optional lane unavailable for new work.
These are proposed PH-A4 limits, not current PhotoHouse runtime behavior.

The server resolves the request into an immutable `SourceSnapshot` before
preparation. The proposed request envelope is capped at 32 KiB; it contains
source references, not caller-supplied copies of source text. The validated
narrative bundle is separately capped at the current `MAX_BUNDLE_BYTES` of
64 KiB, with no more than 96 distinct source records. Each source text is at
most 8,192 UTF-8 bytes, each author/byline at most 256 bytes, and the aggregate
selected source-text budget is proposed at 48 KiB to leave room for metadata
and instructions inside that bundle. Current preview evidence is already
projected to at most 1,800 UTF-8 bytes per item source. Reject over-budget
requests before invoking a model or coordinator.

~~~json
{
  "version": 1,
  "request_id": "22222222-2222-4222-8222-222222222222",
  "library_id": "synthetic-library",
  "target": {"story_id": null, "base_revision": "0"},
  "selection_revision": "<64 lowercase hex characters>",
  "source_policy": "chapter_sources_v1",
  "media": [
    {"asset_id": "17000017", "kind": "image", "recorded_at": "2024-05-12", "stack_id": null},
    {"asset_id": "23000023", "kind": "video", "recorded_at": "2024-05-12", "stack_id": null}
  ],
  "chapters": [
    {
      "id": "chapter-1",
      "asset_ids": ["17000017"],
      "sources": [
        {"source_id": "family-synthetic-note-4", "selected_asset_ids": ["17000017"], "source_kind": "family_note", "source_revision": 3, "source_digest": "<sha256>", "byline": "Synthetic Aunt", "text": "We planted beans together."}
      ]
    },
    {
      "id": "chapter-2",
      "asset_ids": ["23000023"],
      "sources": [
        {"source_id": "caption-synthetic-8", "selected_asset_ids": ["23000023"], "source_kind": "ai_caption", "source_revision": null, "source_digest": "<sha256>", "byline": null, "text": "A green watering can beside the raised bed."}
      ]
    }
  ]
}
~~~

This is a proposed normalized operation snapshot, not the current preview wire
shape. The current preview exposes family evidence and AI or family-edited
captions; it does not expose transcripts as selected evidence. PH-A4 v1 may
consume only evidence actually returned by the current authorized source
service. Use `source_kind: "family_note"` for a family note and
`source_kind: "ai_caption"` or `"family_edited_caption"` for captions, based on
the current record. An accepted contribution or transcript can enter a later
version only through a separately reviewed authorized source contract that
preserves its original attribution and derived-text status. `source_revision`
is nullable because not every evidence type exposes a revision.
`source_digest` is a server-computed digest of the canonical current source
descriptor, never a model-supplied value. `selected_asset_ids` records where a
canonical source is eligible for this chapter; it is not a replacement for its
original `origin_asset_id` or byline when those exist. Keep original note text
and byline on the host; send only the selected, bounded snapshot to the approved
preparation adapter.

For a stack selection, the snapshot must enumerate every media member actually
selected for the story, preserving its ordered member asset IDs and its own
current evidence. A cover or representative asset is only a display choice.
Do not silently expand a cover into unreviewed members, collapse members to
the cover, or treat the cover's source evidence as evidence for its siblings.
If the existing selection UI cannot express and confirm that member set, PH-A4
must remain unavailable for that stack until the user selects the members.

Before provider work starts, the application verifies membership, source
eligibility, exact selection order, chapter partitions, source policy and
selection revision. It takes this snapshot in a bounded read operation, then
releases the database transaction before model or coordinator I/O. Before
returning any draft, it reacquires current authorized state and compares the
selection revision, ordered media, chapter source choices and source digests.
Any difference yields a conflict and discards the generated output. Do not
refresh the snapshot automatically and apply old prose to new sources.

## Proposed draft and citation result

The preparation adapter's strict narrative output should reuse the existing
`validate_narrative` input grammar: `version`, `title`, ordered `chapters`
with `id`, `narration` and `source_ids`, `questions`, and
`needs_review: true`. Its source bundle uses the current narrative validator's
closed bundle types. The host validates this output against the exact selected
chapter evidence IDs, then enriches it into the client result below. The model
does not author citations, chapter media, source metadata, IDs, revisions,
expiry, or the review state. This keeps the current validator useful while
making the returned citation record server-derived.

Use these compatible limits, with PH-A4's story-specific bounds where they
are narrower: one to six chapters; no more than 24 selected media items; one
to four media items per chapter; no more than twelve selected source IDs per
chapter and 96 source records in the validated bundle; source text at most
8,192 UTF-8 bytes and author/byline at most 256 bytes; title at most 160
Unicode scalar values and 512 UTF-8 bytes; chapter title at most 160 scalar
values and 512 bytes; narration at most 6,000 UTF-8 bytes; no more than six
questions, each at most 512 bytes. The narrative bundle and validated model
output each remain at the current 64 KiB limit. The underlying provider response
reader is capped at 128 KiB. The enriched client result is capped at 256 KiB,
matching the existing workspace response bound. The separately proposed
request envelope remains capped at 32 KiB and total source text at 48 KiB.
These bounds are checked on UTF-8 bytes where the current validators do so;
the additional Unicode-character caps keep saved-story content within its
current contract.

The strict client result is an ephemeral proposal. Its source binding is
copied from the server snapshot, never generated by the adapter.

~~~json
{
  "version": 1,
  "request_id": "22222222-2222-4222-8222-222222222222",
  "draft_id": "33333333-3333-4333-8333-333333333333",
  "state": "needs_review",
  "expires_at": "<server-generated timestamp>",
  "selection_revision": "<64 lowercase hex characters>",
  "source_policy": "chapter_sources_v1",
  "title": "Planting beans together",
  "chapters": [
    {
      "id": "chapter-1",
      "title": "Preparing the bed",
      "narration": "We planted beans together.",
      "asset_ids": ["17000017"],
      "citations": [
        {
          "source_id": "family-synthetic-note-4",
          "selected_asset_ids": ["17000017"],
          "source_kind": "family_note",
          "source_revision": 3,
          "source_digest": "<sha256>",
          "byline": "Synthetic Aunt"
        }
      ]
    },
    {
      "id": "chapter-2",
      "title": "Watering the plants",
      "narration": "A green watering can stood beside the raised bed.",
      "asset_ids": ["23000023"],
      "citations": [
        {
          "source_id": "caption-synthetic-8",
          "selected_asset_ids": ["23000023"],
          "source_kind": "ai_caption",
          "source_revision": null,
          "source_digest": "<sha256>",
          "byline": null
        }
      ]
    }
  ],
  "questions": [],
  "needs_review": true
}
~~~

Every nonblank narration chapter must cite one or more source IDs selected for
that chapter and validated against its chapter media. A citation is an
eligibility/provenance link, not proof that every sentence is entailed. The UI
must let the author inspect the cited source and edit or remove generated
wording. A selected source can support more than one chapter without copying
or changing its original identity and byline. Keep authored wording distinct
from transcripts and generated narration in both the snapshot and review UI.
Never present a transcript as the speaker's authored words or generated prose
as source-authored wording.

Reject extra or missing fields, duplicate chapter/source IDs, reordered or
unknown chapters, references not in the immutable snapshot, citations attached
to the wrong media, incomplete chapters, oversized text, unsafe control
characters, stale digests, and any result that does not require review. Do not
let the adapter write `selection_revision`, source identity, revision, byline,
review state, save state or expiry. Validate its `source_ids` with the existing
narrative validator, then build citation objects from the immutable source
snapshot and check their media/source-kind binding on the host.

## Review binding, save and unknown outcomes

The review screen binds one proposal to the current account and library,
`draft_id`, target story and base revision, `selection_revision`, ordered media
and chapter layout, source-policy choice, per-chapter evidence IDs, title,
chapter titles and narration, and citation set. The client computes or stores a
canonical review fingerprint over those exact values. Any edit, source-choice
change, chapter/media rearrangement, scope change or source refresh clears the
review confirmation and requires a fresh review. This binding is a UI integrity
fence; it is not server authorization or a new permission.

After an explicit Save action, the client constructs the existing reviewed
save body from the approved proposal: copy the author-approved title and text,
the exact ordered chapter `asset_ids`, the selected evidence IDs, current
`selection_revision`, `source_policy: "chapter_sources_v1"`, and a fresh
`mutation_id`. For a new story, send `revision: "0"`; for an edit, bind the
existing story ID and current base revision. Do not include source words,
transcripts, citations as copied prose, model prompts, or provider diagnostics
in saved content.

The server's existing save transaction remains the final authority: it checks
`story.write`, current media and source availability, selection revision,
story revision and evidence eligibility. A stale source or revision returns a
conflict and preserves the local draft for reload/review. It must never
silently replace the selected evidence or save a prior proposal against a new
snapshot.

If the save response is lost or ambiguous, freeze the exact request body and
`mutation_id`; retry that exact pair or reconcile with the saved-story read
path. Do not mint a new mutation ID until the prior outcome is known. A
same-ID/same-body replay is the existing idempotent path. Same ID with a
different body is a conflict. If a matching replay returns a newer story
revision, show that current version and do not overwrite it with the stale
editor payload.

## Expiry, recovery and privacy

The prepared prose is volatile and is not an application record. Proposed
client behavior sets `expires_at` once, 30 minutes after the result is issued.
This is a fixed absolute lifetime, not a sliding idle timer. At expiration,
clear the proposal and its review binding; a user can explicitly save an
ordinary local draft if that capability is already available. PH-A4 does not
add server draft persistence, background resume, conversation history or a
new recovery endpoint. If the response is lost before display, retrying the
same request ID may re-run preparation only after revalidating the identical
request and source snapshot; generation has no durable side effect and is not
guaranteed to reproduce the earlier prose. Treat a regenerated result as a
new proposal requiring full review. If the request is still running, join that
operation rather than start a duplicate. An app restart may require the user
to start preparation again.

Source words stay within the authorized application snapshot and the
specifically approved local preparation boundary. No source text, family
identity, private media, draft, prompt or citation is written to logs, Git,
analytics, shared runtime threads or an external service. Runtime qualification
must separately inspect provider, coordinator, crash and diagnostic retention.
The result sent to the client includes citation metadata and generated text,
not a copied source corpus. Clearing the ephemeral draft does not delete or
change originals, sources or saved stories.

## Acceptance cases and dependencies

PH-A4 is ready for implementation only after its benefit comparison, runtime
boundary and client review path are approved for the actual host. Its essential
synthetic acceptance cases are:

| Case | Expected behavior |
| --- | --- |
| Exact selected sources | Draft uses only the selected current media and per-chapter evidence; every nonblank chapter has valid citations. |
| Empty source choice | A chapter with no selected evidence receives no picture-linked evidence. The system asks for sources or leaves its narration blank; it does not silently use all available evidence. |
| Source text injection | Instructions embedded in a note, transcript or caption cannot add tools, sources, people, media or save authority. |
| Mixed source kinds | Family note and AI or family-edited caption remain distinguishable in PH-A4 v1. If a later source contract admits accepted contributions or transcripts, their authored/derived status and original byline remain distinct. |
| Stack member coverage | Each explicitly selected member is represented with its own evidence. Cover-only input cannot cite or imply unselected siblings. |
| Drift during generation | Change, withdrawal, deletion, membership or source revision while preparation is pending; return conflict and no draft. |
| Stale review | Change a source choice, chapter partition, title or wording after review; the old confirmation cannot authorize Save. |
| Lost save response | Retry the frozen body and mutation ID; create/update occurs at most once and current revision is reconciled. |
| Conflicting mutation | Reuse the mutation ID with changed text or selection; show conflict and preserve the local proposal. |
| Expiry and scope change | Expired or account/library-switched proposal is cleared and cannot be saved into a new scope. |
| Invalid adapter output | Reject missing/extra fields, unsupported citations, omissions, duplicates, oversized content and claims of saved/published state. |

Dependencies remain separate: refreshed source review; PH-A0 qualification of
the exact local runtime and retention behavior; a separately reviewed
story-specific benefit threshold; the existing or explicitly designed client
draft/review path; and source, runtime, native-host and family acceptance. PH-A1
is an application seam and does not qualify the model or make PH-A4 available.
PH-A4 does not require shipping the PH-A3 search experience first, but it must
not bypass any enabled application boundary. No model installation, source
deployment, service restart, publication or family-device acceptance follows
from this proposal.
