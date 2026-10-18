"""Synthetic review admission, refreshed scope and guarded kinship integration."""
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict, replace
import io
import json
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'scripts'), str(ROOT/'tests/security')]
from app.access import discovery as d
from app.access.assistant_search import AssistantSearchReads
from app.access.discovery_index import index as load_index, DiscoveryIndexRefused
from app.access.discovery_provider import (MemoryIndexProvider, ProjectedIndex, RefreshingPlaceIndex,
    RefreshingPeopleIndex, ReviewedPlace, RegionRule, ReviewedFace)
from app.access.service import AccessService, AccessDenied
from app.access.kinship import KinshipGraph
from phone_discovery_fixture import create, reviewed, TOKEN, OTHER, NOW
from test_assistant_kinship import assistant_graph
import prepare_reviewed_people_index as tool
from prepare_access_discovery_index import Refused


class RefreshingPeopleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.path = self.root/'fixture.sqlite'
        self.db = create(sqlite3.connect(self.path)); self.addCleanup(self.db.close)
        self.db.executescript('''ALTER TABLE assets ADD COLUMN gps_lat REAL;
            ALTER TABLE assets ADD COLUMN gps_lon REAL;
            CREATE TABLE persons(id INTEGER PRIMARY KEY,display_name TEXT,updated_at TEXT);
            CREATE TABLE access_person_libraries(person_id INTEGER PRIMARY KEY,library_id TEXT,creator_id TEXT,revision INTEGER);
            INSERT INTO persons VALUES(301,'Sample Child / 示例儿童',NULL),(302,'Sample Adult / 示例成人',NULL);
            INSERT INTO access_person_libraries VALUES(301,'family-a','two',1),(302,'family-a','two',1);
            CREATE TABLE access_stories(id TEXT,asset_id INTEGER,library_id TEXT,title TEXT,text TEXT,deleted INTEGER,revision INTEGER,author_id TEXT,updated_at INTEGER);
            UPDATE assets SET gps_lat=0,gps_lon=0 WHERE id IN (101,103);
        '''); self.db.commit()
        self.access = AccessService(self.db, clock=lambda: NOW)
        old = reviewed(self.access)
        self.base = RefreshingPlaceIndex(old.library_id, '1', old.scope_ids, old.scope_ids,
            '0'*64, enabled=('date','locations','media'), places=old.places,
            region_rules=(RegionRule('601',-1,-1,1,1),))
        self.review = dict(base_index_digest=d.digest(asdict(self.base)),library_id='family-a', source_digest='0'*64,
            indexed_ids=[], enabled=list(tool.ENABLED),
            people=[{key:value for key,value in asdict(p).items() if key!='library_id'} for p in old.people],
            assignments=[asdict(f) for f in old.assignments], pinned_ids=list(old.pinned_ids),
            places=[], regions=[], source_fields={})
        self.review=json.loads(json.dumps(self.review))
        self.index, self.envelope = tool.derive(self.db,self.base,'family-a','2',self.review,inspect=True)

    def service(self, index=None, *, assistant=False, budget=None):
        return (AssistantSearchReads if assistant else d.DiscoveryReads)(self.access,
            MemoryIndexProvider((index or self.index,)), budget or d.ReadBudget())

    def change(self, sql, params=()): self.db.execute(sql,params); self.db.commit()

    def facets(self, service=None): return (service or self.service()).facets(TOKEN,'family-a')

    def test_raw_face_volume_cannot_consume_reviewed_query_budget_or_change_matches(self):
        self.db.executemany('INSERT INTO face_detections VALUES(?,?,?,?)',
            [(i,102,301,'dnn') for i in range(1000,4000)])
        self.db.commit()
        # 4 assets + 4 coordinates + 3 reviewed faces + 2 catalog rows +
        # 3 current captions fit. The 3,000 unreviewed rows are never read.
        service=self.service(assistant=True,budget=d.ReadBudget(rows=20))
        facets=self.facets(service)
        self.assertEqual({i['id']:i['asset_count'] for i in facets['items']},{'301':2,'302':1})
        result=service.search(TOKEN,'family-a',binding=facets['binding'],filters={'text':'home'})
        self.assertEqual([a['id'] for a in result['items']],['101'])

    def test_legacy_and_static_artifact_bytes_keep_original_schema(self):
        legacy=reviewed(self.access)
        # Retain nested frozen dataclasses; asdict is for serialization only.
        projected=ProjectedIndex(**{key:getattr(legacy,key) for key in legacy.__dataclass_fields__})
        for original in (legacy,projected,self.base):
            payload=d.packed(asdict(original))
            self.assertNotIn(b'catalog_digest',payload)
            self.assertEqual(load_index(payload,100000),original)

    def test_exact_review_roundtrip_and_two_pass_no_write(self):
        before=self.path.read_bytes()
        index,_=tool.derive(self.db,self.base,'family-a','2',self.envelope)
        self.assertEqual(index,self.index); self.assertEqual(load_index(d.packed(asdict(index)),100000),index)
        self.assertEqual(before,self.path.read_bytes())
        with self.assertRaises(Refused): tool.derive(self.db,self.base,'family-a','2',self.review)
        with self.assertRaises(DiscoveryIndexRefused): load_index(d.packed({'schema':1,'review':self.envelope}),100000)

    def test_cli_two_pass_output_is_private_read_only_and_not_overwritten(self):
        base=self.root/'base.json'; selection=self.root/'selection.json'
        inspection=self.root/'inspection.json'; approved=self.root/'approved.json'; target=self.root/'candidate.json'
        base.write_bytes(d.packed(asdict(self.base))); selection.write_bytes(d.packed(self.review))
        common=['--database',str(self.path),'--base-index',str(base),'--library','family-a','--revision','2']
        before=self.path.read_bytes()
        def run(review,out,*extra):
            stdout=io.StringIO(); stderr=io.StringIO()
            with redirect_stdout(stdout),redirect_stderr(stderr):
                code=tool.main(common+['--review',str(review),'--out',str(out),*extra])
            self.assertNotIn('private-path',stdout.getvalue()+stderr.getvalue())
            return code
        self.assertEqual(run(selection,inspection,'--inspect'),0)
        packet=json.loads(inspection.read_bytes()); self.assertEqual(packet['status'],'requires_explicit_review')
        self.assertEqual(stat.S_IMODE(inspection.stat().st_mode),0o600)
        self.assertEqual(run(inspection,target),2); self.assertFalse(target.exists())
        approved.write_bytes(d.packed(packet['review']))
        self.assertEqual(run(approved,target),0)
        self.assertEqual(load_index(target.read_bytes(),100000),self.index)
        original=target.read_bytes(); self.assertEqual(run(approved,target),2); self.assertEqual(target.read_bytes(),original)
        self.assertEqual(before,self.path.read_bytes())

    def test_changed_base_rules_cannot_reuse_approved_review(self):
        changed=replace(self.base,region_rules=(RegionRule('601',-2,-2,2,2),))
        with self.assertRaises(Refused): tool.derive(self.db,changed,'family-a','2',self.envelope)
        with self.assertRaises(Refused): tool.derive(self.db,changed,'family-a','2',self.review,inspect=True)

    def test_current_upload_text_dates_and_places_without_new_identity_approval(self):
        service=self.service(assistant=True); old=self.facets(service)
        self.change("INSERT INTO assets VALUES(104,'private-path','active','image/jpeg',8,8,NULL,'2027-01-02',0,0)")
        self.change("INSERT INTO access_asset_libraries VALUES(104,'family-a')")
        self.change("INSERT INTO captions VALUES(10,104,'Picnic by the sea',0,0)")
        self.change("INSERT INTO face_detections VALUES(10,104,301,'manual')")
        fresh=self.facets(service)
        self.assertEqual(fresh['catalog_assets'],5); self.assertNotEqual(old['binding'],fresh['binding'])
        self.assertEqual({i['id']:i['asset_count'] for i in fresh['items']},{'301':2,'302':1})
        result=service.search(TOKEN,'family-a',binding=fresh['binding'],filters={'text':'picnic'})
        self.assertEqual([a['id'] for a in result['items']],['104'])
        self.assertEqual(self.service().facets(TOKEN,'family-a',facet='locations')['items'][0]['asset_count'],3)
        with self.assertRaises(d.DiscoveryChanged): service.search(TOKEN,'family-a',binding=old['binding'],filters={})

    def test_joint_people_match_all_uses_only_reviewed_faces(self):
        service=self.service(); binding=self.facets(service)['binding']
        result=service.search(TOKEN,'family-a',binding=binding,filters={'people':{'ids':['301','302'],'match':'all'}})
        self.assertEqual([a['id'] for a in result['items']],['103'])
        result=service.search(TOKEN,'family-a',binding=binding,filters={'people':{'ids':['301'],'match':'any'}})
        self.assertEqual({a['id'] for a in result['items']},{'101','103'})

    def test_current_catalog_and_assignment_withdrawals_fail_closed(self):
        changes=[("UPDATE persons SET display_name='Changed' WHERE id=301",()),
            ("UPDATE access_person_libraries SET library_id='family-b' WHERE person_id=301",()),
            ("DELETE FROM access_person_libraries WHERE person_id=301",()),
            ("DELETE FROM persons WHERE id=301",()),
            ("UPDATE face_detections SET label_source='dnn' WHERE id=1",()),
            ("UPDATE face_detections SET person_id=302 WHERE id=1",()),
            ("DELETE FROM face_detections WHERE id=1",()),
            ("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101",()),
            ("UPDATE assets SET status='hidden' WHERE id=101",())]
        backup=sqlite3.connect(':memory:'); self.addCleanup(backup.close); self.db.backup(backup)
        for sql,params in changes:
            with self.subTest(sql=sql):
                self.change(sql,params)
                try:
                    with self.assertRaises(d.DiscoveryChanged): self.facets()
                finally: backup.backup(self.db)

    def test_catalog_bookkeeping_changes_bindings_without_admitting_new_faces(self):
        service=self.service(); old=self.facets(service)
        self.change("UPDATE persons SET updated_at='2026-10-17' WHERE id=301")
        self.change('UPDATE access_person_libraries SET revision=revision+1 WHERE person_id=301')
        fresh=self.facets(service)
        self.assertNotEqual(old['binding'],fresh['binding'])
        self.assertEqual({i['id']:i['asset_count'] for i in fresh['items']},{'301':2,'302':1})
        with self.assertRaises(d.DiscoveryChanged): service.search(TOKEN,'family-a',binding=old['binding'],filters={})

    def test_kinship_maps_explicit_id_label_and_cannot_bypass_catalog_admission(self):
        graph=KinshipGraph(assistant_graph())
        targets=graph.resolve('mother')
        self.assertEqual(graph.catalog_ids(targets,self.index.people),{'302'})
        result=self.service().search(TOKEN,'family-a',binding=self.facets()['binding'],
            filters={'people':{'ids':sorted(graph.catalog_ids(targets,self.index.people)), 'match':'all'}})
        self.assertEqual([a['id'] for a in result['items']],['103'])
        self.change("UPDATE persons SET display_name='Changed' WHERE id=302")
        with self.assertRaises(d.DiscoveryChanged): self.facets()

    def test_membership_is_checked_before_people_provider_or_catalog(self):
        class Never:
            def get(self,_): raise AssertionError('must not inspect provider')
        service=d.DiscoveryReads(self.access,Never(),d.ReadBudget())
        with self.assertRaises(AccessDenied): service.facets(OTHER,'family-a')
        self.change("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        with self.assertRaises(AccessDenied): service.facets(TOKEN,'family-a')

    def test_closed_policy_aliases_digest_and_budget_validation(self):
        good=self.index
        for candidate in (replace(good,refresh_policy='other'),replace(good,catalog_digest='x'),
                replace(good,people=()),replace(good,enabled=('people','media')),
                replace(good,indexed_ids=good.indexed_ids[:-1]),
                replace(good,region_rules=(RegionRule('601',1,0,-1,1),))):
            with self.subTest(candidate=candidate),self.assertRaises(d.DiscoveryInvalid):
                d.validate(candidate,'family-a',100000)
        with self.assertRaises(d.DiscoveryUnavailable): self.facets(self.service(budget=d.ReadBudget(index_bytes=1)))
        with self.assertRaises(d.DiscoveryUnavailable): self.facets(self.service(budget=d.ReadBudget(rows=2)))
        # The original refreshing-place contract still refuses people.
        with self.assertRaises(d.DiscoveryInvalid): d.validate(replace(self.base,enabled=tool.ENABLED),'family-a',100000)
        payload=asdict(good);payload['refresh_policy']='current-library-regions-v1'
        with self.assertRaises(DiscoveryIndexRefused): load_index(d.packed(payload),100000)
        payload=asdict(good);payload['catalog_digest']='bad'
        with self.assertRaises(DiscoveryIndexRefused): load_index(d.packed(payload),100000)

    def test_unreviewed_foreign_hidden_and_orphan_faces_never_admitted(self):
        for sql in ("INSERT INTO face_detections VALUES(20,102,302,'dnn')",
                "INSERT INTO face_detections VALUES(21,102,301,'manual')",
                "INSERT INTO face_detections VALUES(22,201,302,'manual')",
                "INSERT INTO face_detections VALUES(23,999,302,'manual')"):
            self.change(sql)
        self.assertEqual({i['id']:i['asset_count'] for i in self.facets()['items']},{'301':2,'302':1})
        # A name-only/orphan ID cannot be promoted by an operator review.
        self.change('DELETE FROM access_person_libraries WHERE person_id=301')
        with self.assertRaises(d.DiscoveryChanged): tool.derive(self.db,self.base,'family-a','2',self.review,inspect=True)

    def test_stale_review_refused_and_base_places_cannot_be_replaced(self):
        self.change("UPDATE assets SET taken_at='2027-02-03' WHERE id=102")
        with self.assertRaises(Refused): tool.derive(self.db,self.base,'family-a','2',self.envelope)
        with self.assertRaises(Refused): tool.derive(self.db,self.base,'family-b','2',self.envelope)
        bad=dict(self.envelope,places=[{'id':'999','label':'Injected'}])
        with self.assertRaises(Refused): tool.derive(self.db,self.base,'family-a','2',bad,inspect=True)


if __name__=='__main__': unittest.main()
