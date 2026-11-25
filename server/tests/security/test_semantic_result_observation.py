"""Generated-only tests for the private semantic result-observation hook."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts"), str(ROOT / "tests" / "security")]

import test_qualify_library_semantic as fixture_module  # noqa: E402
import test_qualify_semantic_coverage as coverage_module  # noqa: E402
import qualify_library_semantic as subject  # noqa: E402


PINS = dict(library_id='fixture-family', binding_sha256='a' * 64,
    index_sha256='b' * 64, query_plan_sha256='c' * 64)
QUERY = {'id': 'q1', 'language': 'en', 'text': 'a quiet family garden'}
COHORT = tuple(str(i) for i in range(1, 516))


def _body(*, items=None, candidate_count=515, total=515, library_id='fixture-family',
          page=1, page_size=20, binding='d' * 64, fingerprint='e' * 64,
          coverage_label='complete_eligible_images', coverage_details=None):
    return {'library_id': library_id, 'binding': binding, 'fingerprint': fingerprint,
        'page': page, 'page_size': page_size, 'total': total,
        'semantic': {'candidate_count': candidate_count, 'coverage': coverage_label,
            **({'coverage_details': coverage_details} if coverage_details is not None else {})},
        'items': items if items is not None else [
            {'id': str(i), 'semantic_score': 1.0 - i / 1000}
            for i in range(1, min(page_size, candidate_count) + 1)]}


def _observe(body, *, callback=None):
    sample = {'query_id': QUERY['id'], 'language': QUERY['language'],
        'query_sha256': __import__('hashlib').sha256(QUERY['text'].encode()).hexdigest(),
        'repetition': 0, 'elapsed_ms': 12.5, 'candidate_count': len(COHORT)}
    return subject._result_observation(QUERY, body, sample, cohort_ids=COHORT, **PINS)


def test_pure_observation_is_bounded_redacted_and_uses_only_primitives():
    body = _body()
    observation = _observe(body)
    assert observation['schema'] == 'photohouse.semantic_result_observation.v1'
    assert observation['query_id'] == 'q1' and observation['language'] == 'en'
    assert observation['query_sha256'] == __import__('hashlib').sha256(QUERY['text'].encode()).hexdigest()
    assert len(observation['canonical_response_sha256']) == 64
    assert observation['library_id'] == 'fixture-family'
    assert observation['model_binding_sha256'] == 'a' * 64
    assert observation['response_binding_sha256'] == 'd' * 64
    assert observation['request_fingerprint_sha256'] == 'e' * 64
    assert observation['model_binding_sha256'] != observation['response_binding_sha256']
    assert observation['candidate_count'] == 515
    assert observation['repetition'] == 0
    assert observation['runtime_profile_ordinal'] is None
    assert len(observation['top_results']) == 20
    assert observation['top_results'][0] == {'asset_id': '1', 'rank': 1,
        'semantic_score': pytest.approx(0.999)}
    rendered = json.dumps(observation, allow_nan=False)
    assert QUERY['text'] not in rendered
    assert 'caption' not in rendered.lower() and 'thumbnail' not in rendered.lower()
    assert all(type(value) in (str, int, float, bool, type(None))
        for value in _walk(observation))
    assert body == _body()


def _walk(value):
    if type(value) is dict:
        for key, item in value.items():
            yield key
            yield from _walk(item)
    elif type(value) is list:
        for item in value:
            yield from _walk(item)
    else:
        yield value


@pytest.mark.parametrize('items', [
    [{'id': '9999', 'semantic_score': 0.5}],
    [{'id': '1', 'semantic_score': float('nan')}],
    [{'id': '1', 'semantic_score': float('inf')}],
    [{'id': '1', 'semantic_score': True}],
    [{'id': '1', 'semantic_score': 0.5}, {'id': '1', 'semantic_score': 0.4}],
    [{'id': str(i), 'semantic_score': 0.5} for i in range(1, 22)],
])
def test_invalid_ids_scores_duplicates_and_oversize_fail_closed(items):
    with pytest.raises(subject.LibrarySemanticRefused, match='result_observation_invalid'):
        _observe(_body(items=items))


def test_oversize_or_nonfinite_full_response_fails_closed():
    oversized = _body()
    oversized['diagnostic'] = 'x' * (4 * 1024 * 1024 + 1)
    with pytest.raises(subject.LibrarySemanticRefused, match='result_observation_invalid'):
        _observe(oversized)
    nonfinite = _body()
    nonfinite['unselected_numeric_field'] = float('nan')
    with pytest.raises(subject.LibrarySemanticRefused, match='result_observation_invalid'):
        _observe(nonfinite)


@pytest.mark.parametrize('changes', [
    {'library_id': 'foreign-library'},
    {'page': 2},
    {'page_size': 19},
    {'binding': 'not-a-sha256'},
    {'fingerprint': 'not-a-sha256'},
    {'items': []},
    {'items': [{'id': str(i), 'semantic_score': 0.5} for i in range(1, 20)]},
    {'coverage_label': 'secret/path'},
])
def test_wrong_library_page_pins_empty_short_results_and_coverage_refuse(changes):
    with pytest.raises(subject.LibrarySemanticRefused, match='result_observation_invalid'):
        _observe(_body(**changes))


@pytest.mark.parametrize('details', [
    {'version': 1, 'policy_sha256': 'f' * 64, 'state': '/private/raw/path',
     'catalog_images': 515, 'searchable_images': 515, 'omitted_images': 0,
     'matched_omitted_images': 0},
    {'version': 1, 'policy_sha256': 'f' * 64, 'state': 'complete',
     'catalog_images': 516, 'searchable_images': 515, 'omitted_images': 0,
     'matched_omitted_images': 0},
    {'version': 1, 'policy_sha256': 'f' * 64, 'state': 'partial',
     'catalog_images': 517, 'searchable_images': 514, 'omitted_images': 3,
     'matched_omitted_images': 0},
    {'version': 1, 'policy_sha256': 'not-a-hash', 'state': 'complete',
     'catalog_images': 515, 'searchable_images': 515, 'omitted_images': 0,
     'matched_omitted_images': 0},
    {'version': 1, 'policy_sha256': 'f' * 64, 'state': 'partial',
     'catalog_images': 515, 'searchable_images': 515, 'omitted_images': 0,
     'matched_omitted_images': 1},
])
def test_coverage_state_counts_and_policy_pin_are_validated(details):
    with pytest.raises(subject.LibrarySemanticRefused, match='result_observation_invalid'):
        _observe(_body(coverage_details=details))


def test_valid_coverage_details_are_projected_as_counts_only():
    details = {'version': 1, 'policy_sha256': 'f' * 64, 'state': 'partial',
        'catalog_images': 517, 'searchable_images': 515, 'omitted_images': 2,
        'matched_omitted_images': 1}
    body = _body(coverage_details=details)
    observation = _observe(body)
    assert observation['coverage'] == {
        'label': 'complete_eligible_images', 'candidate_count': 515,
        'policy_sha256': 'f' * 64, 'catalog_images': 517, 'searchable_images': 515,
        'omitted_images': 2, 'matched_omitted_images': 1, 'state': 'partial'}
    assert '/private' not in json.dumps(observation)


def test_cohort_ids_must_fit_canonical_positive_signed_64_bit_asset_id():
    sample = {'query_id': QUERY['id'], 'language': QUERY['language'],
        'query_sha256': __import__('hashlib').sha256(QUERY['text'].encode()).hexdigest(),
        'repetition': 0, 'elapsed_ms': 12.5, 'candidate_count': 1}
    with pytest.raises(subject.LibrarySemanticRefused, match='result_observation_invalid'):
        subject._result_observation(QUERY,
            _body(items=[{'id': '9223372036854775808', 'semantic_score': 0.5}],
                  candidate_count=1, total=1), sample,
            cohort_ids=('9223372036854775808',), **PINS)


def test_callback_receives_detached_redacted_value_and_does_not_mutate_body():
    body = _body()
    before = copy.deepcopy(body)
    captured = []
    def mutate(observation):
        captured.append(copy.deepcopy(observation))
        observation['top_results'][0]['asset_id'] = 'tampered'
        observation['query_id'] = QUERY['text']
    sample = {'query_id': QUERY['id'], 'language': QUERY['language'],
        'query_sha256': __import__('hashlib').sha256(QUERY['text'].encode()).hexdigest(),
        'repetition': 2, 'elapsed_ms': 12.5, 'candidate_count': 515}
    subject._observe_result(mutate, QUERY, body, sample, cohort_ids=COHORT, **PINS)
    assert len(captured) == 1 and body == before
    assert captured[0]['query_id'] == 'q1'
    assert captured[0]['repetition'] == 2 and captured[0]['runtime_profile_ordinal'] is None
    assert 'text' not in captured[0] and QUERY['text'] not in json.dumps(captured[0])


def test_successful_measured_warm_responses_only_nine_and_default_report_shape(
        monkeypatch, tmp_path):
    generated = fixture_module.generated_index.__wrapped__(monkeypatch, tmp_path)
    index_path, model, _manifest, _records, _root = generated
    captured = []
    snapshots = []
    observed_ids = []
    def observer(value):
        captured.append(value)
        snapshots.append(copy.deepcopy(value))
        observed_ids.append(value['query_id'])
        value['query_id'] = 'callback-local-mutation'
    result = subject.measure(index_path, tmp_path / 'observed', model=model,
        queries=[QUERY], repetitions=9, result_observer=observer)
    assert len(captured) == 9  # warm-up and three rejected authorization attempts excluded
    assert observed_ids == ['q1'] * 9
    assert all(row['query_id'] == 'callback-local-mutation'
        and row['candidate_count'] == 515 for row in captured)
    assert all(row['runtime_profile_ordinal'] is None for row in captured)
    assert all('runtime_profile_ordinal' not in sample for sample in result['samples'])
    assert all(observation['repetition'] == sample['repetition']
        and observation['query_id'] == sample['query_id']
        and observation['query_sha256'] == sample['query_sha256']
        and observation['elapsed_ms'] == sample['elapsed_ms']
        and observation['runtime_profile_ordinal'] == sample.get('runtime_profile_ordinal')
        for observation, sample in zip(snapshots, result['samples']))
    assert result['provider_calls'] == result['model_encode_calls'] == model.encode_count == 12
    assert result['latency_ms']['count'] == 9
    assert result['activation_performed'] is False
    assert result['family_relevance_accepted'] is False
    assert result['production_database_opened'] is False
    assert result['resources_closed'] is True
    assert {'viewer_denied_before_model_and_vector_reads',
            'other_owner_denied_before_model_and_vector_reads',
            'invalid_denied_before_model_and_vector_reads'} <= set(result['protected_checks'])
    assert 'result_observations' not in result and 'result_observer' not in result
    assert json.loads((tmp_path / 'observed' / 'measurement.json').read_text()) == result


def test_default_callback_none_keeps_report_contract_and_has_no_observation_fields(
        monkeypatch, tmp_path):
    generated = fixture_module.generated_index.__wrapped__(monkeypatch, tmp_path)
    index_path, model, _manifest, _records, _root = generated
    result = subject.measure(index_path, tmp_path / 'default', model=model,
        queries=[QUERY], repetitions=1, result_observer=None)
    expected_sample_fields = {
        'query_id', 'language', 'query_sha256', 'repetition', 'elapsed_ms', 'candidate_count'}
    assert result['schema'] == 'photohouse.library_semantic_measurement.v1'
    assert set(result['samples'][0]) == expected_sample_fields
    assert 'result_observations' not in result and 'result_observer' not in result
    assert not any('observation' in key for key in result)
    assert result['latency_ms']['count'] == 1
    assert result['activation_performed'] is False
    assert result['family_relevance_accepted'] is False
    assert result['production_database_opened'] is False
    assert result['resources_closed'] is True
    assert json.loads((tmp_path / 'default' / 'measurement.json').read_text()) == result


def _build_full_catalog(monkeypatch, root):
    root.mkdir()
    root.chmod(0o700)
    generated = fixture_module.generated_index.__wrapped__(monkeypatch, root)
    return coverage_module.full_catalog.__wrapped__(generated, root)


def test_partial_catalog_observation_uses_eligible_cohort_and_keeps_default_contract(
        monkeypatch, tmp_path):
    observed_root = tmp_path / 'partial-observed'
    index, model, _manifest, records, _snapshot, _draft, review_path = _build_full_catalog(
        monkeypatch, observed_root)
    captured = []
    result = subject.measure(index, observed_root / 'measured', model=model,
        bulk_vectors=True, omission_review_path=review_path, profile_requests=True,
        queries=[{'id': 'en', 'language': 'en', 'text': 'a garden scene'}],
        repetitions=9, result_observer=captured.append)
    eligible_ids = {str(record.asset_id) for record in records}
    omitted_ids = {str(number) for number in range(516, 581)}
    assert len(captured) == 9
    samples_by_repetition = {sample['repetition']: sample for sample in result['samples']}
    assert len(samples_by_repetition) == 9
    assert all(type(sample.get('runtime_profile_ordinal')) is int
        and 1 <= sample['runtime_profile_ordinal'] <= 256 for sample in result['samples'])
    assert all(observation['query_id'] == samples_by_repetition[observation['repetition']]['query_id']
        and observation['query_sha256'] == samples_by_repetition[observation['repetition']]['query_sha256']
        and observation['elapsed_ms'] == samples_by_repetition[observation['repetition']]['elapsed_ms']
        and observation['runtime_profile_ordinal'] == samples_by_repetition[
            observation['repetition']]['runtime_profile_ordinal'] for observation in captured)
    assert all(len(row['top_results']) == 20
        and {item['asset_id'] for item in row['top_results']} <= eligible_ids
        and not ({item['asset_id'] for item in row['top_results']} & omitted_ids)
        for row in captured)
    coverage_policy_hashes = {row['coverage']['policy_sha256'] for row in captured}
    assert len(coverage_policy_hashes) == 1
    assert len(next(iter(coverage_policy_hashes))) == 64
    assert all(row['coverage'] == {
        'label': 'complete_eligible_images', 'candidate_count': 515,
        'policy_sha256': next(iter(coverage_policy_hashes)),
        'catalog_images': 580, 'searchable_images': 515, 'omitted_images': 65,
        'matched_omitted_images': 65, 'state': 'partial'} for row in captured)
    assert result['catalog_image_count'] == 580
    assert result['available_image_count'] == 515
    assert result['reviewed_omission_count'] == 65
    assert {'omitted_only_hard_filter_disclosed_without_encoding',
            'ordinary_literal_search_retains_omitted_images',
            'changed_policy_refused_before_bulk_and_inference',
            'filtered_out_omitted_source_change_refused_before_inference',
            'mid_encode_omitted_source_change_withheld_cards'} <= set(result['protected_checks'])
    assert result['provider_calls'] == result['model_encode_calls'] == model.encode_count
    assert result['activation_performed'] is False
    assert result['family_relevance_accepted'] is False
    assert result['resources_closed'] is True
    assert json.loads((observed_root / 'measured' / 'measurement.json').read_text()) == result

    default_root = tmp_path / 'partial-default'
    default_index, default_model, _m, _r, _s, _d, default_review = _build_full_catalog(
        monkeypatch, default_root)
    default_result = subject.measure(default_index, default_root / 'measured',
        model=default_model, bulk_vectors=True, omission_review_path=default_review,
        queries=[{'id': 'en', 'language': 'en', 'text': 'a garden scene'}], repetitions=1)
    assert not any('observation' in key for key in default_result)
    assert all('runtime_profile_ordinal' not in sample for sample in default_result['samples'])
    assert json.loads((default_root / 'measured' / 'measurement.json').read_text()) == default_result


def test_multilanguage_observations_join_exact_samples_and_profile_ordinals(
        monkeypatch, tmp_path):
    generated = fixture_module.generated_index.__wrapped__(monkeypatch, tmp_path)
    index_path, model, _manifest, _records, _root = generated
    queries = [
        {'id': 'garden_en', 'language': 'en', 'text': 'A family in a garden'},
        {'id': 'garden_zh', 'language': 'zh', 'text': '一家人在花园里'},
        {'id': 'garden_zh_en', 'language': 'zh-en', 'text': 'family在花园里'},
    ]
    captured = []
    result = subject.measure(index_path, tmp_path / 'multilanguage', model=model,
        profile_requests=True, queries=queries, repetitions=2,
        result_observer=captured.append)

    # Only the six successful measured warm responses are observed: the initial
    # warm-up, authorization refusals, and protected probes never enter this set.
    assert len(captured) == len(result['samples']) == 6
    assert {(row['query_id'], row['language'], row['repetition']) for row in captured} == {
        (query['id'], query['language'], repetition)
        for query in queries for repetition in range(2)}
    sample_by_key = {
        (row['query_id'], row['language'], row['repetition']): row
        for row in result['samples']}
    assert len(sample_by_key) == 6
    profile_requests = result['request_profile']['requests']
    assert result['request_profile']['dropped_requests'] == 0
    assert len(profile_requests) < 256
    ordinals = []
    for observation in captured:
        key = (observation['query_id'], observation['language'], observation['repetition'])
        sample = sample_by_key[key]
        ordinal = observation['runtime_profile_ordinal']
        assert ordinal == sample['runtime_profile_ordinal']
        assert observation['query_sha256'] == sample['query_sha256']
        assert observation['elapsed_ms'] == sample['elapsed_ms']
        assert 1 <= ordinal <= len(profile_requests)
        assert profile_requests[ordinal - 1]['ordinal'] == ordinal
        assert profile_requests[ordinal - 1]['phases']['runtime_total']['calls'] == 1
        assert profile_requests[ordinal - 1]['total_ms'] >= 0
        ordinals.append(ordinal)
    assert len(set(ordinals)) == 6
    assert result['provider_calls'] == result['model_encode_calls'] == model.encode_count
    assert result['activation_performed'] is False
    assert result['family_relevance_accepted'] is False
    assert json.loads((tmp_path / 'multilanguage' / 'measurement.json').read_text()) == result


def _shape(value):
    if type(value) is dict:
        return {key: _shape(item) for key, item in value.items()}
    if type(value) is list:
        return [_shape(value[0])] if value else []
    return type(value).__name__
