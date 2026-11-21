"""Exact multi-seed ranking and refusal checks for the optional Rust consumer."""
from dataclasses import replace
import importlib.util
import math
import os
from pathlib import Path
import random
import struct
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tests/security')]
from app.access import vector_acceleration as acceleration,visual_candidates as visual
import test_visual_candidates as base

class VisualSelectionTests(unittest.TestCase):
    def test_default_does_not_import_and_is_independent_of_bulk_engine(self):
        with patch.dict(os.environ,{'PHOTOHOUSE_VECTOR_ENGINE':'rust'},clear=True),patch.object(acceleration,'load_kernel',side_effect=AssertionError('unselected import')):
            self.assertIsNone(acceleration.visual_backend())
            self.assertEqual(base.rank([base.record('1',(1,0))],[base.record('2',(1,0))]).status,'ready')

    def test_missing_wrong_or_old_capability_and_unknown_selector_refuse(self):
        seed=base.record('1',(1,0));candidate=base.record('2',(1,0))
        old=SimpleNamespace(KERNEL_VERSION=1,POLICY_FINGERPRINT='canonical-f32-fsum-v1:4096:4194304')
        with patch.dict(os.environ,PHOTOHOUSE_VISUAL_ENGINE='rust'):
            for module in [old,SimpleNamespace(VISUAL_POLICY_FINGERPRINT='other'),SimpleNamespace(VISUAL_POLICY_FINGERPRINT='best-seed-fsum-v1:24:512:4096:4194304',best_seed=None)]:
                with patch.object(acceleration,'load_kernel',return_value=module):self.assertIs(base.rank([seed],[candidate]),visual.UNAVAILABLE)
            with patch.object(acceleration.importlib,'import_module',side_effect=ImportError):self.assertIs(base.rank([seed],[candidate]),visual.UNAVAILABLE)
        with patch.dict(os.environ,PHOTOHOUSE_VISUAL_ENGINE='auto'):self.assertIs(base.rank([seed],[candidate]),visual.UNAVAILABLE)

    def test_authorization_and_integrity_precede_native_import(self):
        seed=base.record('1',(1,0));candidate=base.record('2',(1,0))
        with patch.dict(os.environ,PHOTOHOUSE_VISUAL_ENGINE='rust'),patch.object(acceleration,'load_kernel',side_effect=AssertionError('early import'))as load:
            self.assertIs(base.rank([seed],[candidate],authorized_ids={'1'}),visual.UNAVAILABLE)
            self.assertIs(base.rank([seed],[replace(candidate,checksum_sha256='0'*64)]),visual.UNAVAILABLE)
            load.assert_not_called()

@unittest.skipUnless(importlib.util.find_spec('photohouse_vector_kernel'),'native vector module not built')
class NativeVisualTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,PHOTOHOUSE_VISUAL_ENGINE='rust');self.env.start();self.addCleanup(self.env.stop)
        self.native=acceleration.visual_backend()

    def test_random_full_results_match_with_shuffled_numeric_seed_ties(self):
        rng=random.Random(20261121)
        for dimension in [1,2,7,32,768]:
            identity=replace(base.IDENTITY,dimension=dimension)
            values=[]
            for _ in range(12):
                v=[rng.uniform(-1,1)for _ in range(dimension)];n=math.sqrt(math.fsum(x*x for x in v));values.append(tuple(x/n for x in v))
            seeds=[base.record(str(i),values[j],identity)for j,i in enumerate([19,2,11,3])]
            candidates=[base.record(str(i+100),values[i%12],identity)for i in range(32)]+[seeds[0]]
            with patch.dict(os.environ,PHOTOHOUSE_VISUAL_ENGINE='python'):expected=base.rank(seeds,candidates,expected_identity=identity)
            self.assertEqual(base.rank(seeds,candidates,expected_identity=identity),expected)
            self.assertEqual(base.rank(list(reversed(seeds)),list(reversed(candidates)),expected_identity=identity),expected)

    def test_single_seed_keeps_reference_scoring_after_capability_admission(self):
        with patch.object(self.native,'best_seed',side_effect=AssertionError('unprofitable single-seed bridge')):
            self.assertEqual(base.rank([base.record('1',(1,0))],[base.record('2',(1,0))]).status,'ready')

    def test_equal_and_negative_scores_choose_smallest_seed_then_candidate(self):
        seeds=[base.record('10',(1,0)),base.record('2',(1,0))]
        candidates=[base.record('11',(-1,0)),base.record('3',(-1,0))]
        result=base.rank(seeds,candidates)
        self.assertEqual([(x.asset_id,x.matched_seed_asset_id)for x in result.candidates],[('3','2'),('11','2')])
        self.assertEqual(base.rank(seeds,[]),visual.RankingResult('ready',()))

    def test_buffer_is_bounded_across_maximum_shape_and_complete_cohort(self):
        dimension=4096;identity=replace(base.IDENTITY,dimension=dimension);v=(1.0,)+(0.0,)*(dimension-1)
        seeds=[base.record(str(i),v,identity)for i in [10,2]]
        candidates=[base.record(str(i+100),v,identity)for i in range(512)]
        original=self.native.best_seed;sizes=[]
        def checked(data,queries,d,observe):
            sizes.append((len(data),len(queries)))
            return original(data,queries,d,observe)
        with patch.object(self.native,'best_seed',side_effect=checked):actual=base.rank(seeds,candidates,expected_identity=identity)
        self.assertEqual([x.asset_id for x in actual.candidates],[str(i)for i in range(100,120)])
        self.assertEqual(len(sizes),4);self.assertTrue(all(a<=4*1024**2 and b<=24*4096*8 for a,b in sizes))

    def test_direct_exact_sum_callback_order_and_original_exception(self):
        rows=[(1e16,1,-1e16),(1e-16,1,1e16)];data=b''.join(struct.pack('=3d',*r)for r in rows);queries=struct.pack('=6d',1,1,1,-1,-1,-1);seen=[]
        result=self.native.best_seed(data,queries,3,seen.append);self.assertEqual(seen,[0,1])
        for index,seed,score in result:
            expected=math.fsum(rows[index]);self.assertEqual(seed,0);self.assertEqual(struct.pack('=d',score),struct.pack('=d',expected))
        marker=LookupError('owned cancellation')
        def stop(index):raise marker
        with self.assertRaises(LookupError)as caught:self.native.best_seed(data,queries,3,stop)
        self.assertIs(caught.exception,marker)

    def test_native_caps_and_nonfinite_inputs_refuse_without_callback(self):
        seen=[]
        for data,queries,dimension in [(b'',b'',1),(b'',b'\0'*8,0),(b'',b'\0'*8,4097),(b'\0'*(513*8),b'\0'*8,1),(b'\0'*8,b'\0'*(25*8),1),(b'\0'*(4*1024**2+8),b'\0'*8,1)]:
            with self.assertRaises(ValueError):self.native.best_seed(data,queries,dimension,seen.append)
        self.assertEqual(seen,[])
        with self.assertRaises(ValueError):self.native.best_seed(struct.pack('=d',1),struct.pack('=d',math.inf),1,seen.append)
        self.assertEqual(seen,[])

    def test_group_temporal_buckets_never_score_ineligible_seed_pairs(self):
        from app.access import memory_grouping as grouping
        import test_memory_grouping as groups
        seeds=[groups.record('1',(1,0)),groups.record('2',(0,1)),groups.record('10',(0.6,0.8))]
        candidates=[groups.record('100',(0.8,0.6)),groups.record('101',(0.6,0.8)),
                    groups.record('102',(1,0)),groups.record('103',(-1,0)),groups.record('104',(0,1))]
        times={'1':'2026-05-01T10:00:00','2':'2026-05-01T12:00:00','10':'2026-05-01',
               '100':'2026-05-01T10:30:00','101':'2026-05-01T12:30:00','102':'2026-05-02',
               '103':'2026-05-01T10:30:00','104':'2026-05-01T12:30:00'}
        params=dict(times=times,exclusions=('104',),max_gap_seconds=3600,minimum_similarity=0.5)
        with patch.dict(os.environ,PHOTOHOUSE_VISUAL_ENGINE='python'):expected=groups.propose(seeds,candidates,**params)
        seed_bytes={struct.pack('=2d',*visual._canonical_components(r,groups.IDENTITY)):r.asset_id for r in seeds}
        row_bytes={struct.pack('=2d',*visual._canonical_components(r,groups.IDENTITY)):r.asset_id for r in candidates if r.asset_id in ['100','101','103']}
        allowed={'100':{'1','10'},'101':{'2','10'},'103':{'1','10'}};seen=[];original=self.native.best_seed
        def checked(data,queries,dimension,observe):
            query_ids={seed_bytes[queries[i:i+16]]for i in range(0,len(queries),16)}
            for i in range(0,len(data),16):
                candidate=row_bytes[data[i:i+16]];self.assertEqual(query_ids,allowed[candidate]);seen.append(candidate)
            return original(data,queries,dimension,observe)
        with patch.object(self.native,'best_seed',side_effect=checked):actual=groups.propose(seeds,candidates,**params)
        self.assertEqual(actual,expected);self.assertTrue(actual.candidates);self.assertCountEqual(seen,['100','101','103'])
        self.assertNotIn('102',[c.asset_id for c in actual.candidates]);self.assertNotIn('104',[c.asset_id for c in actual.candidates])

    def test_group_maximum_seed_cap_and_integrity_refusal_are_unchanged(self):
        import test_memory_grouping as groups
        seeds=[groups.record(str(i))for i in range(1,25)];candidates=[groups.record('100')]
        self.assertEqual(groups.propose(seeds,candidates).candidates,())
        with patch.object(acceleration,'load_kernel',side_effect=AssertionError('early import')):
            self.assertEqual(groups.propose(seeds,candidates,authorized_ids={'1'}).status,'unavailable')

    def test_bad_native_row_count_index_seed_and_nonfinite_scores_refuse(self):
        seed=base.record('1',(1,0));other=base.record('10',(1,0));candidate=base.record('2',(1,0))
        for value in [[],[(1,0,1.0)],[(False,0,1.0)],[(0,2,1.0)],[(0,0,math.nan)],[(0,0,'1')],[(0,0,1.0),(1,0,1.0)]]:
            with patch.object(self.native,'best_seed',return_value=value):self.assertIs(base.rank([seed,other],[candidate]),visual.UNAVAILABLE)

if __name__=='__main__':unittest.main()
