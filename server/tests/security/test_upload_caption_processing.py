"""Synthetic receipt-selected captioning; no models, network or real media."""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
import json
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))
import test_upload_processing_release as release_fixture
from app.access.runtime import ExistingDatabase
from app.access.original_deletions import OriginalDeletionJournal
from app.access.upload_caption_processing import (CaptionProcessingRefused,
    inspect_released_captions, process_released_caption_task)

GOOD = {'text': 'EN: A red cup rests on a wooden table.\n\nZH-CN: 一个红色杯子放在木桌上。',
        'model': 'qwen3-vl-http|bilingual-en-zh-cn',
        'model_version': 'bilingual-v1', 'quality_tier': 'balanced'}
NOW = release_fixture.promotion_fixture.NOW


class UploadCaptionProcessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): release_fixture.UploadProcessingReleaseTests.setUpClass()

    @classmethod
    def tearDownClass(cls): release_fixture.UploadProcessingReleaseTests.tearDownClass()

    def setUp(self):
        base = release_fixture.UploadProcessingReleaseTests()
        base.setUp(); self.addCleanup(base.doCleanups)
        self.f = base.fixture
        self.release = base.release()
        self.task_id = next(r['task_id'] for r in self.release['released_tasks'] if r['type'] == 'caption')
        self.asset_id = base.asset_id
        self.factory = ExistingDatabase(self.f.path.resolve())
        self.scope = dict(release_plan_id=self.release['plan_id'],
            operator_account_id=self.f.owner_id, library_id='family-a')
        self.generate = Mock(return_value=dict(GOOD))

    def rows(self, sql, args=()): return self.f.rows(sql, args)
    def mutate(self, sql, args=()): self.f.mutate(sql, args)

    def run_task(self, **changes):
        args = dict(self.scope, task_id=self.task_id, originals_root=self.f.originals,
                    generate=self.generate, clock=lambda: NOW)
        args.update(changes)
        return process_released_caption_task(self.factory, **args)

    def state(self):
        return tuple(self.rows('SELECT state,retry_count,last_error FROM tasks WHERE id=?', (self.task_id,))[0])

    def test_preflight_is_metadata_only_and_does_not_claim(self):
        before = [tuple(r) for r in self.rows('SELECT * FROM tasks')]
        with patch('app.access.upload_caption_processing._source_bytes', side_effect=AssertionError('No media IO')):
            result = inspect_released_captions(self.factory, **self.scope,
                task_ids=[self.task_id], clock=lambda: NOW)
        self.assertFalse(result['activated'])
        self.assertEqual(result['items'][0]['state'], 'pending')
        self.assertEqual(before, [tuple(r) for r in self.rows('SELECT * FROM tasks')])
        self.generate.assert_not_called()

    def test_only_selected_caption_is_finished_and_original_is_unchanged(self):
        source = Path(self.rows('SELECT path FROM assets WHERE id=?', (self.asset_id,))[0][0])
        before = source.read_bytes()
        other = [tuple(r) for r in self.rows('SELECT id,type,state,payload_json FROM tasks WHERE id!=?', (self.task_id,))]
        result = self.run_task()
        self.assertEqual(result['outcome'], 'generated')
        self.assertEqual(self.generate.call_args.args, (before, 'image/png'))
        self.assertEqual(self.state(), ('finished', 0, None))
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(other, [tuple(r) for r in self.rows('SELECT id,type,state,payload_json FROM tasks WHERE id!=?', (self.task_id,))])
        self.assertEqual(tuple(self.rows('SELECT text,user_edited,model_version FROM captions WHERE asset_id=?', (self.asset_id,))[0]),
                         (GOOD['text'], 0, 'bilingual-v1'))
        self.assertEqual(self.rows('SELECT caption_processed,caption_variant_count FROM assets WHERE id=?', (self.asset_id,))[0][0:2], (1, 1))

    def test_completed_task_is_never_reprocessed(self):
        self.run_task(); self.generate.reset_mock()
        with self.assertRaisesRegex(CaptionProcessingRefused, 'task_not_pending'): self.run_task()
        self.generate.assert_not_called()
        self.assertEqual(len(self.rows('SELECT 1 FROM captions WHERE asset_id=?', (self.asset_id,))), 1)

    def test_failed_task_is_never_reset(self):
        self.mutate("UPDATE tasks SET state='failed',retry_count=3,last_error='old_failure' WHERE id=?", (self.task_id,))
        with self.assertRaisesRegex(CaptionProcessingRefused, 'task_not_pending'): self.run_task()
        self.assertEqual(self.state(), ('failed', 3, 'old_failure'))
        self.generate.assert_not_called()

    def test_foreign_task_and_non_caption_starter_are_refused(self):
        non_caption = next(r['task_id'] for r in self.release['released_tasks'] if r['type'] != 'caption')
        for identifier in (999999, non_caption):
            with self.subTest(identifier=identifier), self.assertRaisesRegex(CaptionProcessingRefused, 'task_outside_release'):
                self.run_task(task_id=identifier)
        self.generate.assert_not_called()
        self.assertEqual(self.state()[0], 'pending')

    def test_receipt_tampering_refuses_before_claim(self):
        self.mutate("UPDATE access_provisioning_receipts SET receipt='{}' WHERE plan_id=?", (self.release['plan_id'],))
        with self.assertRaisesRegex(CaptionProcessingRefused, 'release_receipt_invalid'): self.run_task()
        self.generate.assert_not_called()
        self.assertEqual(self.state()[0], 'pending')

    def test_scope_revocation_before_claim_refuses_without_inference(self):
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id='family-a'", (self.f.member_id,))
        with self.assertRaisesRegex(CaptionProcessingRefused, 'scope_changed'): self.run_task()
        self.generate.assert_not_called()
        self.assertEqual(self.state()[0], 'pending')

    def test_revocation_during_inference_discards_result(self):
        def revoke(*_):
            self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id='family-a'", (self.f.member_id,))
            return dict(GOOD)
        self.generate.side_effect = revoke
        result = self.run_task()
        self.assertEqual(result['error_code'], 'scope_changed')
        self.assertEqual(self.state()[0], 'failed')
        self.assertEqual(len(self.rows('SELECT 1 FROM captions WHERE asset_id=?', (self.asset_id,))), 0)

    def test_member_caption_arriving_during_inference_is_preserved(self):
        def edit(*_):
            self.mutate("INSERT INTO captions(asset_id,text,model,user_edited,superseded) VALUES(?,'family original','member',1,0)", (self.asset_id,))
            return dict(GOOD)
        self.generate.side_effect = edit
        result = self.run_task()
        self.assertEqual(result['outcome'], 'existing_preserved')
        self.assertEqual([r[0] for r in self.rows('SELECT text FROM captions WHERE asset_id=?', (self.asset_id,))], ['family original'])
        self.assertEqual(self.state()[0], 'finished')

    def test_existing_caption_needs_no_model_call(self):
        self.mutate("INSERT INTO captions(asset_id,text,model,user_edited,superseded) VALUES(?,'family original','member',1,0)", (self.asset_id,))
        result = self.run_task()
        self.assertEqual(result['outcome'], 'existing_preserved')
        self.generate.assert_not_called()
        self.assertEqual(self.state()[0], 'finished')

    def test_source_change_during_inference_is_not_published(self):
        source = Path(self.rows('SELECT path FROM assets WHERE id=?', (self.asset_id,))[0][0])
        def change(*_):
            source.write_bytes(b'changed source')
            return dict(GOOD)
        self.generate.side_effect = change
        result = self.run_task()
        self.assertEqual(result['error_code'], 'source_changed')
        self.assertEqual(self.state()[0], 'failed')
        self.assertEqual(len(self.rows('SELECT 1 FROM captions WHERE asset_id=?', (self.asset_id,))), 0)

    def test_provider_failure_is_sanitized_and_backed_off(self):
        self.generate.side_effect = RuntimeError('private-host private-caption token=secret')
        result = self.run_task()
        self.assertEqual(result['state'], 'pending')
        self.assertEqual(result['error_code'], 'generation_failed')
        self.assertNotIn('secret', json.dumps(result))
        self.assertEqual(self.state(), ('pending', 1, 'generation_failed'))
        self.assertEqual(self.rows('SELECT scheduled_at FROM tasks WHERE id=?', (self.task_id,))[0][0],
                         datetime.fromtimestamp(NOW+60, timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
        with self.assertRaisesRegex(CaptionProcessingRefused, 'task_not_due'): self.run_task()

    def test_invalid_callback_output_fails_without_caption(self):
        self.generate.return_value = dict(GOOD, text='unvalidated private output')
        result = self.run_task()
        self.assertEqual(result['error_code'], 'caption_policy_rejected')
        self.assertEqual(self.state()[0], 'failed')
        self.assertEqual(len(self.rows('SELECT 1 FROM captions WHERE asset_id=?', (self.asset_id,))), 0)

    def test_cancel_during_inference_does_not_publish(self):
        def cancel(*_):
            self.mutate('UPDATE tasks SET cancel_requested=1 WHERE id=?', (self.task_id,))
            return dict(GOOD)
        self.generate.side_effect = cancel
        self.run_task()
        self.assertEqual(len(self.rows('SELECT 1 FROM captions WHERE asset_id=?', (self.asset_id,))), 0)
        self.assertEqual(self.rows('SELECT cancel_requested FROM tasks WHERE id=?', (self.task_id,))[0][0], 1)

    def test_foreign_claim_is_never_overwritten(self):
        def foreign(*_):
            self.mutate("UPDATE tasks SET last_error='foreign-claim' WHERE id=?", (self.task_id,))
            return dict(GOOD)
        self.generate.side_effect = foreign
        with self.assertRaisesRegex(CaptionProcessingRefused, 'claim_changed'): self.run_task()
        self.assertEqual(self.state(), ('running', 0, 'foreign-claim'))

    def test_configured_bound_journal_is_preserved(self):
        journal = OriginalDeletionJournal.initialize(self.f.root/'caption-journal.sqlite', str(uuid.uuid4()), format_version=3)
        with self.f.connection() as db: journal.bind(db)
        self.factory = replace(self.factory, original_deletions=journal)
        self.assertEqual(self.run_task()['outcome'], 'generated')
        with replace(self.factory, read_only=True)() as db: journal.assert_current(db)

    def test_stale_journal_after_inference_blocks_all_final_writes(self):
        class Journal:
            stale = False
            def assert_current(inner, _db):
                if inner.stale: raise RuntimeError('private journal failure')
        journal = Journal(); self.factory = replace(self.factory, original_deletions=journal)
        def stale(*_): journal.stale = True; return dict(GOOD)
        self.generate.side_effect = stale
        with self.assertRaises(Exception): self.run_task()
        self.assertEqual(len(self.rows('SELECT 1 FROM captions WHERE asset_id=?', (self.asset_id,))), 0)
        self.assertEqual(self.state()[0], 'running')

    def test_stop_before_claim_is_inert_and_stop_before_commit_discards(self):
        with self.assertRaisesRegex(CaptionProcessingRefused, 'stop_requested'):
            self.run_task(should_stop=lambda: True)
        self.generate.assert_not_called()
        calls = [False]
        def stop_after(*_): calls[0] = True; return dict(GOOD)
        self.generate.side_effect = stop_after
        result = self.run_task(should_stop=lambda: calls[0])
        self.assertEqual(result['error_code'], 'stop_requested')
        self.assertEqual(self.state()[0], 'failed')
