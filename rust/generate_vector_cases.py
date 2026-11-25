"""Deterministic public/generated characterization, never household vectors."""
import hashlib,json,math,random,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server/backend'))
from app.access.vector_kernel_reference import run_batch,PREFIX
from app.access.visual_candidates import VectorRecord,VectorSpaceIdentity,_canonical_components
out=[]
def add(data):out.append({'fn':'run_batch','args':[json.dumps(data,separators=(',',':'),ensure_ascii=True)]})
def canonical(rows,order='little'):
 d=len(rows[0]);raw=b''.join(struct.pack(f'>{d}f',*r)for r in rows)
 checks=[hashlib.sha256(PREFIX+struct.pack('>I',d)+raw[i:i+d*4]).hexdigest()for i in range(0,len(raw),d*4)]
 return dict(op='canonicalize',dimension=d,byteorder=order,data=raw.hex(),checksums=checks)
rng=random.Random(20261120)
for order in ('little','big'):
 code='<'if order=='little'else'>'
 for dim in (1,2,3,7,32,128,768,4096):
  rows=[]
  for i in range(3):
   v=[rng.uniform(-1,1)for _ in range(dim)];n=math.sqrt(math.fsum(x*x for x in v));rows.append(tuple(x/n for x in v))
  c=canonical(rows,order);add(c)
  result=bytes.fromhex(run_batch(json.dumps(c)))
  ident=VectorSpaceIdentity('a'*64,'b'*64,'fixture','fixture',dim,'unit_l2')
  for i,row in enumerate(rows):
   expected=_canonical_components(VectorRecord('1',ident,row,c['checksums'][i]),ident)
   assert result[i*dim*8:(i+1)*dim*8]==struct.pack(f'{code}{dim}d',*expected)
  add(dict(op='score',dimension=dim,byteorder=order,data=result.hex(),query=result[:dim*8].hex()))
  for bad in ('0'*64,'A'*64,'x',None):add(dict(c,checksums=[bad]+c['checksums'][1:]))
 for row in ((0.0,0.0),(float('nan'),0),(float('inf'),0),(1.0,-0.0),(0.999,0),(0.9989,0),(1.001,0),(1.0009,0),(1.0,2**-149)):
  add(canonical([row],order))
 for products in ((1e16,1,-1e16),(1e-16,1,1e16),(1e-16,1,1e16,-1e16),(-0.0,0.0),(1e308,1e308),(float('inf'),-float('inf')),(float('inf'),1),(float('nan'),1),(2**-1074,2**-1074)):
  d=len(products);add(dict(op='score',dimension=d,byteorder=order,data=struct.pack(f'{code}{d}d',*products).hex(),query=struct.pack(f'{code}{d}d',*([1]*d)).hex()))
 for _ in range(100):
  d=rng.choice((2,7,32,128));values=[rng.choice((-1,1))*rng.random()*2**rng.randint(-530,510)for _ in range(d)]
  add(dict(op='score',dimension=d,byteorder=order,data=struct.pack(f'{code}{d}d',*values).hex(),query=struct.pack(f'{code}{d}d',*([1]*d)).hex()))
base=canonical([(1.0,0.0)])
for key in base:
 d=dict(base);del d[key];add(d)
for key,value in [('dimension',True),('dimension',0),('dimension',4097),('dimension',1.0),('byteorder','native'),('data','00 '),('data','0'),('data','FF'),('data','zz'),('checksums',{}),('checksums',[])]:add(dict(base,**{key:value}))
add(dict(base,extra=1))
add(dict(op='canonicalize',dimension=2,byteorder='little',data='',checksums=[]))
add(dict(op='score',dimension=2,byteorder='little',data='',query=struct.pack('<2d',1,0).hex()))
for d in (None,[],True,1,'hello',{},dict(op='other',dimension=1,byteorder='little',data='')):add(d)
path=ROOT/'rust/vector-inputs.jsonl';path.write_text(''.join(json.dumps(v,ensure_ascii=True)+'\n'for v in out),encoding='utf-8');print('generated',len(out),'cases; canonical bytes match current application exactly')
