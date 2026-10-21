#!/usr/bin/env python3
"""Measure protected semantic search against a verified private library index.

Importing this module and the default command-line plan are side-effect free.
The explicit ``measure`` call uses a newly generated synthetic access database
and accounts, the read-only verified library vector root, and a caller-supplied
already-loaded library SigLIP adapter. It never enables production search.
"""
from __future__ import annotations

import argparse
from contextlib import closing, ExitStack, contextmanager, nullcontext
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import time
from unittest.mock import patch


class LibrarySemanticRefused(ValueError):
    """Fixed refusal for a malformed or unavailable qualification run."""

    def __init__(self, reason="contract_refused"):
        super().__init__("library_semantic_measurement_unavailable:" + reason)


def _require(value, reason="contract_refused"):
    if not value:
        raise LibrarySemanticRefused(reason)


def _valid_queries(queries):
    from app.access.semantic_encoder import _valid_query
    from app.access.search_exclusions import requires_semantic_clarification

    _require(type(queries) is list and 1 <= len(queries) <= 12)
    seen = set()
    clean = []
    for query in queries:
        _require(type(query) is dict and set(query) == {"id", "language", "text"})
        _require(type(query["id"]) is str
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", query["id"], re.ASCII)
            and query["id"] not in seen
            and query["language"] in ("en", "zh", "zh-en")
            and _valid_query(query["text"])
            and not requires_semantic_clarification(query["text"]))
        seen.add(query["id"])
        clean.append(dict(query))
    return tuple(clean)


def _summary(samples):
    ordered = sorted(samples)
    _require(bool(ordered))
    return {"count": len(ordered),
        "p50_ms": ordered[math.ceil(len(ordered) * 0.50) - 1],
        "p95_ms": ordered[math.ceil(len(ordered) * 0.95) - 1],
        "max_ms": ordered[-1]}


def _record_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _index_file_hashes(root, records):
    hashes = {}
    for record in records:
        path = root / record.relative_path
        digest = _record_digest(path)
        _require(digest == record.file_sha256, "candidate_vector_hash_mismatch")
        hashes[record.asset_id] = digest
    return hashes


def _private_json_pin(path, limit):
    """Bound the private document before hashing any newly supplied input."""
    from library_semantic_index import _load_json
    from qualify_semantic_pair import canonical
    document = _load_json(Path(path), limit)
    return document, hashlib.sha256(canonical(document) + b'\n').hexdigest()


def _json_pin_matches(path, digest, limit):
    try:
        return _private_json_pin(path, limit)[1] == digest
    except Exception:
        return False


def _network_files(network, source_root):
    if network is None:
        return None
    from app.access.private_storage import require_private_file

    _require(type(network) is dict and set(network) == {
        "transport", "certificate", "private_key", "ca_file"}
        and network["transport"] == "loopback_https_tcp")
    result = {}
    for key in ("certificate", "private_key", "ca_file"):
        value = network[key]
        _require(isinstance(value, (str, os.PathLike)))
        path = Path(value)
        _require(path.is_absolute() and ".." not in path.parts)
        _require(not path.resolve().is_relative_to(source_root.resolve()))
        require_private_file(path)
        result[key] = path
    return result


def prepare_omission_review(index_path, output_directory):
    """Prepare a private, unreviewed draft from an inspected frozen index.

    This model-free operation verifies the candidate but never grants approval,
    builds a serving policy, or opens a production database.
    """
    repo_backend = str(Path(__file__).parents[1] / 'backend')
    if repo_backend not in sys.path:
        sys.path.insert(0, repo_backend)
    from library_semantic_index import inspect_library_index, MAX_MANIFEST_BYTES
    from semantic_coverage_qualification import omission_review_draft
    from qualify_semantic_pair import output_target, write_record, canonical

    path = Path(index_path)
    _require(path.is_absolute() and '..' not in path.parts and path.name == 'index.json')
    _initial, before = _private_json_pin(path, MAX_MANIFEST_BYTES)
    manifest, records, _identities = inspect_library_index(path)
    snapshot_path = path.parent / 'snapshot.json'
    snapshot, snapshot_pin = _private_json_pin(snapshot_path, MAX_MANIFEST_BYTES)
    draft = omission_review_draft(manifest, records, snapshot, index_sha256=before)
    output = output_target(output_directory)
    resolved = output.resolve(strict=False)
    index_root = path.parent.resolve(strict=True)
    source_root = Path(__file__).resolve().parents[2]
    _require(not any(resolved.is_relative_to(root) or root.is_relative_to(resolved)
        for root in (index_root, source_root)), 'unsafe_draft_output')
    _require(_json_pin_matches(path, before, MAX_MANIFEST_BYTES)
        and _json_pin_matches(snapshot_path, snapshot_pin, MAX_MANIFEST_BYTES),
        'draft_inputs_changed')
    output.mkdir(mode=0o700)
    write_record(output, 'omission-review.DRAFT.json', draft)
    _require(_json_pin_matches(path, before, MAX_MANIFEST_BYTES)
        and _json_pin_matches(snapshot_path, snapshot_pin, MAX_MANIFEST_BYTES),
        'draft_inputs_changed')
    summary = {'status': 'omission_review_draft_prepared', 'operator_reviewed': False,
        'index_sha256': before, 'snapshot_sha256': manifest['snapshot_sha256'],
        'catalog_images': manifest['snapshot_asset_count'], 'searchable_images': len(records),
        'omitted_images': len(draft['omitted']),
        'review_sha256': hashlib.sha256(canonical(draft) + b'\n').hexdigest(),
        'models_loaded': False, 'production_database_opened': False,
        'runtime_policy_created': False, 'activation_performed': False}
    write_record(output, 'draft-summary.json', summary)
    return summary


def measure(index_path, output_directory, *, model, queries, repetitions=1, network=None,
            bulk_vectors=False, omission_review_path=None, profile_requests=False):
    """Run the explicit canary, optionally observing private request phases.

    A full-catalog run requires a separately reviewed omission document. No
    builder promotes an unreviewed draft, and no production accounts are used.
    """
    _require(type(profile_requests) is bool)
    repo_backend = str(Path(__file__).parents[1] / 'backend')
    if repo_backend not in sys.path:
        sys.path.insert(0, repo_backend)
    if profile_requests:
        from semantic_request_profile import instrument_requests
        observation = instrument_requests()
    else:
        observation = nullcontext(None)
    with observation as observer:
        result = _measure(index_path, output_directory, model=model, queries=queries,
            repetitions=repetitions, network=network, bulk_vectors=bulk_vectors,
            omission_review_path=omission_review_path, request_observer=observer)
    if observer is not None:
        result['request_profile'] = observer.snapshot()
    from qualify_semantic_pair import write_record
    write_record(Path(output_directory), 'measurement.json', result)
    return result


def _measure(index_path, output_directory, *, model, queries, repetitions, network,
             bulk_vectors, omission_review_path, request_observer):
    """Run a bounded synthetic-account canary over a verified immutable index.

    ``model`` must be the caller's real, loaded, UNBOUND LibrarySiglipModel.
    ``network`` explicitly opts into temporary loopback HTTPS API and TCP
    provider listeners; omitting it keeps both boundaries listener-free ASGI.
    The report makes no family relevance or activation claim.
    """
    repo_backend = Path(__file__).parents[1] / "backend"
    if str(repo_backend) not in sys.path:
        sys.path.insert(0, str(repo_backend))
    from app.access.semantic_encoder import JointSpaceBinding
    from app.access.semantic_streaming import SemanticServingLimits
    from app.access import discovery as d
    from app.access.discovery_provider import MemoryIndexProvider, ReviewedIndex
    from app.access.discovery_transport import DiscoveryRuntime
    from app.access.private_storage import require_private_directory, require_private_file
    from app.access.semantic_provider_transport import create_provider_app
    from app.access.transport import AccessRuntime
    from app.access.visual_vector_artifacts import identity_sha256, validate_artifact
    from fastapi.testclient import TestClient
    import qualify_multilingual_pilot as fixture_harness
    from library_semantic_index import inspect_library_index
    from qualify_semantic_pair import canonical, output_target, write_record

    _require(type(bulk_vectors) is bool)
    _require(type(repetitions) is int and 1 <= repetitions <= 10)
    query_plan = _valid_queries(queries)
    _require(model is not None and all(hasattr(model, name) for name in (
        "image_identity", "text_identity", "binding", "bind", "encode", "verify", "receipt")))
    _require(model.binding is None, "model_already_bound")

    index_path = Path(index_path)
    _require(index_path.is_absolute() and ".." not in index_path.parts)
    source_root = Path(fixture_harness.qualification.ROOT.parent).resolve()
    net_files = _network_files(network, source_root)
    manifest, records, identities = inspect_library_index(index_path)
    _require(type(manifest) is dict and type(records) is tuple and bool(records)
        and type(identities) is dict and set(identities) == {"image", "text"})
    _require(type(manifest.get("failures")) is list)
    _require(manifest.get("library_id") and manifest.get("snapshot_sha256")
        and manifest.get("model_receipt") == model.receipt()
        and type(manifest.get("processing_complete")) is bool
        and type(manifest.get("complete")) is bool
        and type(manifest.get("record_count")) is int
        and type(manifest.get("failure_count")) is int
        and type(manifest.get("snapshot_asset_count")) is int
        and manifest.get("record_count") == len(records)
        and manifest.get("failure_count") == len(manifest["failures"])
        and manifest.get("snapshot_asset_count") == len(records) + len(manifest["failures"]))
    _require(identities["image"] == model.image_identity
        and identities["text"] == model.text_identity)
    _require(manifest["processing_complete"] is True
        and manifest["complete"] is (not manifest["failures"]), "inconsistent_index_completeness")
    for record in records:
        _require(validate_artifact(record, identities["image"]), "invalid_candidate_artifact")

    index_root = index_path.parent
    original_vector_hashes = _index_file_hashes(index_root, records)
    index_hash = _record_digest(index_path)
    candidate_identity = identity_sha256(identities["image"])
    _require(all(record.identity_sha256 == candidate_identity for record in records))
    omission_review = snapshot = None
    omitted = ()
    review_hash = snapshot_file_hash = None
    if omission_review_path is not None:
        from library_semantic_index import MAX_MANIFEST_BYTES
        from semantic_coverage_qualification import validate_omission_review
        _require(bulk_vectors, 'omission_review_requires_bulk')
        omission_review_path = Path(omission_review_path)
        _require(omission_review_path.is_absolute() and '..' not in omission_review_path.parts
            and not omission_review_path.resolve().is_relative_to(source_root), 'unsafe_review_path')
        require_private_directory(omission_review_path.parent)
        snapshot_path = index_root / 'snapshot.json'
        snapshot, snapshot_file_hash = _private_json_pin(snapshot_path, MAX_MANIFEST_BYTES)
        omission_review, review_hash = _private_json_pin(omission_review_path, 16 * 1024**2)
        omitted = validate_omission_review(omission_review, manifest, records, snapshot,
                                          index_sha256=index_hash)
        _require(_json_pin_matches(omission_review_path, review_hash, 16 * 1024**2)
            and _json_pin_matches(snapshot_path, snapshot_file_hash, MAX_MANIFEST_BYTES), 'review_inputs_changed')

    output = output_target(output_directory)
    resolved_output = output.resolve(strict=False)
    resolved_index_root = index_root.resolve(strict=True)
    _require(not (resolved_output.is_relative_to(resolved_index_root)
        or resolved_index_root.is_relative_to(resolved_output)), "output_overlaps_candidate_index")
    output.mkdir(mode=0o700)
    require_private_directory(output)
    database = output / "synthetic.sqlite"
    with database.open("xb"):
        pass
    database.chmod(0o600)
    require_private_file(database)
    library = manifest["library_id"]
    bulk_store = None
    if bulk_vectors:
        from app.access.semantic_bulk_vectors import write_bulk_vectors
        bulk_store = write_bulk_vectors(output / "bulk-vectors.phbv", index_root,
            tuple(sorted(records, key=lambda item: int(item.asset_id))),
            identities["image"], library)
    now = int(time.time())
    tokens = {name: secrets.token_urlsafe(32)
        for name in ("pilot-owner", "pilot-viewer", "pilot-other")}
    fixture_harness._fixture(database, records, library, tokens, now)
    if omission_review is not None:
        # Only this new synthetic DB receives full-roster failure rows. Its
        # synthetic dates/text make omitted-only hard filters observable.
        with closing(sqlite3.connect(database)) as db, db:
            for number, item in enumerate(omitted, len(records) + 1):
                db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,NULL,?)',
                    (int(item.asset_id), 'synthetic-omitted-no-original', item.source_sha256,
                     'active', 'image/jpeg', 16, 16, '2026-01-03'))
                db.execute('INSERT INTO access_asset_libraries VALUES(?,?)', (int(item.asset_id), library))
                db.execute('INSERT INTO captions VALUES(?,?,?,0,0)',
                    (number, int(item.asset_id), 'Synthetic omitted fixture caption'))

    @contextmanager
    def connection():
        with closing(sqlite3.connect(database, timeout=0.25)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA query_only=ON")
            yield db

    # The 23k+ image source projection includes current asset and caption rows.
    # Use the same large-cohort caps for the initial reviewed-source receipt as
    # for each semantic request; the search view will retain this same semaphore.
    limits = SemanticServingLimits(100000, 1000000, 256 * 1024**2, 120.0)
    base_budget = d.ReadBudget(rows=limits.source_rows,
        source_bytes=limits.source_bytes, seconds=limits.search_seconds,
        search_source_bytes=limits.source_bytes, search_seconds=limits.search_seconds)
    origin = "https://pilot.photohouse.test"
    port = 43871
    network_enabled = net_files is not None
    provider_socket = api_socket = None
    loopback = None
    counters = {"provider_calls": 0, "vector_reads": 0, "model_encode_calls": 0, "bulk_snapshot_calls": 0}
    protected = []
    denial_latencies = []
    rows = []
    provider_token = secrets.token_urlsafe(32)
    during_encode = [None]

    with ExitStack() as resources:
        if network_enabled:
            import semantic_loopback_network as loopback
            provider_socket = loopback.reserve_socket()
            resources.callback(provider_socket.close)
            api_socket = loopback.reserve_socket()
            resources.callback(api_socket.close)
            port = provider_socket.getsockname()[1]
            origin = f"https://127.0.0.1:{api_socket.getsockname()[1]}"

        # From the first reserved socket onward, setup belongs to the same
        # ExitStack as the listeners. A failed source receipt, model bind, or
        # app construction therefore closes every socket already acquired.
        with closing(sqlite3.connect(database)) as db:
            with base_budget.attempt(db, lambda: False) as (_check, read):
                source = d.scoped_source(library, read)
        ids = tuple(str(row[0]) for row in source['assets'])
        reviewed = ReviewedIndex(library, "1", ids, ids, d.digest(source))
        technical_receipt = hashlib.sha256(canonical({
            "role": "synthetic_fixture_not_activation",
            "library_id": library,
            "snapshot_sha256": manifest["snapshot_sha256"],
            "index_sha256": index_hash,
        })).hexdigest()
        binding = JointSpaceBinding(identities["image"], identities["text"], technical_receipt)
        eligibility = None
        if omission_review is not None:
            from semantic_coverage_qualification import runtime_policy
            from app.access.semantic_eligibility import SemanticEligibilityStore
            policy = runtime_policy(omission_review, manifest, records, snapshot,
                index_sha256=index_hash, binding_sha256=binding.binding_sha256,
                bulk_sha256=bulk_store.file_sha256)
            policy_path = output / 'synthetic-eligibility.json'
            write_record(output, policy_path.name, policy)
            policy_hash = _record_digest(policy_path)
            eligibility = SemanticEligibilityStore(policy_path, policy_hash, library,
                binding.binding_sha256, bulk_store.file_sha256, source_root)
        model.bind(binding)
        model.verify()

        class ObservedProvider:
            binding = model.binding

            def encode(self, query, *, check):
                counters["provider_calls"] += 1
                counters["model_encode_calls"] += 1
                if during_encode[0] is not None:
                    callback, during_encode[0] = during_encode[0], None
                    callback()
                return model.encode(query, check=check)

        access = AccessRuntime(connection, origin, clock=lambda: now)
        discovery = DiscoveryRuntime(access, MemoryIndexProvider((reviewed,)), base_budget)
        provider_app = create_provider_app(ObservedProvider(), bearer_token=provider_token, port=port)
        if network_enabled:
            resources.enter_context(loopback.server(provider_app, provider_socket))
            provider_context = resources.enter_context(loopback.http_client(f"http://127.0.0.1:{port}"))
        else:
            provider_context = resources.enter_context(TestClient(provider_app,
                base_url=f"http://127.0.0.1:{port}", client=("127.0.0.1", 41234)))
        result = _run_canary(resources, network_enabled, loopback, provider_context,
            provider_app, access, discovery, base_budget, limits, model, binding,
            database, library, tokens, records, ids, queries=query_plan,
            repetitions=repetitions, origin=origin, api_socket=api_socket,
            provider_token=provider_token, port=port, counters=counters, protected=protected,
            denial_latencies=denial_latencies, rows=rows, index_path=index_path,
            index_root=index_root, index_hash=index_hash, manifest=manifest,
            original_vector_hashes=original_vector_hashes, net_files=net_files,
            warmup_holder=[None], bulk_store=bulk_store, eligibility=eligibility,
            omitted=omitted, during_encode=during_encode, request_observer=request_observer)

    # Only publish the report after all temporary clients/listeners have closed.
    model.verify()
    _require(_record_digest(index_path) == index_hash, "index_changed_during_measurement")
    _require(_index_file_hashes(index_root, records) == original_vector_hashes,
        "candidate_vectors_changed_during_measurement")
    inspect_library_index(index_path, expected_snapshot=manifest["snapshot_sha256"])
    if omission_review is not None:
        _require(_json_pin_matches(omission_review_path, review_hash, 16 * 1024**2)
            and _json_pin_matches(index_root / 'snapshot.json', snapshot_file_hash, MAX_MANIFEST_BYTES),
            'review_inputs_changed')
    result.update({
        "schema": "photohouse.library_semantic_measurement.v1",
        "index_sha256": index_hash,
        "library_id": library,
        "snapshot_sha256": manifest["snapshot_sha256"],
        "available_image_count": len(records),
        'catalog_mode': 'reviewed_full_frozen_catalog' if omission_review is not None else 'ready_only',
        'catalog_image_count': len(records) + len(omitted),
        'reviewed_omission_count': len(omitted),
        'omission_review_sha256': review_hash,
        'eligibility_scope': 'synthetic_accounts_only' if eligibility is not None else None,
        "index_failure_count": len(manifest["failures"]),
        "index_processing_complete": manifest["processing_complete"],
        "full_family_index_complete": manifest["complete"],
        "model_receipt": model.receipt(),
        "query_plan_sha256": hashlib.sha256(canonical(list(query_plan))).hexdigest(),
        "samples": rows,
        "warmup_ms": result["warmup_ms"],
        "latency_ms": _summary([row["elapsed_ms"] for row in rows]),
        "denial_latency_ms": _summary(denial_latencies),
        "provider_calls": counters["provider_calls"],
        "model_encode_calls": counters["model_encode_calls"],
        "vector_reads": counters["vector_reads"],
        "bulk_snapshot_calls": counters["bulk_snapshot_calls"],
        "vector_storage": "pinned_bulk_v1" if bulk_vectors else "individual_npy",
        "bulk_descriptor": bulk_store.descriptor if bulk_store else None,
        "read_limits": {
            "candidate_limit": limits.candidate_limit,
            "source_rows": limits.source_rows,
            "source_bytes": limits.source_bytes,
            "search_seconds": limits.search_seconds,
            "vector_read_bytes": 256 * 1024**2,
            "batch_size": 128,
            "shared_admission_pool": result["shared_admission_pool"],
        },
        "transport_boundary": ("loopback_https_api_and_authenticated_tcp_provider_cpu"
            if network_enabled else "listener_free_asgi_api_and_authenticated_provider_cpu"),
        "protected_checks": protected,
        "resources_closed": True,
        "production_database_opened": False,
        "production_listener_started": False,
        "network_listener_started": network_enabled,
        "real_account_sessions_created": False,
        "production_index_published": False,
        "activation_performed": False,
        "activation_approved": False,
        "serving_load_accepted": False,
        "human_relevance_measured": False,
        "family_relevance_accepted": False,
    })
    return result


def _run_canary(resources, network_enabled, loopback, provider_context, provider_app,
                access, discovery, base_budget, limits, model, binding,
                database, library, tokens, records, ids, *, queries, repetitions,
                origin, api_socket, provider_token, port, counters, protected,
                denial_latencies, rows, index_path, index_root, index_hash,
                manifest, original_vector_hashes, net_files, warmup_holder, bulk_store=None,
                eligibility=None, omitted=(), during_encode=None, request_observer=None):
    import httpx
    from app.access.semantic_encoder import LocalSemanticEncoder
    from app.access.semantic_search import SemanticSearchRuntime
    from app.access.visual_vector_loader import _read_vector
    from app.main import create_app
    from fastapi.testclient import TestClient

    if network_enabled:
        api_context = loopback.http_client(origin, ca_file=net_files["ca_file"],
            read_timeout_seconds=limits.search_seconds)
    else:
        api_context = None

    def forward(request):
        response = provider_context.post("/v1/encode-text", content=request.content,
            headers=dict(request.headers))
        return httpx.Response(response.status_code, content=response.content,
            headers=response.headers)

    provider_url = f"http://127.0.0.1:{port}/v1/encode-text"
    encoder = LocalSemanticEncoder(binding, provider_url, bearer_token=provider_token,
        transport=None if network_enabled else httpx.MockTransport(forward))
    runtime = SemanticSearchRuntime(discovery, index_root, encoder,
        pilot_owner_account_id="pilot-owner", serving_limits=limits, bulk_vectors=bulk_store,
        eligibility=eligibility)
    runtime_budget = runtime.budget
    _require(runtime_budget.slots is base_budget.slots, "admission_pool_not_shared")
    app = create_app(access_runtime=access, discovery_runtime=discovery,
        assistant_enabled=True, semantic_search_runtime=runtime)
    if network_enabled:
        resources.enter_context(loopback.server(app, api_socket,
            certificate=net_files["certificate"], private_key=net_files["private_key"]))
        client = resources.enter_context(api_context)
    else:
        client = resources.enter_context(TestClient(app, base_url=origin))

    def count_read(*args, **kwargs):
        counters["vector_reads"] += 1
        return _read_vector(*args, **kwargs)

    with ExitStack() as observations:
        observations.enter_context(patch("app.access.semantic_search._read_vector", count_read))
        if bulk_store is not None:
            from app.access.semantic_bulk_vectors import BulkVectorStore
            original_snapshot = BulkVectorStore.snapshot
            def observed_snapshot(store, *args, **kwargs):
                counters["bulk_snapshot_calls"] += 1
                return original_snapshot(store, *args, **kwargs)
            observations.enter_context(patch.object(BulkVectorStore, "snapshot", observed_snapshot))
        before = dict(counters)
        bad = provider_context.post("/v1/encode-text", json={"version": 1,
            "binding_sha256": binding.binding_sha256, "query": queries[0]["text"]},
            headers={"Authorization": "Bearer invalid"})
        _require(bad.status_code == 401 and counters == before,
            "provider_bad_bearer_not_blocked_before_model")
        protected.append("provider_bad_bearer_denied_before_model")

        endpoint = f"/libraries/{library}/semantic-search/v1/query"
        last_profile_ordinal = [None]
        def request(text, *, token=None, filters=None):
            before_profile = request_observer.request_count if request_observer else None
            started = time.monotonic()
            response = client.post(endpoint,
                json={"query": text, "filters": filters or {}},
                headers={"Authorization": "Bearer " + (token or tokens["pilot-owner"])})
            after_profile = request_observer.request_count if request_observer else None
            last_profile_ordinal[0] = (after_profile if before_profile is not None
                and after_profile == before_profile + 1 and after_profile <= 256 else None)
            return response, (time.monotonic() - started) * 1000

        def coverage(body, matched):
            if eligibility is None:
                _require('coverage_details' not in body.get('semantic', {}), 'legacy_coverage_changed')
                return
            _require(body.get('semantic', {}).get('coverage_details') == {
                'version': 1, 'policy_sha256': eligibility.file_sha256,
                'state': 'partial' if omitted else 'complete',
                'catalog_images': len(records) + len(omitted),
                'searchable_images': len(records), 'omitted_images': len(omitted),
                'matched_omitted_images': matched}, 'partial_coverage_not_disclosed')

        for label, token in (("viewer", tokens["pilot-viewer"]),
                ("other_owner", tokens["pilot-other"]), ("invalid", "invalid")):
            before = dict(counters)
            response, elapsed = request(queries[0]["text"], token=token)
            _require(response.status_code in (401, 403) and counters == before,
                f"{label}_denial_after_provider_or_vector")
            denial_latencies.append(elapsed)
            protected.append(label + "_denied_before_model_and_vector_reads")

        for excluded in ("no people", "没有人的照片", "没有people"):
            before = dict(counters)
            response, _elapsed = request(excluded)
            _require(response.status_code == 422 and counters == before,
                "exclusion_not_clarified_before_provider_or_vectors")
        protected.append("three_language_exclusions_clarified_before_provider_and_vectors")

        warm, elapsed = request(queries[0]["text"])
        _require(warm.status_code == 200, "warmup_failed")
        coverage(warm.json(), len(omitted))
        warmup_profile_ordinal = last_profile_ordinal[0]
        warmup_holder[0] = elapsed
        for query in queries:
            for repetition in range(repetitions):
                response, elapsed = request(query["text"])
                _require(response.status_code == 200, "semantic_query_failed")
                body = response.json()
                _require(body.get("semantic", {}).get("candidate_count") == len(records)
                    and body.get("total") == len(records), "candidate_cohort_incomplete")
                coverage(body, len(omitted))
                rows.append({"query_id": query["id"], "language": query["language"],
                    "query_sha256": hashlib.sha256(query["text"].encode("utf-8")).hexdigest(),
                    "repetition": repetition, "elapsed_ms": elapsed,
                    **({'runtime_profile_ordinal': last_profile_ordinal[0]} if request_observer else {}),
                    "candidate_count": body["semantic"]["candidate_count"]})

        allowed = {record.asset_id for index, record in enumerate(records) if index % 2 == 1}
        response, _elapsed = request(queries[0]["text"],
            filters={"date": {"from": "2026-01-02", "to": "2026-01-02"}})
        _require(response.status_code == 200 and response.json()["total"] == len(allowed)
            and {item["id"] for item in response.json()["items"]} <= allowed,
            "synthetic_hard_date_filter_failed")
        coverage(response.json(), 0)
        protected.append("synthetic_date_filter_remains_hard_filter")

        if eligibility is not None:
            omitted_filter = {'date': {'from': '2026-01-03', 'to': '2026-01-03'}}
            before = dict(counters)
            empty, _elapsed = request(queries[0]['text'], filters=omitted_filter)
            _require(empty.status_code == 200 and empty.json()['total'] == 0
                and empty.json()['items'] == [] and counters['model_encode_calls'] == before['model_encode_calls'],
                'omitted_only_scope_encoded_or_returned_cards')
            coverage(empty.json(), len(omitted))
            protected.append('omitted_only_hard_filter_disclosed_without_encoding')
            ordinary = client.post('/assistant/v1/turns', json={'library_id': library,
                'text': 'find photos containing "Synthetic omitted fixture caption"', 'context': None},
                headers={'Authorization': 'Bearer ' + tokens['pilot-owner'],
                         'X-PhotoHouse-Search-Version': '2'})
            _require(ordinary.status_code == 200 and ordinary.json().get('total') == len(omitted)
                and counters['model_encode_calls'] == before['model_encode_calls'],
                'ordinary_search_lost_omitted_assets')
            protected.append('ordinary_literal_search_retains_omitted_images')

            policy_bytes = eligibility.path.read_bytes()
            before = dict(counters)
            try:
                eligibility.path.write_bytes(policy_bytes + b' ')
                damaged, _elapsed = request(queries[0]['text'])
                _require(damaged.status_code == 503 and 'items' not in damaged.json()
                    and counters == before, 'changed_policy_reached_semantic_io')
            finally:
                eligibility.path.write_bytes(policy_bytes)
            restored, _elapsed = request(queries[0]['text'], filters=omitted_filter)
            _require(restored.status_code == 200, 'synthetic_policy_restore_failed')
            protected.append('changed_policy_refused_before_bulk_and_inference')

            if omitted:
                row = omitted[0]
                def change_omitted_source():
                    with closing(sqlite3.connect(database, timeout=0.25)) as db, db:
                        db.execute('UPDATE assets SET hash_sha256=? WHERE id=?',
                            ('0' * 64 if row.source_sha256 != '0' * 64 else '1' * 64, int(row.asset_id)))
                def restore_omitted_source():
                    with closing(sqlite3.connect(database, timeout=0.25)) as db, db:
                        db.execute('UPDATE assets SET hash_sha256=? WHERE id=?',
                                   (row.source_sha256, int(row.asset_id)))
                before = dict(counters)
                try:
                    change_omitted_source()
                    changed, _elapsed = request(queries[0]['text'],
                        filters={'date': {'from': '2026-01-02', 'to': '2026-01-02'}})
                    _require(changed.status_code == 503 and 'items' not in changed.json()
                        and counters == before, 'filtered_omitted_source_change_reached_semantic_io')
                finally:
                    restore_omitted_source()
                protected.append('filtered_out_omitted_source_change_refused_before_inference')
                try:
                    during_encode[0] = change_omitted_source
                    changed, _elapsed = request(queries[0]['text'])
                    _require(changed.status_code == 503 and 'items' not in changed.json()
                        and counters['model_encode_calls'] == before['model_encode_calls'] + 1,
                        'mid_encode_omitted_source_change_released_cards')
                finally:
                    during_encode[0] = None
                    restore_omitted_source()
                restored, _elapsed = request(queries[0]['text'], filters=omitted_filter)
                _require(restored.status_code == 200, 'synthetic_omitted_source_restore_failed')
                coverage(restored.json(), len(omitted))
                protected.append('mid_encode_omitted_source_change_withheld_cards')

        if bulk_store is not None:
            from app.access.discovery_provider import MemoryIndexProvider, ReviewedIndex
            from app.access import discovery as discovery_module

            def replace_reviewed_source():
                # This models an operator-reviewed source revision after a
                # synthetic lifecycle change. It does not refresh the pinned
                # bulk container; the next search must still refuse its stale
                # cohort before inference.
                with closing(sqlite3.connect(database, timeout=0.25)) as db:
                    with base_budget.attempt(db, lambda: False) as (_check, read):
                        source = discovery_module.scoped_source(library, read)
                current = discovery.provider.get(library)
                scope = tuple(str(row[0]) for row in source["assets"])
                revision = str(int(current.revision) + 1)
                object.__setattr__(discovery, "provider", MemoryIndexProvider((ReviewedIndex(
                    library, revision, scope, scope, discovery_module.digest(source)),)))

            # Owner authorization is checked independently of the shared
            # library reader and again after provider execution. Revocation
            # must stop at admission, before any vector/container/provider IO.
            before = dict(counters)
            with closing(sqlite3.connect(database, timeout=0.25)) as db, db:
                prior_status = db.execute(
                    "SELECT status FROM access_memberships WHERE account_id='pilot-owner' AND library_id=?",
                    (library,)).fetchone()[0]
                db.execute("UPDATE access_memberships SET status='revoked' "
                    "WHERE account_id='pilot-owner' AND library_id=?", (library,))
            try:
                response, _elapsed = request(queries[0]["text"])
                _require(response.status_code in (401, 403) and counters == before
                    and "items" not in response.json(), "revoked_owner_reached_semantic_io")
            finally:
                with closing(sqlite3.connect(database, timeout=0.25)) as db, db:
                    db.execute("UPDATE access_memberships SET status=? "
                        "WHERE account_id='pilot-owner' AND library_id=?",
                        (prior_status, library))
            restored, _elapsed = request(queries[0]["text"])
            _require(restored.status_code == 200, "owner_membership_restore_failed")
            protected.append("owner_revocation_denied_before_bulk_provider_or_vector_io_and_restore_succeeded")

            def assert_stale_bulk_refuses(label, mutate, restore, *, filters=None):
                prior_provider = discovery.provider
                before = dict(counters)
                try:
                    mutate()
                    replace_reviewed_source()
                    response, _elapsed = request(queries[0]["text"], filters=filters)
                    _require(response.status_code == 503 and "items" not in response.json()
                        and counters["provider_calls"] == before["provider_calls"]
                        and counters["model_encode_calls"] == before["model_encode_calls"]
                        and counters["vector_reads"] == before["vector_reads"],
                        label + "_stale_bulk_cohort_reached_inference_or_released_cards")
                finally:
                    try:
                        restore()
                    finally:
                        object.__setattr__(discovery, "provider", prior_provider)
                recovered, _elapsed = request(queries[0]["text"])
                _require(recovered.status_code == 200, label + "_restore_failed")

            # A soft-deleted image leaves the old immutable bulk cohort stale.
            # Advance only the synthetic reviewed source so the request reaches
            # the pinned bulk validation path instead of stopping at 409.
            with closing(sqlite3.connect(database, timeout=0.25)) as db:
                prior_asset_status = db.execute(
                    "SELECT status FROM assets WHERE id=?", (int(records[0].asset_id),)).fetchone()[0]

            def delete_asset():
                with closing(sqlite3.connect(database, timeout=0.25)) as db, db:
                    db.execute("UPDATE assets SET status='deleted' WHERE id=?",
                        (int(records[0].asset_id),))

            def restore_asset():
                with closing(sqlite3.connect(database, timeout=0.25)) as db, db:
                    db.execute("UPDATE assets SET status=? WHERE id=?",
                        (prior_asset_status, int(records[0].asset_id)))

            assert_stale_bulk_refuses("synthetic_asset_soft_delete", delete_asset, restore_asset)
            protected.append("soft_deleted_asset_refused_by_stale_bulk_cohort_before_inference")

            with closing(sqlite3.connect(database, timeout=0.25)) as db:
                prior_vector_scope = db.execute(
                    "SELECT asset_id,library_id FROM access_asset_libraries "
                    "WHERE asset_id=? AND library_id=?",
                    (int(records[0].asset_id), library)).fetchone()

            def remove_scoped_artifact():
                with closing(sqlite3.connect(database, timeout=0.25)) as db, db:
                    # Vector artifacts are immutable by schema. Retirement from
                    # the current library cohort is represented by removing its
                    # synthetic scope link; the immutable artifact and file stay.
                    db.execute("DELETE FROM access_asset_libraries WHERE asset_id=? AND library_id=?",
                        (int(records[0].asset_id), library))

            def restore_scoped_artifact():
                with closing(sqlite3.connect(database, timeout=0.25)) as db, db:
                    db.execute("INSERT INTO access_asset_libraries(asset_id,library_id) VALUES(?,?)",
                        prior_vector_scope)

            # Asset 1 is outside this date-filtered result set, so removing its
            # current library-scope link reaches the full-cohort snapshot check
            # without becoming a missing per-result vector refusal. The
            # container must reject stale library-wide membership before encoding.
            assert_stale_bulk_refuses("synthetic_scoped_artifact_removal", remove_scoped_artifact,
                restore_scoped_artifact,
                filters={"date": {"from": "2026-01-02", "to": "2026-01-02"}})
            protected.append("scoped_artifact_removal_refused_by_stale_bulk_cohort_before_inference")

    # Mutate and restore only synthetic caption state. The next request proves
    # source-change refusal did not leave stale source binding behind.
    with closing(sqlite3.connect(database, timeout=0.25)) as db, db:
        db.execute("UPDATE captions SET text='Synthetic fixture caption changed' WHERE id=1")
    response, _elapsed = request(queries[0]["text"])
    _require(response.status_code in (409, 503), "stale_synthetic_source_not_refused")
    with closing(sqlite3.connect(database, timeout=0.25)) as db, db:
        db.execute("UPDATE captions SET text='Synthetic fixture caption' WHERE id=1")
    response, _elapsed = request(queries[0]["text"])
    _require(response.status_code == 200, "synthetic_source_restore_failed")
    protected.append("synthetic_source_change_refused_and_restored_separately")

    model.verify()
    _require(_record_digest(index_path) == index_hash
        and _index_file_hashes(index_root, records) == original_vector_hashes,
        "candidate_files_changed_during_canary")
    return {"warmup_ms": warmup_holder[0],
        **({'warmup_profile_ordinal': warmup_profile_ordinal} if request_observer else {}),
        "shared_admission_pool": runtime_budget.slots is base_budget.slots}


def run(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, _message):
            raise LibrarySemanticRefused()
    try:
        parser = Parser(description=__doc__)
        parser.parse_args(argv)
        print(json.dumps({"status": "library_semantic_plan", "private_files_read": False,
            "models_loaded": False, "listener_started": False, "activation_performed": False}))
        return 0
    except Exception:
        print('{"error":"library_semantic_measurement_unavailable"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
