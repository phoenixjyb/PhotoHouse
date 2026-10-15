# Chinese, English and mixed-language search

PhotoHouse search must accept Chinese, English, and a mixture of the two in
one request. A user should not need to insert spaces at a language boundary or
select one input language first. Shanxi/Jin dialect wording and speech are also
part of the intended experience, with qualification still pending. A language
label, a successful model load, and a correct transcript transport do not prove
recognition accuracy or retrieval quality.

## Current source behavior

Negotiated search v2 recognizes its existing English keywords beside Chinese
characters, including search/refine openings, media types, dates, people
connectors, negation and content introducers. For example, the synthetic
`find示例儿童昨天的photos` preserves the reviewed person, yesterday's civil-date
range and photo constraint. `only视频` changes media type while preserving
previous people, date and text filters. English tokens still need boundaries
inside Latin words: `findphotos` is not a search opening. The legacy v1 parser
is unchanged; clients must negotiate v2 for this behavior.

This remains a bounded deterministic parser. It does not understand arbitrary
Chinese, English or dialect sentences. Unmatched conditions and ambiguous
people require clarification; they cannot be silently dropped to produce more
results. Quoted content remains exact literal text. Search does not translate
that literal into another language, and lexical matches do not imply semantic
cross-language recall. See [generated semantic pair qualification](SEMANTIC_PAIR_QUALIFICATION.md)
for the separate model measurement and activation gates.

People and kinship resolution must use the current authorized library and
reviewed identities. Future dialect name/kinship aliases need explicit meanings
and reviewed identity bindings. Do not infer a person's identity, Chinese name,
relationship, or sharing permission from pronunciation or a model suggestion.
No private household roster or recordings belong in source fixtures.

## Grounded conversational follow-ups

Search v2 also accepts explicit references to the people selected in the current
search. The server replays the prior search against current library membership
and source bindings before reusing it. It does not infer people from result
cards, recency of mention, gender, faces, private kinship, or another thread.
No new context fields, stored aliases, model calls or client protocol changes
are needed.

| Follow-up | Meaning |
| --- | --- |
| `same people, last month` | Keep the selected people and other filters; replace the date with last month |
| `他们上个月的视频` | With multiple selected people, replace date and media; retain the exact people IDs and any/all operator |
| `their videos` / `show videos of them` | With multiple selected people, replace media only |
| `her photos` / `他的照片` | With exactly one selected person, retain that person and request photos |
| `same people, any date` / `同一批人，不限日期` | Remove date explicitly and retain the other filters |

The closed generic group forms are `same people` and `同一批人`; they reuse any
nonempty people filter. The plural forms `these people`, `those people`, `them`,
`they`, `their`, `他们`, `她们`, `这些人`, and `那些人` require at least two selected
people. The singular forms `same person`, `him`, `her`, `his`, `他`, `她`, `这个人`,
and `那个人` require exactly one. Singular/plural checks are conservative; the
system asks rather than interpreting singular English “they” or guessing which
member of a group “her” means. Gendered words do not establish anyone's gender.
A reference alone repeats the current search without widening its filters.

Multiple references, conflicting current-turn names or a simultaneous people
removal require clarification. A reference that collides with a reviewed label
also requires clarification. Unknown conditions, negation, malformed dates,
stale context and denied membership retain their existing refusal boundaries.
Quoted references remain literal text, for example `containing "他们"` does not
select people. These rules apply to typed text and submitted transcripts equally;
they do not establish dialect recognition or general conversation understanding.

The protected HTTP fixtures cover exact filters/results, failed clarification
retaining the prior scope, source/membership replay, request recovery and isolated
thread context. No real recognition, device or installed-service acceptance is
inferred from those generated conversations.

## Speech and uncertainty

The ASR adapter preserves the returned text after trimming outer whitespace,
with a bounded script-derived `zh`, `en`, `mixed`, or `unknown` label. That label
is not the recognizer's language confidence or a dialect identification. The
current adapter has no calibrated confidence/uncertainty field; therefore it
cannot promise to detect all mistaken dialect transcripts. Names and dates may
be confidently wrong and still look like valid search syntax.

Outside an explicitly started foreground voice session, transcription remains
a draft for review and explicit insertion/submission. An opted-in foreground
session can submit read-only queries automatically until paused or ended; this
round does not add a dialect-specific pause detector. Original audio, provider
transcript, reviewed corrections and any future normalized interpretation must
remain distinct. Do not silently replace transcripts or use speech consent to
change memories or access.

Before claiming Shanxi/Jin support, obtain owner-provided example phrases and
intended meanings, then privately qualify consented speech with the installed
ASR provider. Include mixed Chinese-English, dialect kinship/date expressions,
name substitutions, background noise, and correction/retry behavior. Store
private examples and recordings outside Git. Do not invent a generic dialect
lexicon or choose translations without reviewed examples.

## Evidence and next gates

| Layer | Source checks in this round | Separate acceptance still needed |
| --- | --- | --- |
| Typed v2 parsing | Synthetic Chinese, English and mixed inputs; adjacent scripts; exact literals; dates; person quantifiers; retained refinement filters | Representative family queries and broader natural-language coverage |
| Protected retrieval | In-process authorized search returns exact expected filters/results; unknown conditions clarify | Installed service and device experience |
| Transcript handoff | Mocked ASR text remains exact through protected transcription and a separate explicit v2 submission | Real Chinese, English, mixed and Shanxi/Jin speech recognition |
| Semantic ranking | Generated canary defines separate English, Chinese and mixed cohorts; scores cannot hide a failing cohort | New native mixed-cohort measurements, reviewed family relevance and compatible image artifacts |

The transport fixtures use generated silence and a mocked ASR response. They
measure no speech recognition accuracy. The mixed canary defines printed text,
not spoken dialect cases. No provider, private roster, database schema or
runtime configuration is activated by these source changes.
