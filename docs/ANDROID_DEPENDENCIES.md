# Android dependencies and third-party notices

## Scope and evidence

This record separates two resolved dependency profiles for production phone module `:connected` and TV module `:tv`. The `:app` module is a synthetic fixture and is excluded from production-phone claims.

The [debug runtime graph](dependencies/android-runtime.json) was resolved at source revision `8a4864202665786e0d93b76dc0c9a85ac80c8777`. It records 98 external module coordinates, 979 unique dependency edges, 136 distinct coordinate/lane/file/hash references (68 per lane), and 69 unique archive files. The artifact view emitted 138 rows; duplicate coordinate, lane, file, and hash rows are deduplicated in the distinct-reference count. Twenty-nine coordinates have no selected external archive in these runtime configurations.

The [release runtime graph](dependencies/android-release-runtime.json) was resolved at source revision `312b40e1f865061ff98ec7f4d52fe3cdd31f4ff6`, using `:connected:releaseRuntimeClasspath` and `:tv:releaseRuntimeClasspath`. Gradle reported `BUILD SUCCESSFUL`; all 136 raw archive-resolution rows (134 distinct references) matched SHA-256 to the exact cached files, and license metadata for all 96 coordinates was checked against the exact POM and inherited parent POM hashes. The graph has 96 external module coordinates, 948 unique dependency edges (478 phone and 470 TV), 134 coordinate/lane/file/hash references (67 per lane), and 67 unique archive files. Twenty-nine coordinates have no selected external archive. This records dependency resolution only; no release APK/AAB was assembled or inspected.

The debug and release records were resolved at different Android source revisions, so their observed differences cannot be attributed to build variant alone. Per the recorded graphs, the phone release graph no longer selects `androidx.compose.ui:ui-test-manifest:1.6.8` and selects `androidx.tracing:tracing:1.0.0` instead of `1.2.0`; the TV release graph no longer selects `ui-test-manifest:1.6.8`. The detailed coordinate, edge, artifact hash, and POM evidence is in the release JSON.

The [license metadata](dependencies/android-licenses.json), [debug archive notices](dependencies/android-notices.json), and [build tooling evidence](dependencies/android-build-tools.json) remain separate records. Release component rows include exact-coordinate license metadata and POM/parent evidence revalidated against the local Maven cache. POM declarations and inherited license metadata are evidence, not legal clearance.

## Distribution notices

OkHttp 4.12.0 bundles Public Suffix List data with a `NOTICE` entry specifying MPL-2.0. The resolved phone and TV release runtime graphs select the same `okhttp-4.12.0.jar` bytes recorded for debug; the release archive hash is `b1050081b14bb7a3a7e55a4d3ef01b5dcfabc453b4573a4fc019767191d5f4e0`. Its embedded notice entry SHA-256 is `8a9c58fbded5ea3474315e4a9824ca8b1486098a1a03e897e0b19419d5e1876a`, matching the retained notice at `../third_party/licenses/android/okhttp-publicsuffix-NOTICE.txt`. Include that notice and the complete [MPL-2.0 text](../third_party/licenses/android/MPL-2.0.txt) in applicable binary distribution notices. OkHttp's resolved POM declares Apache-2.0.

The Android Maven metadata audit found Apache-2.0 declarations for the 96 release graph coordinates, with three Guava-family entries inheriting metadata from exact cached `guava-parent` POMs. The full Apache-2.0 text is included at [`third_party/licenses/android/Apache-2.0.txt`](../third_party/licenses/android/Apache-2.0.txt); the root [`LICENSE`](../LICENSE) also contains Apache-2.0.

## Limits and release gates

The release record covers `releaseRuntimeClasspath` graph resolution and selected external archives. It does not establish which resources survive R8, which files reach APK/AAB packages, merged license resources, application behavior, or device compatibility. A release build, package-content review, embedded-notice scan against each distributable APK/AAB, and device checks remain separate gates. Generate and review Gradle dependency verification metadata before public binary distribution.

Artifact SHA-256 values identify the resolved local artifact bytes; they are not publisher signatures or independently verified upstream checksums. Gradle 8.10.2 bootstrap previously succeeded with the wrapper's pinned distribution checksum, but its downloaded ZIP was not retained for a second local hash. No release assemble, signing, APK/AAB inspection, install, emulator, device, or app-origin request was part of this dependency graph check.

Optional model/provider services are outside this Android inventory. Their software, assets, model weights, and licenses require separate review.
