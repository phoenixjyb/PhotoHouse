#!/usr/bin/env python3
"""Verify frozen consumer fixtures offline; optionally replay against pinned backend.

Default mode is Python-stdlib only. --backend-root uses the explicitly selected
interpreter's dependencies and temporary synthetic databases/media, never settings,
listeners or production data. --record is coordinator-only fixture maintenance.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'contracts/v1'
BACKEND_SHA = '87a60b475b37b1d6873cd977bcb6e7254472da7e'
REPLAY_IMAGE = ROOT / 'scripts/fixtures/replay-8x8.jpg'
REPLAY_IMAGE_SHA256 = 'c311363ddcc33e304b4f657d7fb3353c839bcdbdb9bdbd09bea62b1152fac42d'


def read(name): return json.loads((CONTRACT / name).read_text())
def dump(path, value): path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def replay_image_bytes():
    # Fixture-only asset: independent of the frozen wire-contract file set.
    data = REPLAY_IMAGE.read_bytes()
    assert len(data) == 632 and hashlib.sha256(data).hexdigest() == REPLAY_IMAGE_SHA256, 'Replay image identity differs'
    return data


def validate(value, schema, spec):
    """Strict validator for the JSON Schema subset used by this snapshot only."""
    if '$ref' in schema:
        assert schema['$ref'].startswith('#/components/schemas/')
        return validate(value, spec['components']['schemas'][schema['$ref'].split('/')[-1]], spec)
    supported = {'type','properties','required','additionalProperties','items','enum','pattern',
                 'minimum','maximum','minLength','maxLength','description','writeOnly','default'}
    assert set(schema) <= supported, 'Unreviewed schema keyword'
    kinds = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
    actual = ('null' if value is None else 'boolean' if type(value) is bool else 'integer' if type(value) is int
              else 'number' if type(value) is float else 'string' if isinstance(value,str)
              else 'array' if isinstance(value,list) else 'object' if isinstance(value,dict) else 'invalid')
    assert actual in kinds or actual == 'integer' and 'number' in kinds, (actual,kinds)
    if 'enum' in schema: assert value in schema['enum']
    if actual == 'object':
        assert set(schema.get('required',[])) <= set(value)
        if schema.get('additionalProperties') is False: assert set(value) <= set(schema['properties'])
        for key,item in value.items(): validate(item,schema['properties'][key],spec)
    if actual == 'array':
        for item in value: validate(item,schema['items'],spec)
    if actual == 'string':
        if 'pattern' in schema: assert re.search(schema['pattern'],value)
        assert schema.get('minLength',0) <= len(value) <= schema.get('maxLength',len(value))
    if actual in ('integer','number'):
        assert schema.get('minimum',value) <= value <= schema.get('maximum',value)


def backend_cases(backend):
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=backend,text=True).strip() == BACKEND_SHA, 'Backend SHA differs'
    manifest = read('manifest.json') if (CONTRACT/'manifest.json').exists() else None
    if manifest:
        for name, expected in manifest['backend_sources'].items(): assert sha(backend/name) == expected, name
    with ExitStack() as guards:
        for target in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system'):
            guards.enter_context(patch(target,side_effect=AssertionError('External I/O forbidden')))
        return _guarded_backend_cases(backend)


def _guarded_backend_cases(backend):
    image_bytes = replay_image_bytes()
    sys.path[:0] = [str(backend/'backend'), str(backend/'tests/security')]
    from fastapi.testclient import TestClient
    import test_library_reads as fixture
    from test_access_foundation import NOW, MEMBER, NEW, PASSWORD
    from app.access.runtime import RuntimeConfiguration
    from app.access.service import AccessService
    spec = read('openapi.json')
    cases = []; identities = {}; now = [NOW]
    def normalized(value):
        if isinstance(value,dict):
            return {k: ('F'*43 if k=='access_token' else normalized(v)) for k,v in value.items()}
        if isinstance(value,list): return [normalized(item) for item in value]
        if isinstance(value,str) and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',value):
            if value not in identities: identities[value] = f'00000000-0000-4000-8000-{len(identities)+1:012d}'
            return identities[value]
        return value
    fixture.LibraryReadTests.setUpClass()
    try:
        db = fixture.LibraryReadTests.template
        db.execute("UPDATE captions SET created_at='2026-01-01 00:00:00',updated_at=NULL")
        db.execute("UPDATE captions SET text='Synthetic hillside. 合成山景。' WHERE id=101")
        db.execute("UPDATE captions SET text='<script>synthetic text only</script>' WHERE id=102")
        db.commit()
        database = Path(db.execute('PRAGMA database_list').fetchone()[2])
        with tempfile.TemporaryDirectory(prefix='photohouse-contract-media-') as media:
            directory=Path(media); originals=directory/'originals'; originals.mkdir()
            derived=directory/'derived'; thumbs=derived/'thumbnails/256'; thumbs.mkdir(parents=True)
            (originals/'synthetic.jpg').write_bytes(image_bytes); (thumbs/'101.jpg').write_bytes(image_bytes)
            db.execute('UPDATE assets SET path=? WHERE id=101',(str(originals/'synthetic.jpg'),)); db.commit()
            app=RuntimeConfiguration(database=database,web_origin='https://photohouse.test',
                original_roots=(originals,),derived_root=derived).build_app(clock=lambda:now[0])
            actual={(m,r.path) for r in app.routes for m in (getattr(r,'methods',None) or [])}
            assert {(m.upper(),p) for p,ops in spec['paths'].items() for m in ops} <= actual
            with TestClient(app,base_url='https://photohouse.test',client=('192.0.2.30',1234)) as client:
                def capture(name,operation,method,path,expected,token=None,body=None,headers=None,binary=False):
                    request_headers=dict(headers or {})
                    if token: request_headers['Authorization']='Bearer '+token
                    response=client.request(method,path,json=body,headers=request_headers)
                    assert response.status_code==expected,(name,response.status_code)
                    case={'id':name,'operation_id':operation,'status':expected}
                    if binary:
                        case['body_kind']='binary' if method!='HEAD' else 'empty'
                        case['content_type']=response.headers.get('content-type')
                        if 'content-range' in response.headers: case['content_range']=response.headers['content-range']
                        case['byte_length']=len(response.content)
                    else: case['body']=normalized(response.json())
                    assert response.headers['cache-control']=='no-store'
                    cases.append(case); return response
                login=capture('login','login','POST','/auth/login',200,body={'phone':MEMBER,'password':PASSWORD,'transport':'native'})
                token=login.json()['access_token']
                capture('approved','session','GET','/auth/session',200,token)
                capture('gallery','gallery','GET','/assets?library=family-a',200,token)
                capture('detail','detail','GET','/assets/detail/101?library=family-a',200,token)
                capture('captions-bilingual','captions','GET','/assets/101/captions?library=family-a',200,token)
                capture('captions-untrusted-text','captions','GET','/assets/102/captions?library=family-a',200,token)
                db.execute("UPDATE assets SET mime='video/mp4',duration_sec=2.0 WHERE id=102");db.commit()
                capture('video-metadata-only','detail','GET','/assets/detail/102?library=family-a',200,token)
                capture('empty-page','gallery','GET','/assets?library=family-a&page=2',200,token)
                capture('foreign-asset','detail','GET','/assets/detail/201?library=family-a',401,token)
                capture('missing-original-permission','originalGet','GET','/assets/101/media?library=family-a',401,token)
                capture('thumbnail','thumbnailGet','GET','/assets/101/thumbnail?library=family-a',200,token,binary=True)
                capture('thumbnail-head','thumbnailHead','HEAD','/assets/101/thumbnail?library=family-a',200,token,binary=True)
                capture('missing-thumbnail','thumbnailGet','GET','/assets/102/thumbnail?library=family-a',404,token)
                capture('malformed-query','gallery','GET','/assets?library=family-a&extra=1',400,token)
                capture('anonymous','session','GET','/auth/session',401)
                capture('invalid-invitation','registerInvited','POST','/auth/register',401,
                        body={'phone':NEW,'password':PASSWORD,'transport':'native','code':'synthetic-invalid-code'})
                service=AccessService(db,clock=lambda:now[0])
                code=service.invite(fixture.LibraryReadTests.owner_token,'family-a',NEW)
                registration=capture('invited-registration','registerInvited','POST','/auth/register',201,
                    body={'phone':NEW,'password':PASSWORD,'transport':'native','code':code})
                capture('invited-viewer','session','GET','/auth/session',200,registration.json()['access_token'])
                second_code=service.invite(fixture.LibraryReadTests.other_token,'family-b',MEMBER)
                capture('accept-second-library','acceptInvitation','POST','/auth/invitations/accept',200,token,body={'code':second_code})
                capture('two-libraries','session','GET','/auth/session',200,token)
                db.execute('DELETE FROM access_memberships WHERE account_id=? AND library_id=?',(fixture.LibraryReadTests.member_id,'family-b'));db.commit()
                for status in ('requested','rejected','revoked'):
                    db.execute('UPDATE access_memberships SET status=?,revision=2 WHERE account_id=?',(status,fixture.LibraryReadTests.member_id));db.commit()
                    capture(status,'session','GET','/auth/session',200,token)
                    capture(status+'-read-denied','gallery','GET','/assets?library=family-a',401,token)
                db.execute("UPDATE access_memberships SET status='approved',revision=3,originals=1 WHERE account_id=?",(fixture.LibraryReadTests.member_id,));db.commit()
                capture('original-authorized','originalGet','GET','/assets/101/media?library=family-a',200,token,binary=True)
                capture('original-range','originalGet','GET','/assets/101/media?library=family-a',206,token,headers={'Range':'bytes=0-5'},binary=True)
                capture('original-head','originalHead','HEAD','/assets/101/media?library=family-a',200,token,binary=True)
                db.execute('DELETE FROM captions WHERE asset_id=102');db.commit()
                capture('captions-missing','captions','GET','/assets/102/captions?library=family-a',200,token)
                db.execute('UPDATE access_memberships SET expires_at=? WHERE account_id=?',(NOW+1,fixture.LibraryReadTests.member_id));db.commit()
                now[0]=NOW+2
                capture('membership-expired','session','GET','/auth/session',200,token)
                capture('membership-expired-read-denied','gallery','GET','/assets?library=family-a',401,token)
                db.execute('DELETE FROM access_memberships WHERE account_id=?',(fixture.LibraryReadTests.member_id,));db.commit()
                capture('no-memberships','session','GET','/auth/session',200,token)
                now[0]=NOW+86400
                capture('expired','session','GET','/auth/session',401,token)
                now[0]=NOW
                capture('logout','logout','POST','/auth/logout',200,token)
                capture('logged-out','session','GET','/auth/session',401,token)
                db.execute("INSERT INTO access_attempts VALUES ('global',?,60) ON CONFLICT(bucket) DO UPDATE SET attempts=60,expires_at=excluded.expires_at",(NOW+600,));db.commit()
                capture('rate-limited','login','POST','/auth/login',429,body={'phone':MEMBER,'password':PASSWORD,'transport':'native'})
                app.state.access_runtime=None
                capture('unavailable','session','GET','/auth/session',503,token)
    finally: fixture.LibraryReadTests.tearDownClass()
    return {'contract_version':'1.0.0-fixture.1','synthetic_only':True,'normalization':'Tokens replaced by inert F characters; UUIDs mapped to fixed synthetic IDs; no reusable credentials retained.','cases':cases}


def verify():
    replay_image_bytes()
    manifest=read('manifest.json');spec=read('openapi.json'); fixtures=read('fixtures.json')
    assert manifest['backend_commit']==BACKEND_SHA==spec['x-backend-commit']
    assert spec['openapi']=='3.1.0' and spec['x-real-networking-enabled'] is False and 'servers' not in spec
    for name,expected in manifest['files'].items(): assert sha(CONTRACT/name)==expected, name+' checksum mismatch'
    assert set(manifest['files'])=={str(p.relative_to(CONTRACT)) for p in CONTRACT.rglob('*') if p.is_file() and p.name!='manifest.json'}
    operations={op['operationId']:op for methods in spec['paths'].values() for op in methods.values()}
    assert len(operations)==12
    assert len({case['id'] for case in fixtures['cases']})==len(fixtures['cases'])
    for case in fixtures['cases']:
        response=operations[case['operation_id']]['responses'][str(case['status'])]
        if 'body' in case: validate(case['body'],response['content']['application/json']['schema'],spec)
    for schema in spec['components']['schemas'].values():
        assert isinstance(schema,dict)
    scenarios=read('client-scenarios.json')
    assert scenarios['network_enabled'] is False
    assert scenarios['contract_version']==fixtures['contract_version']==spec['info']['version']
    names={case['id'] for case in fixtures['cases']}
    assert len({case['id'] for case in scenarios['scenarios']})==len(scenarios['scenarios'])
    for scenario in scenarios['scenarios']: assert set(scenario['responses']) <= names
    for url,path in scenarios['thumbnail_resources'].items():
        assert url.startswith('/assets/') and not url.startswith('//')
        assert path in manifest['files'] and path.startswith('media/')
    print(f"PASS frozen contract: {len(operations)} operations, {len(fixtures['cases'])} ASGI cases, {len(manifest['files'])} checksummed files")


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-root',type=Path)
    parser.add_argument('--record',action='store_true',help='Coordinator only: regenerate synthetic fixtures')
    args=parser.parse_args()
    if args.record and not args.backend_root: parser.error('--record requires --backend-root')
    if args.backend_root:
        cases=backend_cases(args.backend_root.resolve())
        if args.record: dump(CONTRACT/'fixtures.json',cases)
        else:
            assert cases==read('fixtures.json'), 'Backend fixture drift; coordinator review required'
            print(f"PASS pinned backend replay: {len(cases['cases'])} synthetic ASGI cases; no listeners/models/live data")
    if not args.record: verify()
