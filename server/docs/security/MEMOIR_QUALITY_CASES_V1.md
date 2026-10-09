# Synthetic memoir quality case plan v1

This local fixture planner prepares bounded, synthetic book bundles for a
possible future human quality review. It does not run inference, contact a
provider, load a model, read family material, or write to the database. Its
output is planning data, not a model result or quality acceptance.

The planner is separate from database-backed memory processing. Its optional
synthetic canary captures one explicitly selected case for review; generating a
plan does not authorize an inference run. Runtime qualification, human review
and family adoption remain separate gates. The curated candidate's scope and future gates are summarized in the
[feature matrix](../../../docs/FEATURES.md) and [roadmap](../../../docs/ROADMAP.md).

## Generate and check

From the repository root, print the deterministic JSON plan with:

```sh
python server/scripts/plan_memoir_quality_cases.py
```

The helper sends the generated bundles through the existing
`app.access.memory_narrative._validate_bundle` contract for the three memoir cases. Each memoir bundle
targets a `book`, stays within 24 chapters, 96 sources, eight recent turns and
64 KiB, and uses synthetic identifiers. The full output is limited to 256 KiB.
Each invocation builds fresh nested objects. Source citations and asset links
are cross-checked before emission.

Run the focused offline tests with:

```sh
python -m unittest discover -s server/tests/security -p test_memoir_quality_cases.py
```

## Cases for human review

1. **Ordered chapters and exact citations:** a Chinese-language garden story
   progresses from planting, through morning watering, to flowers weeks later.
   A reviewer checks
   the chapter order, support for each detail and transitions that connect one
   coherent episode rather than concatenate photo captions. The earthy smell
   and children's pride may add texture because the synthetic source records
   them; no other feeling or event should be invented.
2. **Conflicting authors and uncertain date:** two synthetic family members
   place one picnic in different years and cite the same synthetic photo. A
   reviewer checks that both voices remain separate and attributable even
   though they refer to the same asset, and that an export date does not settle
   the event date. The account should read as one episode with balanced
   perspectives, without turning into a list of source summaries.
3. **Recent clarification and provenance:** a multi-turn exchange includes an
   uncertain detail and an open date question. The bundle contains only the
   currently approved synthetic note and file metadata. A withheld-source ID is
   listed as plan metadata for review, while the withheld source and its content
   are absent from the bundle. A reviewer checks that recent conversation is
   not promoted into a source citation, no omitted source is cited, and the
   response asks for evidence when needed while still answering in a clear,
   coherent conversational voice.

Each case has case-specific human review expectations for grounding, conflicts,
attribution, chronology, transitions and literary style. Reviewers should favor
an opening, connected transitions, consistent perspective and a clear theme;
opaque source IDs and raw technical metadata stay out of prose. Explain relevant
file-date uncertainty in plain language when useful. Use supplied family
emotions or sensory details when recorded, while avoiding invented dialogue,
relationships, feelings or dates. Supported statements do not need artificial
hedging. The JSON intentionally reports no score, semantic pass, model identity
or generated proposal. Known source IDs and bundle validation establish shape
and reference boundaries only; a human must compare any future output with its
exact sources and the case-specific review expectations above.

## Independent title cases

The same planner also emits three smaller, separately validated story-title
bundles through `app.access.story_titles.validate_bundle`. They use `task=suggest`,
not the memoir narrative or companion contract. The original three memoir case
IDs, tasks and canonical bundle hashes remain unchanged.

- `synthetic-title-family`: Chinese family recollection and draft about planting
  sunflowers with grandma, with grounded wording and exact citations.
- `synthetic-title-uncertainty`: English picnic recollection alongside an uncertain
  AI year estimate and a draft preserving the unresolved year.
- `synthetic-title-abstention`: no sources; a valid response contains no titles.

Title bundles contain only version, language, theme, selection revision and
sources. They have no book, chapter, recent-turn or asset-crosslink fields.
Their review criteria cover grounding, exact title citations, uncertainty,
language, empty-input abstention and required human review. See
[model qualification](../../../docs/MODEL_QUALIFICATION.md) for the independently
bound title role and opt-in capture procedure. Plan fixtures and structural
validation do not establish a provider's title quality.

## Limits

The planner is offline and plan-only. It has no execution option and performs
no provider requests, subprocess calls, model loads, database connections or
writes. Its synthetic fixtures are not evidence of model quality, native GPU
readiness, family acceptance or memoir-wide drafting capability. Any future
execution needs a separately reviewed case, resource budget and authority.
