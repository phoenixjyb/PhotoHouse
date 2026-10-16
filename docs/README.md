# Documentation map

Start with the maintained summaries. Follow task contracts for implementation;
use dated release/qualification records as evidence for their exact revision.

| Need | Entry point |
| --- | --- |
| Product and source setup | [Repository README](../README.md) |
| What is delivered, enabled or still unaccepted | [Current project status](PROJECT_STATUS.md) |
| Components, trust/data boundaries and stores | [Architecture](ARCHITECTURE.md) |
| Capabilities and acceptance | [Features](FEATURES.md) |
| Active priorities and exit criteria | [Roadmap](ROADMAP.md) |
| Architecture findings and maintenance decisions | [October 14 review](ARCHITECTURE_REVIEW_2026-10-14.md) |
| Local development commands | [Development](DEVELOPMENT.md#cpu-quick-start), [environment doctor](DEVELOPMENT_ENVIRONMENT.md) |
| Backend/Web entry | [Server README](../server/README.md), [Web development](WEB_DEVELOPMENT.md) |
| Phone/TV entry | [Android README](../clients/android/README.md) |
| Family trial | [Delivered v67 voice guide](../clients/android/docs/PHONE_V67_TEST_GUIDE_ZH.md), [v67 release](../clients/android/docs/PHONE_V67_RELEASE_2026-10-16.md), [proposal adoption guide](../clients/android/docs/PHONE_V66_TEST_GUIDE_ZH.md) |
| Deployment/recovery workflow | [Operations](OPERATIONS.md), [source packaging](SOURCE_PACKAGING.md), [API package inspection](API_PACKAGE_INSPECTION.md) |
| Replaceable models and infrastructure | [Provider architecture](MODEL_PROVIDER_ARCHITECTURE.md), [model directory](../models/README.md) |
| Private manifest and model quality gates | [Deployment manifest](MODEL_DEPLOYMENT_MANIFEST.md), [qualification](MODEL_QUALIFICATION.md) |
| Monorepo transition and old repository disposition | [Repository transition](REPOSITORY_TRANSITION.md) |
| Source ownership/import provenance | [Source ledger](feature-source-changes.json), [contributing](../CONTRIBUTING.md) |
| Reader progress and source status | [Reader UX](READER_PROGRESS_AND_SOURCES.md) |
| Local reading-size controls | [Reading comfort](READER_TEXT_SIZE.md) |
| First saved story and memoir | [Chinese getting-started guide](FIRST_STORY_GUIDE_ZH.md) |
| Guided Web story creation | [Source flow and recovery contract](STORY_FIRST_GUIDE.md) |
| Link an accepted family memory to a story chapter | [Web chooser and protected metadata contract](CHAPTER_FAMILY_MEMORY_CHOOSER.md) |
| Compare synthetic story output with its sources | [Private operator review page](MEMOIR_QUALITY_REVIEW.md) |
| Companion answer grounding | [Cited answers and clarification](STORY_COMPANION_GROUNDING.md) |
| Review wording changes in story suggestions | [Review summary and local focus](STORY_PROPOSAL_WORDING_REVIEW.md) |
| Title from authored chapter wording | [Chapter-opening title contract](CHAPTER_OPENING_TITLE.md) |
| Guided phone story creation | [Flow, draft boundary and trial](../clients/android/docs/PHONE_FIRST_STORY_GUIDE.md) |
| Failed story/memoir images | [Preview recovery](READER_PREVIEW_RECOVERY.md) |
| Natural-language search diagnosis and next work | [Search review](ASSISTANT_SEARCH_REVIEW_2026-10-15.md), [new-session handoff](NEXT_SESSION_SEARCH_REDESIGN_2026-10-15.md) |
| Private search coverage, relevance cases and video dates | [Readiness and relevance](SEARCH_READINESS_AND_RELEVANCE.md) |
| Gated conversational image-semantic retrieval | [Scene-search Web flow and recovery contract](ASSISTANT_SCENE_SEARCH.md), [semantic pilot](SEMANTIC_SEARCH_PILOT.md), [reviewed scene-query provider](REVIEWED_SCENE_PROVIDER.md) |
| Measure scene relevance across languages | [Private scene-set evaluation](SEMANTIC_SCENE_QUALIFICATION.md), [native diagnostic](SEMANTIC_SCENE_BENCHMARK_2026-10-16.md), [local translation experiment](SEMANTIC_SCENE_TRANSLATION_2026-10-16.md), [untouched-photo intent diagnostic](SEMANTIC_SCENE_INTENT_EVALUATION_2026-10-16.md), [generated pair baseline](SEMANTIC_PAIR_QUALIFICATION.md) |
| Assistant voice-turn timing | [Timing contract and source evidence](VOICE_TURN_TIMING.md) |
| Assistant saved-section narration | [Explicit segment reading](ASSISTANT_SEGMENT_READING.md) |
| Long recording retention and withdrawal | [Intake foundation](ORAL_HISTORY_INTAKE_FOUNDATION.md), [withdrawal prototype](ORAL_HISTORY_WITHDRAWAL.md), [generated qualification](ORAL_HISTORY_QUALIFICATION.md) |

Latest delivery: [phone v64 and API/Web story review](../clients/android/docs/PHONE_V64_RELEASE_2026-10-15.md).

Earlier continuation: [October 15 handoff](NEXT_SESSION_HANDOFF_2026-10-15.md) and
[v60 local candidate](../clients/android/docs/PHONE_V60_LOCAL_CANDIDATE_2026-10-15.md).
These are source/package records, not publication notices.

## Document roles

**Maintained summaries** describe current source contracts and link to a dated
runtime snapshot. Public default-off configuration is distinct from an explicitly
enabled installation. **Task contracts** define request shapes, revision, privacy
and lifecycle behavior. **Dated evidence** records a particular source, test,
package or operation; a later release does not retroactively change it.

Features and Roadmap retain their earlier notes in collapsed historical sections.
Development is a chronological qualification log with stable command sections.
The architecture index labels older snapshots explicitly. Historical “pending”
statements are not the active backlog; start with Project Status and Roadmap.

## Update rule for future work

1. Update the affected task contract and its implementation evidence.
2. Update Features/Roadmap and Project Status only for the acceptance level proved.
3. Record source/CI, package, live runtime and physical/family results separately.
4. Append changed source-document hashes to the provenance ledger and check links.
5. Keep private endpoints, accounts, database/media paths, model weights, credentials,
   signing keys and full operator receipts outside Git.

No deployment, activation, deletion or remote publication is authorized by reading
these documents. Use the exact current operation scope and preserved rollback plan.

## Product introduction and family memory direction

- [Introduction website source](../website/README.md): Chinese-first project
  purpose/features, fictional family examples and cartoon illustrations.
- [Family memory hub](FAMILY_MEMORY_HUB.md): proposed long oral histories,
  relative/event organization, attributed contributions and reviewed chapters.

- [Oral-history intake foundation](ORAL_HISTORY_INTAKE_FOUNDATION.md): internal
  bounded section/receipt contract and remaining withdrawal/transport gates.

- [Private story draft save/resume contract](STORY_DRAFT_RESUME.md): encrypted device-local creation drafts, fresh access/evidence and exact uncertain-save recovery.
