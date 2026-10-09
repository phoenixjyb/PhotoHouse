#!/usr/bin/env python3
"""Replay one additive native draft/title contract using synthetic ASGI storage."""
import argparse,hashlib,json,sys,uuid
from unittest.mock import patch
from pathlib import Path

MOBILE=Path(__file__).resolve().parents[1]
PIN='f282472a29d291a8b7ffae1cf6c6ccddd07dc15a'
parser=argparse.ArgumentParser()
parser.add_argument('--backend-root',type=Path,default=MOBILE.parents[1]/'server',
                    help='curated monorepo server directory (defaults to this checkout)')
parser.add_argument('--record',action='store_true',help='Coordinator-only synthetic fixture recording')
args=parser.parse_args()
backend=args.backend_root.resolve()
contract_dir=MOBILE/'android/story-workspace-contract'
manifest_path=contract_dir/'manifest.json'
manifest=json.loads(manifest_path.read_text())
assert manifest['backend_source']==PIN,'Manifest backend revision differs'
for name,digest in manifest['candidate_backend_files'].items():
 assert hashlib.sha256((backend/name).read_bytes()).hexdigest()==digest,'Backend source checksum differs: '+name
if not args.record:
 assert manifest['contract']=='1-preview-title-create','Manifest contract differs'
 for name,digest in manifest['files'].items():
  assert hashlib.sha256((contract_dir/name).read_bytes()).hexdigest()==digest,'Contract file checksum differs: '+name
 assert manifest['fixture_sha256']==manifest['files']['examples.json'],'Fixture manifest checksum differs'

sys.path[:0]=[str(backend/'backend'),str(backend/'tests/security')]
from test_library_reads import LibraryReadTests

class SyntheticTitleAdapter:
 def suggest(self,bundle):
  return {'version':1,'selection_revision':bundle['selection_revision'],
   'titles':[{'text':'一起种花的回忆','source_ids':['family-11111111-1111-4111-8111-111111111111','draft-chapter-1']}],
   'needs_review':True}

LibraryReadTests.setUpClass()
f=LibraryReadTests()
try:
 f.setUp()
 f.mutate("UPDATE assets SET mime='video/mp4',taken_at=NULL,path='mmexport1758585600000.mp4' WHERE id=102")
 f.mutate("""INSERT INTO access_stories
 (id,asset_id,library_id,author_id,revision,title,text,language,byline,created_at,updated_at,deleted)
 VALUES ('11111111-1111-4111-8111-111111111111',101,'family-a',?,1,'家人的回忆','我们一起种花。\r\n这是合成资料。','zh','合成家人',1,1,0)""",(f.member_id,))
 headers={'Authorization':'Bearer '+f.member_token}
 previewRequest={'asset_ids':'102,101','theme':'trip','language':'zh','title':''}
 preview=f.client.post('/story-workspace/preview?library=family-a',headers=headers,json=previewRequest)
 assert preview.status_code==200,preview.status_code
 disabled=f.client.get('/story-workspace/title-capabilities?library=family-a',headers=headers)
 assert disabled.status_code==200
 f.client.app.state.story_title_suggester=SyntheticTitleAdapter()
 enabled=f.client.get('/story-workspace/title-capabilities?library=family-a',headers=headers)
 titleRequest={'asset_ids':'102,101','theme':'trip','language':'zh','selection_revision':preview.json()['selection_revision'],
  'chapters':json.dumps([{'id':'chapter-1','narration':'我们一起种花，这是家人留下的回忆。'}],ensure_ascii=False,separators=(',',':'))}
 titles=f.client.post('/story-workspace/title-suggestions?library=family-a',headers=headers,json=titleRequest)
 assert titles.status_code==200,titles.status_code
 saveRequest={'asset_ids':'102,101','theme':'trip','language':'zh','title':'一起种花的回忆',
  'selection_revision':preview.json()['selection_revision'],'revision':'0',
  'mutation_id':'22222222-2222-4222-8222-222222222222',
  'chapters':json.dumps([dict(c,narration='我们一起种花，这是家人留下的回忆。') for c in preview.json()['chapters']],ensure_ascii=False,separators=(',',':'))}
 denied=f.client.post('/memory-stories?library=family-a',headers=headers,json=saveRequest)
 assert denied.status_code==401
 owner={'Authorization':'Bearer '+f.owner_token}
 with patch('app.access.memory_stories.uuid.uuid4',return_value=uuid.UUID('33333333-3333-4333-8333-333333333333')):
  saved=f.client.post('/memory-stories?library=family-a',headers=owner,json=saveRequest)
 assert saved.status_code==200,saved.status_code
 retry=f.client.post('/memory-stories?library=family-a',headers=owner,json=saveRequest)
 assert retry.status_code==200 and retry.json()==saved.json()
 editedRequest=dict(saveRequest,revision='1',mutation_id='44444444-4444-4444-8444-444444444444',title='家人修改后的标题')
 edited=f.client.put('/memory-stories/'+saved.json()['id']+'?library=family-a',headers=owner,json=editedRequest)
 assert edited.status_code==200 and edited.json()['revision']=='2'
 laterRetry=f.client.post('/memory-stories?library=family-a',headers=owner,json=saveRequest)
 assert laterRetry.status_code==200 and laterRetry.json()==edited.json()
 assert f.client.post('/memory-stories?library=family-a',headers=owner,json=dict(saveRequest,title='复用编号')).status_code==409
 result={'contract':'1-preview-title-create','backend_source':PIN,'library':'family-a','asset_ids':['102','101'],
  'preview_request':previewRequest,'preview':preview.json(),'title_capabilities_off':disabled.json(),
  'title_capabilities_on':enabled.json(),'title_request':titleRequest,'titles':titles.json(),
  'create_request':saveRequest,'created':saved.json(),'create_retry':retry.json(),
  'create_retry_after_edit':laterRetry.json(),'viewer_create_status':denied.status_code}
 encoded=(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
 path=MOBILE/'android/story-workspace-contract/examples.json'
 if args.record:
  path.write_bytes(encoded)
  manifest['contract']='1-preview-title-create'
  manifest['files']={name:hashlib.sha256((contract_dir/name).read_bytes()).hexdigest() for name in manifest['files']}
  manifest['fixture_sha256']=manifest['files']['examples.json']
  manifest['candidate_backend_files']={name:hashlib.sha256((backend/name).read_bytes()).hexdigest()
                                      for name in manifest['candidate_backend_files']}
  manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
 else:assert path.read_bytes()==encoded,'Synthetic backend replay differs from fixture'
 print('Synthetic ASGI workspace/title replay: OK; SHA-256 '+hashlib.sha256(encoded).hexdigest())
finally:
 f.doCleanups();LibraryReadTests.tearDownClass()
