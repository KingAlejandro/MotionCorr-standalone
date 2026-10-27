"""Versioned report-only image analysis after missing-SciPy preflight failures."""
import hashlib,json,os,subprocess,sys,struct,importlib.metadata as metadata
from pathlib import Path
ROOT=Path('/tmp/motioncorr-b2-native-20261026');E=ROOT/'evidence';SRC=ROOT/'source';DEPS=Path('/home/ubuntu/mc-km-truth-20261021/deps')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sys.path.insert(0,str(DEPS))
import numpy as np,scipy
import numpy._core._multiarray_umath as npcore
import scipy.ndimage._nd_image as ndimage
packages={}
for name,module in [('numpy',np),('scipy',scipy)]:
 dist=metadata.distribution(name);metapath=Path(dist._path)
 packages[name]=dict(version=module.__version__,module_path=module.__file__,module_sha256=sha(Path(module.__file__)),metadata_path=str(metapath),metadata_hashes={p.name:sha(p) for p in metapath.iterdir() if p.is_file() and p.name in ('METADATA','RECORD','WHEEL')})
preflight=dict(wrapper_path=__file__,wrapper_sha256=sha(Path(__file__)),evaluator_path=str(SRC/'tools/check_realistic_image.py'),evaluator_sha256=sha(SRC/'tools/check_realistic_image.py'),packages=packages,compiled_modules={m.__name__:dict(path=m.__file__,sha256=sha(Path(m.__file__))) for m in (npcore,ndimage)},images=[])
for name in ('dose1-s01','dose05-s00','dose4-s00','pedestal32-s00'):
 for label in ('OFF1','ON1'):
  p=E/'pilot'/name/label/'output/movie.mrc'
  with p.open('rb') as f:header=f.read(1024)
  nx,ny,nz,mode=struct.unpack('<4i',header[:16]);assert (nx,ny,nz,mode)==(4096,4096,1,2)
  preflight['images'].append(dict(movie=name,label=label,path=str(p),geometry=[nx,ny,nz],mode=mode,bytes=p.stat().st_size))
(E/'image-v2-preflight.json').write_text(json.dumps(preflight,indent=2)+'\n')
records=[];seen=set();scene=None;truth=E/'image-truth-inmodel-v2.npy'
for name in ('dose1-s01','dose05-s00','dose4-s00','pedestal32-s00'):
 receipt=E/(name+'-RECEIPT.json');r=json.loads(receipt.read_text())['recipe'];key={k:r[k] for k in ('nx','ny','scene_seed','texture_rms','oversample')}
 if scene is None:scene=key
 assert key==scene,'truth cache scene differs'
 for label in ('OFF1','ON1'):
  d=E/'pilot'/name/label;p=d/'output/movie.mrc';payload=hashlib.sha256(p.read_bytes()[1024:]).hexdigest()
  if payload in seen:continue
  seen.add(payload);out=d/'image-report-v2.json';assert not out.exists(),'never overwrite a successful report'
  # Same installed/pinned numerical dependencies used by original fixture generation.
  code='import sys,runpy;sys.path.insert(0,'+repr(str(DEPS))+');sys.argv='+repr([str(SRC/'tools/check_realistic_image.py'),'--receipt',str(receipt),'--sum',str(p),'--truth',str(truth),'--json',str(out)])+';runpy.run_path(sys.argv[0],run_name="__main__")'
  with (d/'image-report-v2.stdout').open('w') as f:cp=subprocess.run([sys.executable,'-I','-c',code],stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1'))
  row=dict(movie=name,label=label,exit=cp.returncode,status='REPORT_ONLY' if cp.returncode==0 else 'FAILED',payload_sha256=payload,receipt_sha256=sha(receipt),tool_sha256=sha(SRC/'tools/check_realistic_image.py'),truth_sha256=sha(truth) if truth.exists() else None,dependencies_path=str(DEPS),report=str(out))
  records.append(row);(E/'image-reports-v2.json').write_text(json.dumps(records,indent=2)+'\n');print(name,label,row['status'],flush=True)
  if cp.returncode:raise SystemExit(cp.returncode)
