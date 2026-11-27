import pathlib,json,subprocess,hashlib
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');out={}
for a in ['A0','A1','N']:
 q={'files':{},'cache':{},'exit_codes':{}}
 for f in ['src/acc/cuda/cuda_alignpatch.cu','src/acc/cuda/cuda_movie_session.cu','src/diag_ccf.h','src/motioncorr_runner.cpp']:
  p=s/('src-'+a)/f;q['files'][f]=hashlib.sha256(p.read_bytes()).hexdigest()
 for l in (s/('build-'+a)/'CMakeCache.txt').read_text().splitlines():
  if l.startswith(('CMAKE_BUILD_TYPE:','CMAKE_CXX_FLAGS_RELEASE:','CMAKE_CUDA_FLAGS_RELEASE:','CMAKE_CUDA_ARCHITECTURES:','CUDA:','USE_NVCOMP:')):q['cache'][l.split(':')[0]]=l.split('=',1)[1]
 for kind in ['configure','build']:q['exit_codes'][kind]=int((s/'logs'/(kind+'-'+a+'.exit')).read_text())
 p=pathlib.Path('/mnt/clathrin/mc-diag-'+a+'.tar');q['archive_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();q['binary_sha256']=hashlib.sha256((s/('build-'+a)/'motioncorr').read_bytes()).hexdigest();out[a]=q
print(json.dumps(out,indent=1))
