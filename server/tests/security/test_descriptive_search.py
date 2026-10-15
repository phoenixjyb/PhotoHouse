"""Descriptive v3 search keeps hard filters and literal text authoritative."""
from contextlib import closing, contextmanager
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "security"))

from app.access import discovery as d  # noqa: E402
from app.access.assistant_search import SearchPlan, SearchRuntime  # noqa: E402
from app.access.discovery_provider import MemoryIndexProvider, ReviewedFace  # noqa: E402
from app.access.discovery_transport import DiscoveryRuntime  # noqa: E402
from app.access.service import AccessService  # noqa: E402
from app.access.transport import AccessRuntime  # noqa: E402
from phone_discovery_fixture import NOW, TOKEN, create, reviewed  # noqa: E402


class DescriptiveSearchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="descriptive-search-")
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "synthetic.sqlite"
        with closing(sqlite3.connect(self.database)) as db, db:
            create(db)
            db.executescript("""
                CREATE TABLE access_stories (
                    id TEXT PRIMARY KEY, asset_id INTEGER NOT NULL, library_id TEXT NOT NULL,
                    author_id TEXT NOT NULL, revision INTEGER NOT NULL, title TEXT NOT NULL,
                    text TEXT NOT NULL, updated_at INTEGER NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0);
            """)
            db.execute("UPDATE assets SET taken_at='2026-01-02' WHERE id IN (101,102)")
            db.execute("UPDATE captions SET text='A red shirt.' WHERE id=1")
            db.execute("UPDATE captions SET text='红色衬衫在海边。' WHERE id=2")
            db.execute("INSERT INTO captions VALUES(5,102,'A red shirt near the water.',0,0)")
            db.executemany("""INSERT INTO access_stories
                (id,asset_id,library_id,author_id,revision,title,text,updated_at,deleted)
                VALUES(?,?,?,?,?,?,?,?,0)""", [
                    ('note-101', 101, 'family-a', 'one', 1, 'Family day',
                     "By the sea. Grandma's birthday.", NOW),
                    ('note-102', 102, 'family-a', 'one', 1, 'Family day',
                     "By the sea. Grandma's birthday.", NOW),
                    ('note-103', 103, 'family-a', 'one', 1, 'Family day',
                     'A family picnic.', NOW),
                ])
            # Asset 102 is deliberately a reviewed-person video candidate so
            # only the media hard filter excludes it from the image-only case.
            db.execute("INSERT INTO face_detections VALUES(6,102,301,'manual')")
            db.commit()
            base = reviewed(AccessService(db, clock=lambda: NOW))
            self.index = replace(base, assignments=base.assignments +
                                 (ReviewedFace('6', '102', '301'),))

        self.access = AccessRuntime(self.connection, "https://photohouse.example.test",
                                    clock=lambda: NOW)
        self.discovery = DiscoveryRuntime(self.access, MemoryIndexProvider((self.index,)),
                                          d.ReadBudget())
        self.v3 = SearchRuntime(self.discovery, search_version=3)
        self.binding = self.entities(self.v3)['binding']

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.database, timeout=.25)
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
        finally:
            db.close()

    def entities(self, runtime):
        return runtime.call('entities', TOKEN, 'family-a', lambda: False,
                            {'words': '示例儿童'})

    def query(self, filters, *, binding=None, runtime=None):
        return (runtime or self.v3).call('search', TOKEN, 'family-a', lambda: False, {
            'binding': self.binding if binding is None else binding,
            'filters': filters, 'page': 1, 'page_size': 20,
        })

    def description(self):
        return {'version': 1, 'concepts': [
            {'surface': '穿红色衣服', 'alternatives': ['wearing red', 'red shirt', '红色衬衫']},
            {'surface': '靠近水边', 'alternatives': ['by the sea', 'by the water', '海边']},
        ]}

    def test_descriptive_and_exact_text_match_inside_hard_people_date_media_gates(self):
        common = {
            'people': {'ids': ['301'], 'match': 'all'},
            'date': {'from': '2026-01-01', 'to': '2026-12-31'},
            'descriptive': self.description(),
        }
        broad_media = self.query({**common, 'media': ['image', 'video']})
        self.assertEqual([item['id'] for item in broad_media['items']], ['101', '102'])

        image_only = self.query({**common, 'media': ['image']})
        self.assertEqual([item['id'] for item in image_only['items']], ['101'])
        self.assertEqual(image_only['items'][0]['match_reasons'][0],
                         {'source': 'reviewed_person', 'source_id': '301'})
        self.assertIn({'source': 'capture_date', 'value': '2026-01-02'},
                      image_only['items'][0]['match_reasons'])
        self.assertTrue(all(set(reason) <= {'source', 'source_id', 'revision', 'value'}
                            for reason in image_only['items'][0]['match_reasons']))

        wrong_exact_phrase = self.query({**common, 'media': ['image'], 'text': "Grandma's wedding"})
        self.assertEqual(wrong_exact_phrase['items'], [])
        exact_phrase = self.query({**common, 'media': ['image'], 'text': "Grandma's birthday"})
        self.assertEqual([item['id'] for item in exact_phrase['items']], ['101'])

    def test_people_and_capture_date_filters_remain_hard_constraints(self):
        base = {'media': ['image'], 'descriptive': self.description()}
        selected_adult = self.query({**base, 'people': {'ids': ['302'], 'match': 'all'}})
        self.assertEqual([item['id'] for item in selected_adult['items']], ['103'])

        capture_year = self.query({**base, 'media': ['image', 'video'],
                                   'date': {'from': '2026-01-01', 'to': '2026-12-31'}})
        self.assertEqual([item['id'] for item in capture_year['items']], ['101', '102'])
        old_capture_year = self.query({**base, 'media': ['image', 'video'],
                                       'date': {'from': '2025-01-01', 'to': '2025-12-31'}})
        self.assertEqual([item['id'] for item in old_capture_year['items']], ['103'])

    def test_v2_refuses_descriptive_and_v3_presentation_identifies_its_version(self):
        with self.assertRaises(d.DiscoveryInvalid):
            SearchPlan(2, {'descriptive': self.description()})
        with self.assertRaises(d.DiscoveryInvalid):
            self.query({'descriptive': self.description()}, runtime=SearchRuntime(self.discovery))

        presentation = self.v3.call('presentation', TOKEN, 'family-a', lambda: False, {})
        self.assertEqual(presentation['version'], 3)
        self.assertTrue(self.v3.descriptive_enabled)
        self.assertFalse(SearchRuntime(self.discovery).descriptive_enabled)

    def test_media_only_search_keeps_unindexed_assets_and_existing_id_order(self):
        partial = replace(self.index,
            indexed_ids=tuple(aid for aid in self.index.indexed_ids if aid != '102'),
            assignments=tuple(face for face in self.index.assignments if face.asset_id != '102'),
            regions=tuple(pair for pair in self.index.regions if pair[0] != '102'))
        discovery = replace(self.discovery, provider=MemoryIndexProvider((partial,)))
        v3 = SearchRuntime(discovery, search_version=3)
        binding = self.entities(v3)['binding']
        found = self.query({'media': ['image', 'video']}, runtime=v3, binding=binding)
        self.assertEqual([item['id'] for item in found['items']], ['103', '102', '101'])

    def test_caption_edit_and_photo_note_revocation_invalidate_bound_results(self):
        filters = {'media': ['image'], 'descriptive': self.description()}
        old_binding = self.binding
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE captions SET text='An updated red shirt.' WHERE id=1")
        with self.assertRaises(d.DiscoveryChanged):
            self.query(filters, binding=old_binding)

        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            base = reviewed(AccessService(db, clock=lambda: NOW))
            self.discovery = DiscoveryRuntime(self.access, MemoryIndexProvider((replace(
                base, assignments=base.assignments + (ReviewedFace('6', '102', '301'),)),)),
                self.discovery.budget)
            self.v3 = SearchRuntime(self.discovery, search_version=3)

        refreshed_binding = self.entities(self.v3)['binding']
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE access_stories SET deleted=1 WHERE id='note-101'")
        with self.assertRaises(d.DiscoveryChanged):
            self.query(filters, binding=refreshed_binding)


if __name__ == '__main__':
    unittest.main()
