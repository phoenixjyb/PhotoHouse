# Android memoir citation search

中文摘要：回忆册的来源选择现可按故事、片段与回忆编号搜索，每页最多12项。跨页、筛选和切换语言不会改变已选来源的完整身份；失效来源仍可看见并移除。保存或语音助手忙碌期间，来源与衔接文字均不可编辑。原始回忆仍需主动点开。

The manual memoir editor searches its already loaded citation labels locally. Each result still carries the full story, story revision, chapter, and contribution identity. Search, expanding a chapter, paging, and changing display language never turn a row position into a citation.

The chooser matches story title, chapter label, and the source's displayed memory number. It shows at most 12 available citations on a page, reports the current range, total matches, available and selected counts, and selected citations outside the current page. Clearing or changing a search returns to page one.

Selected citations that no longer appear in the current catalog remain visible in a separate unavailable section and can be removed. Selection limits and save behavior remain owned by the existing editor/store contract. Search and paging controls and citation changes are disabled while a companion operation or a frozen save is active; event callbacks repeat the same guard.

Search only examines citation identity and story/chapter labels. It does not request original contribution text, derived text, or recordings. Original inspection remains an explicit action, and the existing inspector keeps original and derived material separate. Recording and speech playback coordination are unchanged.

The search text, page, and expanded groups reset when language, account, library, memoir, memoir revision, or child-story revision changes. The selected reference list is still keyed by exact citation identity.

## Focused Android checks

From `android/`:

```sh
./gradlew --offline --no-daemon :connected:compileDebugKotlin :connected:compileDebugAndroidTestKotlin
./gradlew --offline --no-daemon :connected:connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=dev.photohouse.connected.MemoryBookEditorialUiTest
```

The focused UI tests use synthetic catalog and contribution data. They cover search and 12-row paging, identity-bound selections across pages and language changes, removal of unavailable selections, frozen-save guards, metadata-only search, and Chinese and English layouts at 150% text scale. They do not exercise live services or establish release, device, or family acceptance.

## October 6 root integration evidence

- Base: `5e62fc509dbb6055a1d6cc917ba0986fcdd971ec` on `codex/phone-v29-candidate-20260929`.
- Root replaced direct StateFlow reads in composition with `collectAsState`, made the available count match distinct identities, and guarded transition text during pending/uncertain saves.
- Final focused emulator class: **7 tests, 0 failures/errors/skips** on the reused `emulator-5558` / Medium Phone API36. All APIs/media in these tests are synthetic.
- `:connected:lintDebug` passed. A test helper now constructs its stable synthetic reader audio coordinator outside composition; no lint suppression or new baseline was added.
- Root inspected Chinese and English chooser captures at 150% text. Search, wrapping counts and citation controls are visible; page navigation was exercised by the tests.
- No API/wire/store schema, release profile, version or TV changes. No release build, signature, OTA publication or physical device install is claimed by these checks.
- Frozen phone v42 remains the unchanged APK at SHA-256 `ee2bba169a89969ed1fe006e8ea1df3a21bce54080cadc5e9806aa2428129779`. This source change belongs to the next phone release and must not be substituted into the v42 publication scope.
