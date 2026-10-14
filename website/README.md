# PhotoHouse public introduction

This is a Chinese-first, static project introduction. It is plain HTML and CSS,
with original CSS/SVG illustration and the existing licensed PhotoHouse mark. It uses no JavaScript, external images,
runtime services, forms, downloads, or build dependencies.

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
