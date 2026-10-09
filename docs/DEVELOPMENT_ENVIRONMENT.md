# Local development environment report

Run the read-only environment doctor from the repository root:

```sh
.venv/bin/python tools/doctor.py
.venv/bin/python tools/doctor.py --json
```

On Windows PowerShell, use:

```powershell
.\.venv\Scripts\python.exe tools\doctor.py
.\.venv\Scripts\python.exe tools\doctor.py --json
```

The report checks the interpreter running the doctor, exact versions pinned by
`config/requirements-dev.lock` and its included API lock, and locally detectable
tools for the repository's supported profiles. It reads package versions with
`importlib.metadata`; it does not import the application, model or provider
packages.

## Profiles and prerequisites

| Profile | Doctor classification | Local prerequisites it checks |
|---|---|---|
| `api` | Required CPU profile | Python 3.12 and installed versions matching the development lock |
| `memory` | Focused CPU profile | The same Python and locked CPU development environment |
| `android` | Phone and TV profile | Python 3.12, JDK 17, Android SDK platform 34, required build-tools 34.0.0 executables, and a complete pinned platform Gradle wrapper |
| `web` | Optional browser profile | The CPU environment, Node.js meeting the resolved Playwright package's declared engine range, the four checked-in browser suites, the module and a detected or configured Chromium executable |
| `all` | API plus Android | The `api` and `android` prerequisites; it excludes optional `web` checks |

The SDK check requires `android.jar` for platform 34 plus `aapt2`, `d8`,
`zipalign` and `lib/apksigner.jar` from build-tools 34.0.0 (using the native
Windows executable names on Windows). The wrapper check requires the current
platform script, `gradle-wrapper.jar`, a pinned distribution URL and a
well-formed `distributionSha256Sum` in
`clients/android/android/gradle/wrapper/gradle-wrapper.properties`. It checks
the checksum's shape, not the downloaded distribution's bytes. The Gradle
wrapper cache is reported as an optional warm cache; without a cached
distribution its first build may need to obtain that distribution. The doctor
itself never starts the wrapper.

The Web module selection follows `tools/check.py`: `PLAYWRIGHT_MODULE` or
`PLAYWRIGHT_MODULE_PATH` may select an existing module, and conflicting values
are reported as unverified. With neither set, the doctor checks the default
`playwright-core` resolution. It checks `PH_BROWSER_EXECUTABLE` when supplied,
or looks for Chromium or `headless_shell` in the standard Playwright cache for
the current platform, including macOS Intel and Apple Silicon cache layouts.
It does not search arbitrary disks for browser installations. For the selected
module, the doctor reads its local package metadata for a simple `engines.node`
minimum and compares the full detected Node version with that minimum. It
supports `playwright` and `playwright-core` package metadata, including when
the selected module is an absolute path containing spaces. Missing or
unsupported engine expressions are `unverified`; a detected Node executable
alone is not enough to mark the Web profile available.

## Reading the report

Each prerequisite is `available`, `missing` or `unverified`:

- `available` means the expected local version or file was detected.
- `missing` means a required tool, file or exact package version was absent.
- `unverified` means the doctor could not safely determine availability, such
  as an unreadable lock, conflicting selection, failed probe or timeout.

Profiles combine the status of their required prerequisites. The report is an
environment inventory only: `available` does not mean tests, builds, browser
journeys or device checks passed. Run the corresponding command in
[Development](DEVELOPMENT.md) to collect test evidence.

The doctor reads local requirement locks, package metadata, selected environment
variables and known SDK/Gradle/Playwright locations. Its only process probes are
short version or module-resolution commands with fixed argument vectors, a
three-second timeout and at most 4 KiB of retained output. Truncated probe
output is treated as unverified. Child probes receive only the environment
entries they need, and raw probe output is not included in either report format.
The doctor does not install, download,
build, start a service, contact a provider, inspect account configuration, or
list models or datasets. Text and JSON output omit absolute paths and
environment-variable values.

## Recorded exact-lock CPU run

On October 6, 2026, a fresh macOS arm64 Python 3.12.12 environment installed
`config/requirements-dev.lock` with required hashes and binary wheels. All 27
applicable package versions matched; one Windows-only package was excluded by
its marker. The doctor reported all profile prerequisites available. The API
profile separately passed 523 tests, 215 subtests and the generated no-listener
demo; 40 standalone tooling tests passed. This does not qualify native Windows,
provider output, hosted CI, release signing or installed devices. Earlier usable
but mismatched environments remain historical evidence in the acceptance data.
