"""Extend the prior exact corpus with bounded multi-seed byte-buffer cases."""
import json,math,random,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];old=ROOT/'rust/vector-core/cases.jsonl'
# Retain every old input/outcome in its existing commit; new recording below
# must reproduce all of those outcomes exactly before acceptance.
cases=[json.loads(line)for line in old.read_text(encoding='utf-8').split('\n')if line.strip()]
inputs=[{'fn':'run_batch','args':c['args']}for c in cases]
def add(data):inputs.append({'fn':'run_batch','args':[json.dumps(data,separators=(',',':'),ensure_ascii=True)]})
rng=random.Random(20261121)
for order in ['little','big']:
 code='<'if order=='little'else'>'
 def batch(rows,queries):
  d=len(queries[0]);return {'op':'best_seed','dimension':d,'byteorder':order,'data':b''.join(struct.pack(f'{code}{d}d',*r)for r in rows).hex(),'query':b''.join(struct.pack(f'{code}{d}d',*q)for q in queries).hex()}
 for dimension in [1,2,3,7,32,128,768,4096]:
  for count in [1,2,24]:
   queries=[[rng.uniform(-1,1)for _ in range(dimension)]for _ in range(count)]
   rows=[queries[0],queries[-1],list(reversed(queries[0]))]
   add(batch(rows,queries));add(batch(rows,[queries[0]]*count));add(batch([],queries))
 for row in [[1e16,1,-1e16],[1e-16,1,1e16],[-0.0,0.0],[2**-1074,2**-1074],[1e308,1e308]]:
  add(batch([row],[[1]*len(row),[-1]*len(row)]))
 for invalid in [math.nan,math.inf,-math.inf]:
  add(batch([[invalid,0]],[[1,0]]));add(batch([[1,0]],[[invalid,0]]))
 base=batch([[1,0]],[[1,0]])
 for key,value in [('query',''),('query','00'),('query','FF'),('query','0'),('query',None),('data','00'),('data',False),('dimension',0),('dimension',4097),('dimension',True),('dimension',1.0),('byteorder','native')]:add(dict(base,**{key:value}))
 add(batch([[1,0]]*513,[[1,0]]));add(batch([[1,0]],[[1,0]]*25));add(dict(base,extra=1))
 for key in base:
  value=dict(base);del value[key];add(value)
path=ROOT/'rust/vector-core/visual-inputs.jsonl';path.write_text(''.join(json.dumps(x,ensure_ascii=True)+'\n'for x in inputs),encoding='utf-8');print(json.dumps({'old_cases':len(cases),'new_inputs':len(inputs)-len(cases),'total_inputs':len(inputs)}))
