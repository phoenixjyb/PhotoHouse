"""Current storage contracts on both engines, plus mandatory native contracts."""
import io,json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'rust/vector-python/target/python'),str(ROOT/'server/backend'),str(ROOT/'server/tests/security')]
import test_semantic_bulk_vectors
# These instrument Python canonicalization or NumPy allocation. Run unchanged
# on Python; mandatory native equivalents cover mutation/callbacks/buffer caps.
PYTHON_IMPLEMENTATION_TESTS={
 'test_cold_matrix_derivation_refuses_same_dimension_identity_mutation',
 'test_optional_backend_keeps_callback_order_and_cancels_before_decode',
 'test_optional_product_backend_matches_scalar_full_filtered_and_sparse_rank',
 'test_optional_product_scratch_is_bounded_private_and_generation_checked'}
OUT=ROOT/'.runtime/vector-kernel';OUT.mkdir(parents=True,exist_ok=True)
records=[]
def flatten(suite):
 for test in suite:
  if isinstance(test,unittest.TestSuite):yield from flatten(test)
  else:yield test
for engine in ('python','rust'):
 tests=list(flatten(unittest.defaultTestLoader.loadTestsFromModule(test_semantic_bulk_vectors)))
 assert len([t for t in tests if t._testMethodName in PYTHON_IMPLEMENTATION_TESTS])==4
 tests=[t for t in tests if engine=='python' or t._testMethodName not in PYTHON_IMPLEMENTATION_TESTS]
 stream=io.StringIO()
 with patch.dict(os.environ,PHOTOHOUSE_VECTOR_ENGINE=engine):
  result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.TestSuite(tests))
 (OUT/f'{engine}-contracts.txt').write_text(stream.getvalue(),encoding='utf-8')
 records.append(dict(engine=engine,tests=result.testsRun,skipped=len(result.skipped),passed=result.wasSuccessful(),python_implementation_tests_run_here=engine=='python'))
 if not result.wasSuccessful():print(stream.getvalue());raise SystemExit(1)
import test_vector_rust
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_vector_rust))
(OUT/'native-contracts.txt').write_text(stream.getvalue(),encoding='utf-8')
assert result.wasSuccessful() and not result.skipped,stream.getvalue()
records.append(dict(engine='native_boundary',tests=result.testsRun,skipped=0,passed=True))
(OUT/'integration-results.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
print(json.dumps(records))
