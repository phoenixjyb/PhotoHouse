# Contributing

## Start with a bounded change

Describe the user action, affected API contract and visible success/failure states. Keep source edits separate from deployment, data migration and publication. One integration owner coordinates contract changes across server and clients.

## Development rules

1. Use generated fixtures and a temporary data directory. A fake authorization state is never proof of production authorization.
2. Keep original input immutable. A transcript, polished memory, tag or story is derived data with provenance.
3. Preserve existing story edits. Submit mutations with a revision and handle conflicts through reload/review.
4. Keep protected library routes separate from anonymous, explicitly configured home-TV routes.
5. Recording is explicitly started, stopped, reviewed and submitted. Playback yields to microphone capture.
6. Keep GPU/provider checks optional. Ordinary PR checks must run without downloaded models or a live server.

## Evidence in a change

Record the base revision, changed behavior, narrow meaningful check and unresolved delivery gate. Distinguish unit/API tests, emulator rendering, signed artifacts, live services and family/device feedback. Inspect a rendered UI after visual changes; include accessibility and text scaling where affected.

## Licensing

Submit code and assets you have the right to redistribute. Record the upstream source and license for copied code, fonts, graphics and fixtures. A dependency's code license does not establish a model weight's license. Do not contribute production endpoints or deployment history.
