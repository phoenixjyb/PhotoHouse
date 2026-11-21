"""Real protected grouping proposal route with generated multi-seed vectors."""
from pathlib import Path
import importlib.util
import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tests/security')]
import test_memory_group_routes as route
import test_visual_vector_loader as vectors

@unittest.skipUnless(importlib.util.find_spec('photohouse_vector_kernel'),'native vector module not built')
class NativeVisualRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):route.MemoryGroupRouteTests.setUpClass()
    @classmethod
    def tearDownClass(cls):route.MemoryGroupRouteTests.tearDownClass()
    def setUp(self):
        self.route=route.MemoryGroupRouteTests();self.route.setUp();self.addCleanup(self.route.doCleanups)
        self.env=patch.dict(os.environ,PHOTOHOUSE_VISUAL_ENGINE='rust');self.env.start();self.addCleanup(self.env.stop)
        self.route.install_vectors()
        with self.route.f.connection()as db:
            changed=db.execute("UPDATE assets SET hash_sha256=?,taken_at=?,mime='image/jpeg',status='active' WHERE id=103",('4'*64,'2026-01-01T10:30:00+08:00'))
            self.assertEqual(changed.rowcount,1)
            self.assertIsNotNone(db.execute("SELECT 1 FROM access_asset_libraries WHERE asset_id=103 AND library_id='family-a'").fetchone())
            helper=SimpleNamespace(db=db,root=self.route.root)
            vectors.VisualVectorLoaderTests.add_vector(helper,103,(1.0,0.0));db.commit()

    def test_multiseed_route_matches_reference_and_does_not_save_or_leak(self):
        from app.access.vector_acceleration import visual_backend
        native=visual_backend();original=native.best_seed;body={'asset_ids':'101,102','excluded_asset_ids':''}
        with patch.dict(os.environ,PHOTOHOUSE_VISUAL_ENGINE='python'):expected=self.route.request('POST','/memory-groups/proposals',body)
        self.route.f.trace.clear()
        with patch.object(native,'best_seed',wraps=original)as called:actual=self.route.request('POST','/memory-groups/proposals',body)
        self.assertEqual(actual.status_code,200,actual.text);self.assertEqual(actual.json(),expected.json());called.assert_called()
        self.assertEqual([x['id']for x in actual.json()['items']],['103']);self.assertEqual(actual.json()['items'][0]['matched_seed_asset_id'],'101');self.assertTrue(actual.json()['needs_review'])
        self.assertNotIn(str(self.route.root),actual.text);self.assertNotIn('synthetic-space',actual.text)
        self.assertFalse(any(sql.lstrip().upper().startswith(('INSERT','UPDATE','DELETE'))for sql in self.route.f.trace))

    def test_excluded_stale_and_unauthorized_photos_do_not_reach_native_scoring(self):
        from app.access.vector_acceleration import visual_backend
        native=visual_backend()
        with patch.object(native,'best_seed',side_effect=AssertionError('ineligible scoring')):
            excluded=self.route.request('POST','/memory-groups/proposals',{'asset_ids':'101,102','excluded_asset_ids':'103'})
            self.assertEqual(excluded.status_code,200,excluded.text);self.assertEqual(excluded.json()['items'],[])
            self.route.f.mutate("UPDATE assets SET taken_at='2026-01-03T10:30:00+08:00' WHERE id=103")
            stale=self.route.request('POST','/memory-groups/proposals',{'asset_ids':'101,102','excluded_asset_ids':''})
            self.assertEqual(stale.status_code,200,stale.text);self.assertEqual(stale.json()['items'],[])
            denied=self.route.request('POST','/memory-groups/proposals',{'asset_ids':'101,201','excluded_asset_ids':''})
            self.assertEqual(denied.status_code,401)
if __name__=='__main__':unittest.main()
