# Memoir editorial model context v1

## Scope

This source change defines an opt-in model-context format for saved memoir
citations and adjacent transitions. It does not change the existing memoir or
story response shapes, sidecar schema, source storage, or contribution handling.
Generated text remains a proposal for human review. The existing worker retains
validated job proposals and conversation answers for 30 days; this path never
applies them to saved story/book content or publishes them.

The opt-in choice is explicit per drafting request. The service and worker must
also have the editorial feature enabled. The job records the selected
`context_profile` as `memoir_editorial_v1`; omitting the choice keeps the
existing v1 bundle and legacy job input behavior. A selected story context is
invalid: this profile is for a book with a current b1 editorial sidecar.

## Context construction

`memory_editorial_context.enrich(access, library, member, book_id,
legacy_bundle)` reauthorizes the book and its ordered child stories through
`MemoryBookEditorial._book_context`, checks the b1 schema gate, then reads the
sidecar with `_read_sidecar`. It accepts only a `current` sidecar whose book
revision matches the already hydrated bundle and whose child revisions match
the current ordered book snapshot. An empty, stale, source-changed, or
unavailable sidecar is refused; callers must refresh and explicitly save a
current editorial basis before choosing this context profile.

The returned bundle is a detached v2 copy of the already-built v1 bundle, with
one additional object:

```json
{
  "book_editorial": {
    "children": [{"story_id": "canonical-uuid", "revision": "1"}],
    "introduction_source_ids": ["contribution-canonical-uuid"],
    "transitions": [{
      "left_story_id": "canonical-uuid",
      "right_story_id": "canonical-uuid",
      "text": "Saved transition text",
      "source_ids": ["contribution-canonical-uuid"]
    }]
  }
}
```

Source IDs are resolved only against family or transcript sources already
hydrated into that bundle and against their chapter evidence. Introduction
citations must belong to a hydrated child chapter. Transition citations must
belong to one of the two adjacent children. A missing source, changed consent,
revision mismatch, reordered child, or unusable audio citation fails closed
with a conflict. The adapter does not fetch any additional source content. The
full parsed sidecar snapshot is returned separately so the job fingerprint
also binds opaque citation identities and editorial wording.

The narrative validator accepts the unchanged exact v1 shape and this exact v2
shape. It bounds context at 64 KiB, 24 children/chapters, 96 sources and 96
editorial references; each introduction/transition section has at most 12
references, and each transition is at most 6,000 UTF-8 bytes. Transition order
must match adjacent ordered children. References must be unique within a v2
section, resolve to hydrated family/transcript sources, and occur in the
referenced child chapter evidence.

## Prompt and trust boundary

The v1 safety prompt is byte-for-byte unchanged for legacy bundles. For v2,
the prompt adds a short rule that saved introductions and transitions are
editorial direction, not independent evidence or authority. Saved prose cannot
establish facts, chronology, dates, causes, or relationships. Existing source
uncertainty and human-review rules continue to apply. The model receives no
tools.

At integration, the explicit HTTP query choice is `editorial_context=1`; the
request body remains unchanged. `GET /memory-community/v1/books/{id}/plan?library=…&editorial_context=1`
reports the selected `context_profile` and `whole.context_bytes`; without the
query choice the legacy plan shape remains unchanged. `memory_editorial_enabled`
is a separate deployment gate. The worker accepts the optional strict boolean
only in narrative mode and checks the exact b1 schema when enabled. Rehydrated
job context and its fingerprint are checked before provider use and again
before the result is accepted. These settings do not turn the source tests
into proof of runtime configuration or model behavior.

## Later prompt revision

The byte-for-byte legacy safety-prompt statement above describes the original
`a56861b` context slice. Later accepted source `13a050c` changed the shared v1
and v2 safety prompt: direct quotations require verbatim family-authored text
and available attribution; transcripts may be attributed paraphrases, not
claimed verbatim authored words. The wire shape, default context profile,
legacy bundles and fingerprints retain their earlier compatibility evidence.
This does not mean provider prompt bodies stayed unchanged in final `635ce03`.
Frozen model V7 source `2594ef5` predates both these revisions; even a future
V7 execution cannot qualify current prompt/v2 prose quality. See the
[development prerequisites](../../../docs/DEVELOPMENT.md).

## Verification boundary

The focused synthetic test uses the local CPython 3.12 test environment and a
temporary SQLite fixture. It verifies the current b1 read path,
detached context, missing/revoked source refusal, stale child snapshot refusal,
strict v2 bounds, and unchanged v1 validation. No provider, Windows runtime,
production database, family media, or live API is accessed by this test.

An independent owner comparison against pre-change source `981d681` confirmed
identical legacy bundles and fingerprints on synthetic b1, a0 and f7 fixtures.

The final owner run passed **103 tests and 73 subtests** across editorial context,
job lifecycle, protected HTTP, legacy jobs/processing, narrative adapters, book
planning, worker configuration, source packaging and deletion integration. It
includes fake-provider pre/commit rechecks, profile-aware history, explicit
default-off behavior, duplicate stored JSON rejection and sizing failures before
provider work. This is source/synthetic evidence; Windows-native execution,
provider prose quality, live configuration and family acceptance remain open.
