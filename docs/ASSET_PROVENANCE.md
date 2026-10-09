# Asset provenance

The public candidate contains no family photo, recording, screenshot or video.
The curated export retains sixteen mathematical media fixtures, including
duplicate copies required by separate test modules. Their exact hashes and
source paths are recorded in `source-export-manifest.json`.

## Synthetic media

| Fixture group | Content and origin |
|---|---|
| `home-8x8.jpg`, `discovery-delivery-photo.jpg`, `replay-8x8.jpg` | Generated 8 × 8 green image; no captured scene or metadata. |
| `home-3840x2160.jpg` | Generated geometric color bars; no captured scene. |
| `home-video.mp4`, `catalog-video.mp4` | Half-second generated test pattern. |
| `synthetic-video.mp4` | Twenty-second generated pattern and tone. |
| `synthetic-long-video.mp4` | 125-second generated pattern and tone. |

These fixtures were inspected independently before export. Byte identity is
retained because range, hash and video-duration tests depend on it. New demos
generate geometric media inside disposable temporary directories.

The two `contracts/v1/media/amber.png` and `blue.png` fixtures render the paired
authored SVG geometry (mountains and sun). They were visually inspected and
retained at their frozen contract hashes; no captured scene is used.

## Generic icon

The SVG and Android vector use newly authored house and photo geometry, covered
by the project's Apache-2.0 license. `generic-brand-transform.json` is a
historical record of the generic transformation applied during source export;
its statement that the supplied raster was excluded describes that transform,
not the current candidate contents. The original raster is now included
separately as the optional, owner-licensed
[`branding/photohouse-mark.png`](../branding/photohouse-mark.png). The project
owner confirmed permission to distribute this exact image under
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0). Its hash,
dimensions and use are recorded in [`branding/README.md`](../branding/README.md).
The generic icon remains the default, and no client resource or route was
changed. The existing household installation keeps its own branding.

## Build tools

The Gradle Wrapper JAR is an upstream build tool, not a PhotoHouse asset. Its
SHA-256 is `2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046`.
The wrapper pins the Gradle 8.10.2 distribution checksum. Its upstream license
and included component notices are retained under `third_party/licenses/gradle/`.
See the [upstream wrapper documentation](https://docs.gradle.org/current/userguide/gradle_wrapper.html).

Model weights, inference repositories, Android SDK tools and FFmpeg executables
are not redistributed in this source candidate. Their installation and licenses
remain separate from the generated output fixtures.
