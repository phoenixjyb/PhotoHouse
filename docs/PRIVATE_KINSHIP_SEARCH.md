# Private kinship search configuration

The negotiated [search-v2 API](ASSISTANT_JOINT_SEARCH_V2.md) can use an explicitly
selected private relationship graph to resolve relative phrases to current
reviewed person identities. This source feature has no public family-tree route,
automatic account provisioning or database migration. Household facts, names,
account bindings and validation reports stay outside Git and source packages.
Tests and examples use fictional people only.

## Privacy and activation

`assistant_kinship_path` is an optional, default-unset staging/runtime field.
It points to an existing owner-only JSON file outside source/Git checkouts and
outside media, databases, incoming data, indexes, updates, journals and workspace
storage. Application construction retains the selected provider without opening
the graph. An authorized request loads it after current library membership checks.

The graph selects one library, an explicit account-ID allowlist, and one chosen
perspective. Merely joining the library does not grant use of this graph. Every
selected account must still have a current session and approved library access.
Account display names and relatives' names are not login IDs: an operator must
confirm the intended accounts before filling `scope.account_ids`. An empty list
is an inactive draft. No account is created or membership changed by this file.
Preapproved people awaiting registration can be recorded in a separate private
access plan with stable logical person IDs and empty login-account bindings.
Registration alone or a matching display name must not activate that approval.

All allowed accounts share the graph's selected perspective. Bare `妈妈` and
`my mother` refer to that chosen center, not an inferred identity of the signed-in
account. Clients must show the chosen center before enabling relative language;
another perspective requires an explicit change and refreshed results.

The loader requires a private parent directory and file (POSIX owner-only modes;
Windows real owner/DACL checks), no symlink/reparse traversal or hard-linked
file, strict duplicate-free JSON, bounded size and stable before/open/after file
identity. It performs no ACL changes or writes. Failures return generic errors
without graph contents or paths. This is access-controlled storage, not an
encryption claim or a backup/disaster-recovery qualification.

## Graph contract

Schema 1 has `graph_id`, `revision` (positive integer or bounded revision label),
`perspective_id`, `scope`, `people` and `assertions`. Limits are 128 KiB, 256
people, 2,048 assertions and 64 selected accounts. The canonical scope is:

```json
{"account_ids": ["fictional-account-one"], "library_id": "fictional-library"}
```

An earlier single-account `account_id` scope is also accepted. Draft scope can
use an empty list and null library. Person records contain stable logical `id`,
`name_en`, nullable `name_zh`, explicit `aliases` and optional `catalog_binding`.
Do not guess Chinese characters from romanization. Rename/add aliases on the
same logical person; do not create a second identity for an alternate name.

Each assertion contains its own `id`, `subject_id`, typed `relation`, `object_id`
and `source: "user"`. Current explicit relations cover mother/father, son/daughter,
elder/younger daughter, older/younger/eldest sister and husband. Self-links,
duplicate assertions, contradictory parent roles and parent/age cycles are
refused. Missing facts remain missing. In particular:

- A spouse is not automatically a child's parent.
- A sister does not automatically inherit the same parents.
- Elder/younger daughter does not establish an exhaustive family or an unknown
  child's birth order. Eldest sister is a separately explicit relation.
- No biological/adoptive distinction or Chinese personal name is invented.

## Resolution and source binding

English and Chinese deterministic forms include `mom`, `妈妈`, `外婆`, `奶奶`,
`my father's mother`, `爸爸的妈妈`, a named person's `younger sister`, and a named
person's `elder daughter`. A coordinated phrase such as `Parent One's mother
and father` retains its named anchor; the anchor is not added as another person
who must appear. `grandmother` remains ambiguous between maternal and paternal
branches. Incomplete paths are not narrowed to the only known branch. Plurals
are explicit sets; existing together/any/all constraints still govern photos.
Quoted relative words remain literal text search.

A target logical person must match exactly one current reviewed catalog
name/alias, or an explicit `catalog_binding` with both `person_id` and expected
current `label`. Relative nicknames alone cannot join identities. Distinct logical
people cannot silently collapse into one catalog person. Missing, ambiguous or
stale bindings clarify without broadening the search. The graph cannot create a
reviewed identity, approve face assignments or enable a disabled people index.

The whole canonical graph digest (including scope, perspective and revision)
joins the existing discovery source binding. Each graph-backed read reloads the
file before returning to detect concurrent edits. Removing an account, changing
perspective, editing/withdrawing a relationship, or deleting/unloading the graph
invalidates previous contexts; current catalog/membership checks still apply.
The graph is never included in media text retrieval, result cards, public
capabilities, private chat transcripts or an automatically generated story.

## Checks and delivery

Run the generated graph/provider and protected HTTP suites:

```sh
.venv/bin/python -m unittest discover -s server/tests/security -p 'test_*kinship.py'
```

Also run affected staging/runtime, joint-search, conversational and package
checks, the source verifier and the API profile. The fixed runtime source
allowlist includes `kinship.py`. Real private graph checks belong in private
artifacts and are separate from synthetic source checks.

Implementation `01cf409` passes 29 focused graph/provider/HTTP tests and the
complete local API profile: 1,552 tests / 988 subchecks plus the generated
no-listener demo and isolated package import checks. The invocation receipt
records unchanged start/end commit and source input hash. Staging configuration,
runtime forwarding, source-verifier and existing joint/conversational checks also
pass. No native Windows file/ACL, installed client, live activation or real-family
search relevance is qualified by this source cohort.

Library/account/person bindings, native file permissions, real relevance,
client perspective display and live activation are separate gates. Editing a
local private draft does not deploy the API or activate a running installation.
