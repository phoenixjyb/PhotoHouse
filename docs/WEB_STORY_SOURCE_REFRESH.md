# Refresh a new story's references

A reviewed new story can encounter a save conflict when its referenced memories
or observations change. The Web editor keeps the unfinished words and offers
**Refresh references / 刷新参考资料**. This is an explicit recovery action, not
another save or a request for generated prose.

## Author's flow

1. A definite create conflict keeps the draft and clears its failed submission.
2. Refresh the references for the same ordered moments, theme and language.
3. Review each chapter's current references. Previously selected references that
   are no longer eligible are removed; newly available references start unchecked.
4. Confirm **I reviewed the updated references for every chapter / 我已重新核对
   每一章的参考资料**, then save explicitly.

Changing a source choice or chapter arrangement clears that confirmation again.
The author can still change the refreshed choices before confirming. Leaving all
references unchecked remains a valid deliberate choice.

## Words, focus and pending work

Refresh retains the manually arranged chapters, chapter titles, narration and
story title. It renews the item evidence and selection revision; it does not copy
an original memory, invent a byline or overwrite text with a preview's prose.
The text fields stay mounted so typing, focus and Chinese input composition can
continue while the request is pending.

During refresh, actions that would replace the draft, reorder its moments,
change its theme or sources, start recording, or request title assistance are
unavailable. Both visible controls and retained callbacks enforce this boundary.
Ordinary title and paragraph editing remains available. Closing the workspace
invalidates the pending result; reopening requires an explicit retry.

## Failure and compatibility

A failed or malformed response retains the old evidence snapshot, layout and
words for another explicit refresh. The replacement preview must match the
current account, library, editor generation, exact draft, ordered moments, theme
and language. Stale completions cannot update a replacement editor. A current
access denial follows the existing protected-data clearing path.

After a successful refresh, the next save captures the revised source snapshot.
An uncertain save still retries its identical frozen body and mutation ID; it
does not refresh or silently submit a different story. Saved-story update
conflicts retain their existing recovery behavior. Legacy creates do not gain
the reviewed source profile automatically.

This uses the existing preview and `chapter_sources_v1` create contracts. It adds
no route, schema, model activation, audio retention or anonymous TV access.
Generated browser results belong in [the development record](DEVELOPMENT.md);
served Web delivery and family editing acceptance remain separate gates.
