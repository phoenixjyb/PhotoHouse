# Phone v50 original artwork and update feedback

Version 50 (`0.50-original-icon-ota`) restores the user-supplied PhotoHouse
artwork and improves update status messages. It is signed and published on phone
HTTPS OTA with owner authority. Windows native checks and an independent Mac
complete HTTPS download passed; physical phone installation remains unverified.

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

The signed APK is **11,381,112 bytes**, SHA-256
`7917fde63817dd7877b1b8258d0ea0b7de07303a129e14ea5d584f4b7cb61e00`.
Native verification confirms the original signing certificate
`56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28`,
package/version, alignment and unchanged DEX contents. The reviewed checkout
`004e8c4a44d68a3cd12ab3ff5334c340b00c3970` has the same Android build subtree
as the artifact source above.

Three controller issues were corrected before publication: a retained v49 size
literal was caught before execution; the older resolver's process predicate
rejected the qualified live Web startup wrapper before signing; and the native
publisher rejected the resolver's stale hash after staging. Failed receipts and
original controllers were preserved. Two added regressions bring the local
controller cohort to 22 distinct checks; native parsing and current task/process
ownership checks passed for the corrected resolver. Signing happened once.

The publication recovery reused the verified staged APK and preserved all seven
original staged files, adding only the corrected controller and authority. It
confirmed both existing feed pointers before the phone-only publication. Windows
and an independent Mac downloaded all signed APK bytes with default trusted TLS
and matched the expected hash. TV v30's served manifest remained byte-identical.
The API task, configuration, wrapper and listener matched the prepublication
snapshot afterward; no API restart, database migration, worker change or model
activation occurred.

See [update troubleshooting](../../../docs/ANDROID_OTA_TROUBLESHOOTING.md) and
the delivered [v49 assistant workspace](PHONE_V49_RELEASE_CANDIDATE_2026-10-12.md).
