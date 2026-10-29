"""Synthetic persistent CPU service capacity and admission; no Windows calls."""
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from backend.app.access.host_inference_admission import (
    HostAdmissionError, HostInferenceAdmission, HostResourceProfile,
    initialize_host_admission,
)
from backend.app.access.windows_story_capacity import NativeCapacity, WindowsProbeIdentity
from backend.app.access.windows_story_service_capacity import (
    WindowsStoryConflictSample, WindowsStoryServiceCapacityProbe,
    windows_service_probe_digest,
)


POLICY = '33333333-3333-4333-8333-333333333333'
OTHER_POLICY = '12345678-1234-4234-8234-123456789abc'
OP = 'abcdefab-cdef-4abc-8def-abcdefabcdef'
OTHER_OP = 'fedcbafe-dcba-4fed-8cba-fedcbafedcba'
HOST = 'synthetic-windows-host'
SID = 'S-1-5-21-111-222-333-1001'
VOLUME = '44444444-4444-4444-8444-444444444444'
IMAGES = (r'C:\PhotoHouse\Runtime\caption.exe', r'C:\PhotoHouse\Runtime\upscale.exe')
GiB = 1024 ** 3


class Clock:
    def __init__(self, value=100.0):
        self.value = value

    def __call__(self):
        return self.value


class Metrics:
    def __init__(self, sample=None, samples=None):
        self.sample = sample or NativeCapacity('cpu', 16 * GiB, 4 * GiB, 0,
                                               HOST, SID, VOLUME, 3600)
        self.samples = list(samples) if samples is not None else None
        self.calls = 0

    def capture(self, resource_id, directory):
        self.calls += 1
        if self.samples is not None:
            return self.samples.pop(0)
        return self.sample


class Conflicts:
    def __init__(self, clock, samples=None):
        self.clock, self.samples = clock, list(samples or [])
        self.calls = 0

    def capture(self, images):
        self.calls += 1
        if self.samples:
            value = self.samples.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        return WindowsStoryConflictSample(self.clock(), False)


class WindowsStoryServiceCapacityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        os.chmod(self.root, 0o700)
        self.capacity_dir = self.root / 'capacity'
        self.capacity_dir.mkdir(mode=0o700)
        self.store = self.root / 'admission'
        self.store.mkdir(mode=0o700)
        self.identity = WindowsProbeIdentity(HOST, SID, VOLUME)
        self.clock = Clock()
        self.metrics = Metrics()
        self.conflicts = Conflicts(self.clock)
        self.profile = HostResourceProfile(
            'cpu', 'a' * 64, 8 * GiB, GiB,
            capacity_sha256=windows_service_probe_digest(
                self.identity, self.capacity_dir, POLICY, IMAGES))

    def probe(self, *, enabled=True, metrics=None, conflicts=None, clock=None):
        return WindowsStoryServiceCapacityProbe(
            self.profile, self.capacity_dir, POLICY, IMAGES, identity=self.identity,
            enabled=enabled,
            metrics_factory=Mock(return_value=metrics or self.metrics),
            conflicts_factory=Mock(return_value=conflicts or self.conflicts),
            monotonic=clock or self.clock)

    def admission(self, probe, *, clock=None, enabled=True):
        initialize_host_admission(self.store, enabled=True)
        return HostInferenceAdmission(self.store, self.profile, capacity_probe=probe,
                                      enabled=enabled, monotonic=clock or self.clock)

    def denied(self, function, reason='unavailable'):
        with self.assertRaises(HostAdmissionError) as caught:
            function()
        self.assertEqual(reason, caught.exception.reason)
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_digest_is_stable_case_insensitive_for_images_and_binds_operator_policy(self):
        digest = windows_service_probe_digest(self.identity, self.capacity_dir, POLICY, IMAGES)
        self.assertEqual(digest, windows_service_probe_digest(
            self.identity, self.capacity_dir, POLICY, tuple(p.upper() for p in IMAGES)))
        self.assertNotEqual(digest, windows_service_probe_digest(
            self.identity, self.capacity_dir, OTHER_POLICY, IMAGES))
        self.assertNotEqual(digest, windows_service_probe_digest(
            WindowsProbeIdentity('another-host', SID, VOLUME), self.capacity_dir, POLICY, IMAGES))
        self.assertNotEqual(digest, windows_service_probe_digest(
            self.identity, self.capacity_dir, POLICY, IMAGES + (r'C:\Other\worker.exe',)))

    def test_default_off_is_inert_and_requires_explicit_policy_activation(self):
        probe = self.probe(enabled=False)
        self.denied(probe, 'disabled')
        self.assertEqual((0, 0), (self.metrics.calls, self.conflicts.calls))
        host = self.admission(probe, enabled=False)
        self.denied(lambda: host.acquire(OP), 'disabled')
        host.enabled = True
        self.denied(lambda: host.acquire(OP), 'maintenance')
        host.set_maintenance(False, clearance_id=POLICY)
        host.probe = self.probe(enabled=True)
        self.assertTrue(host.acquire(OP).finish(reconciled=True))
        self.assertEqual((2, 2), (self.metrics.calls, self.conflicts.calls))

    def test_each_acquisition_gets_fresh_measurements_without_receipt_or_short_expiry(self):
        probe = self.probe()
        host = self.admission(probe)
        host.set_maintenance(False, clearance_id=POLICY)
        first = host.acquire(OP)
        self.assertEqual(2, self.metrics.calls)
        self.assertTrue(first.finish(reconciled=True))
        # There is no wall-clock receipt window; a later acquisition samples again.
        self.clock.value += 301
        second = host.acquire(OTHER_OP)
        self.assertEqual(4, self.metrics.calls)
        self.assertEqual(4, self.conflicts.calls)
        self.assertTrue(second.finish(reconciled=True))

    def test_policy_id_is_operator_activation_identity_and_maintenance_never_reclaims(self):
        probe = self.probe()
        host = self.admission(probe)
        host.set_maintenance(False, clearance_id=POLICY)
        permit = host.acquire(OP)
        host.set_maintenance(True)
        self.denied(lambda: host.acquire(OP), 'maintenance')
        self.denied(lambda: host.set_maintenance(False, clearance_id=OTHER_POLICY), 'busy')
        # Advancing time or entering maintenance cannot remove the durable claim.
        self.clock.value += 100000
        self.denied(lambda: host.acquire(OP), 'maintenance')
        self.assertTrue(permit.finish(reconciled=True))
        self.denied(lambda: host.acquire(OP), 'maintenance')
        host.set_maintenance(False, clearance_id=POLICY)
        self.assertTrue(host.acquire(OTHER_OP).finish(reconciled=True))

    def test_profile_policy_drift_refuses_before_metrics(self):
        probe = self.probe()
        probe.policy_id = OTHER_POLICY
        self.denied(probe)
        self.assertEqual((0, 0), (self.metrics.calls, self.conflicts.calls))
        with self.assertRaises(ValueError):
            WindowsStoryServiceCapacityProbe(
                replace(self.profile, capacity_sha256='f' * 64), self.capacity_dir,
                POLICY, IMAGES, identity=self.identity, enabled=True)

    def test_conflict_observation_busy_before_and_after_refuses(self):
        for samples in (
            [WindowsStoryConflictSample(self.clock.value, True),
             WindowsStoryConflictSample(self.clock.value, False)],
            [WindowsStoryConflictSample(self.clock.value, False),
             WindowsStoryConflictSample(self.clock.value, True)],
        ):
            with self.subTest(samples=samples):
                conflicts = Conflicts(self.clock, samples)
                probe = self.probe(conflicts=conflicts)
                self.denied(probe, 'busy')
                self.assertEqual(2, conflicts.calls)
                self.assertEqual(2, self.metrics.calls)
                self.metrics.calls = 0

    def test_conflict_observations_must_be_ordered(self):
        conflicts = Conflicts(self.clock, [
            WindowsStoryConflictSample(self.clock.value + 0.2, False),
            WindowsStoryConflictSample(self.clock.value + 0.1, False),
        ])
        self.denied(self.probe(conflicts=conflicts))
        self.assertEqual(2, self.metrics.calls)

    def test_stale_nonfinite_unknown_or_slow_observation_refuses(self):
        bad_samples = (
            WindowsStoryConflictSample(self.clock.value - 1, False),
            WindowsStoryConflictSample(float('nan'), False),
            WindowsStoryConflictSample(self.clock.value, 0),
            object(),
        )
        for bad in bad_samples:
            with self.subTest(bad=bad):
                conflicts = Conflicts(self.clock, [bad,
                    WindowsStoryConflictSample(self.clock.value, False)])
                self.denied(self.probe(conflicts=conflicts))
        slow_clock = Clock()
        def slow():
            value = slow_clock.value
            slow_clock.value += 0.26
            return value
        conflicts = Conflicts(slow)
        self.denied(self.probe(conflicts=conflicts, clock=slow))
        self.assertEqual(2, conflicts.calls)

    def test_native_resource_and_host_identity_or_capacity_floor_mismatch_refuses(self):
        samples = (
            replace(self.metrics.sample, resource_id='gpu:12345678-1234-4234-8234-123456789abc'),
            replace(self.metrics.sample, host_id='other-host'),
            replace(self.metrics.sample, principal_sid='S-1-5-18'),
            replace(self.metrics.sample, volume_id=OTHER_POLICY),
            replace(self.metrics.sample, free_ram=float('nan')),
            object(),
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.denied(self.probe(metrics=Metrics(sample)))
        # The native probe reports measured values; the shared host admission
        # applies the configured free-memory and disk floors to those values.
        probe = self.probe(metrics=Metrics(replace(self.metrics.sample, free_ram=1)))
        host = self.admission(probe)
        host.set_maintenance(False, clearance_id=POLICY)
        self.denied(lambda: host.acquire(OP))
        probe = self.probe(metrics=Metrics(replace(self.metrics.sample, free_disk=1)))
        host.probe = probe
        self.denied(lambda: host.acquire(OP))

    def test_after_resource_sample_identity_resource_and_uptime_must_match(self):
        first = NativeCapacity('cpu', 14 * GiB, 3 * GiB, 0, HOST, SID, VOLUME, 3600)
        bad_after = (
            replace(first, host_id='other-host'),
            replace(first, resource_id='gpu:12345678-1234-4234-8234-123456789abc'),
            replace(first, uptime_seconds=3599),
        )
        for after in bad_after:
            with self.subTest(after=after):
                metrics = Metrics(samples=[first, after])
                self.denied(self.probe(metrics=metrics))
                self.assertEqual(2, metrics.calls)

    def test_capacity_result_uses_minimum_of_both_resource_samples(self):
        first = NativeCapacity('cpu', 14 * GiB, 3 * GiB, 0, HOST, SID, VOLUME, 3600)
        second = NativeCapacity('cpu', 11 * GiB, 2 * GiB, 0, HOST, SID, VOLUME, 3600)
        metrics = Metrics(samples=[first, second])
        sample = self.probe(metrics=metrics)()
        self.assertEqual((11 * GiB, 2 * GiB), (sample.free_ram, sample.free_disk))
        self.assertEqual(2, metrics.calls)

    def test_probe_busy_is_nonblocking_and_does_not_start_measurement(self):
        probe = self.probe()
        self.assertTrue(probe._lock.acquire(blocking=False))
        try:
            self.denied(probe, 'busy')
        finally:
            probe._lock.release()
        self.assertEqual((0, 0), (self.metrics.calls, self.conflicts.calls))

    def test_shared_durable_claim_blocks_second_coordinator_until_reconciled_release(self):
        probe = self.probe()
        first = self.admission(probe)
        first.set_maintenance(False, clearance_id=POLICY)
        second = HostInferenceAdmission(self.store, self.profile, capacity_probe=probe,
                                        enabled=True, monotonic=self.clock)
        permit = first.acquire(OP)
        self.denied(lambda: second.acquire(OTHER_OP), 'busy')
        self.assertEqual(2, self.metrics.calls)
        self.assertTrue(permit.finish(reconciled=True))
        recovered = second.acquire(OTHER_OP)
        self.assertEqual(4, self.metrics.calls)
        self.assertTrue(recovered.finish(reconciled=True))


if __name__ == '__main__':
    unittest.main()
