"""Build the optional extension locally from locked, already cached dependencies."""
import json,os,platform,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
crate=ROOT/'rust/vector-python';target=crate/'target';output=target/'python'
if os.name=='nt':
    # Windows owns its build admission. Never put a source build/cache/temp on C:.
    for name,path in {'source':ROOT,'target':target,'Cargo cache':Path(os.environ.get('CARGO_HOME','C:/')),
                      'TEMP':Path(os.environ.get('TEMP','C:/')),'TMP':Path(os.environ.get('TMP','C:/'))}.items():
        if path.drive.upper()!='D:':raise SystemExit(f'{name} must be explicitly located on D:')
cargo=shutil.which('cargo') or str(Path.home()/'.cargo/bin/cargo')
subprocess.run([cargo,'build','--release','--locked','--offline','--manifest-path',str(crate/'Cargo.toml')],check=True)
name='photohouse_vector_kernel.dll'if os.name=='nt'else('libphotohouse_vector_kernel.dylib'if sys.platform=='darwin'else'libphotohouse_vector_kernel.so')
output.mkdir(exist_ok=True)
shutil.copyfile(target/'release'/name,output/('photohouse_vector_kernel.pyd'if os.name=='nt'else'photohouse_vector_kernel.so'))
print(json.dumps({'status':'LOCAL_EXTENSION_BUILT','python':platform.python_version(),'machine':platform.machine(),'output':str(output.relative_to(ROOT))}))
