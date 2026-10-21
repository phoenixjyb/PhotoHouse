"""Full frozen-catalog canary fixtures; no household store or actual model."""
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import sqlite3
import sys

import pytest

from test_qualify_library_semantic import generated_index
import library_semantic_index as library_index
import qualify_library_semantic as subject
from semantic_coverage_qualification import omission_review_draft, CoverageQualificationRefused


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


@pytest.fixture
def full_catalog(generated_index, tmp_path):
    index, model, manifest, records, root = generated_index
    index = root / 'index.json'
    snapshot = {'schema': 'photohouse.library_semantic_snapshot.v1',
                'library_id': manifest['library_id'], 'assets': []}
    summaries = []
    for record in records:
        source_path = str(tmp_path / 'never-open-originals' / f'{record.asset_id}.jpg')
        snapshot['assets'].append({'asset_id': record.asset_id, 'path': source_path,
            'sha256': record.source_sha256, 'mime': 'image/jpeg', 'width': 16, 'height': 16})
        summaries.append({'status': 'ready', 'asset_id': record.asset_id,
            'source_path': source_path, 'source_sha256': record.source_sha256,
            'source_stat_identity': {}, 'derived_sha256': 'd' * 64,
            'preparation_recipe_sha256': 'e' * 64, 'observed_format': 'JPEG',
            'observed_width': 16, 'observed_height': 16, 'orientation': 1,
            'prepared_width': 16, 'prepared_height': 16, 'record_id': record.record_id,
            'metadata_sha256': 'f' * 64})
    failures = []
    for number in range(516, 581):
        source_hash = hashlib.sha256(f'omitted-{number}'.encode()).hexdigest()
        source_path = str(tmp_path / 'never-open-originals' / f'{number}.jpg')
        snapshot['assets'].append({'asset_id': str(number), 'path': source_path,
            'sha256': source_hash, 'mime': 'image/jpeg', 'width': 16, 'height': 16})
        failures.append({'status': 'failed', 'asset_id': str(number), 'source_path': source_path,
            'code': 'source_missing' if number == 580 else 'preparation_unavailable',
            'source_sha256': None if number == 580 else source_hash, 'source_stat_identity': None})
    manifest.update(snapshot_sha256=hashlib.sha256(canonical(snapshot)).hexdigest(),
        snapshot_asset_count=580, failure_count=65, failures=failures, records=summaries,
        image_identity=asdict(model.image_identity), text_identity=asdict(model.text_identity),
        model_receipt_sha256=hashlib.sha256(canonical(model.receipt())).hexdigest(),
        activation_approved=False, relevance_accepted=False)
    index.write_bytes(canonical(manifest) + b'\n')
    index.chmod(0o600)
    snapshot_path = root / 'snapshot.json'
    snapshot_path.write_bytes(canonical(snapshot) + b'\n')
    snapshot_path.chmod(0o600)
    # Only the expensive, independently covered inspector is replaced; real
    # private JSON reads, vector files, runtime and protected API remain in use.
    fake = sys.modules['library_semantic_index']
    fake._load_json = library_index._load_json
    fake.MAX_MANIFEST_BYTES = library_index.MAX_MANIFEST_BYTES
    draft = omission_review_draft(manifest, records, snapshot,
        index_sha256=hashlib.sha256(index.read_bytes()).hexdigest())
    review_path = tmp_path / 'explicit-fixture-review.json'
    review_path.write_bytes(canonical({**draft, 'operator_reviewed': True}) + b'\n')
    review_path.chmod(0o600)
    return index, model, manifest, records, snapshot, draft, review_path


def test_draft_stays_unreviewed_and_cannot_start_canary(full_catalog, tmp_path):
    index, model, manifest, records, snapshot, draft, review_path = full_catalog
    summary = subject.prepare_omission_review(index, tmp_path / 'draft-output')
    saved = tmp_path / 'draft-output' / 'omission-review.DRAFT.json'
    assert json.loads(saved.read_bytes()) == draft
    assert summary['operator_reviewed'] is False
    assert summary['runtime_policy_created'] is False
    assert summary['omitted_images'] == 65
    with pytest.raises(CoverageQualificationRefused):
        subject.measure(index, tmp_path / 'refused-output', model=model,
            queries=[{'id': 'en', 'language': 'en', 'text': 'a garden scene'}],
            bulk_vectors=True, omission_review_path=saved)
    assert not (tmp_path / 'refused-output').exists()
    assert model.bind_count == model.encode_count == 0


def test_full_catalog_canary_preserves_65_omissions_and_profiles_actual_runtime(full_catalog, tmp_path):
    index, model, manifest, records, snapshot, draft, review_path = full_catalog
    output = tmp_path / 'full-catalog-canary'
    result = subject.measure(index, output, model=model, bulk_vectors=True,
        omission_review_path=review_path, profile_requests=True,
        queries=[{'id': 'en', 'language': 'en', 'text': 'a garden scene'},
                 {'id': 'zh', 'language': 'zh', 'text': '花园里的家人'},
                 {'id': 'mixed', 'language': 'zh-en', 'text': '花园 family scene'}])
    assert result['catalog_mode'] == 'reviewed_full_frozen_catalog'
    assert result['catalog_image_count'] == 580
    assert result['available_image_count'] == 515
    assert result['reviewed_omission_count'] == 65
    assert result['eligibility_scope'] == 'synthetic_accounts_only'
    assert result['vector_reads'] == 0
    assert not result['activation_performed'] and not result['family_relevance_accepted']
    assert not result['production_database_opened'] and not result['production_index_published']
    assert {
        'omitted_only_hard_filter_disclosed_without_encoding',
        'ordinary_literal_search_retains_omitted_images',
        'changed_policy_refused_before_bulk_and_inference',
        'filtered_out_omitted_source_change_refused_before_inference',
        'mid_encode_omitted_source_change_withheld_cards',
    } <= set(result['protected_checks'])
    with sqlite3.connect(output / 'synthetic.sqlite') as db:
        assert db.execute('SELECT count(*) FROM assets').fetchone()[0] == 580
        assert db.execute('SELECT count(*) FROM image_vector_artifacts').fetchone()[0] == 515
        assert db.execute('SELECT hash_sha256 FROM assets WHERE id=580').fetchone()[0] == snapshot['assets'][-1]['sha256']
    profile = result['request_profile']
    assert profile['schema'] == 'photohouse.semantic_request_profile.v1'
    assert profile['dropped_requests'] == 0
    assert profile['phases']['eligibility_validation']['calls'] > 0
    requests = {row['ordinal']: row for row in profile['requests']}
    for sample in result['samples']:
        observation = requests[sample['runtime_profile_ordinal']]
        assert observation['phases']['encoder_roundtrip']['calls'] == 1
        # One complete ranking generation and the final fresh source check.
        assert observation['phases']['eligibility_validation']['calls'] == 2
        assert observation['phases']['source_sql']['calls'] > 0
    assert all(text not in json.dumps(profile) for text in ('garden scene', 'omitted-', 'source_sha256', str(tmp_path)))
    assert json.loads((output / 'measurement.json').read_bytes()) == result


def test_review_must_be_exact_and_requires_explicit_bulk(full_catalog, tmp_path):
    index, model, _manifest, _records, _snapshot, _draft, review_path = full_catalog
    with pytest.raises(subject.LibrarySemanticRefused, match='omission_review_requires_bulk'):
        subject.measure(index, tmp_path / 'no-bulk', model=model,
            omission_review_path=review_path,
            queries=[{'id': 'en', 'language': 'en', 'text': 'a garden scene'}])
    assert not (tmp_path / 'no-bulk').exists()
    doc = json.loads(review_path.read_bytes())
    doc['omitted'].pop()
    review_path.write_bytes(canonical(doc) + b'\n')
    with pytest.raises(CoverageQualificationRefused):
        subject.measure(index, tmp_path / 'incomplete-review', model=model,
            bulk_vectors=True, omission_review_path=review_path,
            queries=[{'id': 'en', 'language': 'en', 'text': 'a garden scene'}])
    assert not (tmp_path / 'incomplete-review').exists()
    assert model.bind_count == model.encode_count == 0


@pytest.mark.parametrize('target,expected', [('review', 'review_inputs_changed'),
    ('index', 'candidate_files_changed_during_canary'), ('snapshot', 'review_inputs_changed')])
def test_changed_pinned_input_never_publishes_measurement(full_catalog, tmp_path, target, expected):
    index, model, _manifest, _records, _snapshot, _draft, review_path = full_catalog
    encode = model.encode
    selected = {'review': review_path, 'index': index, 'snapshot': index.parent / 'snapshot.json'}[target]
    changed = [False]
    def change_review(*args, **kwargs):
        if not changed[0]:
            changed[0] = True
            selected.write_bytes(selected.read_bytes() + b' ')
        return encode(*args, **kwargs)
    model.encode = change_review
    output = tmp_path / 'changed-review'
    with pytest.raises(subject.LibrarySemanticRefused, match=expected):
        subject.measure(index, output, model=model, bulk_vectors=True,
            omission_review_path=review_path,
            queries=[{'id': 'en', 'language': 'en', 'text': 'a garden scene'}])
    assert not (output / 'measurement.json').exists()


def test_oversized_review_is_refused_before_payload_read(full_catalog, tmp_path, monkeypatch):
    index, model, _manifest, _records, _snapshot, _draft, review_path = full_catalog
    with review_path.open('wb') as stream:
        stream.truncate(16 * 1024**2 + 1)
    original_read = Path.read_bytes
    def refuse_unbounded_read(path):
        assert path != review_path, 'oversized review was read before its size limit'
        return original_read(path)
    monkeypatch.setattr(Path, 'read_bytes', refuse_unbounded_read)
    with pytest.raises(library_index.LibraryIndexUnavailable):
        subject.measure(index, tmp_path / 'oversized-review', model=model, bulk_vectors=True,
            omission_review_path=review_path,
            queries=[{'id': 'en', 'language': 'en', 'text': 'a garden scene'}])
    assert not (tmp_path / 'oversized-review').exists()
    assert model.bind_count == model.encode_count == 0
