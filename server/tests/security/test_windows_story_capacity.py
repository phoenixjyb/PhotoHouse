"""Synthetic owner receipts and OS/NVML counters; no model or GPU workload."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from backend.app.access import windows_story_capacity as capacity
from backend.app.access.host_inference_admission import (
    HostAdmissionError, HostInferenceAdmission, HostResourceProfile, initialize_host_admission,
    resource_profile_digest,
)

CLEAR='33333333-3333-4333-8333-333333333333'
OP='abcdefab-cdef-4abc-8def-abcdefabcdef'
GPU='gpu:12345678-1234-4234-8234-123456789abc'
GiB=1024**3
HOST='synthetic-pc'
SID='S-1-5-21-111-222-333-1001'
VOLUME='44444444-4444-4444-8444-444444444444'

def native_sample(resource, ram, disk, vram=0):
    return capacity.NativeCapacity(resource,ram,disk,vram,HOST,SID,VOLUME,1000)



class ProbeFixture:
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve();os.chmod(self.root,0o700)
        self.identity=capacity.WindowsProbeIdentity(HOST,SID,VOLUME)
        self.profile=HostResourceProfile('cpu','a'*64,8*GiB,GiB)
        self.now=1000;self.tick=10
        self.document={'version':1,'clearance_id':CLEAR,'profile_sha256':resource_profile_digest(self.profile),
            'probe_sha256':capacity.windows_probe_binding(self.identity,self.root,self.root/'clearance.json',('index','services'),CLEAR),
            'issued_unix':1000,'expires_unix':1240,'owners':[
                {'id':name,'state':'clear','evidence_sha256':'b'*64}for name in ('index','services')]}
        self.metrics=Mock();self.metrics.capture.return_value=native_sample('cpu',16*GiB,4*GiB)
        self.factory=Mock(return_value=self.metrics)

    def probe(self, *, document=None, raw=None, profile=None, **kwargs):
        receipt=self.root/'clearance.json'
        if raw is None:raw=json.dumps(document if document is not None else self.document).encode()
        receipt.write_bytes(raw);os.chmod(receipt,0o600)
        selected=profile or replace(self.profile,capacity_sha256=capacity.windows_probe_digest(
            self.identity,self.root,receipt,('index','services'),CLEAR,hashlib.sha256(raw).hexdigest()))
        return capacity.WindowsStoryCapacityProbe(selected,self.root,receipt,
            hashlib.sha256(raw).hexdigest(),CLEAR,('index','services'),enabled=True,
            identity=self.identity,metrics_factory=self.factory,wall_clock=lambda:self.now,monotonic=lambda:self.tick,**kwargs)

    def denied(self, function, reason='unavailable'):
        with self.assertRaises(HostAdmissionError)as caught:function()
        self.assertEqual(reason,caught.exception.reason)
        self.assertNotIn(str(self.root),str(caught.exception))


class WindowsProbeTests(ProbeFixture,unittest.TestCase):
    def test_default_off_performs_no_receipt_or_native_io(self):
        probe=self.probe();probe.enabled=False
        probe.receipt.unlink()
        with patch.object(capacity,'_read_pinned')as read:
            self.denied(probe,'disabled')
        read.assert_not_called();self.factory.assert_not_called()

    def test_clear_receipt_returns_fresh_bound_sample(self):
        probe=self.probe();sample=probe()
        self.assertEqual(('cpu',CLEAR,10,False),(sample.resource_id,sample.clearance_id,
                         sample.observed_monotonic,sample.external_busy))
        self.metrics.capture.assert_called_once_with('cpu',self.root)

    def test_owner_and_profile_clearance_must_be_exact(self):
        changes=[{'clearance_id':OP},{'profile_sha256':'c'*64},{'version':True},
                 {'owners':[]},{'unknown':True},
                 {'owners':[self.document['owners'][0]]*2},
                 {'owners':[self.document['owners'][0],{'id':'services','state':'busy','evidence_sha256':'b'*64}]},
                 {'owners':[self.document['owners'][0],{'id':'unknown','state':'clear','evidence_sha256':'b'*64}]},
                 {'owners':[self.document['owners'][0],{'id':'services','state':'clear','evidence_sha256':'bad'}]}]
        for change in changes:
            with self.subTest(change=change):self.denied(self.probe(document=self.document|change))
        self.factory.assert_not_called()

    def test_expiry_future_time_and_overlong_windows_refused(self):
        for change in ({'issued_unix':1001},{'expires_unix':1059},{'expires_unix':1400},
                       {'issued_unix':True},{'expires_unix':1000}):
            with self.subTest(change=change):self.denied(self.probe(document=self.document|change))
        self.factory.assert_not_called()

    def test_duplicate_json_missing_and_oversized_receipts_refused(self):
        for raw in (b'{"version":1,"version":1}',b'[]',b'x'*8193):
            self.denied(self.probe(raw=raw))
        probe=self.probe();probe.receipt.unlink();self.denied(probe)
        self.factory.assert_not_called()

    def test_changed_receipt_hash_refuses_before_metrics(self):
        probe=self.probe();probe.receipt.write_bytes(b'{}');self.denied(probe)
        self.factory.assert_not_called()

    def test_revocation_or_expiry_during_measurement_refuses(self):
        for mode in ('changed','expiry'):
            probe=self.probe()
            def capture(*args):
                if mode=='changed':probe.receipt.write_bytes(b'{}')
                else:self.now=1200
                return native_sample('cpu',16*GiB,4*GiB)
            self.metrics.capture.side_effect=capture
            self.denied(probe);self.now=1000

    def test_clock_rollback_and_slow_completion_refuse(self):
        probe=self.probe();probe();self.now=999;self.denied(probe)
        self.now=1000;probe=self.probe()
        def capture(*args):self.tick=11;return native_sample('cpu',16*GiB,4*GiB)
        self.metrics.capture.side_effect=capture;self.denied(probe)

    def test_invalid_metrics_and_native_error_are_sanitized(self):
        for sample in (object(),native_sample(GPU,16*GiB,4*GiB),
                       native_sample('cpu',True,4*GiB),native_sample('cpu',-1,4*GiB)):
            self.metrics.capture.return_value=sample;self.denied(self.probe())
        self.metrics.capture.side_effect=RuntimeError('synthetic-private-path-token')
        self.denied(self.probe())

    def test_probe_concurrency_refuses_without_another_native_call(self):
        probe=self.probe();probe._lock.acquire()
        try:self.denied(probe,'busy')
        finally:probe._lock.release()
        self.factory.assert_not_called()

    def test_host_admission_needs_both_clear_receipt_and_capacity(self):
        store=self.root/'store';store.mkdir(mode=0o700);initialize_host_admission(store,enabled=True)
        probe=self.probe();host=HostInferenceAdmission(store,probe.profile,capacity_probe=probe,
                                                      enabled=True,monotonic=lambda:self.tick)
        host.set_maintenance(False,clearance_id=CLEAR)
        permit=host.acquire(OP);permit.finish(reconciled=True)
        self.metrics.capture.return_value=native_sample('cpu',GiB,4*GiB)
        self.denied(lambda:host.acquire(OP))
        self.metrics.capture.return_value=native_sample('cpu',16*GiB,4*GiB)
        probe.receipt.write_bytes(b'{}');self.denied(lambda:host.acquire(OP))

    def test_cpu_never_accepts_implicit_gpu_selection(self):
        selection=capacity.NvmlSelection(str(self.root/'nvml.dll'),'a'*64,GPU)
        with self.assertRaises(ValueError):self.probe(nvml=selection)
        with self.assertRaises(ValueError):self.probe(profile=replace(self.profile,resource_id=GPU,minimum_free_vram=GiB))

    def test_native_identity_mismatch_and_preboot_clearance_refuse(self):
        sample=native_sample('cpu',16*GiB,4*GiB)
        for change in ({'host_id':'other-pc'},{'principal_sid':'S-1-5-18'},
                       {'volume_id':OP},{'uptime_seconds':0},{'uptime_seconds':True}):
            with self.subTest(change=change):
                self.metrics.capture.return_value=replace(sample,**change)
                self.denied(self.probe())
        self.now=1100;self.metrics.capture.return_value=replace(sample,uptime_seconds=20)
        self.denied(self.probe())

    def test_probe_configuration_drift_requires_new_profile_clearance(self):
        profile=replace(self.profile,capacity_sha256='f'*64)
        with self.assertRaises(ValueError):self.probe(profile=profile)
        with self.assertRaises(ValueError):
            capacity.WindowsStoryCapacityProbe(self.profile,self.root,self.root/'clearance.json',
                'a'*64,CLEAR,('index',),identity=self.identity)

    def test_same_profile_uuid_cannot_substitute_a_new_receipt_pin(self):
        probe=self.probe();changed=json.dumps(self.document|{'expires_unix':1250}).encode()
        probe.receipt.write_bytes(changed)
        with self.assertRaises(ValueError):
            capacity.WindowsStoryCapacityProbe(probe.profile,self.root,probe.receipt,
                hashlib.sha256(changed).hexdigest(),CLEAR,('index','services'),identity=self.identity)

    def test_probe_trust_configuration_cannot_mutate_after_construction(self):
        probe=self.probe()
        for name,value in (('digest','f'*64),('profile',self.profile),('owners',('index',)),
                           ('identity',None),('receipt',self.root/'other.json')):
            with self.subTest(name=name):
                with self.assertRaises(AttributeError):setattr(probe,name,value)
        self.factory.assert_not_called()

    def test_blocked_native_call_does_not_establish_maintenance_closure(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from contextlib import closing
        import sqlite3
        store=self.root/'store';store.mkdir(mode=0o700);initialize_host_admission(store,enabled=True)
        probe=self.probe();host=HostInferenceAdmission(store,probe.profile,capacity_probe=probe,
                                                      enabled=True,monotonic=lambda:self.tick)
        host.set_maintenance(False,clearance_id=CLEAR)
        entered=threading.Event();release=threading.Event()
        def blocked(*args):
            entered.set()
            if not release.wait(5):raise RuntimeError('Synthetic wait timed out')
            return native_sample('cpu',16*GiB,4*GiB)
        self.metrics.capture.side_effect=blocked
        with ThreadPoolExecutor(max_workers=1)as pool:
            pending=pool.submit(host.acquire,OP)
            try:
                self.assertTrue(entered.wait(3))
                self.assertFalse(pending.done())
                self.denied(lambda:host.set_maintenance(True),'busy')
                with closing(sqlite3.connect(host.path))as db:
                    self.assertIsNone(db.execute('SELECT 1 FROM claim').fetchone())
            finally:release.set()
            permit=pending.result(timeout=3)
        host.set_maintenance(True)
        permit.finish(reconciled=True)

    def test_nonprivate_receipt_refused_on_posix(self):
        if os.name=='nt':self.skipTest('POSIX permissions assertion; Windows uses actual DACL checks')
        probe=self.probe();os.chmod(probe.receipt,0o644);self.denied(probe)
        self.factory.assert_not_called()


class NativeBindingsTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve();os.chmod(self.root,0o700)
        self.kernel=Mock();self.kernel.GetDriveTypeW.return_value=3
        def ram(pointer):
            pointer._obj.total=64*GiB;pointer._obj.available=16*GiB;return 1
        def disk(path,available,total,free):
            available._obj.value=4*GiB;total._obj.value=64*GiB;free._obj.value=8*GiB;return 1
        def host(buffer,length):buffer.value=HOST;return 1
        def volume(root,buffer,length):buffer.value='\\\\?\\Volume{'+VOLUME+'}\\';return 1
        self.kernel.GetVolumePathNameW.side_effect=lambda path,buffer,length:(setattr(buffer,'value',self.root.anchor)or 1)
        self.kernel.GetComputerNameW.side_effect=host
        self.kernel.GetVolumeNameForVolumeMountPointW.side_effect=volume
        self.kernel.GetTickCount64.return_value=1000000
        self.kernel.GlobalMemoryStatusEx.side_effect=ram
        self.kernel.GetDiskFreeSpaceExW.side_effect=disk
        # Do not change global os.name/pathlib's host platform in portable tests.
        class NativeOS:
            name='nt'
            def __getattr__(self,key):return getattr(os,key)
        self.fake_os=NativeOS()

    def native(self, metrics):
        with patch.object(capacity,'require_private_directory'),patch.object(capacity,'os',self.fake_os),patch('ctypes.WinDLL',create=True,return_value=self.kernel),patch.object(capacity.WindowsCapacityMetrics,'_principal',return_value=SID),patch('_ctypes.FreeLibrary',create=True)as free_library:
            self.free_library=free_library
            return metrics.capture('cpu'if metrics.nvml is None else GPU,self.root)

    def test_cpu_uses_available_physical_ram_and_caller_disk_quota(self):
        with patch('ctypes.CDLL')as loader:
            sample=self.native(capacity.WindowsCapacityMetrics())
        self.assertEqual((16*GiB,4*GiB,0),(sample.free_ram,sample.free_disk,sample.free_vram))
        loader.assert_not_called()

    def test_network_volume_and_failed_native_counter_refuse_stickily(self):
        for attr in ('GetVolumePathNameW','GetDriveTypeW','GlobalMemoryStatusEx','GetDiskFreeSpaceExW'):
            with self.subTest(attr=attr):
                call=getattr(self.kernel,attr);side=call.side_effect;previous=call.return_value
                call.side_effect=None;call.return_value=4 if attr=='GetDriveTypeW'else 0
                metrics=capacity.WindowsCapacityMetrics()
                with self.assertRaises(HostAdmissionError):self.native(metrics)
                call.side_effect=side;call.return_value=previous
                with self.assertRaises(HostAdmissionError):self.native(metrics)

    def test_volume_identity_uses_the_target_mount_not_drive_anchor(self):
        mount=str(self.root/'mounted-volume')+os.sep
        self.kernel.GetVolumePathNameW.side_effect=lambda path,buffer,length:(setattr(buffer,'value',mount)or 1)
        self.native(capacity.WindowsCapacityMetrics())
        self.kernel.GetDriveTypeW.assert_called_once_with(mount)
        self.assertEqual(mount,self.kernel.GetVolumeNameForVolumeMountPointW.call_args.args[0])

    def gpu(self):
        dll=self.root/'nvml.dll';dll.write_bytes(b'synthetic NVML fixture')
        selection=capacity.NvmlSelection(str(dll),hashlib.sha256(dll.read_bytes()).hexdigest(),GPU)
        api=Mock();api._handle=123;api.nvmlInit_v2.return_value=api.nvmlShutdown.return_value=0
        def loaded(handle,buffer,length):buffer.value=str(dll);return len(str(dll))
        self.kernel.GetModuleFileNameW.side_effect=loaded
        def select(expected,pointer):pointer._obj.value=123;return 0
        def identity(device,buffer,length):buffer.value=('GPU-'+GPU[4:]).encode();return 0
        def memory(device,pointer):
            pointer._obj.total=24*GiB;pointer._obj.free=20*GiB;pointer._obj.used=4*GiB;return 0
        api.nvmlDeviceGetHandleByUUID.side_effect=select
        api.nvmlDeviceGetUUID.side_effect=identity
        api.nvmlDeviceGetMemoryInfo.side_effect=memory
        return selection,api

    def test_gpu_reads_exact_uuid_with_restricted_dll_search_and_shutdown(self):
        selection,api=self.gpu()
        with patch('ctypes.CDLL',return_value=api)as loader:sample=self.native(capacity.WindowsCapacityMetrics(nvml=selection))
        self.assertEqual(20*GiB,sample.free_vram)
        self.assertEqual({'winmode':0x900},loader.call_args.kwargs)
        self.assertEqual(('GPU-'+GPU[4:]).encode(),api.nvmlDeviceGetHandleByUUID.call_args.args[0])
        api.nvmlShutdown.assert_called_once_with()
        self.free_library.assert_called_once_with(123)

    def test_gpu_dll_digest_mismatch_prevents_loading(self):
        selection,api=self.gpu();selection=replace(selection,dll_sha256='0'*64)
        with patch('ctypes.CDLL',return_value=api)as loader:
            with self.assertRaises(HostAdmissionError):self.native(capacity.WindowsCapacityMetrics(nvml=selection))
        loader.assert_not_called()

    def test_system_driver_link_count_must_be_explicitly_pinned(self):
        selection,api=self.gpu()
        os.link(selection.dll_file,self.root/'driver-alias.dll')
        with patch('ctypes.CDLL',return_value=api)as loader:
            with self.assertRaises(HostAdmissionError):self.native(capacity.WindowsCapacityMetrics(nvml=selection))
            loader.assert_not_called()
            sample=self.native(capacity.WindowsCapacityMetrics(nvml=replace(selection,dll_link_count=2)))
        self.assertEqual(20*GiB,sample.free_vram)

    def test_gpu_wrong_uuid_counter_failure_and_shutdown_failure_refuse(self):
        for mode in ('uuid','counter','shutdown'):
            selection,api=self.gpu()
            if mode=='uuid':api.nvmlDeviceGetUUID.side_effect=lambda d,b,l:(setattr(b,'value',b'GPU-wrong')or 0)
            if mode=='counter':api.nvmlDeviceGetMemoryInfo.side_effect=None;api.nvmlDeviceGetMemoryInfo.return_value=1
            if mode=='shutdown':api.nvmlShutdown.return_value=1
            with patch('ctypes.CDLL',return_value=api):
                with self.assertRaises(HostAdmissionError):self.native(capacity.WindowsCapacityMetrics(nvml=selection))
            api.nvmlShutdown.assert_called_once_with()
