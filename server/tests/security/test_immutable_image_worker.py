"""Real worker/journal transactions with synthetic decoder/provider children.

This suite needs no NumPy, Pillow, model, GPU or running service. A separate
subprocess dies after publication to exercise restart with the actual claim.
"""
import base64
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'backend')]
import run_approved_image_embed_worker as worker
from app.access.visual_candidates import VectorSpaceIdentity
from app.access.visual_vector_schema import create_visual_vector_schema
from app.access.visual_vector_publication import create_visual_publication_schema, VectorPublicationStore


def recipe():
    return {'schema': 'photohouse.image_preprocessing_recipe.v1',
            'source_digests': worker._receipt_sources(), 'input_profile': 'bounded_rgb_jpeg',
            'output_profile': 'float32_unit_l2',
            'package_versions': {n: 'synthetic' for n in
                ('open_clip_torch', 'torch', 'torchvision', 'Pillow', 'numpy')},
            'transforms': [{'type': 'Resize', 'size': [224], 'max_size': None,
                'interpolation': {'name': 'BICUBIC', 'value': 'bicubic'}, 'antialias': True},
                {'type': 'CenterCrop', 'size': [224, 224]}, {'type': '_convert_to_rgb'},
                {'type': 'ToTensor'}, {'type': 'Normalize', 'mean': [0.48, 0.46, 0.41],
                 'std': [0.27, 0.26, 0.28], 'inplace': False}]}


def receipt(args):
    observed = recipe()
    return {'identity_receipt_version': 1, 'checkpoint_sha256': args.checkpoint_sha256,
            'image_model': args.image_model, 'preprocessing_recipe': observed,
            'preprocessing_sha256': worker.recipe_sha256(observed), 'dimension': 512,
            'model_version': args.model_version, 'provider': 'open_clip',
            'effective_provider': 'open_clip', 'effective_device': 'cpu',
            'selected_physical_device': 'cpu', 'selected_gpu_uuid': None}


def raw_vector():
    header = repr({'descr': '<f4', 'fortran_order': False, 'shape': (512,)}).encode('ascii')
    header += b' ' * (-(10 + len(header) + 1) % 16) + b'\n'
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + struct.pack('<512f', 1., *([0.] * 511))


def fake_decode(source, stage, derived, deadline, stop_file):
    target = stage / '1024.jpg'
    target.write_bytes(b'synthetic decoder receipt input')
    return target


def fake_embed(image, stage, args, checkpoint, deadline):
    raw = raw_vector()
    (stage / 'vector.npy').write_bytes(raw)
    return SimpleNamespace(shape=(512,)), receipt(args), hashlib.sha256(raw).hexdigest()


class ImmutableImageWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='immutable-worker-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.originals = self.base / 'originals'; self.originals.mkdir()
        self.derived = self.base / 'derived'; self.derived.mkdir()
        self.source = self.originals / 'synthetic.png'
        self.source.write_bytes(base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg=='))
        self.checkpoint = self.base / 'checkpoint.bin'; self.checkpoint.write_bytes(b'synthetic model pin')
        self.database = self.base / 'catalog.sqlite'
        self.db = sqlite3.connect(self.database)
        self.addCleanup(self.db.close)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE alembic_version(version_num TEXT NOT NULL);
            INSERT INTO alembic_version VALUES ('a0c9d2e4f817');
            CREATE TABLE assets(id INTEGER PRIMARY KEY,path TEXT,file_size INTEGER,hash_sha256 TEXT,mime TEXT,status TEXT);
            CREATE TABLE access_uploads(asset_id INTEGER,state TEXT,sha256 TEXT,bytes INTEGER);
            CREATE TABLE access_asset_libraries(asset_id INTEGER,library_id TEXT);
            CREATE TABLE access_libraries(id TEXT,state TEXT);
            CREATE TABLE tasks(id INTEGER PRIMARY KEY,type TEXT,state TEXT,payload_json TEXT,
                retry_count INTEGER DEFAULT 0,cancel_requested INTEGER DEFAULT 0,scheduled_at TEXT,
                started_at TEXT,finished_at TEXT,last_error TEXT,priority INTEGER DEFAULT 80);
            CREATE TABLE embeddings(asset_id INTEGER,modality TEXT,model TEXT,dim INTEGER,
                storage_path TEXT,vector_checksum TEXT,device TEXT,model_version TEXT);
        ''')
        self.source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.db.execute('INSERT INTO assets VALUES (1,?,?,?,?,?)',
            (str(self.source), self.source.stat().st_size, self.source_hash, 'image/png', 'active'))
        self.db.execute("INSERT INTO access_uploads VALUES (1,'assigned',?,?)",
            (self.source_hash, self.source.stat().st_size))
        self.db.execute("INSERT INTO access_asset_libraries VALUES (1,'family')")
        self.db.execute("INSERT INTO access_libraries VALUES ('family','active')")
        self.db.execute("INSERT INTO tasks(id,type,state,payload_json) VALUES (1,'embed','pending',?)",
            ('{"asset_id":1,"modality":"image"}',))
        self.db.commit()
        self.args = SimpleNamespace(database=str(self.database), originals_root=str(self.originals),
            derived_root=str(self.derived), checkpoint=str(self.checkpoint),
            checkpoint_sha256=hashlib.sha256(self.checkpoint.read_bytes()).hexdigest(),
            image_model='clip-ViT-B-32', model_version='synthetic-v1', device='cpu',
            expected_gpu_uuid=None, stop_file=str(self.base / 'stop'), execute=True, once=True)
        self.args.immutable_vector_identity = VectorSpaceIdentity(
            artifact_sha256=self.args.checkpoint_sha256,
            preprocessing_sha256=worker.recipe_sha256(recipe()), vector_space_id='synthetic-v1',
            model_version=self.args.model_version, dimension=512, normalization='unit_l2')

    def install_synthetic_contract(self):
        create_visual_vector_schema(self.db)
        create_visual_publication_schema(self.db)
        self.db.commit()

    def state(self):
        return self.db.execute('SELECT state,started_at,retry_count FROM tasks WHERE id=1').fetchone()

    def run_worker(self):
        with patch.object(worker, '_run_bounded_decoder', side_effect=fake_decode), \
             patch.object(worker, '_run_embed_child', side_effect=fake_embed), \
             patch.object(worker, '_probe_provider', return_value=receipt(self.args)):
            return worker.run(self.args)

    def test_absent_optional_schema_refuses_before_provider_or_task_claim(self):
        with patch.object(worker, '_probe_provider') as provider, self.assertRaises(worker.Refused):
            worker.run(self.args)
        provider.assert_not_called()
        self.assertEqual(self.state(), ('pending', None, 0))
        self.assertFalse((self.derived / 'image-vectors').exists())

    def test_profile_mismatch_refuses_before_provider_or_claim(self):
        self.install_synthetic_contract()
        self.args.model_version = 'different-version'
        with patch.object(worker, '_probe_provider') as provider, self.assertRaises(worker.Refused):
            worker.run(self.args)
        provider.assert_not_called()
        self.assertEqual(self.state(), ('pending', None, 0))

    def test_opt_in_worker_publishes_immutable_record_and_finishes_exact_task(self):
        self.install_synthetic_contract()
        result = self.run_worker()
        self.assertEqual((result['completed'], result['recovered']), (1, 0))
        self.assertEqual(self.state()[0], 'finished')
        row = self.db.execute('SELECT source_sha256,artifact_sha256,preprocessing_sha256,relative_path '
                              'FROM image_vector_artifacts').fetchone()
        self.assertEqual(row[:3], (self.source_hash, self.args.checkpoint_sha256,
                                   self.args.immutable_vector_identity.preprocessing_sha256))
        self.assertEqual((self.derived / row[3]).read_bytes(), raw_vector())
        self.assertEqual(self.db.execute('SELECT state FROM image_vector_publications').fetchone(), ('committed',))
        self.assertEqual(self.db.execute('SELECT count(*) FROM embeddings').fetchone()[0], 0)
        self.assertFalse((self.derived / 'embeddings').exists())

    def test_post_prepare_failure_preserves_claim_and_restart_uses_no_provider(self):
        self.install_synthetic_contract()
        with patch.object(VectorPublicationStore, '_complete', side_effect=RuntimeError('synthetic interruption')), \
             patch.object(worker, 'record_failure') as retry, self.assertRaises(worker.PreparedVectorPublicationPending):
            self.run_worker()
        retry.assert_not_called()
        before = self.state()
        self.assertEqual(before[0], 'running')
        self.assertEqual(self.db.execute('SELECT state FROM image_vector_publications').fetchone(), ('prepared',))
        with patch.object(worker, '_probe_provider') as provider, \
             patch.object(worker, '_run_embed_child') as embed:
            result = worker.run(self.args)
        provider.assert_not_called(); embed.assert_not_called()
        self.assertEqual((result['attempted'], result['completed'], result['recovered']), (0, 1, 1))
        self.assertFalse(result['provider_activated'])
        self.assertEqual(self.state(), ('finished', before[1], before[2]))

    def test_source_change_blocks_recovery_and_preserves_pending_evidence(self):
        self.install_synthetic_contract()
        with patch.object(VectorPublicationStore, '_complete', side_effect=RuntimeError('synthetic interruption')), \
             self.assertRaises(worker.PreparedVectorPublicationPending):
            self.run_worker()
        before = self.state()
        self.source.write_bytes(b'changed original')
        with patch.object(worker, '_probe_provider') as provider, self.assertRaises(worker.PreparedVectorPublicationPending):
            worker.run(self.args)
        provider.assert_not_called()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.db.execute('SELECT count(*) FROM image_vector_artifacts').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT state FROM image_vector_publications').fetchone(), ('prepared',))

    def test_completed_profile_skips_duplicate_pending_task_without_reembedding(self):
        self.install_synthetic_contract()
        self.run_worker()
        before = self.state()
        self.db.execute("INSERT INTO tasks(id,type,state,payload_json) VALUES (2,'embed','pending',?)",
                        ('{"asset_id":1,"modality":"image"}',))
        self.db.commit()
        candidate = worker._claim_one(self.database, immutable_identity=self.args.immutable_vector_identity)
        self.assertIsNone(candidate)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.db.execute('SELECT state,started_at FROM tasks WHERE id=2').fetchone(),
                         ('pending', None))
        self.assertEqual(self.db.execute('SELECT count(*) FROM image_vector_artifacts').fetchone()[0], 1)

    def test_orphan_prepared_intent_blocks_new_claim_and_preserves_evidence(self):
        self.install_synthetic_contract()
        with patch.object(VectorPublicationStore, '_complete', side_effect=RuntimeError('synthetic interruption')), \
             self.assertRaises(worker.PreparedVectorPublicationPending):
            self.run_worker()
        # Simulate an external operator resetting the task. Recovery must not
        # invent a replacement claim or hide the earlier durable intent.
        self.db.execute("UPDATE tasks SET state='pending',started_at=NULL WHERE id=1")
        self.db.commit()
        before = self.state()
        with patch.object(worker, '_probe_provider') as provider, self.assertRaises(worker.PreparedVectorPublicationPending):
            worker.run(self.args)
        provider.assert_not_called()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.db.execute('SELECT state FROM image_vector_publications').fetchone(), ('prepared',))

    def test_running_claim_without_intent_requires_reconciliation_before_provider(self):
        self.install_synthetic_contract()
        worker._claim_one(self.database)
        before = self.state()
        with patch.object(worker, '_probe_provider') as provider, self.assertRaises(worker.PreparedVectorPublicationPending):
            worker.run(self.args)
        provider.assert_not_called()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.db.execute('SELECT count(*) FROM image_vector_publications').fetchone()[0], 0)

    def test_unreadable_journal_after_prepare_does_not_reset_claim(self):
        self.install_synthetic_contract()
        prepare = VectorPublicationStore.prepare
        def lose_connection(store, *args):
            prepare(store, *args)
            store.db.close()
            raise RuntimeError('synthetic connection loss after durable prepare')
        with patch.object(VectorPublicationStore, 'prepare', lose_connection), \
             patch.object(worker, 'record_failure') as retry, self.assertRaises(worker.PreparedVectorPublicationPending):
            self.run_worker()
        retry.assert_not_called()
        before = self.state()
        self.assertEqual(before[0], 'running')
        self.assertEqual(self.db.execute('SELECT state FROM image_vector_publications').fetchone(), ('prepared',))
        # No bytes were written: recovery preserves this evidence for an
        # operator rather than rerunning inference or inventing completion.
        with patch.object(worker, '_probe_provider') as provider, self.assertRaises(worker.PreparedVectorPublicationPending):
            worker.run(self.args)
        provider.assert_not_called()
        self.assertEqual(self.state(), before)

    def test_process_death_after_file_publication_recovers_original_claim(self):
        self.install_synthetic_contract()
        data = vars(self.args).copy()
        data['immutable_vector_identity'] = asdict(self.args.immutable_vector_identity)
        code = '''import json,os,sys
from pathlib import Path
from types import SimpleNamespace
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'scripts'),str(root/'backend'),str(root/'tests/security')]
import test_immutable_image_worker as fixture
import run_approved_image_embed_worker as worker
from app.access.visual_candidates import VectorSpaceIdentity
from app.access.visual_vector_publication import VectorPublicationStore
values=json.loads(sys.argv[2]);profile=VectorSpaceIdentity(**values.pop('immutable_vector_identity'))
args=SimpleNamespace(**values,immutable_vector_identity=profile)
worker._run_bounded_decoder=fixture.fake_decode;worker._run_embed_child=fixture.fake_embed
VectorPublicationStore._complete=lambda *_:os._exit(47)
candidate=worker._claim_one(Path(args.database))
worker._process_task(candidate,Path(args.database),Path(args.originals_root),Path(args.derived_root),args,
    Path(args.checkpoint),worker.identity(Path(args.checkpoint)),Path(args.stop_file))
'''
        child = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(ROOT), json.dumps(data)],
                               capture_output=True, timeout=30)
        self.assertEqual(child.returncode, 47, child.stderr.decode(errors='replace'))
        original_claim = self.state()
        self.assertEqual(original_claim[0], 'running')
        self.assertEqual(self.db.execute('SELECT state FROM image_vector_publications').fetchone(), ('prepared',))
        with patch.object(worker, '_probe_provider') as provider, \
             patch.object(worker, '_run_bounded_decoder') as decode:
            result = worker.run(self.args)
        provider.assert_not_called(); decode.assert_not_called()
        self.assertEqual(result['recovered'], 1)
        self.assertEqual(self.state(), ('finished', original_claim[1], original_claim[2]))


if __name__ == '__main__':
    unittest.main()
