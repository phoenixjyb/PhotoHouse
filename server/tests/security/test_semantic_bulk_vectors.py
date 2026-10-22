"""Synthetic integrity, cohort, and exact-ranking checks for bulk vectors."""
from dataclasses import fields, replace
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
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
            {'created_at': 2},
            {'source_sha256': 'd' * 64},
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
        with patch.object(module, '_CACHE_BLOCK_BYTES', 768 * 8 * 2):
            snapshot = store.snapshot(records, library_id='family-a')
        actual = snapshot.rank(query, tuple(record.asset_id for record in records))
        expected = []
        for row, (_, _, vector) in zip(records, vectors):
            canonical = _canonical_components(VectorRecord(row.asset_id, ident, vector, row.component_sha256), ident)
            expected.append((row.asset_id, math.fsum(a * b for a, b in zip(query, canonical))))
        expected.sort(key=lambda value: (-value[1], int(value[0])))
        self.assertEqual([(aid, struct.pack('>d', score)) for aid, score in actual],
                         [(aid, struct.pack('>d', score)) for aid, score in expected])

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
