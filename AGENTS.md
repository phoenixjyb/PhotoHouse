# PhotoHouse contributor guide

## Ownership and layout

- `server/` owns the API, Web UI, database migrations and worker contracts.
- `clients/android/android/` owns phone and TV clients and shared Kotlin modules.
- Keep contract changes consistent across server, Web and Android. Add meaningful
  tests for authorization, revisions, retries and visible user actions.
- Preserve local changes. Work from the actual revision, rather than a dated
  handoff or an installed application's version number.

## Local checks

- Follow `docs/DEVELOPMENT.md`. `tools/check.py api` uses temporary databases and
  generated media; it needs no model, GPU or listening server.
- `tools/check.py android` runs JVM tests, lint and unconfigured debug builds.
  It does not sign release packages, install them or publish updates.
- Render changed UI at phone and desktop widths; check large text and keyboard
  or TV remote navigation when affected. Separate fixture, emulator and physical
  device evidence.

## Data and runtime boundaries

- Never add household endpoints, accounts, credentials, original media, voice
  recordings, embeddings, databases, model weights or signing keys to Git.
- Libraries require membership. Anonymous TV viewing is a separate, explicitly
  configured access path; it must not broaden library or assistant access.
- Preserve original text/audio and distinguish it from transcripts, polished
  prose, tags and chapter links. A chapter link does not transfer ownership.
- Recording, transcript insertion, command submission and playback are explicit
  user actions. Do not start listening or send a command automatically.
- Failed or incomplete conversion records are evidence. Resume unfinished work
  without re-encoding completed videos or silently clearing source failures.
- Deployment, service control, production data changes, release signing and
  publication require authority for that operation. Local checks do not grant it.

## Public source maintenance

The source baseline and deliberate icon transformations are recorded in
`docs/source-export-manifest.json`, `docs/generic-brand-transform.json` and
`docs/documentation-transform.json`.
Dependency notices belong in `third_party/`; model providers have separate
licenses and installation lifecycles. Keep optional provider services outside
the ordinary CPU development profile.
