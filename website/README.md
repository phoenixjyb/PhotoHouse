# PhotoHouse public introduction

This is a Chinese-first, static project introduction centered on family-owned
local storage/processing and stories carried by images, video, audio and text. It is plain HTML and CSS,
with original CSS/SVG illustration and the existing licensed PhotoHouse mark. It uses no JavaScript, external images,
runtime services, forms, downloads, or build dependencies.

## Published introduction

[Open PhotoHouse](https://photohouse-family-memories.yanbophx.chatgpt.site).
The private preview was verified and then made public at the owner's request.
[Delivery record](RELEASE_2026-10-14.md) separates local layout checks, hosted
readback and audience status. Development remains in this monorepo; the hosting
repository is an immutable deployment mirror.

Any static host can serve `dist/`; no application server or private configuration
is needed. Keep hosting credentials and deployment-specific state outside Git.

## Preview locally

From the repository root, run:

```sh
python3 -m http.server 8000 --directory website/dist
```

Then open <http://127.0.0.1:8000>. Stop the preview with `Ctrl-C`.

Opening `dist/index.html` directly also works. The GitHub links point to the
public source repository. The story and people shown on this page are invented
examples; they do not use family content and do not claim that automatic story
stitching is available.

## Contents

- `dist/index.html` — page structure and copy
- `dist/styles.css` — responsive styles, illustration, focus and reduced-motion
  handling
- `dist/photohouse-mark.png` — unchanged shared Android mark; its license/source
  identity is documented in [branding](../clients/android/android/branding/README.md)

The feature summary reflects the project status reviewed on 2026-10-14. Refresh
it against `../docs/PROJECT_STATUS.md`, `../docs/FEATURES.md` and
`../docs/ROADMAP.md` before a later publication.
