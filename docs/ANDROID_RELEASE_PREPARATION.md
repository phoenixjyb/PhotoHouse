# Prepare phone and TV releases

The [ordinary Android profile](DEVELOPMENT.md) runs JVM tests, lint and
unconfigured debug builds. A household release additionally needs an exact
source revision, explicit private build inputs and its own artifact checks.

## Pin the build inputs

Start from a clean committed monorepo. Record its full commit, the module's
Gradle file hash, JDK/Gradle/Android build-tool versions and the private property
profile hash. Keep household routing values outside Git and public build logs.
Gradle properties take precedence over `local.properties`; explicitly supply
every routing value and feature choice used for the release so an old local
file cannot silently choose them.

The supported inputs and constraints are in the
[phone build file](../clients/android/android/connected/build.gradle.kts) and
[TV build file](../clients/android/android/tv/build.gradle.kts). A previous APK
can establish shipped `BuildConfig` values, package, version and signer. It
cannot establish the historical value of every build-only property. Record
inferred values and newly selected choices separately. Release preparation
keeps `photohouseStoryFixtureEnabled=false`; the phone's
`photohousePhoneUiQa=false` selects the household package.

Build the modules in separate serial invocations. Shared property names such
as `photohouseHomeCalendarEnabled` can legitimately have different phone and
TV values. Clear inherited `ORG_GRADLE_PROJECT_*` variables before supplying
the selected module's complete profile. Reuse existing toolchains and caches;
Gradle's `--offline` does not prevent a wrapper from downloading its missing
distribution before Gradle starts.

## Verify the unsigned artifacts

Run `:connected:assembleRelease` and `:connected:lintRelease`, then the TV
equivalents with the TV profile. Preserve complete build output privately.
Copy each unsigned APK to a fresh candidate filename and record its size and
SHA-256. Check native package/version metadata, absence of an APK signature,
and the actual DEX `BuildConfig` values against the selected profile. Recheck
source and profile identities after building. A successful task or an existing
APK filename alone does not bind the artifact to those inputs.

## Sign and publish

Signing and OTA publication require authority for that exact operation. Use
the existing application certificate when updating an installed application;
verify the signed package, version, certificate and full APK digest. Publish
phone and TV to their respective feeds only after the signed artifact passes
those checks, then read back the complete HTTPS APK and compare it to the
published artifact. Feed metadata alone does not establish download integrity.

Installation, owner/member journeys, real voice input and physical TV playback
remain separate acceptance checks. Source CI, unsigned builds and publication
must not be reported as those outcomes.
