# Story name grounding reference data

The offline story grounder uses a bounded Wikidata singer-name roster under
[CC0](https://www.wikidata.org/wiki/Wikidata:Licensing), and a derived
character-pronunciation table from
[mozillazg/pinyin-data v0.15.0](https://github.com/mozillazg/pinyin-data/tree/v0.15.0)
under MIT. The full MIT notice is kept alongside the runtime data in
[`PINYIN-DATA-LICENSE.txt`](../server/backend/app/access/data/PINYIN-DATA-LICENSE.txt).
The [provenance record](../server/backend/app/access/data/story-grounding-provenance.json)
records successful public queries, transformations and hashes. No private story
was used as a query to build these generic public resources. Coverage is bounded;
a phonetic match is a reviewable spelling proposal, not proof of an event or identity.
