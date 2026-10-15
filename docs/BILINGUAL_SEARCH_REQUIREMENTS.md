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

A complete reviewed name can also replace the people selected in an existing,
revalidated v2 search. For example, `Sample Adult` retains the current date,
media, text, tags and locations while selecting that person. Multiple names
require `and` / `和` for everyone together or `or` / `或` for any of them.
Unjoined names ask for that distinction. Extra wording, actions and quoted
names do not become bare-name answers. A fresh thread still needs a search;
this does not retain or complete an unresolved earlier request. Saved turns,
recovery and membership/source revalidation use the normal search context.

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

## Recovering from zero results

Users can ask `why no results?`, `为什么没有结果？`, or `为什么没有results`.
The assistant revalidates the current search and explains only known policy.
It does not guess that a person, event or model caused a miss. A date-filtered
search explains that items without recorded capture dates are excluded, then
offers `any date` / `不限日期` to remove only that filter. Without a date filter,
a text-filtered search offers `any text` / `不限内容`. Other searches offer a
review of the active filters. The suggestions themselves never change filters;
a separate explicit turn is needed, and all omitted constraints stay intact.
If the current search has results, the assistant reports its actual count
instead of inventing an empty-result explanation. Missing context asks for a
search first. Compound actions and quoted question text are not commands.

## Optional descriptive intent search (v3)

The optional v3 path accepts natural openings such as `I'm looking for`,
`do we have`, `我想看看` and `有没有`, as well as descriptive requests. A local
planner proposes exact input spans and bounded Chinese/English alternatives.
The server, rather than the model, resolves reviewed people and hard filters.
The planner receives a view of the query with resolved names/labels, recognized
dates, media terms and quoted literals replaced by spaces, plus the civil date
and a previous-search flag. It receives no roster, captions, credentials or
database access. Code-point offsets stay fixed, including complete Unicode
normalization clusters; unsafe partial mappings refuse provider invocation.
Every accepted span must be visible and identical in the untouched original.
All hard filters and residual requirements still compile from that original.
An unfamiliar name does not authorize guessing an identity or consuming it as a
scene. The local adapter accepts only scene extraction or a description question;
the server owns time, identity, scope and action decisions. Fictional prompt
examples demonstrate separate required activities and objects, with color/object
phrases kept together. They are not a family vocabulary.

Each descriptive concept is required. Its alternatives are interchangeable
phrases, so `snow` and `red coat` require evidence for both concepts on the same
asset. Current captions and photo memories may supply that evidence across
sources. These are normalized lexical matches of proposed alternatives, not
image-vector similarity or proof that a model's interpretation is correct.
Ordinary quoted text remains a separate literal condition. Source reasons name
the contributing current records; they do not turn generated interpretations
into family facts.

The compiler refuses spans that hide reviewed labels, known kinship terms,
supported unresolved vague-time phrases, quoted text, recognized dates, media
types or negation, and refuses unparsed extra conditions. Kinship words cannot
become descriptive guesses when the account lacks an authorized graph. Generic
`children` / `孩子们` can describe a scene without a possessive cue; reviewed
relationship labels remain protected. Person,
date, media and exact-text filters remain independent requirements. Refinements
retain descriptive concepts unless an explicit new search replaces the search,
or `any description` / `不限描述` removes that filter. A new explicit search can
refresh a stale result snapshot; refining or opening that snapshot still requires
its original source and membership binding.

Model outages or invalid proposals ask for clarification without broadening the
search. The local adapter bounds response size, deadline and concurrent HTTP
workers. Provider-side admission and GPU/resource lifetime require separate
native qualification; an HTTP timeout alone cannot prove remote computation
has stopped. The provider is optional, configured as an explicit loopback URL
and installed model pair, and disabled by default. Importing or building the
application starts no provider and downloads no weights.

An explicit `/api/chat` URL selects the chat protocol; a base URL or
`/api/generate` selects generation. Both send a closed JSON schema, disable
thinking and streaming, and request a 4096-token context with at most 1024
output tokens. Chat uses a separate system instruction and user query object.
Only a completed assistant content response without tool calls can become a
proposal. Endpoint errors and invalid responses get no retry or protocol
fallback. These bounds and protocol checks do not establish model latency or
semantic accuracy; the installed provider must be measured separately.

Web and Android negotiate v3 only through the existing protected routes. An
explicit unsupported-version response permits fallback to v2, then v1; generic
errors, timeouts and authentication failures do not. Saved v1/v2 history retains
its original version and binding when read by a newer client. Recovery never
calls the planner again, and changes to membership or contributing sources
withhold stale results. Search summaries show input surfaces, not the model's
alternative phrases. Descriptive questions and zero-result guidance remain
bounded, deterministic replies.

Generated tests establish the protocol and retrieval contracts with a stand-in
planner. The separate twelve-case synthetic qualification runner measures the
production compiler path in English, Chinese and mixed cohorts with no family
records, retries or hidden warm-up. Qualification policy 2 reports actual
adapter attempts separately from twelve logical cases: the three deterministic
age questions need no model, and nine cases may call it once. The fixed case
digest remains unchanged, while policy 1 raw-proposal/replay measurements remain
historical evidence. Its private measurement records the masked view and validated
proposal for each fixed fictional case, including proposals the compiler
refuses, so interpretation failures can be diagnosed without another provider
request. Invalid extensions are excluded. Ordinary user requests and provider
responses are not added to production logs by this measurement feature.
A passing generated test does not establish native
latency, family relevance, speech accuracy or device usability. Missing-date
questions such as “childhood” must not invent dates. The bounded date-answer
continuation below is separate from free-form model-generated questions.

## Correcting one scene clue

A v3 refinement can replace one stored descriptive clue with an anchored paired
correction such as `not red coat, but blue coat`, `不是红外套，是蓝外套` or
`不是red coat，是蓝外套`. The old clue must match exactly one normalized surface
shown in the current search summary. Model-proposed alternative phrases do not
identify a correction target.

The replacement phrase alone goes through the bounded compiler. It must produce
one descriptive concept without people, date, media, exact-text or other hard
filter changes. The other descriptive concepts and all existing hard filters
remain required. Unknown or ambiguous targets, unsupported replacements and
provider failures retain the current search and ask for clarification. The
ordinary media/date correction flow remains available. The original correction
is stored as the user's turn; recovery replays its stored result without asking
the provider again. This flow changes search conditions only, not captions,
memories or family facts.

## Removing one scene clue

When a v3 search is too narrow, `remove the "red coat" clue`, `drop "red coat" clue`
or `去掉“红外套”这条线索` removes one exact normalized surface shown in the current
search conditions. Straight double quotes and matched curly double quotes are
supported. Alternative phrases do not identify the target. The other descriptive
clues, people, capture dates, media type, exact quoted text, tags and places remain
unchanged. Removing the last clue clears only the descriptive filter.

This refinement uses no language-model request. Missing context, unknown targets,
reviewed-label collisions and extra unsupported instructions ask for clarification
without changing the current search. Current membership and source bindings still
apply, and workspace recovery returns the saved result without a duplicate turn.
The empty-state reply explains this explicit option without claiming to know which
clue caused the empty result. Removing a clue changes the search only; it edits no
family record.

## Asking why a result matched

`why the first result`, `为什么是第一项` and other supported current-list ordinals
explain that item without opening it or changing the result order or filters.
`why this photo`, `why this video`, `为什么这张照片` and `为什么这个视频` require
one current result of the requested type. A missing result, an out-of-page ordinal
or an ambiguous singleton reference asks for clarification.

This read-only path works with v1, v2 and v3 and makes no model request. It first
replays the current authorized result snapshot. The bounded reply summarizes the
active conditions and may name matching saved photo memories, edited captions or
generated captions. Reviewed-person and capture-date reasons must agree with the
active filters and current item metadata. It exposes no source IDs, raw source
prose, model alternatives or unselected names. Provenance is not a claim about
every visual detail, a clue-to-source mapping, or calibrated ranking confidence.
Source/access changes withhold stale explanations; private workspace recovery
returns the saved reply without submitting another turn. Explicit opening
commands retain their existing behavior.

## Answering a missing-date question

In a private v3 workspace conversation, an explicit new search with one supported
vague-time phrase can ask for a year or date range and retain the original
request. Supported phrases include `from childhood`, `childhood`, `when younger`,
`a long time ago`, `long ago`, `小时候`, `儿时`, `小的时候`, `很久以前` and `好久以前`.
For example, `找示例儿童小时候玩雪红外套的照片` followed by `2032年9月`
keeps the reviewed person, image type, snow and red-coat requirements and adds
the supplied capture-date bounds. It does not infer the person's age in 2032.

The same question can retain explicitly uncertain phrases such as `maybe two
summers ago`, `about two years ago`, `around a few winters ago`, `大概两年前`,
`可能在3年前`, `前几年` and `前些年`. English forms require `maybe`, `about` or
`around`, one/two/three/a few (or 1–3), and plural summers/winters/years followed
by `ago`. Chinese forms accept `大概` or `可能`, optional `是`/`在`, and a
supported small year count, or `前` followed by that count/`几` and `年`, or
`前些年`. These phrases trigger a question; they supply no calendar bounds.
No season, hemisphere or relative-year calculation is inferred. Bare forms
such as `two years ago` and `两年前` do not acquire this continuation.

The pending slot identifies an exact original span; a date-only answer resolves
through the normal deterministic date parser and fresh reviewed-entity checks.
The compiler first blanks that exact original time span. Its provider view also
hides the resolved hard conditions described above, while the supplied date is
added as a separate hard filter before retrieval. Neither the
original request nor the answer is overwritten or concatenated into generated
prose. Unknown extra conditions still require clarification. Quoted time phrases,
reviewed names that collide with a date, multiple vague-time phrases and existing
explicit dates do not create this slot.

Pending state is private server metadata in the existing turn record, excluded
from client results and conversation-history payloads. It is usable only from
the immediately preceding completed clarification in the same owned thread and
revision, with the same current session/library/source binding. It expires after
15 minutes; invalid answers cannot extend that time. Expiry asks for the full
request again, and a new explicit search replaces pending state. Source or access
changes withhold continuation. A failed local proposal can be retried with the
same date answer within the original expiry. Saved request recovery replays the
stored outcome without another model call.

This is a bounded date-answer flow. Other model questions, pronouns without a
reviewed person, and arbitrary conversational rewrites do not acquire pending
state. New private pending records use policy version 3. Earlier version 1 and 2
records retain their frozen phrase-validation policies for stored readback;
continuation still rechecks the current phrase rules and source binding, so an
old request that has become ambiguous must be restated. Existing v1/v2 search
behavior, public payloads and database schema remain unchanged.

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
