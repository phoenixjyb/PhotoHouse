"""Win32 call-shape/handle tests with a synthetic kernel; never native Windows."""
import ctypes
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.app.access.host_inference_admission import HostAdmissionError
from backend.app.access import windows_story_service_capacity as capacity

IMAGE = r'C:\Synthetic\caption.exe'

class Kernel:
    def __init__(self, rows):
        self.rows, self.index, self.error = rows, 0, 18
        self.inaccessible = self.query_failure = self.close_failure = False
        self.closed = []
        self.CreateToolhelp32Snapshot = Mock(return_value=99)
        self.Process32FirstW = Mock(side_effect=self.first)
        self.Process32NextW = Mock(side_effect=self.next)
        self.OpenProcess = Mock(side_effect=lambda access, inherit, pid: 0 if self.inaccessible else pid + 100)
        self.QueryFullProcessImageNameW = Mock(side_effect=self.query)
        self.CloseHandle = Mock(side_effect=self.close)
    def fill(self, pointer):
        entry = pointer._obj
        self.assert_size = entry.size
        pid, image = self.rows[self.index]
        entry.pid = pid
        raw = capacity.ntpath.basename(image).encode('utf-16-le') + b'\0\0'
        for i in range(260):
            entry.image[i] = int.from_bytes(raw[2*i:2*i+2], 'little') if 2*i < len(raw) else 0
        return 1
    def first(self, handle, pointer):
        self.index = 0
        return self.fill(pointer) if self.rows else 0
    def next(self, handle, pointer):
        self.index += 1
        return self.fill(pointer) if self.index < len(self.rows) else 0
    def query(self, handle, flags, buffer, size):
        if self.query_failure:
            return 0
        buffer.value = self.rows[self.index][1]
        size._obj.value = len(buffer.value.encode('utf-16-le')) // 2
        return 1
    def close(self, handle):
        self.closed.append(handle)
        return 0 if self.close_failure else 1

class WindowsStoryProcessConflictTests(unittest.TestCase):
    def capture(self, kernel, probe=None, clock=lambda:100, images=(IMAGE,)):
        probe = probe or capacity.WindowsStoryProcessConflicts(monotonic=clock)
        with patch.object(capacity, 'os', SimpleNamespace(name='nt')), \
                patch('ctypes.WinDLL', create=True, return_value=kernel) as dll, \
                patch('ctypes.get_last_error', create=True, side_effect=lambda:kernel.error):
            value = probe.capture(images)
        dll.assert_called_once_with('kernel32', use_last_error=True, winmode=0x800)
        return value
    def test_complete_nonmatching_snapshot_has_no_process_query_and_closes_handle(self):
        k=Kernel([(12,r'C:\Other\unrelated.exe')]);s=self.capture(k)
        self.assertFalse(s.busy);self.assertEqual(s.observed_monotonic,100)
        self.assertEqual(k.assert_size,568);k.CreateToolhelp32Snapshot.assert_called_once_with(2,0)
        k.OpenProcess.assert_not_called();self.assertEqual(k.closed,[99])
    def test_matching_exact_image_is_busy_without_pid_or_shared_python_exclusion(self):
        k=Kernel([(12,IMAGE)]);s=self.capture(k)
        self.assertTrue(s.busy);k.OpenProcess.assert_called_once_with(0x1000,False,12)
        self.assertEqual(k.closed,[112,99])
        python=r'C:\Synthetic\python.exe';k=Kernel([(12,python),(13,python)])
        p=capacity.WindowsStoryProcessConflicts(monotonic=lambda:100)
        with patch.object(capacity,'os',SimpleNamespace(name='nt')),patch('ctypes.WinDLL',create=True,return_value=k),patch('ctypes.get_last_error',create=True,return_value=18):
            self.assertTrue(p.capture((python,)).busy)
        self.assertEqual(k.OpenProcess.call_count,2)
    def test_native_path_and_entry_lengths_use_utf16_units(self):
        image = 'C:\\Synthetic\\家😀.exe'
        k=Kernel([(12,image)]);self.assertTrue(self.capture(k,images=(image,)).busy)
        self.assertEqual(k.closed,[112,99])
    def test_same_basename_other_exact_image_is_queried_not_claimed_clear_globally(self):
        k=Kernel([(12,r'D:\Other\caption.exe')]);self.assertFalse(self.capture(k).busy)
        self.assertEqual(k.closed,[112,99])
    def test_matching_inaccessible_or_unqueryable_process_refuses_and_closes(self):
        for setting in ['inaccessible','query_failure']:
            k=Kernel([(12,IMAGE)]);setattr(k,setting,True)
            with self.assertRaises(HostAdmissionError):self.capture(k)
            self.assertIn(99,k.closed)
            if setting=='query_failure':self.assertIn(112,k.closed)
    def test_incomplete_snapshot_handle_failure_and_slow_capture_refuse(self):
        for setting in ['end','close','slow']:
            k=Kernel([(12,IMAGE)])
            if setting=='end':k.error=5
            if setting=='close':k.close_failure=True
            ticks=iter([100,100.26])
            with self.assertRaises(HostAdmissionError):self.capture(k,clock=(lambda:next(ticks)) if setting=='slow' else lambda:100)
            self.assertIn(99,k.closed)
    def test_uncertain_native_failure_stays_failed_without_automatic_retry(self):
        p=capacity.WindowsStoryProcessConflicts(monotonic=lambda:100);k=Kernel([(12,IMAGE)]);k.query_failure=True
        with self.assertRaises(HostAdmissionError):self.capture(k,p)
        k.query_failure=False;k.CreateToolhelp32Snapshot.reset_mock()
        with self.assertRaises(HostAdmissionError):self.capture(k,p)
        k.CreateToolhelp32Snapshot.assert_not_called()
    def test_invalid_or_ambiguous_policy_spelling_refuses_before_native_import(self):
        for images in [(),('python.exe',),(r'1:\Synthetic\caption.exe',),(r'中:\Synthetic\caption.exe',),(r'C:\Synthetic\..\caption.exe',),(r'C:\Synthetic.\caption.exe',),(r'C:\Synthetic\a:caption.exe',),(IMAGE,IMAGE.upper()),(r'\\server\share\caption.exe',)]:
            with self.subTest(count=len(images)),self.assertRaises(ValueError):capacity._images(images)
    def test_default_nonwindows_capture_does_not_load_native_api(self):
        with patch.object(capacity,'os',SimpleNamespace(name='posix')),patch('ctypes.WinDLL',create=True) as dll:
            with self.assertRaises(HostAdmissionError):capacity.WindowsStoryProcessConflicts().capture((IMAGE,))
        dll.assert_not_called()
