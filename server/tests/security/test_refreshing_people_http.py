"""Search-v2 turns over the refreshing reviewed identity layer (fictional data)."""
from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts'),str(ROOT/'tests/security')]
from app.access.discovery_provider import RefreshingPlaceIndex, RegionRule
import test_assistant_kinship as fixture_module
from app.access import discovery as d
from phone_discovery_fixture import SECOND
import prepare_reviewed_people_index as tool


class RefreshingPeopleHttpTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture_module.AssistantKinshipTests('runTest'); self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp(); f=self.fixture; old=f.index
        with closing(sqlite3.connect(f.database)) as db,db:
            db.executescript('''ALTER TABLE assets ADD COLUMN gps_lat REAL;
                ALTER TABLE assets ADD COLUMN gps_lon REAL;
                CREATE TABLE persons(id INTEGER PRIMARY KEY,display_name TEXT,updated_at TEXT);
                CREATE TABLE access_person_libraries(person_id INTEGER PRIMARY KEY,library_id TEXT,creator_id TEXT,revision INTEGER);
                INSERT INTO persons VALUES(301,'Sample Child / 示例儿童',NULL),(302,'Sample Adult / 示例成人',NULL);
                INSERT INTO access_person_libraries VALUES(301,'family-a','two',1),(302,'family-a','two',1);''')
            base=RefreshingPlaceIndex(old.library_id,'1',old.scope_ids,old.scope_ids,'0'*64,
                places=old.places,enabled=('date','locations','media'),
                region_rules=(RegionRule('601',-1,-1,1,1),))
            review=dict(base_index_digest=d.digest(asdict(base)),library_id=old.library_id,source_digest='0'*64,indexed_ids=[],
                enabled=list(tool.ENABLED),pinned_ids=list(old.pinned_ids),places=[],regions=[],source_fields={},
                people=[{k:v for k,v in asdict(p).items() if k!='library_id'} for p in old.people],
                assignments=[asdict(a) for a in old.assignments])
            candidate,_=tool.derive(db,base,'family-a','2',json.loads(json.dumps(review)),inspect=True)
        f.install(candidate)

    def test_chinese_english_and_mixed_people_kinship_and_text_remain_conjunctive(self):
        for words in ('找示例儿童和妈妈一起的照片',
                'find photos of Sample Child and mom',
                'find示例儿童和妈妈一起的photos'):
            with self.subTest(words=words):
                response=self.fixture.turn(words); self.assertEqual(response.status_code,200,response.text)
                body=response.json(); self.assertEqual(body['kind'],'results',body)
                self.assertEqual(body['filters']['people'],{'ids':['301','302'],'match':'all'})
                self.assertEqual([a['id'] for a in body['items']],['103'])
        response=self.fixture.turn('找妈妈包含“Example Park”的照片')
        self.assertEqual(response.status_code,200,response.text)
        body=response.json();self.assertEqual(body['kind'],'results',body)
        self.assertEqual([a['id'] for a in body['items']],['103'])
        self.assertIn('text',body['filters'])

    def test_catalog_changes_and_face_withdrawal_withhold_old_and_new_results(self):
        f=self.fixture;first=f.turn('找妈妈的照片').json();self.assertEqual(first['kind'],'results',first)
        f.mutate("UPDATE persons SET display_name='Changed' WHERE id=302")
        for words,context in [('介绍这些结果',first['context']),('找妈妈的照片',None)]:
            response=f.turn(words,context=context);self.assertEqual(response.status_code,409,response.text)
            self.assertNotIn('Sample Adult',response.text)

    def test_graph_withdrawal_and_selected_accounts_remain_separate_from_people_visibility(self):
        f=self.fixture;first=f.turn('找妈妈的照片').json()
        excluded=f.turn('找妈妈的照片',token=SECOND)
        self.assertEqual(excluded.status_code,200,excluded.text)
        self.assertEqual(excluded.json()['items'],[])
        f.kinship.graph=None
        stale=f.turn('介绍这些结果',context=first['context'])
        self.assertEqual(stale.status_code,409,stale.text)
        fresh=f.turn('找妈妈的照片')
        self.assertEqual(fresh.status_code,200,fresh.text)
        self.assertEqual(fresh.json()['items'],[])

    def test_new_text_upload_refreshes_without_claiming_unreviewed_person_assignment(self):
        f=self.fixture
        first=f.turn('找妈妈的照片').json()
        f.mutate("INSERT INTO assets VALUES(104,'private-upload','active','image/jpeg',8,8,NULL,'2026-10-17',0,0)")
        f.mutate("INSERT INTO access_asset_libraries VALUES(104,'family-a')")
        f.mutate("INSERT INTO captions VALUES(20,104,'new picnic',0,0)")
        f.mutate("INSERT INTO face_detections VALUES(20,104,302,'manual')")
        stale=f.turn('介绍这些结果',context=first['context'])
        self.assertEqual(stale.status_code,409,stale.text)
        people=f.turn('找妈妈的照片').json();self.assertEqual([a['id'] for a in people['items']],['103'])
        text=f.turn('找包含“new picnic”的照片').json()
        self.assertEqual(text['kind'],'results',text);self.assertEqual([a['id'] for a in text['items']],['104'])


if __name__=='__main__':unittest.main()
