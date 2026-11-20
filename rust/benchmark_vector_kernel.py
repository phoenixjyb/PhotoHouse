"""Same-call generated-data benchmark; bridge, callbacks and sorting included."""
from contextlib import ExitStack
import hashlib,json,math,os,platform,random,statistics,struct,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'rust/vector-python/target/python'),str(ROOT/'server/backend')]
from app.access import semantic_bulk_vectors as bulk
from app.access.visual_candidates import VectorSpaceIdentity,canonical_vector_checksum,_canonical_components,VectorRecord
from app.access.visual_vector_artifacts import ImmutableVectorArtifact,identity_sha256
OUT=ROOT/'.runtime/vector-kernel';OUT.mkdir(parents=True,exist_ok=True)
dimension=768;count=4096;rng=random.Random(20261120);vectors=[]
for _ in range(64):
 v=[rng.uniform(-1,1)for _ in range(dimension)];norm=math.sqrt(math.fsum(x*x for x in v))
 vectors.append(tuple(struct.unpack(f'>{dimension}f',struct.pack(f'>{dimension}f',*(x/norm for x in v)))))
identity=VectorSpaceIdentity('a'*64,'b'*64,'synthetic-vector-v1','synthetic-v1',dimension,'unit_l2');digest=identity_sha256(identity)
checksums=[canonical_vector_checksum(v)for v in vectors]
artifacts=tuple(ImmutableVectorArtifact(f'{i:064x}',str(i),f'{i:064x}','synthetic',identity.artifact_sha256,identity.preprocessing_sha256,identity.vector_space_id,identity.model_version,dimension,'unit_l2',digest,f'image-vectors/{digest}/{i:064x}.npy','f'*64,checksums[i%64],1,'ready')for i in range(1,count+1))
payload=memoryview(b''.join(struct.pack(f'>{dimension}f',*vectors[i%64])for i in range(1,count+1)))
query=_canonical_components(VectorRecord('1',identity,vectors[0],checksums[0]),identity);ids=tuple(a.asset_id for a in artifacts)
with patch.dict(os.environ,PHOTOHOUSE_VECTOR_ENGINE='python'):
 reference=bulk._canonical_matrix(payload,artifacts,identity,lambda:None)
 snapshot=bulk.BulkVectorSnapshot(artifacts,identity,reference);expected=snapshot.rank(query,ids)
np=bulk._rank_numpy_backend();assert np is not None,'NumPy baseline required; do not substitute scalar timings'
records=[]
def measure(name,engine,call,verify,scalar=False):
 with ExitStack()as stack:
  stack.enter_context(patch.dict(os.environ,PHOTOHOUSE_VECTOR_ENGINE=engine))
  if scalar:stack.enter_context(patch.object(bulk,'_rank_numpy_backend',return_value=None))
  verify(call());samples=[];cpu=[]
  for _ in range(5):
   start=time.perf_counter();c=time.process_time();value=call();cpu.append(time.process_time()-c);samples.append(time.perf_counter()-start);verify(value)
 record=dict(name=name,engine=engine,warmups=1,repeats=5,wall_seconds=samples,wall_median=statistics.median(samples),wall_min=min(samples),wall_max=max(samples),cpu_median=statistics.median(cpu))
 records.append(record);print(json.dumps({'name':name,'median_seconds':record['wall_median']}),flush=True)
def same_matrix(value):assert value==reference
def same_rank(value):assert value==expected
cold=lambda:bulk._canonical_matrix(payload,artifacts,identity,lambda:None)
for engine in ('python','rust'):measure('cold_'+engine,engine,cold,same_matrix)
measure('warm_scalar','python',lambda:snapshot.rank(query,ids),same_rank,scalar=True)
measure('warm_numpy','python',lambda:snapshot.rank(query,ids),same_rank)
measure('warm_rust','rust',lambda:snapshot.rank(query,ids),same_rank)
for engine in ('python','rust'):
 measure('cold_and_rank_'+engine,engine,lambda:bulk.BulkVectorSnapshot(artifacts,identity,cold()).rank(query,ids),same_rank)
result=dict(schema='photohouse-vector-kernel-local-benchmark@1',python=platform.python_version(),machine=platform.machine(),numpy=np.__version__,rows=count,dimensions=dimension,unique_generated_patterns=64,payload_sha256=hashlib.sha256(payload).hexdigest(),scope='Mac CPU components; excludes file admission/DB/HTTP/model/network and household data',exact_matrix_bytes_and_ranked_scores=True,results=records)
import photohouse_vector_kernel
result['native_sha256']=hashlib.sha256(Path(photohouse_vector_kernel.__file__).read_bytes()).hexdigest()
result['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
 'server/backend/app/access/semantic_bulk_vectors.py','server/backend/app/access/vector_acceleration.py',
 'rust/vector-core/src/port.rs','rust/vector-core/src/lib.rs','rust/vector-core/Cargo.toml','rust/vector-core/Cargo.lock',
 'rust/vector-python/src/lib.rs','rust/vector-python/Cargo.toml','rust/vector-python/Cargo.lock','rust/benchmark_vector_kernel.py')}
(OUT/'benchmark.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
