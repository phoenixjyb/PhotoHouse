# Third-party notices

First-party PhotoHouse code uses Apache-2.0. Dependencies retain their upstream
licenses. This inventory covers the supported API development profile; optional
inference installations and release APKs need their own inventory.

## Python API and development profile

The hash-locked profile installed 27 packages. Upstream license and attribution
files copied from those distributions are retained in `third_party/licenses/python/`.
`docs/python-license-notices.json` records their exact hashes.

| Package | Version | Declared license |
|---|---|---|
| alembic | 1.19.2 | MIT |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| click | 8.5.0 | BSD-3-Clause |
| fastapi | 0.135.2 | MIT |
| greenlet | 3.5.5 | MIT AND PSF-2.0 |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| idna | 3.19 | BSD-3-Clause |
| iniconfig | 2.1.0 | MIT |
| Mako | 1.4.1 | MIT |
| MarkupSafe | 3.0.3 | BSD-3-Clause |
| packaging | 25.0 | See retained upstream notice |
| pillow | 12.3.0 | MIT-CMU |
| pluggy | 1.6.0 | MIT |
| pydantic | 2.12.5 | MIT |
| pydantic_core | 2.41.5 | MIT |
| Pygments | 2.19.2 | BSD-2-Clause |
| pytest | 9.0.3 | MIT |
| colorama (Windows test runner) | 0.4.6 | BSD-3-Clause |
| SQLAlchemy | 2.0.52 | MIT |
| starlette | 1.3.1 | BSD-3-Clause |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| uvicorn | 0.52.4 | BSD-3-Clause |

## Gradle Wrapper

The upstream Gradle 8.10.2 license, including component notices, is retained in
`third_party/licenses/gradle/`. The JAR hash and pinned distribution checksum are
documented in [asset provenance](docs/ASSET_PROVENANCE.md). The full Gradle
distribution is downloaded as a build tool and is not tracked here.

## Android dependencies

The production phone (`:connected`) and TV (`:tv`) debug runtime graphs cover
98 external components and 69 unique archive files. Their resolved metadata
declares Apache-2.0; exact artifact and metadata hashes are recorded in the
[Android inventory](docs/ANDROID_DEPENDENCIES.md). These hashes identify the
resolved bytes, rather than publisher signatures.

OkHttp 4.12.0 also bundles Public Suffix List data with an MPL-2.0 notice. The
exact notice and complete license are retained in `third_party/licenses/android/`.
Applicable binary distributions must retain those notices. Release variants,
packaged APK notices and dependency verification remain separate checks.

## Optional Web browser test tools

The isolated generated-browser profile pins Playwright Core 1.55.0
(Apache-2.0) in its [tooling lock](server/tests/security/browser-tooling/package-lock.json).
It uses Node 22.17.0 and the matching Chromium headless shell as external CI
tools. These packages, runtimes and browser binaries are not vendored or
redistributed in PhotoHouse source archives. Their upstream notices remain
with the installed tools; PhotoHouse's first-party license does not replace
them. See [Web development](docs/WEB_DEVELOPMENT.md) for the isolated hosted
installation and generated-only check boundary.

## Optional models and runtime tools

Model weights, external inference repositories, FFmpeg executables and Android
SDK tools are not redistributed. Each installation must select and qualify its
own explicitly configured versions and licenses. `models/` contains a disabled
provider template rather than weights or download hooks.

## Assets

See [asset provenance](docs/ASSET_PROVENANCE.md). The generic icon and synthetic
media are authored/generated project assets; unidentified historical branding
and private screenshots are excluded.

## Optional editorial and worker synthetic-test profile

The separate [test profile](server/docs/PHOTOHOUSE_EDITORIAL_TEST_PROFILE_2026-10-04.md)
has its own [32-package artifact and license inventory](docs/editorial-test-dependencies.json).
It includes ImageHash, NumPy, PyWavelets and SciPy for generated CPU fixtures.
Existing matching license artifacts are reused; additional release and bundled
license texts are retained under `third_party/licenses/python-editorial-test/`.
Wheels, model weights and installed environments are not included in source archives.
