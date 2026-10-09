"""Synthetic queue and encoder failure contracts; no GPU required."""
from contextlib import closing
import json
import sys
import unittest
from unittest.mock import patch
import test_home_library as fixture
import prepare_home_catalog as prep
import prepare_home_library as lib

class EncoderBatchTests(unittest.TestCase):
    setUp=fixture.LibraryTests.setUp
    guard=fixture.LibraryTests.guard
    item=fixture.LibraryTests.item
    create=fixture.LibraryTests.create
    run_job=fixture.LibraryTests.run_job

    def test_nonzero_child_exit_has_distinct_reason(self):
        with self.assertRaises(prep.PreparationError) as caught:
            prep.run_process([sys.executable,'-c','import sys;sys.exit(7)'],
                             self.root,self.budget)
        self.assertEqual(caught.exception.reason,'child_failed')

    def test_video_queue_resume_does_not_prepare_photos_or_reencode_ready_video(self):
        self.create()
        result=self.run_job(kind='video')
        self.assertEqual(result['run_status'],'video_queue_drained')
        self.assertEqual(result['progress']['new_ready'],1)
        self.assertEqual(result['progress']['ready_rechecked'],0)
        self.assertEqual(result['progress']['phase'],'complete')
        self.assertFalse(result['queue_drained'])
        self.assertEqual(self.item(101)['status'],'pending')
        self.assertEqual(self.item(102)['status'],'ready')
        observed=[]
        verify=prep.verify_ready
        def track(*args,**kwargs):
            observed.append(lib.status(self.job)['progress'].copy())
            return verify(*args,**kwargs)
        with patch.object(prep,'prepare_one',side_effect=AssertionError('duplicate encoding')):
            with patch.object(prep,'verify_ready',side_effect=track):
                resumed=self.run_job(kind='video')
        self.assertEqual(resumed['ready'],1)
        self.assertEqual(resumed['progress']['new_ready'],0)
        self.assertEqual(resumed['progress']['ready_rechecked'],1)
        self.assertEqual(resumed['progress']['position'],1)
        self.assertEqual(resumed['progress']['phase'],'complete')
        self.assertEqual(observed[-1]['phase'],'ready_recheck')
        self.assertEqual(observed[-1]['asset_id'],102)
        self.assertTrue(self.run_job()['verified_complete'])

    def test_gpu_encode_failure_stops_queue_without_silent_cpu_fallback(self):
        lib.create(self.db,self.sources,self.job,self.ffmpeg,self.ffprobe,self.base,2,
                   self.budget,encoder='h264_nvenc',gpu=1)
        job=lib.load_job(self.job)
        self.assertEqual(job['encoder'],{'name':'h264_nvenc','gpu':1})
        real=prep.run_process;calls=[]
        def run(args,*a,**kw):
            if 'h264_nvenc' in args:
                calls.append(args);raise prep.PreparationError()
            return real(args,*a,**kw)
        with patch.object(prep,'run_process',side_effect=run):
            result=self.run_job(kind='video')
        self.assertEqual(result['run_status'],'nvenc_encode_failed')
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][calls[0].index('-gpu')+1],'1')
        self.assertEqual(self.item(102)['status'],'working')
        self.assertEqual(self.item(101)['status'],'pending')
        self.assertEqual(result['ready'],0)

    def test_bad_source_decode_after_nvenc_failure_is_recorded_and_queue_continues(self):
        lib.create(self.db,self.sources,self.job,self.ffmpeg,self.ffprobe,self.base,2,
                   self.budget,encoder='h264_nvenc',gpu=1)
        real=prep.run_process;diagnostics=[]
        def run(args,*a,**kw):
            if 'h264_nvenc' in args:raise prep.PreparationError('child_failed')
            if '-f' in args and 'null' in args:
                diagnostics.append(args)
                raise prep.PreparationError('child_failed')
            return real(args,*a,**kw)
        with patch.object(prep,'run_process',side_effect=run):
            result=self.run_job(kind='video')
        self.assertEqual(len(diagnostics),1)
        self.assertIn('setpts=N/(30*TB)',diagnostics[0])
        self.assertEqual(result['run_status'],'video_queue_drained')
        self.assertEqual(self.item(102)['status'],'error')
        self.assertEqual(self.item(102)['reason'],'source_decode_failed')
        self.assertEqual(self.item(101)['status'],'pending')

    def test_nvenc_failure_with_decodable_source_still_stops(self):
        lib.create(self.db,self.sources,self.job,self.ffmpeg,self.ffprobe,self.base,2,
                   self.budget,encoder='h264_nvenc',gpu=1)
        real=prep.run_process;diagnostics=[]
        def run(args,*a,**kw):
            if 'h264_nvenc' in args:raise prep.PreparationError('child_failed')
            if '-f' in args and 'null' in args:
                diagnostics.append(args)
                return b''
            return real(args,*a,**kw)
        with patch.object(prep,'run_process',side_effect=run):
            result=self.run_job(kind='video')
        self.assertEqual(len(diagnostics),1)
        self.assertEqual(result['run_status'],'nvenc_encode_failed')
        self.assertEqual(self.item(102)['status'],'working')

    def test_encoder_settings_are_pinned_and_invalid_selection_cannot_create_job(self):
        for encoder,gpu in [('auto',0),('h264_nvenc',True),('h264_nvenc',-1),('libx264',1)]:
            with self.assertRaises(ValueError):
                lib.create(self.db,self.sources,self.job,self.ffmpeg,self.ffprobe,self.base,2,
                           self.budget,encoder=encoder,gpu=gpu)
            self.assertFalse(self.job.exists())
        self.create()
        p=self.job/'job.json';data=json.loads(p.read_text());data['encoder']['name']='h264_nvenc';p.write_text(json.dumps(data))
        with self.assertRaises(ValueError):lib.load_job(self.job)

    def test_invalid_kind_cannot_modify_checkpoint(self):
        self.create();before=(self.job/'state.sqlite').read_bytes()
        with self.assertRaises(ValueError):self.run_job(kind='everything')
        self.assertEqual((self.job/'state.sqlite').read_bytes(),before)

if __name__=='__main__':unittest.main()
