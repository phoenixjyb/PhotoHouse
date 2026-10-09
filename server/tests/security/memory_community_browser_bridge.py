"""Synthetic, no-listener ASGI bridge for the community browser checkpoint."""
import base64
from contextlib import closing
import json
from pathlib import Path
import sys
import uuid
import httpx

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'tests/security'))
from test_library_reads import LibraryReadTests
from test_access_foundation import MEMBER, PASSWORD
from app.access.media import MediaRuntime
from app.access.memory_processing import process_contribution,process_job
from app.access.runtime import AccessRuntime
from app.access.service import AccessService
from app.access.assistant_speech import LocalAssistantAsr
from app.access.discovery import ReadBudget
from app.access.discovery_transport import DiscoveryRuntime
from app.access.discovery_provider import MemoryIndexProvider
from app.main import create_app

fixture=LibraryReadTests()
LibraryReadTests.setUpClass()
fixture.setUp()
fixture.client.close()
root=fixture.path.parent
originals=root/'originals';derived=root/'derived'
originals.mkdir();(derived/'thumbnails/256').mkdir(parents=True)
for ident,color in ((101,'#b6c7b0'),(102,'#d2ad89'),(201,'#8aa9c4')):
    image=Image.new('RGB',(400,300),color)
    draw=ImageDraw.Draw(image);draw.rectangle((24,24,376,276),outline='#fff9ed',width=4)
    draw.text((132,142),f'SYNTHETIC {ident}',fill='#302c28')
    image.save(originals/f'{ident}.jpg');image.save(derived/f'thumbnails/256/{ident}.jpg')
    fixture.mutate('UPDATE assets SET path=? WHERE id=?',(str(originals/f'{ident}.jpg'),ident))

# A second protected library lets the browser verify that changing scope clears
# the first library's book, contribution and conversation content.
with fixture.connection() as db:
    access=AccessService(db,clock=lambda:fixture.now)
    code=access.invite(fixture.other_token,'family-b',MEMBER)
    access.accept_invitation(fixture.member_token,code)

runtime=AccessRuntime(fixture.connection,'https://photohouse.test',clock=lambda:fixture.now)
asr_requests=[]
def synthetic_asr(request):
    asr_requests.append(len(request.content))
    return httpx.Response(200,json={'success':True,'text':'合成口述：湖边的家庭回忆。'})
asr=LocalAssistantAsr(url='http://127.0.0.1:8021/transcribe',model='synthetic-only',
                     transport=httpx.MockTransport(synthetic_asr))
app=create_app(access_runtime=runtime,media_runtime=MediaRuntime((originals,),derived),
    discovery_runtime=DiscoveryRuntime(runtime,MemoryIndexProvider(()),ReadBudget()),
    memory_collaboration_enabled=True,memory_originals_enabled=True,memory_generation_enabled=True,
    assistant_enabled=True,assistant_asr=asr)
fixture.client=TestClient(app,base_url='https://photohouse.test',client=('192.0.2.25',23461))
fixture.client.headers['Sec-Fetch-Site']='same-origin'
fixture.addCleanup(fixture.client.close)

# Seed a real protected saved story through its existing workspace/HTTP routes.
headers={'Authorization':'Bearer '+fixture.owner_token}
preview=fixture.client.post('/story-workspace/preview?library=family-a',headers=headers,
    json={'asset_ids':'101,102','title':'一起走过的日子','theme':'everyday','language':'zh'})
if preview.status_code!=200:raise RuntimeError('Synthetic story setup failed')
draft=preview.json();draft['chapters'][0]['narration']='家人一起沿着湖边散步，留下了这段回忆。'
body={'title':draft['title'],'theme':draft['theme'],'language':'zh','asset_ids':'101,102',
      'chapters':json.dumps(draft['chapters'],ensure_ascii=False),
      'selection_revision':draft['selection_revision'],'revision':'0','mutation_id':str(uuid.uuid4())}
saved=fixture.client.post('/memory-stories?library=family-a',headers=headers,json=body)
if saved.status_code!=200:raise RuntimeError('Synthetic saved story setup failed')
story_id=saved.json()['id']
second_body={**body,'title':'第二段家庭回忆','mutation_id':str(uuid.uuid4())}
second_chapters=json.loads(second_body['chapters'])
second_chapters[0]['narration']='第二段合成故事：家人坐下来，继续聊起往事。'
second_body['chapters']=json.dumps(second_chapters,ensure_ascii=False)
second=fixture.client.post('/memory-stories?library=family-a',headers=headers,json=second_body)
if second.status_code!=200:raise RuntimeError('Synthetic second story setup failed')
fixture.mutate('UPDATE access_memory_stories SET updated_at=? WHERE id=?',(fixture.now-1,second.json()['id']))


class FakeNarrator:
    def companion(self,bundle):
        last=bundle['recent_turns'][-1]['user'] if bundle['recent_turns'] else '刚才的回忆'
        source_ids=[]
        for kind in ('family','transcript','ai','editorial','metadata'):
            source=next((item for item in bundle['sources'] if item['kind']==kind),None)
            if source is not None:source_ids.append(source['id'])
        return {'version':1,'kind':'answer','reply':'本地模拟助手记下了：'+last,
                'source_ids':source_ids,'questions':['你还记得那天还有谁在场吗？'],'proposal':None}

    def narrative(self,bundle):
        chapters=[]
        for chapter in bundle['chapters']:
            refs=chapter['evidence_ids'][:1]
            chapters.append({'id':chapter['id'],'narration':'待家人核对的整理建议：'+chapter['narration'],
                             'source_ids':refs})
        return {'version':1,'title':'需要核对的家庭回忆建议','chapters':chapters,
                'questions':['这段记忆的时间还需要补充吗？'],'needs_review':True}


def worker_job():
    from app.access.memory_processing import process_job
    with fixture.connection() as db:
        return process_job(db,narrator=FakeNarrator(),clock=lambda:fixture.now)


def worker_contribution():
    with fixture.connection() as db:
        return process_contribution(db,
            transcribe=lambda _audio,_language:{'text':'合成录音里的湖边回忆。','provider':'synthetic','model':'fixture-asr'},
            polish=lambda source,_language:{'text':'本地整理：'+source,'tags':['湖边','家人'],
                                           'provider':'synthetic','model':'fixture-polish'},
            clock=lambda:fixture.now)


def state():
    with fixture.connection() as db:
        story=db.execute('SELECT revision,content FROM access_memory_stories WHERE id=?',(story_id,)).fetchone()
        contributions=db.execute('''SELECT c.kind,c.state,c.original_text,length(c.original_audio),
                d.state,d.transcript FROM access_memory_contributions c LEFT JOIN access_memory_contribution_derivations d
                ON d.contribution_id=c.id ORDER BY c.created_at,c.id''').fetchall()
        jobs=db.execute('SELECT kind,state FROM access_memory_jobs ORDER BY created_at,id').fetchall()
        books=db.execute('SELECT count(*) FROM access_memory_books').fetchone()[0]
        return {'story_revision':story[0],'story_content':story[1],
                'contributions':[tuple(row) for row in contributions],
                'jobs':[tuple(row) for row in jobs],'books':books,'asr_requests':asr_requests}

def seed_long_thread(target_story_id):
    headers={'Authorization':'Bearer '+fixture.member_token}
    with fixture.connection() as db:
        row=db.execute('SELECT revision FROM access_memory_stories WHERE id=?',(target_story_id,)).fetchone()
        if row is None:raise RuntimeError('Synthetic long-thread story is missing')
        revision=row[0]
    conversation_id=str(uuid.uuid4())
    response=fixture.client.post('/memory-community/v1/conversations?library=family-a',headers=headers,
        json={'id':conversation_id,'target_type':'story','target_id':target_story_id})
    if response.status_code!=200:raise RuntimeError(f'Synthetic long-thread conversation failed: {response.status_code}')
    job_id=None
    for sequence in range(1,18):
        response=fixture.client.post(f'/memory-community/v1/conversations/{conversation_id}/turns?library=family-a',headers=headers,
            json={'revision':str(revision),'mutation_id':str(uuid.uuid4()),'text':f'Synthetic long thread turn {sequence}'})
        if response.status_code!=200:raise RuntimeError(f'Synthetic long-thread turn {sequence} failed: {response.status_code} {response.text}')
        job_id=response.json()['id']
        if sequence<17:
            outcome=worker_job()
            if outcome.get('state')!='ready':raise RuntimeError(f'Synthetic long-thread reply {sequence} did not become ready')
    with fixture.connection() as db:
        db.execute('UPDATE access_memory_conversations SET created_at=? WHERE id=?',(fixture.now+1,conversation_id))
    listed=fixture.client.get(f'/memory-community/v1/conversations?library=family-a&target_type=story&target_id={target_story_id}',headers=headers)
    if listed.status_code!=200:raise RuntimeError(f'Synthetic long-thread listing failed: {listed.status_code} {listed.text}')
    return {'story_id':target_story_id,'conversation_id':conversation_id,'pending_job_id':job_id,'turn_count':17,'listed_ids':[item['id'] for item in listed.json()['items']]}


try:
    print(json.dumps({'ready':True,'story_id':story_id}),flush=True)
    for line in sys.stdin:
        message=json.loads(line)
        command=message.get('command')
        if command=='quit':break
        if command=='worker-job':
            print(json.dumps({'id':message['id'],'outcome':worker_job()},ensure_ascii=False),flush=True);continue
        if command=='worker-contribution':
            print(json.dumps({'id':message['id'],'outcome':worker_contribution()},ensure_ascii=False),flush=True);continue
        if command=='state':
            print(json.dumps({'id':message['id'],'state':state()},ensure_ascii=False),flush=True);continue
        if command=='seed-long-thread':
            print(json.dumps({'id':message['id'],'seed':seed_long_thread(message['story_id'])},ensure_ascii=False),flush=True);continue
        fixture.client.cookies.clear()
        response=fixture.client.request(message['method'],message['path'],headers=message['headers'],
            content=base64.b64decode(message.get('body','')),follow_redirects=False)
        fixture.client.cookies.clear()
        result={'id':message['id'],'status':response.status_code,'headers':dict(response.headers),
                'body':base64.b64encode(response.content).decode()}
        # Run only the synthetic provider adapter after the real queue request has
        # committed. The browser receives the queued receipt then observes the
        # completed result through its ordinary authenticated GET/poll path.
        if response.status_code==200 and message['method']=='POST':
            if message['path'].split('?')[0].endswith('/review'):
                try:
                    if json.loads(base64.b64decode(message.get('body','')).decode()).get('state')=='accepted':
                        result['worker_contribution']=worker_contribution()
                except (ValueError,UnicodeError):pass
            elif '/conversations/' in message['path'] and message['path'].split('?')[0].endswith('/turns'):
                result['worker_job']=worker_job()
            elif message['path'].split('?')[0].endswith('/jobs'):
                result['worker_job']=worker_job()
        print(json.dumps(result,ensure_ascii=False),flush=True)
finally:
    fixture.doCleanups()
    LibraryReadTests.tearDownClass()
