#!/usr/bin/env python3
"""Create a fresh synthetic export and capture real ASGI responses for the JVM parser."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, required=True)
args = parser.parse_args()
root = args.source_root.resolve(strict=True)
sys.path[:0] = [str(root/'scripts'), str(root/'backend')]
import export_home_discovery as exporter
from build_home_discovery_export_fixture import create
from app.home_discovery import Configuration, create_home_discovery
from fastapi.testclient import TestClient

with tempfile.TemporaryDirectory(prefix='android-discovery-export-') as temporary, ExitStack() as stack:
    for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
        stack.enter_context(patch(target, side_effect=AssertionError('External operation forbidden')))
    # The approval below is test-only, over the fresh synthetic fixture just created here.
    fixture = create(Path(temporary).resolve()/'fixture')
    database, candidate, request = fixture/'snapshot.sqlite', fixture/'candidate', fixture/'request.json'
    before = {p.relative_to(fixture).as_posix(): exporter.sha(p.read_bytes()) for p in fixture.rglob('*') if p.is_file()}
    review = exporter.review(database, candidate, request, fixture/'review.json')
    approval = {'version': 1, 'plan_sha256': review['plan_sha256'], **{key: True for key in (
        'approve_selection', 'approve_roster', 'approve_assignments', 'approve_regions', 'approve_metadata')}}
    (fixture/'synthetic-approval.json').write_bytes(exporter.packed(approval))
    publication = fixture/'published'
    receipt = exporter.publish(database, candidate, request, fixture/'review.json', fixture/'synthetic-approval.json', publication)
    assert receipt['enabled'] is False
    assert all(exporter.sha((fixture/name).read_bytes()) == digest for name, digest in before.items())
    control_path = publication/'control.json'
    disabled = control_path.read_bytes()
    config = Configuration(control_path, publication/'prepared', 'https://home.photohouse.test:18444', ('192.168.40.0/24',))
    app = create_home_discovery(config, publication/'discovery.json', receipt['output_hashes']['discovery.json'])
    responses = {}
    with TestClient(app, base_url=config.origin, client=('192.168.40.20', 1)) as client:
        for route in ('/home/v2/catalog', '/home/discovery/v1/facets'):
            assert client.get(route).status_code == 403
        try:
            control = json.loads(disabled); control['enabled'] = True
            control_path.write_bytes(exporter.packed(control))
            for name in ('people', 'tags', 'locations'):
                response = client.get('/home/discovery/v1/facets', params={'facet': name, 'page': 1, 'page_size': 50, 'revision': 7})
                assert response.status_code == 200
                responses[name] = response.json()
            filters = {
                'combined': {'people': {'ids': [201, 202], 'match': 'all'}, 'caption': 'family',
                    'tags': {'ids': [301, 302], 'match': 'all'}, 'locations': [401],
                    'date': {'from': '2025-12-01', 'to': '2025-12-01'}, 'media': ['photo']},
                'videos': {'media': ['video']},
                'caption-is-not-identity': {'people': {'ids': [201], 'match': 'any'}, 'caption': 'sample child'},
            }
            for name, selection in filters.items():
                response = client.post('/home/discovery/v1/search', json={'revision': 7, 'page': 1, 'page_size': 50, 'filters': selection})
                assert response.status_code == 200
                responses[name] = response.json()
        finally:
            control_path.write_bytes(disabled)
        assert client.get('/home/discovery/v1/facets').status_code == 403
    assert all(exporter.sha((publication/name).read_bytes()) == digest for name, digest in receipt['output_hashes'].items())
    print(json.dumps({'synthetic_only': True, 'final_enabled': False, 'input_unchanged': True,
        'coverage': receipt['coverage'], 'output_hashes': receipt['output_hashes'], 'responses': responses}, indent=2, sort_keys=True))
