# Optional synthetic Web browser checks

The optional `web` profile runs the generated-data CommonJS browser suites
listed in `tools/check.py`. It includes:

- `server/tests/security/test_assistant_pending_recovery_browser.cjs`
- `server/tests/security/test_memory_book_editorial_browser.cjs`
- `server/tests/security/test_memory_book_editorial_reader_browser.cjs`
- `server/tests/security/test_memory_book_edition_browser.cjs`
- `server/tests/security/test_memory_book_edition_shelf_browser.cjs`
- `server/tests/security/test_memory_community_browser.cjs`
- `server/tests/security/test_memory_book_edition_sources_browser.cjs`
- `server/tests/security/test_story_titles_browser.cjs`
- `server/tests/security/test_story_related_media_browser.cjs`

The saved-edition editor and reader suites use generated records. The separate
shelf journey checks fresh detail reads, current chapter scope, source
invalidation, reader-only access, localized speech controls and stopping
speech when the shelf refreshes. It does not activate C2 or contact a household
service.

The conversation suite covers first-user-message previews, unchanged legacy
list responses, one-request fallback for an older server, stale-scope rejection,
draft recovery, and Chinese/English layout at 390 px and 150% text. It renders
preview text as native option text and uses generated records only.
The [conversation-preview contract](../server/docs/security/MEMORY_CONVERSATION_PREVIEWS_V1.md)
documents the opt-in wire field and compatibility behavior.

On October 5, 2026, its focused run passed 17 checkpoints and its bilingual
screenshots were reviewed. The first combined run stopped at an earlier native
disclosure-marker assertion because the test sampled computed style before the
stylesheet rule and connected summary were ready. The test now waits for that
same-origin stylesheet rule and still requires `display: list-item`. The focused
journey and the combined four-suite profile passed after this test-only fix.
See [local Web acceptance](local-web-acceptance.json).

The current profile requires every listed file. If an imported source snapshot does not
contain them, it refuses with the missing suite names before starting Node.
This profile is separate from `api`, `android`, and `all`; `all` continues to
run only API and Android checks, so ordinary development does not require
Node, Playwright, or Chromium.

## Existing local tools

Provide an existing Node.js executable, an already provisioned Playwright
module, and a compatible Chromium executable. The check wrapper does not run a
package manager, install dependencies, download a browser, invoke a provider,
or contact a production origin. It starts each CJS suite in its own Node
process. The suites use a pipe bridge to the API test process and intercept
browser requests against synthetic origins; they do not start an HTTP listener.

Use portable paths for the tools and a private directory for generated
screenshots and reports:

```sh
export PLAYWRIGHT_MODULE="<existing Playwright module name or path>"
export PH_BROWSER_PYTHON="<existing Python executable; defaults to sys.executable>"
export PH_BROWSER_EXECUTABLE="<existing Chromium executable>"
export PH_BROWSER_ARTIFACTS="<private directory for synthetic browser artifacts>"
python tools/check.py web
```

`PH_BROWSER_EXECUTABLE` may be omitted when the selected existing Playwright
installation already knows its browser executable. The suites also support
`PLAYWRIGHT_MODULE_PATH`; when both module variables are set, they must agree.
The wrapper passes `PH_BROWSER_EXECUTABLE` and `PH_BROWSER_ARTIFACTS` through
unchanged and uses the current Python `sys.executable` for the ASGI bridge
unless `PH_BROWSER_PYTHON` is supplied.

Record the Node, Python, Playwright module, and Chromium versions alongside
local results when reproducing a failure. The profile honors existing module
and executable selections instead of pinning a global “latest” version, so
browser-rendering results may differ across already provisioned toolchains.
Artifacts contain generated synthetic test output only; keep them local and do
not publish them as household or family acceptance evidence.

Passing these suites qualifies their synthetic navigation and rendering paths
for that source/toolchain combination. It does not establish a live service,
provider, production browser, real account, family data, device, or household
acceptance.

For source-only deployment preparation, see [static UI overlays](WEB_DELIVERY.md).

The recorded local result and toolchain are in [Web acceptance](local-web-acceptance.json).
