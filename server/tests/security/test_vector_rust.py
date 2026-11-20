"""Generated-data contracts for the optional native byte-buffer boundary."""
from dataclasses import replace
import importlib.util
import math
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access import semantic_bulk_vectors as bulk
from app.access import vector_acceleration as acceleration
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
from app.access.visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256


def fixture():
    identity = VectorSpaceIdentity('a'*64, 'b'*64, 'fixture', 'fixture', 2, 'unit_l2')
    digest = identity_sha256(identity)
    vectors = ((1.0,-0.0), (0.6,0.8), (-1.0,0.0), (0.6,0.8))
    artifacts = tuple(ImmutableVectorArtifact(f'{i:064x}',str(i),'c'*64,'fixture',
        identity.artifact_sha256,identity.preprocessing_sha256,identity.vector_space_id,
        identity.model_version,2,'unit_l2',digest,f'image-vectors/{digest}/{i:064x}.npy',
        'd'*64,canonical_vector_checksum(v),1,'ready') for i,v in enumerate(vectors,1))
    return identity,artifacts,memoryview(b''.join(struct.pack('>2f',*v)for v in vectors))


class VectorEngineSelectionTests(unittest.TestCase):
    def test_default_never_imports_native_and_invalid_choice_refuses(self):
        with patch.dict(os.environ,{},clear=True),patch.object(acceleration.importlib,'import_module') as load:
            self.assertIsNone(acceleration.backend())
            load.assert_not_called()
        with patch.dict(os.environ,PHOTOHOUSE_VECTOR_ENGINE='auto'):
            with self.assertRaisesRegex(ValueError,'invalid_vector_engine'):
                acceleration.backend()

    def test_explicit_native_missing_or_wrong_identity_refuses(self):
        with patch.dict(os.environ,PHOTOHOUSE_VECTOR_ENGINE='rust'):
            with patch.object(acceleration.importlib,'import_module',side_effect=ImportError):
                with self.assertRaisesRegex(ValueError,'vector_kernel_unavailable'):
                    acceleration.backend()
            with patch.object(acceleration.importlib,'import_module',return_value=object()):
                with self.assertRaisesRegex(ValueError,'vector_kernel_identity_mismatch'):
                    acceleration.backend()


@unittest.skipUnless(importlib.util.find_spec('photohouse_vector_kernel'),'optional native kernel not built')
class NativeVectorTests(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,PHOTOHOUSE_VECTOR_ENGINE='rust');env.start();self.addCleanup(env.stop)
        self.native=acceleration.backend()

    def test_canonical_bytes_scores_ties_and_callback_counts(self):
        identity,artifacts,payload=fixture();results=[]
        for engine in ('python','rust'):
            checks=[]
            with patch.dict(os.environ,PHOTOHOUSE_VECTOR_ENGINE=engine),patch.object(bulk,'_CACHE_BLOCK_BYTES',32):
                matrix=bulk._canonical_matrix(payload,artifacts,identity,lambda:checks.append('cold'))
                snap=bulk.BulkVectorSnapshot(artifacts,identity,matrix)
                values=snap.rank((0.6,0.8),('4','2','1'),check=lambda:checks.append('rank'))
                results.append((matrix,values,checks))
        self.assertEqual(results[0],results[1]);self.assertEqual([x[0]for x in results[1][1]],['2','4','1'])
        self.assertEqual(results[1][2].count('cold'),5);self.assertEqual(results[1][2].count('rank'),5)

    def test_cancellation_keeps_original_exception_and_stops_on_same_row(self):
        identity,artifacts,payload=fixture();marker=LookupError('owned cancellation')
        for operation in ('cold','rank'):
            calls=0
            def check():
                nonlocal calls
                calls+=1
                if calls==3:raise marker
            matrix=bulk._canonical_matrix(payload,artifacts,identity,lambda:None)
            snap=bulk.BulkVectorSnapshot(artifacts,identity,matrix)
            with self.assertRaises(LookupError)as caught:
                if operation=='cold':
                    try:bulk._canonical_matrix(payload,artifacts,identity,check)
                    except bulk._CallbackFailure as e:raise e.error
                else:snap.rank((1.0,0.0),('4',),check=check)
            self.assertIs(caught.exception,marker);self.assertEqual(calls,3)

    def test_corrupt_checksum_and_norm_refuse_whole_batch(self):
        identity,artifacts,payload=fixture()
        bad=artifacts[:2]+(replace(artifacts[2],component_sha256='0'*64),)+artifacts[3:]
        with self.assertRaises(bulk.BulkVectorUnavailable):bulk._canonical_matrix(payload,bad,identity,lambda:None)
        bad=replace(artifacts[0],component_sha256=canonical_vector_checksum((0.2,0)))
        with self.assertRaises(bulk.BulkVectorUnavailable):
            bulk._canonical_matrix(memoryview(struct.pack('>2f',0.2,0)),(bad,),identity,lambda:None)

    def test_identity_mutation_inside_native_derivation_refuses(self):
        identity,artifacts,payload=fixture();native=self.native
        class Mutator:
            def canonicalize(self,*args):
                result=native.canonicalize(*args)
                object.__setattr__(identity,'model_version','changed')
                return result
        with patch.object(bulk,'_vector_backend',return_value=Mutator()):
            with self.assertRaises(bulk.BulkVectorUnavailable):bulk._canonical_matrix(payload,artifacts,identity,lambda:None)

    def test_rank_callback_time_generation_change_refuses(self):
        identity,artifacts,payload=fixture();calls=0
        snap=bulk.BulkVectorSnapshot(artifacts,identity,bulk._canonical_matrix(payload,artifacts,identity,lambda:None))
        def mutate():
            nonlocal calls
            calls+=1
            if calls==3:object.__setattr__(artifacts[0],'asset_id','99')
        with self.assertRaises(bulk.BulkVectorUnavailable):snap.rank((1.0,0.0),('1','2'),check=mutate)

    def test_buffer_caps_before_callback_and_exact_compensated_scores(self):
        calls=[]
        with self.assertRaises(ValueError):self.native.canonicalize(b'',4097,lambda i:calls.append(i))
        with self.assertRaises(ValueError):self.native.score(bytes(4*1024*1024+8),struct.pack('=d',1),1,lambda i:calls.append(i))
        self.assertEqual(calls,[])
        for values in ((1e16,1,-1e16),(1e-16,1,1e16),(2**-1074,2**-1074),(-0.0,0.0)):
            d=len(values);result=self.native.score(struct.pack(f'={d}d',*values),struct.pack(f'={d}d',*([1]*d)),d,lambda _:True)
            self.assertEqual(struct.pack('=d',result[0][1]),struct.pack('=d',math.fsum(values)))
        with self.assertRaisesRegex(OverflowError,'intermediate overflow in fsum'):
            self.native.score(struct.pack('=2d',1e308,1e308),struct.pack('=2d',1,1),2,lambda _:True)


if __name__=='__main__':unittest.main()
