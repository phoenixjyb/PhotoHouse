# Phone v50 original artwork and update feedback

Version 50 (`0.50-original-icon-ota`) restores the user-supplied PhotoHouse
artwork and improves update status messages. This is a qualified unsigned
candidate; it has not been signed, published or installed.

## Changes

- The shared Android launcher resources again use the original full-color PNG,
  white adaptive background and 18dp inset. The TV banner source also uses the
  original artwork; no TV package or feed is published by this phone release.
- The update screen shows the installed version and distinguishes already
  current, connection/TLS failure, invalid update information and other safe
  preparation failures.
- Equal or older feeds undergo all package, channel, signer and same-origin URL
  validation before being classified as already current. TLS checks, redirects,
  package signatures and artifact hashes retain their existing constraints.

The original image's SHA-256 is
`c8fc559e39c5c4d0b9902cafca47e15ac4e6cfa2cbc18d81a40d956e8a8f8909`.
The owner confirmed copyright ownership and Apache-2.0 distribution permission.
The earlier generic-brand transformation remains historical evidence; the new
source overlay records this restoration.

## Qualification

Artifact source: `4dcb0bc61dd78c5641caeaf7bf082b666acb95f2`.
Package: `dev.photohouse.connected`, version code 50.

The unsigned APK is **11,362,617 bytes**, SHA-256
`abe200d88e658bbfdb23439a288c29d7e8dbd0efd9300e8aafe7b06b565ce36a`.
Release assembly and lint passed. TV and fixture-app resource processing passed.
Ten focused update wire/HTTPS-client tests passed, covering safe version
classification, corrupt files, redirects, disconnects and untrusted TLS.

All 17 embedded build-profile fields match the retained reviewed phone profile;
fixture and UIQA flags are off. Native metadata verifies the package/version,
and signature verification rejects this unsigned candidate as expected.
The packaged 1254 × 1254 icon's decoded pixels match the original exactly;
compiled resources use the restored bitmap foreground and original inset.

The owner reported installing v49. This does not establish acceptance of the
v50 candidate. The earlier unconfigured updater QA screen was exercised in the
emulator; physical phone update, launcher appearance and voice acceptance remain
separate checks.

## Delivery

Use the original signing certificate, stage this exact APK privately on Windows,
verify native package/signature/bytes, publish only the phone feed and read back
the complete APK through trusted HTTPS. Preserve the current phone pointer for
guarded rollback. Signing and publication require this release's operation
authority. No API restart, database migration, worker change or model activation
is needed.

See [update troubleshooting](../../../docs/ANDROID_OTA_TROUBLESHOOTING.md) and
the delivered [v49 assistant workspace](PHONE_V49_RELEASE_CANDIDATE_2026-10-12.md).
