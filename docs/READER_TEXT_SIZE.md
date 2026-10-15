# Comfortable story and memoir reading

This is the next local source increment after the frozen v59 candidate. Its
phone source reserves v60; package publication and family-device acceptance
remain separate.

## Interaction

Story and memoir readers offer Smaller / Default / Larger (`较小 / 标准 / 较大`)
prose presets at 0.9, 1.0 and 1.25 times the existing text style. System font
scaling or browser zoom still applies. Controls have a named group, a selected
state and at least a 48 dp phone / 48 px Web target. Titles, source disclosures,
navigation, narration controls and contribution editors keep their usual style.

The choice stays local to the current open reader. Chapter/frame navigation and
child-story navigation within the same memoir keep the selection. Closing the
reader or changing its account, library or source binding resets the default;
there is no saved preference or automatic network request. Preset actions keep
the selected media, saved words, speech ownership and unsent contribution text.
They preserve the current reader and do not submit an edit.

The phone memoir reader keeps chapter navigation at the bottom and places
adjacent-story navigation in the scrolling story area. Both retain their existing
explicit actions and current-source guards. At 150% text, the generated reader
viewport gained about 125 dp in English and 94 dp in Chinese; the action targets
measure 48 dp. This is fixture geometry, not a measurement on the family phone.

Web font controls are optional during module initialization. An older partial
reader template without the new control still supports its original shelf and
narration actions. The generated compatibility journey retained all edition-shelf
assertions and completed with no browser errors or external requests.

## Qualification

Focused generated browser and API 36 emulator verification passed. The phone's
saved-story journey passed eight cases and its memoir journey passed two;
Kotlin main/instrumentation compilation and debug lint also passed. Chinese and
English renders were inspected at 150% text with the larger preset. The browser
checks exercise actual prose sizes, selected state, 48 px targets, retained
chapter/frame selection and reader scroll, unchanged titles, no preset request
or write, and a real editable memoir's unsent instruction draft. The separate
read-only community fixture stays read-only.

These are local generated checks, not a physical family's reading acceptance.
The complete integrated profiles and any remaining delivery gates are recorded
separately; this source increment does not replace or publish the frozen v59
archive or APK.
See [Development](DEVELOPMENT.md) for the final evidence and [Roadmap](ROADMAP.md)
for delivery and physical reading acceptance. The
[Chinese phone/Web trial](../clients/android/docs/PHONE_V60_TEST_GUIDE_ZH.md)
keeps these reader checks separate from the v59 voice and assistant trial.
