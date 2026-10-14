# PhotoHouse as a family memory hub

**Product direction, reviewed 2026-10-14.** This extends current protected
media, original contributions, stories and memoirs. Long oral-history projects,
people-centered retrieval and automatic multi-source stitching are proposed
work, not enabled features. See [current status](PROJECT_STATUS.md).

## Purpose

PhotoHouse is a family memory hub designed for fully local deployment. Original
images, video, audio and text belong on the family's own devices/server; configured
local providers handle AI processing. Remote family access connects back to that
server. The public introduction is separate and cannot read the private archive.
Local deployment does not imply that every remote client, update or setup step
works without a network connection.

Stories are the organizing purpose. Images, video, audio and text are complementary
ways to tell, evidence and revisit them. A relative can tell a long account,
others can add their perspectives, and the family can cherish a reviewed chapter
without losing original voices or source media. People, events and narratives
provide the intended structure, with existing library permissions retained.
The [project introduction](../website/README.md) explains this through fictional
stories and original cartoon illustrations; it contains no household data.

## Concepts and relationships

| Concept | Role |
| --- | --- |
| Library | Existing membership/access boundary; a relationship does not grant access |
| Person/relative | Proposed subject identity with display name, aliases and family relationships; distinct from login account and detected face identity |
| Memory contribution | Existing attributable original text/audio and derived transcript; author account, speaker and story subject are distinct roles |
| Oral-history project | Proposed collection of interview/recording sections about a person, period or theme, with an editable outline |
| Recording section | Proposed resumable bounded segment, ordered within a session, with source identity and optional time anchors; no unlimited single upload |
| Event/group | Proposed reviewed relationship among media and contributions, with uncertain time/person/place labels and manual split/merge/exclusion |
| Story/chapter | Existing revisioned narrative/media selection; proposed richer citations to exact recording sections and speaker excerpts |
| Memoir/family book | Existing ordered saved-story composition; proposed longer reviewed continuity across periods and narrators |

A contributor can speak about a relative who has no account. Voice similarity,
face recognition, a byline or an AI guess must not create a subject/account
identity or invent consent. A person may appear in several libraries; sharing
requires the target library's existing authorization, not a global family graph.

## Intended family journey

1. Choose a person, event or theme, or start with a photo. The app suggests a
   gentle optional prompt; the narrator can tell the story in their own order.
2. Start recording explicitly. Show recording, elapsed time, saved sections and
   Pause/End. Persist accepted sections durably with retry identity before
   claiming they are saved; recover interrupted sessions without duplicates.
3. Review the transcript. Keep the source recording and machine transcript
   separate from corrections. Mark uncertain names/dates instead of guessing.
4. Invite an authorized relative to add their perspective. Contributions retain
   attribution and their own edit/withdrawal rules. Disagreements stay visible;
   the editor can place accounts side by side.
5. Propose an outline, title, media links and chapter wording using only selected,
   current, authorized evidence. Preview what was used and what was omitted.
6. Explicitly accept/edit the proposed chapter or book revision. A model does not
   silently replace originals, assign an author, publish to TV or broaden access.
7. Read/listen with photos and video at a calm pace. Speaker excerpts and source
   links make it possible to hear the original account as well as narration.

A proposed title may be editable. Attribution comes from authenticated authors
and explicitly named narrators; AI-assisted editorial wording has its own label.
The person a story is about is not automatically its author.

## Processing and trust

Long family recordings require a durable intake contract distinct from transient
assistant ASR. Existing bounded contribution recordings are not a long-session
transport. Define section size/duration/total budgets, media formats, quotas,
storage placement and resumable receipts before adding the UI.

Proposed stages are accepted source → queued ASR → reviewed transcript →
selected evidence → outline/title/chapter proposal → explicit adoption.
Workers need bounded resources, idempotent claims, cancellation, retry status
and source-revision checks before and after computation. ASR, narrative and TTS
adapters remain replaceable; model weights stay outside source Git.

Each proposal should include a complete input manifest, exact citation anchors,
provider/prompt/preprocessing identity and uncertainty. A stitched chronology
must distinguish known capture dates, received dates and narrator estimates.
Contradictory testimony must not be flattened into a confident invented fact.
A useful story may preserve multiple perspectives rather than reconcile them.

Original retention remains until explicit authorized deletion/withdrawal.
Assistant exchanges/receipts expire after 30 days and do not become family
stories automatically. A source withdrawal must invalidate pending proposals
and derived bindings according to qualified dependency/restore rules.
Public cartoons replace private media only on the introduction site; the site
never reads the real family archive.

## Bounded implementation sequence

1. **Domain/recovery design:** additive person/project/section schemas, consent
   and membership contracts, quotas, source withdrawal and paired restore tests.
2. **Long recording pilot:** resumable section upload and durable receipts,
   interruption/retry/cancel flows, waveform/transcript review on Web and phone.
3. **Relative/event organization:** manual subject links first; proposed time and
   image-similarity grouping with explicit adjustment and no silent propagation.
4. **Grounded editorial pilot:** synthetic multi-speaker corpus with conflicting
   dates, ambiguous names and missing sources; then consented family evaluation.
5. **Immersive reading:** reviewed book/chapter view, source audio, narration
   progress/continuation and separate explicit Home TV presentation.

Exit criteria include no lost accepted sections, no repeated uploads/effects,
no cross-member leakage, traceable speaker evidence, faithful writing, accessible
Chinese UI and recovery after process/server interruption. No migration, provider
activation or live publication follows merely from approval of this direction.
