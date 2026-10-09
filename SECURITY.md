# Security and privacy

PhotoHouse stores private family media. Access control must apply to originals, previews, playback exports, story sources and assistant records, including error responses and caches.

## Boundaries

- Library membership and role checks precede protected reads and writes.
- Upload auto-approval is selected by the owner per member and library, and defaults off.
- Anonymous home-TV access is a separate, explicitly restricted configuration. It grants no phone/Web library access.
- Original memories persist until the owner explicitly deletes them. Derived processing requires consent.
- Assistant troubleshooting records contain recognized/submitted text and status for 30 days; ASR recordings remain transient.
- Deletion uses a journal bound to the database. Backup and restore procedures must preserve both and replay deletions before reads.

## Reporting

Report vulnerabilities through [private GitHub Security Advisories](https://github.com/phoenixjyb/PhotoHouse/security/advisories/new). Private reporting is enabled for this repository. Do not post vulnerability details, passwords, recordings, family account identifiers, private URLs or database excerpts in a public issue.

## Deployment

Configure HTTPS, secrets, service accounts and media roots outside source control. Production signing material and OTA release publication are separate operator actions. New migrations require a stopped-writer backup, copy rehearsal and independent verification; a source test does not establish live safety.
