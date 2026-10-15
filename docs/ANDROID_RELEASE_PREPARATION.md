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
The new `photohouseMemoryGroupsEnabled` property defaults to false and requires
`photohouseProtectedNativeV2Enabled=true`. Enabling the phone control does not
enable server storage or similarity lookup. Record it explicitly in a future
phone release profile, and qualify the e7 API and private vector profile before
claiming the shared-memory journey works live.

Build the modules in separate serial invocations. Shared property names such
as `photohouseHomeCalendarEnabled` can legitimately have different phone and
TV values. Clear inherited `ORG_GRADLE_PROJECT_*` variables before supplying
the selected module's complete profile. Reuse existing toolchains and caches;
Gradle's `--offline` does not prevent a wrapper from downloading its missing
distribution before Gradle starts.

### Check a complete private profile

`tools/prepare_android_profile.py` checks the actual module's declared property
keys against a complete explicit profile. It requires a clean full commit, an
expected profile SHA-256 and a direct private profile file outside the repository.
The profile format is deliberately simple UTF-8 `key=value` lines and `#`
comments, with no property escapes, continuations, duplicate keys or credentials.

```sh
python3 tools/prepare_android_profile.py --module phone \
  --commit FULL_40_CHARACTER_COMMIT \
  --profile /absolute/private/phone.properties \
  --profile-sha256 FULL_64_CHARACTER_SHA256
```

Use `--module tv` for the separate TV profile. The checker validates boolean
dependencies, release QA/fixture mode, catalog constraints and routing shape.
Current phone/TV Home and OTA consumers require canonical HTTPS DNS origins.
Private RFC1918 IPv4 LAN overrides map only the selected hostname; they preserve
TLS and hostname checks. This checker does not attest HTTP media support, which
is not implemented by the current APK clients. No path, query, credential or
trust override can be embedded in an origin.
The main phone/API or TV/catalog origin is required, as is the phone Home origin
when Home discovery is enabled. A disconnected debug profile is not a release
profile. Optional disabled Home/OTA routes can remain empty.

Its JSON contains source/profile/Gradle hashes, boolean choices and routing-value
hashes, never the original endpoints. It performs no Gradle invocation, network
request, signature access, service operation or publication. A passed preparation
is not an APK check: embedded DEX values, actual icon, signer and full artifact
still need the checks below. Source property additions deliberately fail closed
until this checker and its generated tests are updated. POSIX fixture checks are
recorded locally; native Windows release preparation remains a separate gate.

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
