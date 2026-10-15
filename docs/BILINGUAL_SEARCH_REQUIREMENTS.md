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

## Correcting a search in conversation

Negotiated v2 supports a bounded one-filter correction after a search. Intro
forms such as `no, I meant videos`, `I meant August 2032`,
`actually, videos`, `不对，我说的是视频`, and `我说的是2032年8月` replace one
existing media or date filter. Mixed forms such as `I meant视频` and
`actually，我说的是2032年8月` follow the same rule. Other filters, including
reviewed people IDs and their any/all operator, stay unchanged. The original
message and transcript are not rewritten.

Paired forms such as `not photos, but videos`, `不是照片，是视频`, and
`不是2032年9月，而是2032年8月` also require the stated old value to exactly match
the current filter. Both sides must resolve to one media/date filter of the same
kind. A stale or mistaken old value asks for clarification and preserves the
existing search. Date interpretation uses the same supplied civil date and
inclusive capture-date ranges as ordinary search.

Corrections need a validated prior search and an existing target filter. They
cannot exclude a person, replace an identity, clear filters, combine multiple
filter changes or execute an action. Explicit filter-removal commands and
ordinary refinements remain separate. Unknown wording, extra negation, invalid
dates and conflicting constraints still require clarification. A reviewed label
colliding with a correction introducer cannot be silently consumed as grammar.
Quoted text stays literal; `find photos containing "no, I meant videos"` is a
text search, not a correction.

Generated direct-search and saved-conversation checks cover the replacement,
old-value check, missing context/filter, denied/tampered/stale source, exact
result IDs and request recovery. These source changes add no provider, private
alias, database migration or new client response fields. The legacy v1 parser
and the unverified Shanxi/Jin speech boundary remain unchanged.

## Asking what the current search means

After a v2 search, users can ask `what are we looking for?`,
`what filters are active?`, `explain the current search`, `现在在找什么？`,
`现在筛选了哪些条件？`, or mixed forms such as `当前search条件是什么`.
These are complete read-only requests; adding an action or another condition
does not authorize the assistant to discard that extra text.

The answer describes the revalidated current filters: media kinds, inclusive
capture-date bounds, selected people and tags with their any/all operators,
locations, and the text phrase. It uses current reviewed labels for selected
IDs, including when no results match. It does not infer identities from cards,
quote captions or family notes, reveal unselected roster entries or kinship
perspective, or explain a similarity score as a probability. A singleton asset
lookup has no search filters; the answer says so without replacing that item
with a catalogue search. Without context, the assistant asks the user to search
first.

Replies stay within the existing 600 UTF-8-byte limit. Ordinary bilingual names
remain intact when space permits. At most two names per facet are previewed,
with an explicit count for the remaining selections. Shortened names use an
ellipsis, and shortened text is marked as an excerpt. All active filter clauses
remain visible; the underlying filters and original text are unchanged. Quoted
values and escaped controls are data. The text phrase still follows the existing
normalized lexical matching contract; this is not a new case-sensitive or
cross-language semantic matcher.

The explanation preserves current result order, context and any subsequent
refinement or correction. Saved conversations and request recovery keep the
same reply, subject to current source and membership checks. Existing opt-in
reply speech reads the bounded saved explanation and withholds audio if the
source changes during synthesis. Generated tests cover that transport behavior;
real TTS listening, installed service and device acceptance remain separate.
The legacy v1 parser and all model/runtime settings are unchanged.

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
