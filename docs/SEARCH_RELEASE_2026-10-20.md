# Guarded bilingual search release — October 20, 2026

The completed guarded-search work is merged and its API/Web package was deployed
and verified at **2026-10-20 10:49 Asia/Shanghai**. **Semantic search remains OFF.**
This is a dated release snapshot; recheck the current source and runtime before
another operation. It does not establish family/device acceptance.

## Source and delivery

| Item | Verified release |
| --- | --- |
| Review | [PR #101](https://github.com/phoenixjyb/PhotoHouse/pull/101), merged |
| Qualified and deployed API/Web source | `b170a97ff2dba42b29b35c659ae40f0749f28974` |
| Main merge | `a4e39221a3dab8ee84bacc7c9226e7b3a71b112b`; Git tree identical to the qualified source |
| Hosted source checks | [Run 39359164477](https://github.com/phoenixjyb/PhotoHouse/actions/runs/39359164477), all five jobs passed |
| API package | 256 source files; archive/local Git attestation and native source readback passed |
| Phone and TV feeds | Phone v74 and TV v30 preserved; no APK was published by this release |
| Runtime policy | Existing configuration and private search artifacts preserved; semantic search OFF with no configured semantic serving path |
| Schema | `a0c9d2e4f817` retained; no migration or library-wide photo-stack refresh activation |

The source integrates main through PRs #99 and #100, preserving gallery and
upload work alongside search. Their library-wide stack implementation is in
source; its production schema/index activation remains a separate operation.
Android source changes are merged and passed hosted checks, but this release
does not deliver a new phone/TV binary. A later APK must be built from combined
main and retain its own signing, publication and device gates.

## Search capabilities and their limits

| Capability | Delivered behavior / boundary |
| --- | --- |
| Combined conditions | Reviewed people with any/all matching, capture dates, media, tags, locations and literal caption/photo-memory text can be combined within the authorized library. Available facets and coverage depend on that library. |
| Chinese, English and mixed input | Recognized openings, conditions and grounded follow-ups share bounded parsing rules. This is not arbitrary language understanding or cross-language visual recall. |
| Reviewed people and private kinship | Resolution uses current reviewed assignments and the configured account/library/perspective scope. This release expands neither identity assignments nor sharing permissions. |
| Conversational refinement | Supported follow-ups retain or explicitly replace conditions after current access/source checks. Unknown names, ambiguous references and unmatched conditions require clarification. |
| Exclusions and strict conditions | Closed media forms such as “find photos, not videos” / “找照片，不要视频” compile to the existing filter. Unsupported visual absence, exclusivity and strict counts are refused before ranking or model planning rather than silently dropped. |
| Clarification and recovery | Private pending state retains the exact unresolved request. Short replies, GET recovery and expiry cannot silently discard an exclusion or start a broader search. Explicit complete revision and fresh scope validation are required. |
| Result explanations | Replies identify interpreted conditions and available match evidence, including the limits of reviewed-person coverage. Empty results do not prove that a person/object is absent from the library. |
| Coverage and quality tools | Readiness separates recorded/searchable dates, text and reviewed identity coverage. The scorecard reports language/category cohorts, labeled relevance and evaluator timings; tool availability is not a quality pass. |
| Optional semantic scene search | The serving/client contracts, qualification tools and refusal/rewording flow exist in source. Live semantic ranking remains OFF; its UI is capability-gated. |

Contracts: [joint search](ASSISTANT_JOINT_SEARCH_V2.md),
[bilingual parsing and follow-ups](BILINGUAL_SEARCH_REQUIREMENTS.md),
[private kinship](PRIVATE_KINSHIP_SEARCH.md),
[exclusions and rewording](SCENE_QUERY_REWORDING.md),
[readiness](SEARCH_READINESS_AND_RELEVANCE.md), and
[quality scorecard](SEARCH_QUALITY_SCORECARD.md).

## Qualification and runtime verification

- The full local API profile passed **2,647 tests and 2,764 subtests**, plus the
  generated no-listener demo. The invocation receipt binds the same start/end
  source commit and input hashes.
- All five hosted jobs passed: API, Web browser, Windows CPU, Windows private
  readers and Android. Android checks are not signed APK publication.
- The focused scene browser journey passed all **eight checkpoints**. Chinese
  and English phone-width layouts at 150% text size were inspected. Exclusion
  assertions require zero encoder calls; separate generated provider-refusal
  and GET-only recovery cases remain covered.
- Native candidate qualification passed with a bounded Windows Job and
  read-only store guards before the API switch. Four stopped-writer store
  backups and four on-disk restore rehearsals passed; no production store was
  restored. All nine scoped task states were restored and the other 78 task
  definitions were preserved.
- Independent native postflight verified the exact API listener/source,
  configuration and private search-artifact preservation, semantic OFF, and
  access boundaries. Independent Mac HTTPS reads matched the served HTML,
  JavaScript and CSS, confirmed four anonymous protected-route denials and
  verified the unchanged phone/TV feed metadata.

Complete operator receipts, rollback roots, task/process identities and private
data evidence remain outside Git. The operation is consumed and must not be
replayed. These results prove the stated source/delivery checks, not model
relevance, complete library coverage, physical installation or family acceptance.

## Remaining work and next gates

1. **Qualify semantic relevance while keeping semantic search OFF.** The
   [multilingual encoder screen](MULTILINGUAL_ENCODER_QUALIFICATION.md) still
   exposes weak negation and mixed-language contrasts. Admission refusals do
   not repair those rankings. Evaluate English, Chinese and mixed literal,
   vague, contrast, absence, count and relationship requests; report refusals
   separately from retrieval correctness. Translation comparisons also require
   [meaning-fidelity review](SEMANTIC_SCENE_TRANSLATION_FIDELITY.md).
2. **Measure and improve authorized coverage.** Expand reviewed identity
   assignments only through confirmation, audit missing/uncertain capture dates
   including video, and measure searchable text coverage. Unknown dates remain
   unknown; this release performs no bulk date repair or identity expansion.
3. **Qualify any proposed serving path separately.** Compatible vector coverage,
   protected provider integration, resource/latency checks and explicit activation
   authority remain required. This document enables no provider or model.
4. **Complete family/device trials when available.** Check Chinese/English/mixed
   queries, follow-ups, clarification/recovery and actual relevance on authorized
   devices. Shanxi/Jin dialect understanding and dialect ASR accuracy remain
   unqualified. The published phone v74 and TV v30 have their own acceptance
   gates; merged client source is not an installed update.

See [Project Status](PROJECT_STATUS.md), [Features](FEATURES.md) and
[Roadmap](ROADMAP.md) for the maintained project summaries. Earlier “local source
only” sections in the search contracts retain their original checkpoint meaning;
this release closes their merge/API-Web delivery gates, not semantic activation.
