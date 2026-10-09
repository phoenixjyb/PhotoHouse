# Android same day related moments

The grouped story selector has a collapsed “同一天的更多瞬间” panel. Expanding
it does not send a request. A contributor explicitly requests suggestions, reviews
each returned photo or video, and taps “加入故事” to append it to the ordered
selection. The panel says that a recorded capture date match does not establish
one activity and that filename or upload dates are not proof.

The phone client implements the protected related-media v1 request as an optional
`StoryWorkspaceApi` capability. Older fake adapters remain source compatible and
report the feature unavailable. The HTTPS adapter sends the request through the
existing authenticated, no-store story workspace transport. A strict bounded
decoder checks the exact response keys, library, ordered seed IDs, sorted valid
recorded days, review flag, pagination cursor, descending unique candidate IDs,
full `taken_at` values, media kinds, and library-scoped thumbnail paths. Date-only
and ISO datetime values follow the server grammar; offsets preserve the written
calendar day. Filename and upload receipt hints are neither read nor returned.

The editor binds each request to its account token, library, membership generation,
selection, and editor lifetime. Selection or scope changes cancel delayed results
and clear candidate thumbnail buffers. Lookup failure leaves the current selection
available. Candidate pagination replaces the bounded page, preserves the exact
cursor on retry, and keeps its preview cache separate from the gallery page cache.
The related preview cache is limited to 20 images and 2 MiB; individual images
remain subject to the existing 1 MiB thumbnail cap. Candidate inclusion appends
to the existing order and rejects the 25th asset.

## Local source evidence

On 2026-10-09, the following focused profile passed on macOS with JDK 17, the
existing Android SDK, offline Gradle 8.10.2, and two workers. It
used the existing shared Gradle distribution directly; the Gradle wrapper was not
used to verify or download a distribution.

```sh
# Set JAVA_HOME and ANDROID_HOME for your installed JDK 17 and SDK.
/path/to/gradle-8.10.2/bin/gradle \
  --offline --no-daemon --max-workers=2 -PphotohousePhoneUiQa=true \
  :live-core:test :connected:compileDebugKotlin \
  :connected:compileDebugAndroidTestKotlin :connected:lintDebug
```

Results: 591 live-core JVM tests passed, including ten related-media wire,
repository, pagination, failure, stale-response, explicit-inclusion, and account,
library, membership, and editor-close scope checks. Phone debug Kotlin and Android-test Kotlin compilation passed. Phone debug
lint passed. `git diff --check` passed. The fixture UI covers Chinese and English
at 150% text, confirms expansion does not fetch, makes lookup explicit, adds a
video after existing selections, and checks that invalidated preview bytes are
zeroed.

## Emulator and delivery boundary

The two bilingual Compose journeys passed on an existing API 36 AVD at 150%
text after fixing the lazy-list fixture scroll discovered in the first attempt.
The unconfigured QA package is separate from the family app. The bilingual
candidate renders, selection, review and saved-reader captures were inspected;
the scrolling candidate list keeps the header and outline action accessible.
The same two journeys were also run directly through instrumentation to retain
the generated captures after Gradle's test cleanup. These runs overlap and do
not count as four different tests.
No physical phone, deployed API, release signing, household data, or family
acceptance was used. The deployed API and phone release do not gain this feature
from the local source changes alone.
