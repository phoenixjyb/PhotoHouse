"""Synthetic integrity, cohort, and exact-ranking checks for bulk vectors."""
from dataclasses import fields, replace
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from asyncio import CancelledError
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.access.semantic_bulk_vectors import (
    BulkVectorStore,
    BulkVectorUnavailable,
    MAX_BULK_BYTES,
    MAX_HEADER_BYTES,
    _MAGIC,
    write_bulk_vectors,
)
from app.access.visual_candidates import VectorSpaceIdentity, _canonical_components, VectorRecord, canonical_vector_checksum
from app.access.visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256


def npy_bytes(vector):
    header = repr({"descr": "<f4", "fortran_order": False, "shape": (len(vector),)}).encode("ascii")
    padding = (-(10 + len(header) + 1)) % 16
    header += b" " * padding + b"\n"
    return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header + struct.pack(f"<{len(vector)}f", *vector)


def identity(dimension=2):
    return VectorSpaceIdentity("a" * 64, "b" * 64, "synthetic-space-v1", "synthetic-v1", dimension, "unit_l2")


def artifact(identity_value, asset_id, record_char, raw, vector):
    digest = identity_sha256(identity_value)
    record_id = record_char * 64
    return ImmutableVectorArtifact(
        record_id, str(asset_id), f"{asset_id:064x}", "synthetic-model", identity_value.artifact_sha256,
        identity_value.preprocessing_sha256, identity_value.vector_space_id, identity_value.model_version,
        identity_value.dimension, identity_value.normalization, digest,
        f"image-vectors/{digest}/{record_id}.npy", hashlib.sha256(raw).hexdigest(),
        canonical_vector_checksum(vector), 1, "ready",
    )


class SemanticBulkVectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bulk-vectors-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(strict=True)
        self.root = self.base / "vectors"
        self.root.mkdir()
        self.out = self.base / "cohort.bulk"

    def source(self, identity_value, asset_id, char, vector, *, raw=None):
        raw = npy_bytes(vector) if raw is None else raw
        record = artifact(identity_value, asset_id, char, raw, vector)
        path = self.root / record.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return record

    def build(self, vectors, identity_value=None):
        identity_value = identity_value or identity(len(vectors[0][2]))
        records = tuple(self.source(identity_value, aid, char, vector) for aid, char, vector in vectors)
        store = write_bulk_vectors(self.out, self.root, records, identity_value, "family-a")
        return store, records

    def test_round_trip_2d_and_768d_exact_legacy_scores_ties_and_subset(self):
        identity2 = identity()
        vectors2 = ((9, "a", (1.0, 0.0)), (2, "b", (0.0, 1.0)), (7, "c", (0.0, 1.0)))
        store, records = self.build(vectors2, identity2)
        snapshot = store.snapshot(records, library_id="family-a")
        self.assertEqual(snapshot.count, 3)
        query = (0.0, 1.0)
        expected = []
        for record, vector in zip(records, (row[2] for row in vectors2)):
            canonical = _canonical_components(VectorRecord(record.asset_id, identity2, vector, record.component_sha256), identity2)
            expected.append((record.asset_id, __import__("math").fsum(a * b for a, b in zip(query, canonical))))
        self.assertEqual(snapshot.rank(query, ("9", "2", "7")), tuple(sorted(expected, key=lambda item: (-item[1], int(item[0])))))
        self.assertEqual(snapshot.rank(query, ("7", "2")), (("2", 1.0), ("7", 1.0)))
        with self.assertRaises(BulkVectorUnavailable):
            snapshot.rank(query, ("2", "2"))
        with self.assertRaises(BulkVectorUnavailable):
            snapshot.rank(query, ("8",))

        identity768 = identity(768)
        vector768 = (1.0,) + (0.0,) * 767
        self.out = self.base / "cohort-768.bulk"
        store768, records768 = self.build(((44, "d", vector768),), identity768)
        self.assertEqual(store768.snapshot(records768, library_id="family-a").rank(vector768, ("44",)), (("44", 1.0),))

    def test_canonical_constructor_is_pure_and_descriptor_is_pinned(self):
        ident = identity()
        path = self.base / "not-created.bulk"
        store = BulkVectorStore(path, "c" * 64, "family-a", ident)
        self.assertFalse(path.exists())
        self.assertEqual(store.descriptor["library_id"], "family-a")
        with self.assertRaises(BulkVectorUnavailable):
            BulkVectorStore(path, "C" * 64, "family-a", ident)

    def test_refuses_stale_order_duplicates_library_identity_and_changed_binding(self):
        store, records = self.build(((1, "a", (1.0, 0.0)), (2, "b", (0.0, 1.0))))
        self.out = self.base / "reversed.bulk"
        reversed_store, reversed_records = self.build(
            ((2, "b", (0.0, 1.0)), (1, "a", (1.0, 0.0))), identity(),
        )
        self.assertEqual(reversed_store.snapshot(reversed_records, library_id="family-a").count, 2)
        variants = (
            (records[0], replace(records[1], source_sha256="f" * 64)),
            (records[0], records[0]),
        )
        for variant in variants:
            with self.subTest(variant=variant), self.assertRaises(BulkVectorUnavailable):
                store.snapshot(variant, library_id="family-a")
        with self.assertRaises(BulkVectorUnavailable):
            store.snapshot(records, library_id="family-b")
        with self.assertRaises(BulkVectorUnavailable):
            write_bulk_vectors(self.base / "wrong.bulk", self.root, records,
                               replace(identity(), model_version="other-v1"), "family-a")

    def test_every_snapshot_rereads_hash_and_rejects_post_cache_mutation(self):
        store, records = self.build(((1, "a", (1.0, 0.0)),))
        first = store.snapshot(records, library_id="family-a")
        self.assertEqual(first.rank((1.0, 0.0), ("1",)), (("1", 1.0),))
        original = self.out.read_bytes()
        self.out.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        with self.assertRaises(BulkVectorUnavailable):
            store.snapshot(records, library_id="family-a")

    def test_corrupt_truncated_oversized_header_tail_checksum_and_norm_refuse(self):
        store, records = self.build(((1, "a", (1.0, 0.0)),))
        good = self.out.read_bytes()
        variants = [good[:-1], good + b"tail", b"bad" + good[3:]]
        prefix = len(_MAGIC)
        variants.append(good[:prefix] + struct.pack(">I", MAX_HEADER_BYTES + 1) + good[prefix + 4:])
        # A valid descriptor hash must still fail malformed container syntax.
        for index, bad in enumerate(variants):
            self.out.write_bytes(bad)
            store_bad = BulkVectorStore(self.out, hashlib.sha256(bad).hexdigest(), "family-a", identity())
            with self.subTest(index=index), self.assertRaises(BulkVectorUnavailable):
                store_bad.snapshot(records, library_id="family-a")

        # Rebuild the file with a correctly bound header and malicious payload.
        self.out = self.base / "payload-corrupt.bulk"
        store, records = self.build(((1, "a", (1.0, 0.0)),))
        raw = bytearray(self.out.read_bytes())
        raw[-4:] = struct.pack(">f", 0.25)  # finite but no longer checksum/norm bound
        self.out.write_bytes(raw)
        changed_store = BulkVectorStore(self.out, hashlib.sha256(raw).hexdigest(), "family-a", identity())
        with self.assertRaises(BulkVectorUnavailable):
            changed_store.snapshot(records, library_id="family-a")

    def test_source_file_symlink_root_change_and_failed_build_leave_no_final(self):
        ident = identity()
        record = self.source(ident, 1, "a", (1.0, 0.0))
        target = self.root / record.relative_path
        saved = target.read_bytes()
        target.unlink()
        target.symlink_to(self.base / "elsewhere")
        with self.assertRaises(BulkVectorUnavailable):
            write_bulk_vectors(self.out, self.root, (record,), ident, "family-a")
        self.assertFalse(self.out.exists())
        target.unlink()
        target.write_bytes(saved)

        root_link = self.base / "root-link"
        root_link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(BulkVectorUnavailable):
            write_bulk_vectors(self.base / "other.bulk", root_link, (record,), ident, "family-a")

        with self.assertRaises(RuntimeError):
            write_bulk_vectors(self.out, self.root, (record,), ident, "family-a",
                               check=lambda: (_ for _ in ()).throw(RuntimeError("cancel")))
        self.assertFalse(self.out.exists())

    def test_builder_refuses_overwrite_and_checks_permissions_and_charge(self):
        store, records = self.build(((1, "a", (1.0, 0.0)),))
        original = self.out.read_bytes()
        with self.assertRaises(BulkVectorUnavailable):
            write_bulk_vectors(self.out, self.root, records, identity(), "family-a")
        self.assertEqual(self.out.read_bytes(), original)
        charged = []
        store.snapshot(records, library_id="family-a", charge=charged.append)
        self.assertEqual(sum(charged), len(original))
        with patch("app.access.semantic_bulk_vectors._READ_CHUNK", MAX_BULK_BYTES + 1):
            with self.assertRaises(BulkVectorUnavailable):
                with self.out.open("wb") as oversized:
                    oversized.truncate(MAX_BULK_BYTES + 1)
                store.snapshot(records, library_id="family-a")

    def test_bulk_path_must_stay_private_regular_and_unaliased(self):
        store, records = self.build(((1, "a", (1.0, 0.0)),))
        alias = self.base / "hardlink.bulk"
        alias.hardlink_to(self.out)
        with self.assertRaises(BulkVectorUnavailable):
            store.snapshot(records, library_id="family-a")
        alias.unlink()
        self.out.chmod(0o644)
        with self.assertRaises(BulkVectorUnavailable):
            store.snapshot(records, library_id="family-a")
        self.out.chmod(0o600)
        self.out.unlink()
        self.out.symlink_to(self.base / "missing.bulk")
        with self.assertRaises(BulkVectorUnavailable):
            store.snapshot(records, library_id="family-a")

    def test_reparse_or_parent_identity_change_during_read_refuses(self):
        store, records = self.build(((1, "a", (1.0, 0.0)),))
        with patch("app.access.semantic_bulk_vectors._is_reparse", return_value=True):
            with self.assertRaises(BulkVectorUnavailable):
                store.snapshot(records, library_id="family-a")

        from app.access import semantic_bulk_vectors as module
        real_snapshot = module._root_snapshot
        calls = 0

        def changing_snapshot(path):
            nonlocal calls
            calls += 1
            result = real_snapshot(path)
            return result + ((-1, -1, -1),) if calls == 2 and result is not None else result

        with patch("app.access.semantic_bulk_vectors._root_snapshot", side_effect=changing_snapshot):
            with self.assertRaises(BulkVectorUnavailable):
                store.snapshot(records, library_id="family-a")

    def test_charge_and_cancellation_failures_propagate_unchanged(self):
        store, records = self.build(((1, "a", (1.0, 0.0)),))
        with self.assertRaisesRegex(RuntimeError, "cancel snapshot"):
            store.snapshot(records, library_id="family-a",
                           check=lambda: (_ for _ in ()).throw(RuntimeError("cancel snapshot")))
        with self.assertRaisesRegex(RuntimeError, "budget cancelled"):
            store.snapshot(records, library_id="family-a",
                           charge=lambda _size: (_ for _ in ()).throw(RuntimeError("budget cancelled")))

    def test_temp_name_collision_never_removes_unowned_file(self):
        ident = identity()
        record = self.source(ident, 1, 'a', (1.0, 0.0))
        collision = self.out.with_name('.' + self.out.name + '.' + '0' * 32 + '.tmp')
        collision.write_bytes(b'preexisting evidence')
        with patch('app.access.semantic_bulk_vectors.os.urandom', return_value=b'\x00' * 16):
            with self.assertRaises(BulkVectorUnavailable):
                write_bulk_vectors(self.out, self.root, (record,), ident, 'family-a')
        self.assertEqual(collision.read_bytes(), b'preexisting evidence')
        self.assertFalse(self.out.exists())

    def test_warm_metadata_digest_reuse_still_requires_exact_current_rows(self):
        from app.access import semantic_bulk_vectors as module
        store, records = self.build(((1, 'a', (1.0, 0.0)),))
        store.snapshot(records, library_id='family-a')
        with patch.object(module, '_cohort_digest', side_effect=AssertionError('unchanged metadata rebuilt')):
            store.snapshot(tuple(replace(row) for row in records), library_id='family-a')
        with self.assertRaises(AttributeError):
            store.file_sha256 = 'f' * 64
        self.assertFalse(hasattr(store, '__dict__'))
        with self.assertRaises(BulkVectorUnavailable):
            store.snapshot((replace(records[0], created_at=2),), library_id='family-a')

    def test_warm_cache_uses_immutable_full_metadata_key_after_object_mutation(self):
        from app.access import semantic_bulk_vectors as module
        self.assertEqual(module._ARTIFACT_COHORT_FIELDS,
                         tuple(field.name for field in fields(ImmutableVectorArtifact)))
        store, records = self.build(((1, 'a', (1.0, 0.0)),))
        store.snapshot(records, library_id='family-a')
        original_matrix = store._cache[2]
        original = records[0]
        original_values = {name: getattr(original, name) for name in module._ARTIFACT_COHORT_FIELDS}
        cached_rows = store._cache[1]
        self.assertIs(type(cached_rows), tuple)
        self.assertIs(type(cached_rows[0]), tuple)
        self.assertNotIn(original, cached_rows)

        mutations = (
            {'asset_id': '2'},
            {'created_at': 2},
            {'source_sha256': 'd' * 64},
            {'model_name': 'other-model'},
            {'file_sha256': 'e' * 64},
            {'component_sha256': 'f' * 64},
            {'record_id': 'c' * 64,
             'relative_path': f'image-vectors/{original.identity_sha256}/' + 'c' * 64 + '.npy'},
        )
        for changes in mutations:
            with self.subTest(changes=changes):
                for name, value in changes.items():
                    object.__setattr__(original, name, value)
                self.assertTrue(module.validate_artifact(original, identity()))
                # A warm cache must not use old metadata just because the same
                # dataclass object is still present in its old cohort tuple.
                with self.assertRaises(BulkVectorUnavailable):
                    store.snapshot((original,), library_id='family-a')

                # The same mutated but grammar-valid cohort must also fail cold.
                cold_store = BulkVectorStore(self.out, hashlib.sha256(self.out.read_bytes()).hexdigest(),
                                             'family-a', identity())
                with self.assertRaises(BulkVectorUnavailable):
                    cold_store.snapshot((original,), library_id='family-a')

                for name, value in original_values.items():
                    object.__setattr__(original, name, value)
                # Restoring the exact previously validated primitive key may
                # reuse the matrix, but still passes fresh file verification.
                with patch.object(module, '_cohort_digest', side_effect=AssertionError('digest rebuilt')), \
                        patch.object(module, '_canonical_matrix', side_effect=AssertionError('matrix rebuilt')), \
                        patch.object(module, '_read_secure_file', wraps=module._read_secure_file) as read:
                    store.snapshot((original,), library_id='family-a')
                self.assertEqual(read.call_count, 1)
                self.assertIs(store._cache[2], original_matrix)

    def test_warm_exact_primitive_cohort_skips_only_duplicate_validation(self):
        from app.access import semantic_bulk_vectors as module
        store, records = self.build(((1, 'a', (1.0, 0.0)),))
        with patch.object(module, 'validate_artifact', wraps=module.validate_artifact) as validate:
            first = store.snapshot(records, library_id='family-a')
            self.assertEqual(validate.call_count, 1)
            validate.reset_mock()
            with patch.object(module, '_read_secure_file', wraps=module._read_secure_file) as read:
                warm = store.snapshot(tuple(replace(row) for row in records), library_id='family-a')
            self.assertEqual(validate.call_count, 0)
            self.assertEqual(read.call_count, 1)
            self.assertEqual(warm.rank((1.0, 0.0), ('1',)), first.rank((1.0, 0.0), ('1',)))

    def test_warm_callback_identity_mutation_refuses_before_file_read(self):
        from app.access import semantic_bulk_vectors as module
        store, records = self.build(((1, 'a', (1.0, 0.0)),))
        store.snapshot(records, library_id='family-a')
        original = store.identity.model_version
        calls = 0

        def mutate_identity():
            nonlocal calls
            calls += 1
            if calls == 2:
                object.__setattr__(store.identity, 'model_version', 'other-v1')

        try:
            with patch.object(module, '_read_secure_file', wraps=module._read_secure_file) as read:
                with self.assertRaises(BulkVectorUnavailable):
                    store.snapshot(tuple(replace(row) for row in records),
                                   library_id='family-a', check=mutate_identity)
            self.assertEqual(read.call_count, 0)
        finally:
            object.__setattr__(store.identity, 'model_version', original)

    def test_warm_callback_invalid_identity_refuses_with_fixed_error_before_file_read(self):
        from app.access import semantic_bulk_vectors as module
        store, records = self.build(((1, 'a', (1.0, 0.0)),))
        store.snapshot(records, library_id='family-a')
        original = store.identity.dimension
        calls = 0

        def invalidate_identity():
            nonlocal calls
            calls += 1
            if calls == 2:
                object.__setattr__(store.identity, 'dimension', True)

        try:
            with patch.object(module, '_read_secure_file', wraps=module._read_secure_file) as read:
                with self.assertRaises(BulkVectorUnavailable):
                    store.snapshot(tuple(replace(row) for row in records),
                                   library_id='family-a', check=invalidate_identity)
            self.assertEqual(read.call_count, 0)
        finally:
            object.__setattr__(store.identity, 'dimension', original)

    def test_warm_order_scope_identity_and_duplicate_fallbacks(self):
        from app.access import semantic_bulk_vectors as module
        store, records = self.build(((1, 'a', (1.0, 0.0)), (2, 'b', (0.0, 1.0))))
        first = store.snapshot(records, library_id='family-a')
        with patch.object(module, 'validate_artifact', wraps=module.validate_artifact) as validate:
            reordered = store.snapshot(tuple(reversed(records)), library_id='family-a')
            self.assertEqual(validate.call_count, len(records))
        self.assertEqual(reordered.rank((1.0, 0.0), ('1', '2')),
                         first.rank((1.0, 0.0), ('1', '2')))
        with self.assertRaises(BulkVectorUnavailable):
            store.snapshot((records[0], records[0]), library_id='family-a')
        with self.assertRaises(BulkVectorUnavailable):
            store.snapshot(records, library_id='family-b')
        original = store.identity.model_version
        try:
            object.__setattr__(store.identity, 'model_version', 'other-v1')
            with self.assertRaises(BulkVectorUnavailable):
                store.snapshot(records, library_id='family-a')
        finally:
            object.__setattr__(store.identity, 'model_version', original)

    def test_warm_snapshot_uses_private_copies_across_callbacks_and_after_return(self):
        from app.access import semantic_bulk_vectors as module
        store, records = self.build(((1, 'a', (1.0, 0.0)), (2, 'b', (0.0, 1.0))))
        store.snapshot(records, library_id='family-a')
        calls = 0

        def mutate_caller_artifacts():
            nonlocal calls
            calls += 1
            if calls == 3:
                # The first current row was already copied for the warm key.
                object.__setattr__(records[0], 'component_sha256', 'f' * 64)
            elif calls == 6:
                # This callback runs during the secure bulk read, after private
                # artifacts have been reconstructed from the captured rows.
                object.__setattr__(records[0], 'asset_id', '3')
                object.__setattr__(records[0], 'record_id', 'd' * 64)
                object.__setattr__(records[0], 'relative_path',
                                   f"image-vectors/{records[0].identity_sha256}/" + 'd' * 64 + '.npy')

        with patch.object(module, '_read_secure_file', wraps=module._read_secure_file) as read:
            snapshot = store.snapshot(records, library_id='family-a', check=mutate_caller_artifacts)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(snapshot.rank((1.0, 0.0), ('1', '2')), (('1', 1.0), ('2', 0.0)))
        object.__setattr__(records[1], 'asset_id', '4')
        self.assertEqual(snapshot.rank((1.0, 0.0), ('1', '2')), (('1', 1.0), ('2', 0.0)))

    def test_cold_snapshot_uses_private_copies_after_secure_read_callback(self):
        from app.access import semantic_bulk_vectors as module
        store, records = self.build(((1, 'a', (1.0, 0.0)), (2, 'b', (0.0, 1.0))))
        calls = 0

        def mutate_caller_artifacts():
            nonlocal calls
            calls += 1
            if calls == 8:
                object.__setattr__(records[0], 'asset_id', '3')
                object.__setattr__(records[0], 'record_id', 'd' * 64)
                object.__setattr__(records[0], 'relative_path',
                                   f"image-vectors/{records[0].identity_sha256}/" + 'd' * 64 + '.npy')

        with patch.object(module, '_read_secure_file', wraps=module._read_secure_file) as read:
            snapshot = store.snapshot(records, library_id='family-a', check=mutate_caller_artifacts)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(snapshot.rank((1.0, 0.0), ('1', '2')), (('1', 1.0), ('2', 0.0)))

    def test_wrong_primitive_types_refuse_on_warm_and_cold_cohorts(self):
        from app.access import semantic_bulk_vectors as module
        store, records = self.build(((1, 'a', (1.0, 0.0)),))
        store.snapshot(records, library_id='family-a')
        original = records[0]
        wrong_types = {
            'record_id': 1,
            'asset_id': 1,
            'source_sha256': 1,
            'model_name': 1,
            'artifact_sha256': 1,
            'preprocessing_sha256': 1,
            'vector_space_id': 1,
            'model_version': 1,
            'dimension': True,
            'normalization': 1,
            'identity_sha256': 1,
            'relative_path': 1,
            'file_sha256': 1,
            'component_sha256': 1,
            'created_at': True,
            'status': 1,
        }
        self.assertEqual(set(wrong_types), set(module._ARTIFACT_COHORT_FIELDS))
        for name, value in [*wrong_types.items(), ('created_at', 1.0)]:
            changed = replace(original, **{name: value})
            with self.subTest(field=name):
                with self.assertRaises(BulkVectorUnavailable):
                    store.snapshot((changed,), library_id='family-a')
                cold = BulkVectorStore(self.out, hashlib.sha256(self.out.read_bytes()).hexdigest(),
                                       'family-a', identity())
                with self.assertRaises(BulkVectorUnavailable):
                    cold.snapshot((changed,), library_id='family-a')

    def test_768d_scores_are_bitwise_legacy_equivalent_across_cached_blocks(self):
        import math
        from app.access import semantic_bulk_vectors as module
        ident = identity(768)
        vectors = []
        for index in range(7):
            raw = tuple(math.sin((index + 1) * (j + 1) * 0.017) for j in range(768))
            norm = math.sqrt(math.fsum(x * x for x in raw))
            vector = tuple(x / norm for x in raw)
            vectors.append((index + 1, 'abcdef0'[index], vector))
        store, records = self.build(tuple(vectors), ident)
        query = _canonical_components(VectorRecord('1', ident, vectors[0][2], records[0].component_sha256), ident)
        block_patch = patch.object(module, '_CACHE_BLOCK_BYTES', 768 * 8 * 2)
        block_patch.start()
        self.addCleanup(block_patch.stop)
        snapshot = store.snapshot(records, library_id='family-a')
        actual = snapshot.rank(query, tuple(record.asset_id for record in records))
        expected = []
        for row, (_, _, vector) in zip(records, vectors):
            canonical = _canonical_components(VectorRecord(row.asset_id, ident, vector, row.component_sha256), ident)
            expected.append((row.asset_id, math.fsum(a * b for a, b in zip(query, canonical))))
        expected.sort(key=lambda value: (-value[1], int(value[0])))
        self.assertEqual([(aid, struct.pack('>d', score)) for aid, score in actual],
                         [(aid, struct.pack('>d', score)) for aid, score in expected])

    def test_f64_cached_rank_matches_legacy_fsum_across_dimensions_and_query_ranges(self):
        import math
        from app.access import semantic_bulk_vectors as module

        asset_ids = (9, 2, 7, 101, 13)
        for dimension in (2, 3, 128, 768, module.MAX_DIMENSION):
            with self.subTest(dimension=dimension):
                ident = identity(dimension)
                basis0 = (1.0,) + (0.0,) * (dimension - 1)
                basis1 = (0.0, 1.0) + (0.0,) * (dimension - 2)
                neg_basis0 = (-1.0,) + (0.0,) * (dimension - 1)
                diagonal = (0.6, 0.8) + (0.0,) * (dimension - 2)
                vectors = ((9, 'a', basis0), (2, 'b', basis0), (7, 'c', basis1),
                           (101, 'd', neg_basis0), (13, 'e', diagonal))
                vectors_by_id = sorted(vectors, key=lambda row: row[0])
                self.out = self.base / f'cohort-{dimension}.bulk'
                store, records = self.build(vectors, ident)
                records_by_id = {record.asset_id: record for record in records}
                original_file = self.out.read_bytes()
                expected_disk_payload = b''.join(
                    struct.pack(f'>{dimension}f', *vector) for _, _, vector in vectors_by_id)
                self.assertEqual(module._decode_container(original_file)[1].tobytes(),
                                 expected_disk_payload)
                queries = (
                    tuple(0.5 if index % 2 == 0 else -0.25 for index in range(dimension)),
                    (1e-300, -2e-300) + (0.0,) * (dimension - 2),
                    (1e308,) + (0.0,) * (dimension - 1),
                )
                # Five rows force two complete blocks plus a one-row tail.
                block_bytes = dimension * 8 * 2
                block_patch = patch.object(module, '_CACHE_BLOCK_BYTES', block_bytes)
                block_patch.start()
                self.addCleanup(block_patch.stop)
                snapshot = store.snapshot(records, library_id='family-a')
                matrix = snapshot._matrix
                self.assertIs(type(matrix), tuple)
                self.assertEqual(len(matrix), 3)
                blocks, rows_per_block, layout_tag = matrix
                self.assertIs(type(blocks), tuple)
                self.assertEqual(rows_per_block, 2)
                self.assertEqual(layout_tag,
                    ('canonical_f64_native_v1', sys.byteorder, dimension, len(records),
                     identity_sha256(ident)))
                self.assertEqual(len(blocks), 3)
                self.assertTrue(all(type(block) is bytes for block in blocks))
                self.assertEqual(tuple(map(len, blocks)),
                    (dimension * 8 * 2, dimension * 8 * 2, dimension * 8))
                for index, (aid, _, vector) in enumerate(vectors_by_id):
                    record = records_by_id[str(aid)]
                    canonical = _canonical_components(VectorRecord(
                        record.asset_id, ident, vector, record.component_sha256), ident)
                    block = blocks[index // rows_per_block]
                    actual_canonical = struct.unpack_from(
                        f'={dimension}d', block, (index % rows_per_block) * dimension * 8)
                    self.assertEqual(actual_canonical, canonical)
                self.assertEqual(snapshot.count, 5)
                for query in queries:
                    expected = []
                    for aid, _, vector in vectors_by_id:
                        record = records_by_id[str(aid)]
                        canonical = _canonical_components(VectorRecord(
                            record.asset_id, ident, vector, record.component_sha256), ident)
                        expected.append((record.asset_id, math.fsum(
                            left * right for left, right in zip(query, canonical))))
                    expected.sort(key=lambda row: (-row[1], int(row[0])))
                    actual = snapshot.rank(query, tuple(str(aid) for aid in asset_ids))
                    self.assertEqual([(aid, struct.pack('>d', score)) for aid, score in actual],
                                     [(aid, struct.pack('>d', score)) for aid, score in expected])
                    sparse_ids = ('101', '2')
                    sparse_expected = tuple(row for row in expected if row[0] in sparse_ids)
                    self.assertEqual([(aid, struct.pack('>d', score)) for aid, score in
                                      snapshot.rank(query, sparse_ids)],
                                     [(aid, struct.pack('>d', score)) for aid, score in sparse_expected])
                    self.assertEqual(snapshot.rank(query, ()), ())
                tied = snapshot.rank(basis0, ('9', '2'))
                self.assertEqual(tuple(aid for aid, _ in tied), ('2', '9'))
                self.assertEqual(self.out.read_bytes(), original_file)
                with patch.object(module, '_read_secure_file', wraps=module._read_secure_file) as read:
                    warm = store.snapshot(tuple(replace(record) for record in records),
                                          library_id='family-a')
                self.assertEqual(read.call_count, 1)
                self.assertEqual(read.call_args.args[1], store.file_sha256)
                self.assertEqual(hashlib.sha256(original_file).hexdigest(), store.file_sha256)
                self.assertEqual(warm.rank(queries[0], tuple(str(aid) for aid in asset_ids)),
                                 snapshot.rank(queries[0], tuple(str(aid) for aid in asset_ids)))
                self.assertEqual(self.out.read_bytes(), original_file)

    def test_empty_bulk_snapshot_has_empty_rank_and_cache(self):
        from app.access import semantic_bulk_vectors as module
        ident = identity(3)
        store = write_bulk_vectors(self.out, self.root, (), ident, 'family-a')
        snapshot = store.snapshot((), library_id='family-a')
        self.assertEqual(snapshot.count, 0)
        self.assertEqual(snapshot.rank((1.0, -2.0, 3.0), ()), ())
        self.assertEqual(snapshot._matrix,
            ((), max(1, module._CACHE_BLOCK_BYTES // (3 * 8)),
             ('canonical_f64_native_v1', sys.byteorder, 3, 0, identity_sha256(ident))))
        self.assertEqual(module._decode_container(self.out.read_bytes())[1].tobytes(), b'')

    def test_malformed_matrix_layout_and_warm_cache_refuse(self):
        from app.access import semantic_bulk_vectors as module
        ident = identity(3)
        store, records = self.build(((1, 'a', (1.0, 0.0, 0.0)),
                                     (2, 'b', (0.0, 1.0, 0.0)),
                                     (3, 'c', (0.0, 0.0, 1.0))))
        snapshot = store.snapshot(records, library_id='family-a')
        blocks, rows_per_block, tag = snapshot._matrix
        damaged_blocks = list(blocks)
        variants = (
            snapshot._matrix[:2],
            (blocks, rows_per_block, ('canonical_f64_native_v1',
                                      'big' if sys.byteorder == 'little' else 'little', 3, 3,
                                      identity_sha256(ident))),
            (blocks, rows_per_block, ('canonical_f64_native_v1', sys.byteorder, 2, 3,
                                      identity_sha256(ident))),
            (blocks, rows_per_block, ('canonical_f64_native_v1', sys.byteorder, 3, 4,
                                      identity_sha256(ident))),
            (blocks, rows_per_block, ('canonical_f64_native_v1', sys.byteorder, 3, 3,
                                      'f' * 64)),
            (blocks, rows_per_block, ('canonical_f64_native_v1', sys.byteorder, 3, 3)),
            (damaged_blocks, rows_per_block, tag),
            ((bytearray(blocks[0]),) + blocks[1:], rows_per_block, tag),
            ((blocks[0][:-1],) + blocks[1:], rows_per_block, tag),
            ((blocks[0] + b'\x00',) + blocks[1:], rows_per_block, tag),
            ((blocks[0][:-24],) + blocks[1:], rows_per_block, tag),
            ((blocks[0] + bytes(24),) + blocks[1:], rows_per_block, tag),
            (blocks, 0, tag),
            (blocks, True, tag),
            (blocks, rows_per_block + 1, tag),
        )
        for index, matrix in enumerate(variants):
            with self.subTest(matrix_variant=index):
                object.__setattr__(snapshot, '_matrix', matrix)
                with self.assertRaises(BulkVectorUnavailable):
                    snapshot.rank((1.0, 0.0, 0.0), ('1',))
        object.__setattr__(snapshot, '_matrix', (blocks, rows_per_block, tag))

        cache = store._cache
        corrupted_matrix = (blocks, 0, tag)
        object.__setattr__(store, '_cache', (cache[0], cache[1], corrupted_matrix))
        with self.assertRaises(BulkVectorUnavailable):
            store.snapshot(tuple(replace(record) for record in records), library_id='family-a')

    def test_malformed_cache_wrapper_refuses_before_reuse(self):
        store, records = self.build(((1, 'a', (1.0, 0.0)),))
        store.snapshot(records, library_id='family-a')
        valid_cache = store._cache
        equality_calls = []

        class HostileCacheRow:
            def __eq__(self, _other):
                equality_calls.append('called')
                raise RuntimeError('malformed cached row must not be compared')

        malformed = (
            ((), valid_cache[1], valid_cache[2]),
            valid_cache[:2],
            (valid_cache[0], list(valid_cache[1]), valid_cache[2]),
            (valid_cache[0], (HostileCacheRow(),), valid_cache[2]),
            (('bad-file-hash', valid_cache[0][1], 'family-a', valid_cache[0][3]),
             valid_cache[1], valid_cache[2]),
        )
        try:
            for index, value in enumerate(malformed):
                with self.subTest(cache_shape=index):
                    object.__setattr__(store, '_cache', value)
                    with self.assertRaises(BulkVectorUnavailable):
                        store.snapshot(tuple(replace(record) for record in records),
                                       library_id='family-a')
            self.assertEqual(equality_calls, [])
        finally:
            object.__setattr__(store, '_cache', valid_cache)
        self.assertEqual(store.snapshot(tuple(replace(record) for record in records),
                                         library_id='family-a').count, 1)

    def test_cache_replacement_from_last_secure_read_callback_refuses(self):
        from app.access import semantic_bulk_vectors as module

        store, records = self.build(((1, 'a', (1.0, 0.0)),))
        store.snapshot(records, library_id='family-a')
        valid_cache = store._cache
        malformed = ((), valid_cache[1], valid_cache[2])
        original_read = module._read_secure_file
        inside_read = False
        read_checks = 0

        def marked_read(path, expected_sha, check, charge):
            nonlocal inside_read
            inside_read = True
            try:
                return original_read(path, expected_sha, check, charge)
            finally:
                inside_read = False

        def replace_cache_during_read():
            nonlocal read_checks
            if inside_read:
                read_checks += 1
                if read_checks == 2:
                    # The secure read's final callback runs after descriptor
                    # and path verification; the next cache-pointer read must
                    # reject this replacement before indexing it.
                    object.__setattr__(store, '_cache', malformed)

        try:
            with patch.object(module, '_read_secure_file', side_effect=marked_read):
                with self.assertRaises(BulkVectorUnavailable):
                    store.snapshot(tuple(replace(record) for record in records),
                                   library_id='family-a', check=replace_cache_during_read)
            self.assertEqual(read_checks, 2)
        finally:
            object.__setattr__(store, '_cache', valid_cache)
        self.assertEqual(store.snapshot(tuple(replace(record) for record in records),
                                         library_id='family-a').count, 1)

    def test_cold_matrix_derivation_refuses_same_dimension_identity_mutation(self):
        from app.access import semantic_bulk_vectors as module
        store, records = self.build(((1, 'a', (1.0, 0.0)), (2, 'b', (0.0, 1.0))))
        original_version = store.identity.model_version
        original_canonical = module._canonical_components

        def mutate_identity(record, identity_value):
            result = original_canonical(record, identity_value)
            object.__setattr__(store.identity, 'model_version', 'mutated-generation')
            return result

        try:
            with patch.object(module, '_canonical_components', side_effect=mutate_identity):
                with self.assertRaises(BulkVectorUnavailable):
                    store.snapshot(records, library_id='family-a')
            self.assertIsNone(store._cache)
        finally:
            object.__setattr__(store.identity, 'model_version', original_version)

    def test_rank_checks_skipped_rows_and_propagates_callback_failure(self):
        store, records = self.build(((1, 'a', (1.0, 0.0)), (2, 'b', (0.0, 1.0)),
                                     (3, 'c', (-1.0, 0.0))))
        snapshot = store.snapshot(records, library_id='family-a')
        checks = []

        def cancel_on_second_row():
            checks.append(True)
            if len(checks) == 2:
                raise RuntimeError('rank cancelled across skipped rows')

        from app.access import semantic_bulk_vectors as module
        with patch.object(module, 'memoryview', side_effect=AssertionError('view before selected row'),
                          create=True):
            with self.assertRaisesRegex(RuntimeError, 'rank cancelled across skipped rows'):
                snapshot.rank((0.0, 1.0), ('3',), check=cancel_on_second_row)
        self.assertEqual(len(checks), 2)

    def test_rank_refuses_callback_time_identity_and_artifact_generation_changes(self):
        from app.access import semantic_bulk_vectors as module

        store, records = self.build(((1, 'a', (1.0, 0.0)), (2, 'b', (0.0, 1.0))))
        base = store.snapshot(records, library_id='family-a')

        for field, replacement in (('model_version', 'other-same-dimension'),
                                   ('dimension', 3)):
            with self.subTest(identity_field=field):
                original = getattr(base.identity, field)
                calls = 0

                def change_identity():
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        object.__setattr__(base.identity, field, replacement)

                try:
                    with self.assertRaises(BulkVectorUnavailable):
                        base.rank((1.0, 0.0), ('1', '2'), check=change_identity)
                    self.assertEqual(calls, 3)  # precheck plus both ordered rows
                finally:
                    object.__setattr__(base.identity, field, original)
                self.assertEqual(base.rank((1.0, 0.0), ('1', '2'))[0][0], '1')

        mutable_artifact = base._artifacts[0]
        original_asset_id = mutable_artifact.asset_id
        calls = 0

        def relabel_during_row_callback():
            nonlocal calls
            calls += 1
            if calls == 2:
                object.__setattr__(mutable_artifact, 'asset_id', '3')

        try:
            with self.assertRaises(BulkVectorUnavailable):
                base.rank((1.0, 0.0), ('1', '2'), check=relabel_during_row_callback)
            self.assertEqual(calls, 3)
        finally:
            object.__setattr__(mutable_artifact, 'asset_id', original_asset_id)
        self.assertEqual(base.rank((1.0, 0.0), ('1', '2'))[0][0], '1')

    def test_rank_refuses_replaced_snapshot_identity_matrix_and_id_slots(self):
        store, records = self.build(((1, 'a', (1.0, 0.0)), (2, 'b', (0.0, 1.0))))
        snapshot = store.snapshot(records, library_id='family-a')
        replacements = (
            ('_matrix', tuple(list(snapshot._matrix))),
            ('_ids', frozenset(('1',))),
            ('_asset_ids', tuple(list(snapshot._asset_ids))),
            ('_identity_sha256', 'f' * 64),
            ('identity', replace(snapshot.identity, model_version='same-dimension-replacement')),
        )
        for slot, replacement in replacements:
            with self.subTest(slot=slot):
                original = getattr(snapshot, slot)
                calls = 0

                def replace_during_rank():
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        object.__setattr__(snapshot, slot, replacement)

                try:
                    with self.assertRaises(BulkVectorUnavailable):
                        snapshot.rank((1.0, 0.0), ('1', '2'), check=replace_during_rank)
                finally:
                    object.__setattr__(snapshot, slot, original)
                self.assertEqual(snapshot.rank((1.0, 0.0), ('1', '2'))[0][0], '1')

    def test_snapshot_constructor_rejects_exact_primitive_tag_spoofs(self):
        from app.access.semantic_bulk_vectors import BulkVectorSnapshot
        from app.access import semantic_bulk_vectors as module

        ident = identity(2)
        store, records = self.build(((1, 'a', (1.0, 0.0)), (2, 'b', (0.0, 1.0))))
        snapshot = store.snapshot(records, library_id='family-a')
        blocks, rows_per_block, tag = snapshot._matrix
        malformed = (
            (blocks, True, tag),
            (blocks, rows_per_block, (tag[0], tag[1], True, tag[3], tag[4])),
            (blocks, rows_per_block, (tag[0], tag[1], tag[2], True, tag[4])),
            (blocks, rows_per_block, (tag[0], 1, tag[2], tag[3], tag[4])),
            (list(blocks), rows_per_block, tag),
            ((bytearray(blocks[0]),) + blocks[1:], rows_per_block, tag),
        )
        for index, matrix in enumerate(malformed):
            with self.subTest(matrix=index), self.assertRaises(BulkVectorUnavailable):
                BulkVectorSnapshot(records, ident, matrix)
        self.assertEqual(module._native_matrix_parts(snapshot._matrix, 2, 2,
                                                       snapshot._identity_sha256)[0], blocks)

    def test_snapshot_constructor_rejects_artifactlike_rows_before_property_access(self):
        from app.access.semantic_bulk_vectors import BulkVectorSnapshot

        ident = identity(2)
        store, records = self.build(((1, 'a', (1.0, 0.0)),))
        matrix = store.snapshot(records, library_id='family-a')._matrix
        property_calls = []

        class ForgedArtifactLike:
            @property
            def asset_id(self):
                property_calls.append('accessed')
                raise RuntimeError('must not inspect a forged row')

        with self.assertRaises(BulkVectorUnavailable):
            BulkVectorSnapshot((ForgedArtifactLike(),), ident, matrix)
        self.assertEqual(property_calls, [])

    def test_rank_callbacks_cover_block_boundaries_and_preserve_baseexceptions(self):
        from app.access import semantic_bulk_vectors as module

        store, records = self.build(((1, 'a', (1.0, 0.0)), (2, 'b', (0.0, 1.0)),
                                     (3, 'c', (-1.0, 0.0))))
        with patch.object(module, '_CACHE_BLOCK_BYTES', 16):
            snapshot = store.snapshot(records, library_id='family-a')
            self.assertEqual(snapshot._matrix[1], 1)
            calls = []

            def trace():
                calls.append(len(calls))

            result = snapshot.rank((1.0, 0.0), ('1', '2', '3'), check=trace)
            self.assertEqual(calls, [0, 1, 2, 3])  # initial check and each row, including block edges
            self.assertEqual(tuple(aid for aid, _ in result), ('1', '2', '3'))

            for error in (KeyboardInterrupt('interrupt'), CancelledError('cancelled')):
                calls.clear()

                def raise_same_error(error=error):
                    calls.append('called')
                    raise error

                with self.assertRaises(type(error)) as caught:
                    snapshot.rank((1.0, 0.0), ('1', '2', '3'), check=raise_same_error)
                self.assertIs(caught.exception, error)
                self.assertEqual(calls, ['called'])

    def test_matching_checksum_nonunit_and_boolean_schema_are_refused(self):
        from app.access import semantic_bulk_vectors as module
        store, records = self.build(((1, 'a', (1.0, 0.0)),))
        raw = self.out.read_bytes()
        start = len(_MAGIC) + 4
        header_size = struct.unpack_from('>I', raw, len(_MAGIC))[0]
        header = json.loads(raw[start:start + header_size])
        bad_records = (replace(records[0], component_sha256=canonical_vector_checksum((2.0, 0.0))),)
        header['cohort_sha256'] = module._cohort_digest(bad_records, lambda: None)
        encoded = module._canonical_json(header)
        bad = _MAGIC + struct.pack('>I', len(encoded)) + encoded + struct.pack('>2f', 2.0, 0.0)
        self.out.write_bytes(bad)
        bad_store = BulkVectorStore(self.out, hashlib.sha256(bad).hexdigest(), 'family-a', identity())
        with self.assertRaises(BulkVectorUnavailable):
            bad_store.snapshot(bad_records, library_id='family-a')
        header = json.loads(raw[start:start + header_size])
        header['schema'] = True
        encoded = module._canonical_json(header)
        bad = _MAGIC + struct.pack('>I', len(encoded)) + encoded + raw[start + header_size:]
        self.out.write_bytes(bad)
        bad_store = BulkVectorStore(self.out, hashlib.sha256(bad).hexdigest(), 'family-a', identity())
        with self.assertRaises(BulkVectorUnavailable):
            bad_store.snapshot(records, library_id='family-a')

    def test_budget_charge_happens_before_payload_read_and_valueerror_is_preserved(self):
        store, records = self.build(((1, 'a', (1.0, 0.0)),))
        original = ValueError('budget value error')
        def refuse(_amount):
            raise original
        with patch('app.access.semantic_bulk_vectors.os.read', side_effect=AssertionError('read before budget')):
            with self.assertRaises(ValueError) as caught:
                store.snapshot(records, library_id='family-a', charge=refuse)
        self.assertIs(caught.exception, original)
        with self.assertRaises(ValueError) as caught:
            write_bulk_vectors(self.base / 'cancelled.bulk', self.root, records, identity(), 'family-a',
                check=lambda: (_ for _ in ()).throw(original))
        self.assertIs(caught.exception, original)

    def test_deep_malformed_header_is_fixed_refusal_before_model(self):
        store, records = self.build(((1, 'a', (1.0, 0.0)),))
        encoded = b'{"schema":1,"nested":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}'
        raw = _MAGIC + struct.pack('>I', len(encoded)) + encoded
        self.out.write_bytes(raw)
        bad = BulkVectorStore(self.out, hashlib.sha256(raw).hexdigest(), 'family-a', identity())
        with self.assertRaises(BulkVectorUnavailable):
            bad.snapshot(records, library_id='family-a')

    def test_extreme_integer_query_component_has_fixed_refusal(self):
        store, records = self.build(((1, 'a', (1.0, 0.0)),))
        snapshot = store.snapshot(records, library_id='family-a')
        with self.assertRaises(BulkVectorUnavailable):
            snapshot.rank((10 ** 400, 0), ('1',))


if __name__ == "__main__":
    unittest.main()
