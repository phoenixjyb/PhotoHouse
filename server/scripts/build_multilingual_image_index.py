#!/usr/bin/env python3
"""Prepare an unpublished private SigLIP2 image cohort; plan-only by default.

Only explicitly reviewed JPEG/PNG files are read. A completed manifest is
written last. No database, legacy index, service or production config is used.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import struct
import time

from semantic_siglip import SiglipModel, DIMENSION, SPACE
import qualify_multilingual_scenes as qualification
from qualify_semantic_pair import canonical, output_target, write_record, quiet_dependencies
from qualify_semantic_scenes import inspect_images
from image_embedding_receipts import inspect_checkpoint, verify_checkpoint, recipe_sha256
from app.access.model_deployment import _load_private_document
from app.access.private_storage import require_private_directory, require_private_file
from app.access.visual_candidates import (VectorSpaceIdentity, VectorRecord,
    canonical_vector_checksum, _canonical_components)
from app.access.visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256, validate_artifact
from app.access.visual_vector_loader import _decode_npy, _read_vector

ROOT = qualification.ROOT
MAX_IMAGES = 512
_SHA = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
_ID = re.compile(r'[1-9][0-9]{0,18}\Z', re.ASCII)
_LIBRARY = re.compile(r'[a-z0-9][a-z0-9._-]{0,63}\Z', re.ASCII)


class IndexRefused(ValueError):
    def __init__(self):
        super().__init__('multilingual_index_unavailable')


def validate_cohort(value):
    if (type(value) is not dict or set(value) != {'schema', 'library_id', 'reviewed', 'assets'}
            or value['schema'] != 'photohouse.multilingual_image_cohort.v1'
            or type(value['library_id']) is not str or not _LIBRARY.fullmatch(value['library_id'])
            or value['reviewed'] is not True or type(value['assets']) is not list
            or not 1 <= len(value['assets']) <= MAX_IMAGES):
        raise IndexRefused()
    seen = set()
    for asset in value['assets']:
        if (type(asset) is not dict or set(asset) != {'asset_id', 'path', 'sha256'}
                or type(asset['asset_id']) is not str or not _ID.fullmatch(asset['asset_id'])
                or int(asset['asset_id']) > 2**63-1 or asset['asset_id'] in seen
                or type(asset['sha256']) is not str or not _SHA.fullmatch(asset['sha256'])
                or type(asset['path']) is not str or not Path(asset['path']).is_absolute()
                or '..' in Path(asset['path']).parts):
            raise IndexRefused()
        seen.add(asset['asset_id'])
    return json.loads(canonical(value))


def cohort_sha256(value):
    value = validate_cohort(value)
    content = {**value, 'assets': [{k: a[k] for k in ('asset_id', 'sha256')}
                                  for a in value['assets']]}
    return hashlib.sha256(canonical(content)).hexdigest()


def npy_bytes(vector):
    if type(vector) not in (tuple, list) or len(vector) != DIMENSION:
        raise IndexRefused()
    canonical_vector_checksum(vector)
    if abs(math.sqrt(math.fsum(x*x for x in vector))-1) > 1e-3:
        raise IndexRefused()
    header = b"{'descr': '<f4', 'fortran_order': False, 'shape': (768,), }"
    header += b' ' * ((64 - (10 + len(header) + 1) % 64) % 64) + b'\n'
    raw = b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + struct.pack('<768f', *vector)
    if _decode_npy(raw, DIMENSION) is None:
        raise IndexRefused()
    return raw


def _record_id(cohort_digest, asset_id, identity_digest):
    return hashlib.sha256(canonical({'schema': 'photohouse.siglip2_index_record.v1',
        'cohort_sha256': cohort_digest, 'asset_id': asset_id,
        'identity_sha256': identity_digest})).hexdigest()


def configuration(path):
    value = _load_private_document(path, source_root=ROOT.parent)
    if (type(value) is not dict or set(value) != {'schema', 'model_directory', 'artifacts',
            'package_versions', 'cohort', 'max_elapsed_seconds'}
            or value['schema'] != 'photohouse.multilingual_image_index_run.v1'
            or type(value['model_directory']) is not str or type(value['cohort']) is not str
            or value['artifacts'] != qualification.OFFICIAL_ARTIFACTS
            or value['package_versions'] != qualification.EXPECTED_PACKAGES
            or type(value['max_elapsed_seconds']) is not int
            or not 30 <= value['max_elapsed_seconds'] <= 1800):
        raise IndexRefused()
    cohort = validate_cohort(_load_private_document(value['cohort'], source_root=ROOT.parent))
    return value, cohort


def execute(config_path, output, *, model_loader=SiglipModel.load):
    config, cohort = configuration(config_path)
    target = output_target(output)
    pins = inspect_images({'images': [dict(id=a['asset_id'], path=a['path'], sha256=a['sha256'])
                                     for a in cohort['assets']]})
    start = time.monotonic()
    deadline = start + config['max_elapsed_seconds']
    def check():
        if time.monotonic() >= deadline:
            raise IndexRefused()
    target.mkdir(mode=0o700)
    require_private_directory(target)
    fingerprint = cohort_sha256(cohort)
    write_record(target, 'started.json', {'cohort_sha256': fingerprint,
        'image_count': len(pins), 'production_published': False, 'activation_performed': False})
    model = model_loader(model_directory=config['model_directory'], artifacts=config['artifacts'],
                         package_versions=config['package_versions'])
    identity = model.image_identity
    if identity.dimension != DIMENSION or identity.vector_space_id != SPACE:
        raise IndexRefused()
    digest = identity_sha256(identity)
    directory = target / 'image-vectors' / digest
    directory.parent.mkdir(mode=0o700)
    directory.mkdir(mode=0o700)
    require_private_directory(directory)
    summaries = []
    created = int(time.time())
    timings = []
    for asset in cohort['assets']:
        check()
        began = time.monotonic()
        vector = model.encode_image(pins[asset['asset_id']], check=check)
        raw = npy_bytes(vector)
        decoded = _decode_npy(raw, DIMENSION)
        record_id = _record_id(fingerprint, asset['asset_id'], digest)
        record = ImmutableVectorArtifact(record_id=record_id, asset_id=asset['asset_id'],
            source_sha256=asset['sha256'], model_name='siglip2-base-p16-256',
            artifact_sha256=identity.artifact_sha256, preprocessing_sha256=identity.preprocessing_sha256,
            vector_space_id=identity.vector_space_id, model_version=identity.model_version,
            dimension=DIMENSION, normalization='unit_l2', identity_sha256=digest,
            relative_path=f'image-vectors/{digest}/{record_id}.npy',
            file_sha256=hashlib.sha256(raw).hexdigest(), component_sha256=canonical_vector_checksum(decoded),
            created_at=created)
        if not validate_artifact(record, identity):
            raise IndexRefused()
        fd = os.open(target / record.relative_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'wb') as stream:
            require_private_file(target / record.relative_path)
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        write_record(directory, record_id + '.json', asdict(record))
        metadata = directory / (record_id + '.json')
        summaries.append({'asset_id': record.asset_id, 'record_id': record_id,
            'metadata_sha256': hashlib.sha256(metadata.read_bytes()).hexdigest()})
        verify_checkpoint(pins[asset['asset_id']])
        check()
        timings.append(time.monotonic()-began)
    model.verify()
    for pin in pins.values():
        verify_checkpoint(pin)
    check()
    manifest = {'schema': 'photohouse.multilingual_image_index.v1',
        'library_id': cohort['library_id'], 'cohort_sha256': fingerprint,
        'model_receipt': model.receipt(), 'records': summaries,
        'image_timings_seconds': timings, 'complete': True,
        'production_published': False, 'activation_performed': False}
    if len(canonical(manifest))+1 > 128*1024:
        raise IndexRefused()
    # Absence of this final record means the entire candidate is incomplete.
    write_record(target, 'index.json', manifest)
    inspect_index(target / 'index.json', expected_library=cohort['library_id'], expected_cohort=cohort)
    return {'status': 'private_multilingual_index_prepared', 'image_count': len(pins),
        'cohort_sha256': fingerprint, 'index_sha256': hashlib.sha256(canonical(manifest)+b'\n').hexdigest(),
        'image_identity': asdict(identity), 'production_published': False, 'activation_performed': False}


def inspect_index(path, *, expected_library, expected_cohort):
    """Verify a complete unpublished cohort; no DB insertion or model work."""
    cohort = validate_cohort(expected_cohort)
    if cohort['library_id'] != expected_library:
        raise IndexRefused()
    expected_sources = {a['asset_id']: a['sha256'] for a in cohort['assets']}
    root = qualification.canonical_private_directory(str(Path(path).parent))
    if Path(path).name != 'index.json':
        raise IndexRefused()
    value = _load_private_document(path, source_root=ROOT.parent)
    if (type(value) is not dict or set(value) != {'schema', 'library_id', 'cohort_sha256',
            'model_receipt', 'records', 'image_timings_seconds', 'complete',
            'production_published', 'activation_performed'}
            or value['schema'] != 'photohouse.multilingual_image_index.v1'
            or value['library_id'] != expected_library or value['complete'] is not True
            or value['production_published'] is not False or value['activation_performed'] is not False
            or type(value['cohort_sha256']) is not str or not _SHA.fullmatch(value['cohort_sha256'])
            or value['cohort_sha256'] != cohort_sha256(cohort)
            or type(value['records']) is not list or not 1 <= len(value['records']) <= MAX_IMAGES
            or type(value['image_timings_seconds']) is not list
            or len(value['image_timings_seconds']) != len(value['records'])
            or any(type(x) not in (float, int) or not math.isfinite(x) or x < 0
                   for x in value['image_timings_seconds'])):
        raise IndexRefused()
    receipt = value['model_receipt']
    if (type(receipt) is not dict or set(receipt) != {'schema', 'image_identity', 'text_identity',
            'recipes', 'cpu_threads', 'relevance_accepted', 'activation_approved'}
            or receipt['schema'] != 'photohouse.siglip2_adapter_receipt.v1'
            or receipt['activation_approved'] is not False or receipt['relevance_accepted'] is not False
            or receipt['cpu_threads'] != 2):
        raise IndexRefused()
    if type(receipt['recipes']) is not dict or set(receipt['recipes']) != {'image', 'text'}:
        raise IndexRefused()
    identities = {}
    for role in ('image', 'text'):
        identity = VectorSpaceIdentity(**receipt[role+'_identity'])
        recipe = receipt['recipes'][role]
        if (identity.dimension != DIMENSION or identity.vector_space_id != SPACE
                or identity.artifact_sha256 != qualification.OFFICIAL_ARTIFACTS['model.safetensors']['sha256']
                or identity.preprocessing_sha256 != recipe_sha256(recipe)
                or recipe['role'] != role
                or recipe.get('model_id') != qualification.MODEL_ID
                or recipe.get('revision') != qualification.REVISION
                or recipe.get('artifacts') != qualification.OFFICIAL_ARTIFACTS
                or recipe.get('package_versions') != qualification.EXPECTED_PACKAGES):
            raise IndexRefused()
        identity_sha256(identity)
        identities[role] = identity
    if {s.get('asset_id') for s in value['records'] if type(s) is dict} != set(expected_sources):
        raise IndexRefused()
    records, seen = [], set()
    for summary in value['records']:
        if (type(summary) is not dict or set(summary) != {'asset_id', 'record_id', 'metadata_sha256'}
                or any(type(summary[k]) is not str or not _SHA.fullmatch(summary[k])
                       for k in ('record_id', 'metadata_sha256'))
                or type(summary['asset_id']) is not str or not _ID.fullmatch(summary['asset_id'])
                or summary['asset_id'] in seen):
            raise IndexRefused()
        seen.add(summary['asset_id'])
        if summary['record_id'] != _record_id(value['cohort_sha256'], summary['asset_id'],
                                              identity_sha256(identities['image'])):
            raise IndexRefused()
        metadata = root / 'image-vectors' / identity_sha256(identities['image']) / (summary['record_id']+'.json')
        pin = inspect_checkpoint(metadata, summary['metadata_sha256'])
        record = ImmutableVectorArtifact(**_load_private_document(metadata, source_root=ROOT.parent))
        verify_checkpoint(pin)
        vector = _read_vector(root, record) if validate_artifact(record, identities['image']) else None
        if (record.record_id != summary['record_id'] or record.asset_id != summary['asset_id']
                or record.source_sha256 != expected_sources[record.asset_id]
                or vector is None):
            raise IndexRefused()
        _canonical_components(VectorRecord(record.asset_id, identities['image'], vector,
            record.component_sha256), identities['image'])
        records.append(record)
    return value, tuple(records), identities


def run(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, _message):
            raise IndexRefused()
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('--run', action='store_true')
        parser.add_argument('--configuration', type=Path)
        parser.add_argument('--output-directory', type=Path)
        args = parser.parse_args(argv)
        if not args.run:
            if args.configuration is not None or args.output_directory is not None:
                raise IndexRefused()
            print(json.dumps({'status': 'multilingual_index_plan', 'max_images': MAX_IMAGES,
                'dimension': DIMENSION, 'private_files_read': False, 'models_loaded': False,
                'activation_performed': False}))
            return 0
        if args.configuration is None or args.output_directory is None:
            raise IndexRefused()
        previous = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            with quiet_dependencies():
                result = execute(args.configuration, args.output_directory)
        finally:
            logging.disable(previous)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except Exception:
        print('{"error":"multilingual_index_unavailable"}', file=__import__('sys').stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(run())
