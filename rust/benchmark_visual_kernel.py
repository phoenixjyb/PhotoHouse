"""Generated full-call visual ranking benchmark; excludes file/DB/model work."""
import argparse,hashlib,json,math,os,platform,random,statistics,struct,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def fixture(seed_count):
    from app.access import visual_candidates as visual
    rng=random.Random(20261121);dimension=768;values=[]
    for _ in range(64):
        row=[rng.uniform(-1,1)for _ in range(dimension)];norm=math.sqrt(math.fsum(x*x for x in row))
        values.append(tuple(struct.unpack(f'>{dimension}f',struct.pack(f'>{dimension}f',*(x/norm for x in row)))))
    identity=visual.VectorSpaceIdentity('a'*64,'b'*64,'synthetic-visual-v1','synthetic-v1',dimension,'unit_l2')
    checksums=[visual.canonical_vector_checksum(v)for v in values]
    seeds=tuple(visual.VectorRecord(str(i+1),identity,values[i],checksums[i])for i in range(seed_count))
    candidates=tuple(visual.VectorRecord(str(i+25),identity,values[i%64],checksums[i%64])for i in range(512))
    args={'authorization':visual.AuthorizationSnapshot('fixture',frozenset(r.asset_id for r in seeds+candidates)),
          'seed_ids':tuple(r.asset_id for r in seeds),'seed_vectors':seeds,
          'candidate_ids':tuple(r.asset_id for r in candidates),'candidate_vectors':candidates,'expected_identity':identity}
    return args

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--engine',choices=['python','rust'],required=True);parser.add_argument('--seeds',choices=[1,2,4,8,16,24],type=int,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--native-dir',type=Path);parser.add_argument('--mode',choices=['visual','group'],default='visual');a=parser.parse_args()
    if os.name=='nt'and any(p.drive.upper()!='D:'for p in [ROOT,a.output]):parser.error('Windows source/output must be on D:')
    sys.path[:0]=[str(a.native_dir or ROOT/'rust/vector-python/target/python'),str(ROOT/'server/backend'),str(ROOT/'rust')]
    from app.access import visual_candidates as visual
    args=fixture(a.seeds)
    if a.mode=='group':
        from app.access.memory_grouping import propose_memory_group
        target=propose_memory_group;args['capture_times']={key:'2026-05-01T10:00:00'for key in args['authorization'].photo_ids}
    else:target=visual.rank_visual_candidates
    os.environ['PHOTOHOUSE_VISUAL_ENGINE']='python';reference=target(**args);assert reference.status=='ready'and (reference.candidates or a.seeds==24)
    os.environ['PHOTOHOUSE_VISUAL_ENGINE']=a.engine
    assert target(**args)==reference
    wall=[];cpu=[]
    for _ in range(5):
        start=time.perf_counter();c=time.process_time();actual=target(**args);cpu.append(time.process_time()-c);wall.append(time.perf_counter()-start);assert actual==reference
    from dataclasses import asdict
    from benchmark_vector_kernel import process_memory
    result={'status':'PASS','mode':a.mode,'engine':a.engine,'seed_count':a.seeds,'candidates':512,'dimensions':768,'warmups':1,'repeats':5,'wall_seconds':wall,'wall_median':statistics.median(wall),'cpu_seconds':cpu,'python':platform.python_version(),'system':platform.system(),'machine':platform.machine(),'memory':process_memory(),'exact_result_sha256':hashlib.sha256(json.dumps(asdict(reference),sort_keys=True,separators=(',',':')).encode()).hexdigest(),'scope':'Generated full rank_visual_candidates call incl validation/packing/bridge/sort; excludes authorization transaction/file/DB/provider/model/network'}
    result['scoring_engine']='python' if a.engine=='python' or a.seeds==1 else 'rust'
    result['result_count']=len(reference.candidates)
    result['scope']=f'Generated full {target.__name__} call incl validation/eligibility/packing/bridge/sort; excludes authorization transaction/file/DB/provider/model/network'
    result['source_sha256']={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()for n in ['server/backend/app/access/visual_candidates.py','server/backend/app/access/memory_grouping.py','server/backend/app/access/vector_acceleration.py','rust/vector-core/src/port.rs','rust/vector-python/src/lib.rs','rust/benchmark_visual_kernel.py']}
    if a.engine=='rust':
        import photohouse_vector_kernel as native
        result['native_sha256']=hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()
        result['visual_policy']=native.VISUAL_POLICY_FINGERPRINT
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8')as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'status':'PASS','mode':a.mode,'engine':a.engine,'seeds':a.seeds,'median':result['wall_median']}))
if __name__=='__main__':main()
