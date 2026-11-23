# PhotoHouse Web redesign review — 2026-11-24

## Scope and method

This review covers the signed-in PhotoHouse Web Assistant modal and its private conversation pane in the `literal-rust-20261123` worktree. It records the redesign and the available generated-browser evidence; it is not a whole-application accessibility certification.

The requested Google Chrome `modern-web-guidance` audit used package snapshot `v2026_11_16-268fb9ea` and CLI 1.0.2 through an ephemeral npm invocation. No persistent installer or package change was made. The responsive-design, form-factor-adaptation, CSS-layout, dialog, accessibility, motion, and JavaScript guides informed the review. The [official repository](https://github.com/GoogleChrome/modern-web-guidance) and its [skill workflow](https://github.com/GoogleChrome/modern-web-guidance/blob/main/skills/modern-web-guidance/SKILL.md) are the primary references. Reproduce the retrieved snapshot with `npx -y modern-web-guidance@latest retrieve "responsive-design,form-factor-adaptation,css-layout,dialog,accessibility,motion,js" --skill-version 2026_11_16-268fb9ea`.

The supporting legacy-rule scan covered 9 files and 52 rules, about 20% of the identified corpus. It surfaced a `Promise.withResolvers()` suggestion in `story-workspace.js`; the existing deferred helper was retained for compatibility. This bounded scan does not certify the unscanned code.

## Design changes

The modal now has a named `h1`, a named conversation region, and explicit header, voice, conversation, and composer grid rows. The header and private controls wrap at narrow widths, including long library labels; controls keep a 44 CSS-pixel minimum. Small text and the composer placeholder use darker contrast tokens. Sign-in inputs and the composer boundary use a unified green-gray border measured at 3.35:1 against white. The mobile layout uses dynamic viewport sizing and safe-area padding for the header and composer, while the footer stays inside the modal in the measured normal and idle text-resize states. At crowded large-text sizes the conversation retains a `4rem` minimum row and the dialog can also scroll as a whole, keeping messages and composer actions reachable. Touch-only clients omit the desktop keyboard-shortcut hint; the visible input label and Send action remain. Focus-visible styling remains visible in forced colors, and decorative listening motion is opt-in under `prefers-reduced-motion: no-preference`.

The conversation trail now scrolls within the pane that actually owns scrolling. While the modal is open, that is `#assistant-workspace-content`; in the inline view, it is the bounded message list. New replies follow the tail only when the reader was already there. When older messages are being read, the visible message anchor and scroll position are restored after the next reply. “Jump to latest” and the trail keyboard scroll keys act on the active pane without scrolling the page or moving the voice controls. See [app.js](../server/backend/app/ui/access/app.js), [index.html](../server/backend/app/ui/access/index.html), and [styles.css](../server/backend/app/ui/access/styles.css).

The selected-source story editor also has a native, collapsed **View original wording** disclosure for each proposed chapter. It reuses the existing volatile pre-generation text, keeps the proposal editable and preserves explicit review/Save. Its 44px disclosure retains the browser's open/closed marker. See the [story editor contract](SELECTED_SOURCE_STORY_UI.md); this is distinct from the saved-story refinement screen's existing comparison.

## Generated-browser evidence

An explicit language change can now resume the same idle private conversation after a fresh session, membership, capability, list and exact-thread read. Only server-confirmed text history returns; previous result cards, media and audio do not. An unsent draft survives only when no newer typing has replaced it. Account/library changes, a manual conversation selection, missing permission and late responses discard the superseded resume intent. This is an in-memory language-change convenience, not background execution or automatic submission. The nine-case generated locale-resume browser regression covers successful resumption, an explicit next turn, newer typing, permission loss, pending work and superseded success/failure responses.

The final design journey used the private-workspace ASGI bridge, a synthetic same-origin browser route, generated account/chat data, and generated placeholder SVG thumbnails only for fixture thumbnail requests that returned 404. No household media, model, Windows host, or microphone was used. The private `final-locale-design/result.json` receipt records these measured states:

| View | Page width | Dialog | Composer footer | Minimum sampled small-text contrast | Enabled control minimum height |
| --- | ---: | --- | --- | ---: | ---: |
| Desktop, 1280 × 900 | 1280 px; no horizontal overflow | 1120 × 852 px, within viewport | Bottom at 875 px; 17.6 px padding | 5.33:1 | 44 px |
| Phone, 390 × 844 | 390 px; no horizontal overflow | 390 × 844 px | Bottom at viewport edge; 12 px padding | 5.33:1 | 44 px |
| Phone, 320 × 720, 150% root text | 320 px; no horizontal overflow | 320 × 720 px | Bottom at viewport edge; 18 px padding | 5.33:1 | 44 px |
| Phone, 320 × 720, 200% root text | 320 px; no horizontal overflow | 320 × 720 px | Bottom at viewport edge; 24 px padding | 5.33:1 | 44 px |

The companion private `final-locale-design/run.log` records PASS for the native dialog name/heading, keyboard focus and Escape return, two explicit typed follow-ups in one private conversation, and reduced-motion/forced-colors focus checks. The forced-colors computed focus outline was solid and 3 px. The 150% and 200% states enlarge the root font size. They are text-resize checks, not browser zoom or device-scale-factor tests. The final receipt lists sign-in, library, conversation, forced-colors and generated paused-voice styling screenshots. Sign-in and the library also passed 320px/200% root-text reflow. The generated paused layout retained a 128px conversation pane and keyboard-reachable typing/Send actions without microphone access.

The private `final-locale-turn_trail/run.log` reports PASS for the eight-turn Chinese trail at 390 px with 150% root text, for the actual modal scroll pane and older-message position preservation, for “Jump to latest” and keyboard scrolling, and for English localization, narrow layout, lazy restoration, draft preservation, and no automatic replay. It also records delayed-response and account-scope protections.

The final affected journeys passed against generated, scoped data:

| Journey | Result |
| --- | --- |
| Assistant search, `final-locale-search` | 8 checkpoints; joint person/text search, date refinement, ordered results and GET-only recovery |
| Private workspace, `final-locale-workspace` | 17 checkpoints; creation, history, preferences, refinements and scope protection |
| Selected frames to story, `final-locale-story` | 19 checkpoints; ordered handoff, paging, explicit saves, undo and permission refusal |
| Voice session, `final-locale-voice_session` | Passed; foreground Start/Pause/End, reply, transcript review, interruption and scoped cleanup |
| Turn trail, `final-locale-turn_trail` | Passed; inline and modal scroll owners, anchor preservation, restoration and late-response protection |
| Explicit language change, `final-locale-locale_resume` | 9 cases passed; authorized history/draft resume, no automatic send or capture, late-response and scope protection |
| Selected-source proposal review, `story-original-phone-final` | 17 checkpoints passed; original/proposal distinction, keyboard disclosure, enlarged phone reflow, cancel/source-change clearing and explicit save |
| UI overlay builder/router | 12 tests passed; exact source-only asset binding |

After integrating locale resumption, the affected design, workspace, search, voice-session, turn-trail and nine-case locale journeys all passed again. The final design journey checks listening-state CSS under both reduced-motion settings without requesting a microphone. Node 22.17.0, Python 3.12.12 and Playwright 1.55.0 were used. Detailed generated screenshots, request logs and private receipts are retained outside Git; this document deliberately does not link to developer-local artifacts.

During the trail-test update, an older fixture assumption expected private capabilities to load eagerly and allowed a turn while account restoration was still blocking the UI. The fixture was corrected to preserve the existing restoration gate; the trail-r6 run then passed with that gate intact. This was a stale test expectation, not authorization to bypass the application’s account-restoration behavior.

## Acceptance boundary

These artifacts establish source and generated local-browser evidence only. They do not establish Windows deployment, service behavior, physical-device layout, real microphone consent/capture, or family acceptance. The final checks above cover the changed source and its generated journeys. Safari, Firefox, actual browser zoom, production Core Web Vitals and physical microphone/speaker behavior were not evaluated in this increment. No Windows deployment is claimed here.
