"""Exact generated-data checks for existing Rust kernel reuse, never a build."""
import json
import math
import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app.access import semantic_encoder as encoder, semantic_streaming as streaming
from app.access import vector_acceleration, visual_candidates as visual
from app.access.vector_kernel_reference import run_batch


def fixture(dimension=4):
    identity = visual.VectorSpaceIdentity('a'*64, 'b'*64, 'generated-v1',
        'generated-v1', dimension, 'unit_l2')
    binding = encoder.JointSpaceBinding(identity, identity, 'c'*64)
    v = (0.6, 0.8) + (0.0,)*(dimension-2)
    checksum = visual.canonical_vector_checksum(v)
    query = encoder.TextVector(binding.binding_sha256, 'd'*64, v, checksum)
    rows = tuple(visual.VectorRecord(str(i), identity, v, checksum) for i in (9, 3, 1, 6))
    return identity, binding, query, rows


class Kernel:
    """Recorded byte-buffer policy; the actual DLL is checked separately."""
    def __init__(self):
        self.calls = 0

    def canonicalize(self, data, dimension, checksum):
        self.calls += 1
        value = run_batch(json.dumps({'op': 'canonicalize', 'data': data.hex(),
            'dimension': dimension, 'byteorder': sys.byteorder, 'checksums': [checksum(0)]}))
        return bytes.fromhex(value)


def ranked(function, binding, query, rows, callback):
    if function is encoder.rank_semantic:
        return function(query, binding, rows, check=callback)
    return function(query, binding, (rows[:2], rows[2:]),
        expected_count=len(rows), candidate_limit=513, check=callback)


class SemanticRustReuseTests(unittest.TestCase):
    def test_exact_components_and_both_rank_paths_with_original_callback_counts(self):
        for dimension in (4, 768, 4096):
            identity, binding, query, rows = fixture(dimension)
            kernel = Kernel()
            self.assertEqual(visual._canonical_components(rows[0], identity),
                visual._canonical_components(rows[0], identity, kernel=kernel))
            for function in (encoder.rank_semantic, streaming.rank_semantic_batches):
                old_checks, new_checks = [], []
                with patch.object(vector_acceleration, 'backend', return_value=None):
                    expected = ranked(function, binding, query, rows, lambda: old_checks.append(1))
                before = kernel.calls
                with patch.object(vector_acceleration, 'backend', return_value=kernel):
                    actual = ranked(function, binding, query, rows, lambda: new_checks.append(1))
                self.assertEqual(actual, expected)
                self.assertEqual([x[0] for x in actual], ['1', '3', '6', '9'])
                self.assertEqual(old_checks, new_checks)
                self.assertEqual(kernel.calls-before, len(rows)+1)

    def test_cancellation_preserves_original_exception_at_every_boundary(self):
        class Cancel(BaseException):
            pass
        for function in (encoder.rank_semantic, streaming.rank_semantic_batches):
            _, binding, query, rows = fixture()
            calls = []
            with patch.object(vector_acceleration, 'backend', return_value=None):
                ranked(function, binding, query, rows, lambda: calls.append(1))
            for boundary in range(1, len(calls)+1):
                for native in (None, Kernel()):
                    count = [0]
                    failure = Cancel()
                    def stop():
                        count[0] += 1
                        if count[0] == boundary:
                            raise failure
                    with patch.object(vector_acceleration, 'backend', return_value=native):
                        with self.assertRaises(Cancel) as caught:
                            ranked(function, binding, query, rows, stop)
                    self.assertIs(caught.exception, failure)
                    self.assertEqual(count[0], boundary)

    def test_callback_time_mutation_is_not_hidden_by_prefreezing_a_batch(self):
        for function in (encoder.rank_semantic, streaming.rank_semantic_batches):
            for native in (None, Kernel()):
                _, binding, query, rows = fixture()
                count = [0]
                def mutate():
                    count[0] += 1
                    # Before the second row is validated, never before the
                    # entire batch has been packed by a new accelerator.
                    if count[0] == 5:
                        object.__setattr__(rows[1], 'checksum_sha256', '0'*64)
                with patch.object(vector_acceleration, 'backend', return_value=native):
                    with self.assertRaises(encoder.SemanticUnavailable):
                        ranked(function, binding, query, rows, mutate)

    def test_packing_keeps_exact_builtin_types_and_f32_bytes(self):
        class Float(float):
            pass
        class Int(int):
            pass
        for bad in (True, Float(0.0), Int(0), object(), '0', None):
            with self.subTest(value=type(bad).__name__), self.assertRaises(ValueError):
                visual._packed_vector((1.0, bad))
        for values in ((1, 0), (0.6, 0.8), [-0.0, 1.0]):
            self.assertEqual(visual._packed_vector(values), struct.pack('>2f', *values))
        for values in ((), [0]*4097, (float('nan'),), (float('inf'),), (10**400,)):
            with self.assertRaises(ValueError):
                visual._packed_vector(values)

    def test_changed_checksum_identity_shape_and_native_wire_refuse(self):
        identity, _, _, rows = fixture()
        for vector in ((0.0,)*4, (2.0, 0.0, 0.0, 0.0)):
            record = visual.VectorRecord('1', identity, vector,
                visual.canonical_vector_checksum(vector))
            for kernel in (None, Kernel()):
                with self.assertRaises(ValueError):
                    visual._canonical_components(record, identity, kernel=kernel)
        for field, value in (('checksum_sha256', '0'*64), ('vector', (1.0,)),
                             ('vector', [0.6, 0.8, 0.0, 0.0])):
            for kernel in (None, Kernel()):
                _, _, _, current = fixture()
                object.__setattr__(current[0], field, value)
                with self.assertRaises(ValueError):
                    visual._canonical_components(current[0], identity, kernel=kernel)
        for output in (None, b'', bytearray(32), struct.pack('=4d', math.nan, 0, 0, 0)):
            def native(data, dimension, checksum):
                checksum(0)
                return output
            with self.assertRaisesRegex(ValueError, '^invalid_vector_record$'):
                visual._canonical_components(rows[0], identity,
                    kernel=SimpleNamespace(canonicalize=native))
        for indices in ((), (True,), (1,), (0, 0)):
            def native(data, dimension, checksum):
                for index in indices:
                    checksum(index)
                return struct.pack('=4d', 0.6, 0.8, 0, 0)
            with self.assertRaisesRegex(ValueError, '^invalid_vector_record$'):
                visual._canonical_components(rows[0], identity,
                    kernel=SimpleNamespace(canonicalize=native))

    def test_default_does_not_load_native_and_explicit_unavailable_never_falls_back(self):
        _, binding, query, rows = fixture()
        for function in (encoder.rank_semantic, streaming.rank_semantic_batches):
            with patch.dict(os.environ, PHOTOHOUSE_VECTOR_ENGINE='python'), \
                    patch.object(vector_acceleration.importlib, 'import_module',
                                 side_effect=AssertionError('No native import')):
                self.assertEqual(len(ranked(function, binding, query, rows, lambda: None)), 4)
            for engine in ('rust', 'unknown'):
                with patch.dict(os.environ, PHOTOHOUSE_VECTOR_ENGINE=engine), \
                        patch.object(vector_acceleration.importlib, 'import_module', side_effect=ImportError):
                    with self.assertRaises(encoder.SemanticUnavailable):
                        ranked(function, binding, query, rows, lambda: None)


if __name__ == '__main__':
    unittest.main()
