"""Integrated reviewed-people and private kinship journeys (fictional only)."""
from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts'), str(ROOT / 'tests/security')]

from app.access.discovery_provider import RefreshingPlaceIndex, ReviewedFace, RegionRule
from app.access import discovery as d
import test_assistant_kinship as fixture_module
import prepare_reviewed_people_index as prepare
from phone_discovery_fixture import SECOND


def three_person_graph():
    """A fictional child, mother and father, each bound to a reviewed ID."""
    return {
        'schema': 1,
        'graph_id': 'fictional-three-person-graph',
        'revision': 'journey-one',
        'perspective_id': 'child',
        'scope': {'account_id': 'one', 'library_id': 'family-a'},
        'people': [
            {'id': 'child', 'name_en': 'Sample Child', 'name_zh': '示例儿童', 'aliases': [],
             'catalog_binding': {'person_id': '301', 'label': 'Sample Child / 示例儿童'}},
            {'id': 'mother', 'name_en': 'Sample Parent', 'name_zh': '示例家长',
             'aliases': ['Mom', '妈妈'],
             'catalog_binding': {'person_id': '302', 'label': 'Sample Adult / 示例成人'}},
            {'id': 'father', 'name_en': 'Sample Father', 'name_zh': '示例父亲', 'aliases': ['Dad', '爸爸'],
             'catalog_binding': {'person_id': '303', 'label': 'Sample Father / 示例父亲'}},
        ],
        'assertions': [
            {'id': 'child-mother', 'subject_id': 'child', 'relation': 'mother',
             'object_id': 'mother', 'source': 'user'},
            {'id': 'child-father', 'subject_id': 'child',
             'relation': 'father', 'object_id': 'father', 'source': 'user'},
        ],
    }


class ReviewedFamilySearchJourneys(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.AssistantKinshipTests('runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        f = self.fixture
        old = f.index
        with closing(sqlite3.connect(f.database)) as db, db:
            db.executescript('''
                ALTER TABLE assets ADD COLUMN gps_lat REAL;
                ALTER TABLE assets ADD COLUMN gps_lon REAL;
                CREATE TABLE persons(id INTEGER PRIMARY KEY,display_name TEXT,updated_at TEXT);
                CREATE TABLE access_person_libraries(person_id INTEGER PRIMARY KEY,library_id TEXT,creator_id TEXT,revision INTEGER);
                INSERT INTO persons VALUES
                    (301,'Sample Child / 示例儿童',NULL),
                    (302,'Sample Adult / 示例成人',NULL),
                    (303,'Sample Father / 示例父亲',NULL);
                INSERT INTO access_person_libraries VALUES
                    (301,'family-a','two',1),(302,'family-a','two',1),(303,'family-a','two',1);
                INSERT INTO assets VALUES(104,'fictional-upload','active','image/jpeg',8,8,NULL,'2026-05-05',0,0);
                INSERT INTO access_asset_libraries VALUES(104,'family-a');
                INSERT INTO face_detections VALUES
                    (6,103,303,'manual'),(7,104,301,'manual'),(8,104,302,'manual'),
                    (9,104,303,'manual'),(10,101,303,'dnn');
            ''')
            base = RefreshingPlaceIndex(old.library_id, '1', old.scope_ids, old.scope_ids,
                '0' * 64, places=old.places, enabled=('date', 'locations', 'media'),
                region_rules=(RegionRule('601', -1, -1, 1, 1),))
            reviewed_people = [
                {key: value for key, value in asdict(person).items() if key != 'library_id'}
                for person in old.people
            ]
            reviewed_people.append({'id': '303', 'label': 'Sample Father / 示例父亲',
                                    'aliases': [], 'allow_zero': False})
            assignments = [asdict(face) for face in old.assignments]
            assignments.extend(asdict(ReviewedFace(str(face_id), str(asset_id), str(person_id)))
                for face_id, asset_id, person_id in ((6, 103, 303), (7, 104, 301),
                                                       (8, 104, 302), (9, 104, 303)))
            review = dict(base_index_digest=d.digest(asdict(base)), library_id=old.library_id,
                source_digest='0' * 64, indexed_ids=[], enabled=list(prepare.ENABLED),
                pinned_ids=list(old.pinned_ids), places=[], regions=[], source_fields={},
                people=reviewed_people, assignments=assignments)
            candidate, _ = prepare.derive(db, base, 'family-a', '2',
                                          json.loads(json.dumps(review)), inspect=True)
        f.install(candidate)
        f.kinship.install(three_person_graph())

    def test_three_person_bilingual_queries_refine_by_capture_date_and_open_visible_result(self):
        f = self.fixture
        # Each phrase must resolve to exactly the same three reviewed catalog IDs.
        for words in (
            '找示例儿童、妈妈和爸爸一起的照片',
            'find Sample Child, mom, and dad together photos',
            'find示例儿童和妈妈和爸爸一起的photos',
        ):
            with self.subTest(words=words):
                response = f.turn(words)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(body['kind'], 'results', body)
                self.assertEqual(body['filters']['people'],
                                 {'ids': ['301', '302', '303'], 'match': 'all'})
                self.assertEqual([item['id'] for item in body['items']], ['104', '103'])

        first = f.turn('找示例儿童、妈妈和爸爸一起的照片').json()
        refined = f.turn('2025年', context=first['context'])
        self.assertEqual(refined.status_code, 200, refined.text)
        result = refined.json()
        self.assertEqual(result['kind'], 'results', result)
        self.assertEqual(result['filters'], {
            'media': ['image'],
            'people': {'ids': ['301', '302', '303'], 'match': 'all'},
            'date': {'from': '2025-01-01', 'to': '2025-12-31'},
        })
        self.assertEqual([item['id'] for item in result['items']], ['103'])
        self.assertEqual(result['items'][0]['match_reasons'], [
            {'source': 'reviewed_person', 'source_id': '301'},
            {'source': 'reviewed_person', 'source_id': '302'},
            {'source': 'reviewed_person', 'source_id': '303'},
            {'source': 'capture_date', 'value': '2025-12-01'},
        ])

        opened = f.turn('打开第一个', context=result['context'])
        self.assertEqual(opened.status_code, 200, opened.text)
        self.assertEqual(opened.json()['kind'], 'open', opened.json())
        self.assertEqual(opened.json()['effect'], {'type': 'open_asset', 'asset_id': '103'})

    def test_suppressed_reviewed_sample_cannot_be_returned_or_opened(self):
        f = self.fixture
        first = f.turn('找示例儿童、妈妈和爸爸一起的照片').json()
        self.assertEqual(first['kind'], 'results', first)
        f.mutate("UPDATE assets SET status='suppressed' WHERE id=104")
        for words, context in (('打开第一个', first['context']),
                               ('找示例儿童、妈妈和爸爸一起的照片', None)):
            response = f.turn(words, context=context)
            self.assertEqual(response.status_code, 409, response.text)
            self.assertNotIn('fictional-upload', response.text)
            self.assertNotIn('Sample Father', response.text)

    def test_unreviewed_face_and_graph_account_scope_do_not_expand_three_person_results(self):
        f = self.fixture
        father = f.turn('找爸爸的照片')
        self.assertEqual(father.status_code, 200, father.text)
        self.assertEqual([item['id'] for item in father.json()['items']], ['104', '103'])

        other_account = f.turn('找示例儿童、妈妈和爸爸一起的照片', token=SECOND)
        self.assertEqual(other_account.status_code, 200, other_account.text)
        self.assertNotEqual(other_account.json()['kind'], 'results', other_account.json())
        self.assertEqual(other_account.json()['items'], [])

        # Withdrawal of a reviewed assignment invalidates both old and fresh reads.
        context = f.turn('找示例儿童、妈妈和爸爸一起的照片').json()['context']
        f.mutate("UPDATE face_detections SET label_source='dnn' WHERE id=6")
        for words, old_context in (('介绍这些结果', context),
                                   ('找示例儿童、妈妈和爸爸一起的照片', None)):
            response = f.turn(words, context=old_context)
            self.assertEqual(response.status_code, 409, response.text)
            self.assertNotIn('Sample Father', response.text)
            self.assertNotIn('示例父亲', response.text)


if __name__ == '__main__':
    unittest.main()
