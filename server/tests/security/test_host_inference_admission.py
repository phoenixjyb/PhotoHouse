"""Generated-only host claim, crash retention and provider cleanup checks."""
import asyncio
from dataclasses import replace, astuple
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.app.access.host_inference_admission import (
    HostAdmissionError, HostCapacity, HostInferenceAdmission, HostResourceProfile,
    initialize_host_admission,
)
from backend.app.access.selected_story_process import process_launch_digest
from test_selected_story_native import launch_spec
import test_selected_story_process as fixtures
from test_selected_story_process import encoded_response
from test_selected_story_local import bundle, make_scope
from test_selected_story_process_lifecycle import worker_environment

OP='abcdefab-cdef-4abc-8def-abcdefabcdef'
OTHER='12345678-1234-4234-8234-123456789abc'
CLEAR='33333333-3333-4333-8333-333333333333'
GiB=1024**3


class HostFixture:
    def host(self, *, digest=None, enabled=True, clear=True):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name).resolve();os.chmod(root,0o700)
        initialize_host_admission(root,enabled=True)
        profile=HostResourceProfile('cpu',digest or 'a'*64,8*GiB,GiB)
        def probe():return HostCapacity('cpu',CLEAR,time.monotonic(),16*GiB,4*GiB,False)
        host=HostInferenceAdmission(root,profile,capacity_probe=probe,enabled=enabled)
        if clear:host.set_maintenance(False,clearance_id=CLEAR)
        return host

    def reason(self, reason, function, *args, **kwargs):
        with self.assertRaises(HostAdmissionError) as caught:function(*args,**kwargs)
        self.assertEqual(reason,caught.exception.reason)

    def other(self, host):
        return HostInferenceAdmission(host.directory,host.profile,capacity_probe=host.probe,enabled=True)


class HostAdmissionTests(HostFixture,unittest.TestCase):
    def test_disabled_and_fresh_store_are_closed(self):
        host=self.host(enabled=False,clear=False)
        self.reason('disabled',host.acquire,OP)
        host.enabled=True
        self.reason('maintenance',host.acquire,OP)
        self.reason('disabled',initialize_host_admission,host.directory)
        with self.assertRaises(HostAdmissionError):initialize_host_admission(host.directory,enabled=True)
        self.assertEqual({'host-story.sqlite3'},{p.name for p in host.directory.iterdir()})

    def test_exact_owner_releases_only_after_true_proof(self):
        host=self.host();permit=host.acquire(OP)
        self.reason('busy',self.other(host).acquire,OTHER)
        self.assertFalse(permit.finish(reconciled=False))
        with self.assertRaises(ValueError):permit.finish(reconciled=1)
        self.reason('busy',host.acquire,OTHER)
        self.assertTrue(permit.finish(reconciled=True))
        self.assertTrue(permit.finish(reconciled=True))
        self.assertTrue(self.other(host).acquire(OTHER).finish(reconciled=True))

    def test_maintenance_does_not_clear_active_or_stale_claim(self):
        host=self.host();permit=host.acquire(OP)
        host.set_maintenance(True)
        self.reason('maintenance',self.other(host).acquire,OTHER)
        self.reason('busy',host.set_maintenance,False,clearance_id=CLEAR)
        permit.finish(reconciled=True)
        self.reason('maintenance',host.acquire,OTHER)
        host.set_maintenance(False,clearance_id=CLEAR)
        self.assertTrue(host.acquire(OTHER).finish(reconciled=True))

    def test_missing_or_replaced_store_is_never_recreated(self):
        host=self.host();host.acquire(OP)
        old=host.path.with_suffix('.retained');host.path.rename(old)
        self.reason('unavailable',host.acquire,OTHER)
        self.assertFalse(host.path.exists())
        host.path.write_bytes(old.read_bytes());os.chmod(host.path,0o600)
        self.reason('unavailable',host.acquire,OTHER)

    def test_resource_probe_must_be_fresh_exact_clear_and_sufficient(self):
        host=self.host();sample=host.probe()
        changes=[{'external_busy':True},{'external_busy':1},{'resource_id':'gpu:'+OTHER},
                 {'clearance_id':OTHER},{'observed_monotonic':time.monotonic()-5},
                 {'observed_monotonic':time.monotonic()+5},{'observed_monotonic':float('nan')},
                 {'free_ram':GiB},{'free_disk':0},{'free_ram':True}]
        for change in changes:
            with self.subTest(change=change):
                host.probe=lambda:replace(sample,**change)
                self.reason('unavailable',host.acquire,OP)
        host.probe=lambda:object()
        self.reason('unavailable',host.acquire,OP)
        def failed():raise OSError('synthetic-private-detail')
        host.probe=failed
        self.reason('unavailable',host.acquire,OP)

    def test_locked_sqlite_returns_busy_without_a_claim(self):
        host=self.host()
        with closing(sqlite3.connect(host.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            self.reason('busy',host.acquire,OP)
            db.rollback()
        host.acquire(OP).finish(reconciled=True)

    def test_wrong_owner_cannot_release_claim(self):
        host=self.host();permit=host.acquire(OP)
        permit._owner=OTHER
        self.reason('unavailable',permit.finish,reconciled=True)
        self.reason('busy',self.other(host).acquire,OTHER)

    def test_nonprivate_or_symlink_storage_is_refused(self):
        host=self.host()
        if os.name=='nt':self.skipTest('POSIX permissions/symlink assertion; native ACL tested separately')
        os.chmod(host.directory,0o755)
        self.reason('unavailable',host.acquire,OP)
        os.chmod(host.directory,0o700)
        alias=host.directory/'alias';alias.symlink_to(host.path)
        self.reason('unavailable',HostInferenceAdmission(alias,host.profile,capacity_probe=host.probe,enabled=True).acquire,OP)

    def child(self, host, action):
        source=str(Path(__file__).resolve().parents[2])
        code=('import sys,os,time;sys.path.insert(0,'+repr(source)+');'
            'from backend.app.access.host_inference_admission import *;'
            f'p=HostResourceProfile("cpu","'+host.profile.launch_sha256+'",8*1024**3,1024**3);'
            f'h=HostInferenceAdmission({str(host.directory)!r},p,capacity_probe=lambda:HostCapacity("cpu",{CLEAR!r},time.monotonic(),16*1024**3,4*1024**3,False),enabled=True);'+action)
        return subprocess.run([sys.executable,'-I','-B','-c',code],env=worker_environment(),
                              cwd=host.directory,capture_output=True,text=True,timeout=10)

    def test_independent_process_refuses_an_existing_claim(self):
        host=self.host();permit=host.acquire(OP)
        code=f'\ntry:h.acquire({OTHER!r})\nexcept HostAdmissionError as e:print(e.reason)\n'
        result=self.child(host,code)
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertEqual('busy',result.stdout.strip())
        permit.finish(reconciled=True)

    def test_abrupt_child_exit_leaves_durable_claim_and_clearance_refuses(self):
        host=self.host()
        result=self.child(host,f'h.acquire({OP!r});os._exit(0)')
        self.assertEqual(0,result.returncode,result.stderr)
        self.reason('busy',self.other(host).acquire,OTHER)
        self.reason('busy',host.set_maintenance,False,clearance_id=CLEAR)
        with closing(sqlite3.connect(host.path)) as db:
            self.assertEqual(OP,db.execute('SELECT operation FROM claim').fetchone()[0])

    def test_invalid_profiles_and_operation_ids_refused(self):
        for args in [('gpu:0','a'*64,GiB,GiB),('cpu','a'*63,GiB,GiB),('cpu','a'*64,True,GiB)]:
            with self.assertRaises(ValueError):HostResourceProfile(*args)
        host=self.host()
        for op in ['',None,True,'not-an-operation']:
            with self.assertRaises(ValueError):host.acquire(op)
        with self.assertRaises(ValueError):host.set_maintenance(False,clearance_id='')


    def test_clearance_pins_launch_recipe_and_resource_thresholds(self):
        host=self.host()
        for profile in (replace(host.profile,launch_sha256='b'*64),
                        replace(host.profile,minimum_free_ram=9*GiB)):
            changed=HostInferenceAdmission(host.directory,profile,capacity_probe=host.probe,enabled=True)
            self.reason('unavailable',changed.acquire,OP)
        host.acquire(OP).finish(reconciled=True)

    def test_slow_probe_or_unknown_schema_is_unavailable(self):
        host=self.host();times=iter((10,11))
        host.clock=lambda:next(times)
        host.probe=lambda:HostCapacity('cpu',CLEAR,11,16*GiB,4*GiB,False)
        self.reason('unavailable',host.acquire,OP)
        host.clock=time.monotonic
        with closing(sqlite3.connect(host.path)) as db:
            db.execute('UPDATE control SET version=99');db.commit()
        self.reason('unavailable',host.acquire,OP)

    def test_gpu_identity_requires_and_checks_vram_capacity(self):
        host=self.host();profile=replace(host.profile,resource_id='gpu:'+OTHER,minimum_free_vram=2*GiB)
        host=HostInferenceAdmission(host.directory,profile,capacity_probe=lambda:HostCapacity(
            profile.resource_id,CLEAR,time.monotonic(),16*GiB,4*GiB,False),enabled=True)
        host.set_maintenance(False,clearance_id=CLEAR)
        self.reason('unavailable',host.acquire,OP)
        host.probe=lambda:HostCapacity(profile.resource_id,CLEAR,time.monotonic(),16*GiB,4*GiB,False,4*GiB)
        host.acquire(OP).finish(reconciled=True)


class HostProviderTests(HostFixture,unittest.IsolatedAsyncioTestCase):
    provider = fixtures.ProcessSelectedStoryTests.provider
    async def test_host_busy_creates_no_exchange_and_calls_no_kernel(self):
        digest=process_launch_digest(launch_spec(environment={'PATH':'/synthetic/bin'}))
        host=self.host(digest=digest);claim=host.acquire(OTHER)
        provider,kernel,factories=self.provider(host_admission=host)
        scope=make_scope()
        with patch('backend.app.access.selected_story_process.tempfile.mkdtemp') as mkdtemp:
            with self.assertRaises(HostAdmissionError) as caught:await provider.prepare(bundle(),scope)
            self.assertEqual('busy',caught.exception.reason)
            self.assertTrue(await provider.stop_and_reconcile(scope))
        mkdtemp.assert_not_called();self.assertEqual([],factories)
        claim.finish(reconciled=True)

    async def test_host_claim_retained_until_exchange_disposal_and_then_released(self):
        digest=process_launch_digest(launch_spec(environment={'PATH':'/synthetic/bin'}))
        host=self.host(digest=digest)
        def writer(env):
            from backend.app.access.selected_story_process import RESPONSE_ENV
            Path(env[RESPONSE_ENV]).write_bytes(encoded_response())
        provider,kernel,factories=self.provider(writer,host_admission=host)
        scope=make_scope();await provider.prepare(bundle(),scope)
        self.reason('busy',self.other(host).acquire,OTHER)
        with patch.object(provider,'_dispose',return_value=False):
            self.assertFalse(await provider.stop_and_reconcile(scope))
        self.reason('busy',self.other(host).acquire,OTHER)
        self.assertTrue(await provider.stop_and_reconcile(scope))
        host.acquire(OTHER).finish(reconciled=True)

    async def test_host_profile_must_match_exact_launch_recipe(self):
        host=self.host()
        with self.assertRaises(ValueError):self.provider(host_admission=host)


    async def test_cancelled_acquisition_is_retained_until_its_thread_settles(self):
        import threading
        digest=process_launch_digest(launch_spec(environment={'PATH':'/synthetic/bin'}))
        host=self.host(digest=digest);acquire=host.acquire
        entered=threading.Event();release=threading.Event()
        def blocked(operation):
            permit=acquire(operation);entered.set()
            if not release.wait(5):raise RuntimeError('Synthetic wait timed out')
            return permit
        provider,kernel,factories=self.provider(host_admission=host)
        scope=make_scope()
        with patch.object(host,'acquire',side_effect=blocked):
            task=asyncio.create_task(provider.prepare(bundle(),scope))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait,3))
                scope._invalidation.set();task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
                cleanup=asyncio.create_task(provider.stop_and_reconcile(scope))
                await asyncio.sleep(0.02)
                self.assertFalse(cleanup.done())
                self.reason('busy',self.other(host).acquire,OTHER)
            finally:release.set()
            self.assertTrue(await asyncio.wait_for(cleanup,3))
        self.assertEqual([],factories)
        host.acquire(OTHER).finish(reconciled=True)

    async def test_operation_busy_is_retryable_after_host_contention(self):
        from backend.app.access.selected_story_operations import DraftOperations, DraftOperationError
        from backend.app.access.inference_admission import InferenceAdmission
        from test_selected_story_operations import SyntheticSources, TOKEN_A, LIBRARY, request, REQUEST_ID
        digest=process_launch_digest(launch_spec(environment={'PATH':'/synthetic/bin'}))
        host=self.host(digest=digest);claim=host.acquire(OTHER)
        provider,kernel,factories=self.provider(host_admission=host)
        # Existing lifecycle fixtures use the legacy access import namespace.
        # Adapt their typed read results to this provider's canonical namespace.
        from backend.app.access.selected_story_operations import DraftPrincipal
        from backend.app.access.selected_story_snapshot import SourceSnapshot
        class Sources(SyntheticSources):
            def authenticate(self,*args):
                value=super().authenticate(*args)
                return DraftPrincipal(value.account_id,value.session_digest)
            def resolve(self,*args):return SourceSnapshot(*astuple(super().resolve(*args)))
        service=DraftOperations(Sources(),provider,InferenceAdmission())
        self.addAsyncCleanup(service.close)
        with self.assertRaises(DraftOperationError) as caught:
            await service.prepare(TOKEN_A,LIBRARY,request())
        self.assertEqual('busy',caught.exception.reason)
        record=service._records[('account-a',LIBRARY,REQUEST_ID)]
        self.assertEqual('retryable',record.state)
        self.assertIsNone(record.permit)
        self.assertEqual([],factories)
        claim.finish(reconciled=True)
        # A maintenance block returns unavailable and starts no child.
        host.set_maintenance(True)
        with self.assertRaises(DraftOperationError) as caught:
            await service.prepare(TOKEN_A,LIBRARY,request())
        self.assertEqual('unavailable',caught.exception.reason)
        self.assertEqual([],factories)

    async def test_real_synthetic_child_holds_claim_through_cancellation_and_cleanup(self):
        import hashlib
        from backend.app.access.selected_story_native import NativeStoryLaunch
        from backend.app.access.selected_story_process import ProcessSelectedStoryProvider
        from test_selected_story_process_lifecycle import WORKER, WorkerKernel
        from test_selected_story_local import MODEL
        host=self.host()
        spec=NativeStoryLaunch(sys.executable,hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            (sys.executable,'-I','-B','-c','exec('+repr(WORKER)+')','120','0'),
            str(host.directory),worker_environment(),minimum_free_ram=0)
        host=HostInferenceAdmission(host.directory,replace(host.profile,launch_sha256=process_launch_digest(spec)),
            capacity_probe=host.probe,enabled=True)
        host.set_maintenance(False,clearance_id=CLEAR)
        kernel=WorkerKernel(helpers=0);self.addCleanup(kernel.finish)
        provider=ProcessSelectedStoryProvider(spec,MODEL,kernel_factory=lambda:kernel,
            enabled=True,cleanup_seconds=2,host_admission=host)
        self.addAsyncCleanup(provider.close)
        scope=make_scope();task=asyncio.create_task(provider.prepare(bundle(),scope))
        try:
            self.assertTrue(await asyncio.to_thread(kernel.resumed.wait,5))
            self.assertGreater(kernel.active_processes(kernel.jobs[-1]),0)
            self.reason('busy',self.other(host).acquire,OTHER)
            host.set_maintenance(True)
            scope._invalidation.set();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            self.assertTrue(await asyncio.wait_for(provider.stop_and_reconcile(scope),4))
        finally:
            scope._invalidation.set()
            if not task.done():
                task.cancel();await asyncio.gather(task,return_exceptions=True)
        self.assertTrue(all(p.poll() is not None for p in kernel.children))
        self.reason('maintenance',self.other(host).acquire,OTHER)
        host.set_maintenance(False,clearance_id=CLEAR)
        host.acquire(OTHER).finish(reconciled=True)
