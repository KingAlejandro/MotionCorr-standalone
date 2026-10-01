#!/usr/bin/env python3
"""Compile single-boundary production mutants without changing pinned candidate."""
import argparse,hashlib,json,re,shlex,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args();a.root.mkdir(parents=True,exist_ok=False)
src=a.source/'src/acc/cuda/cuda_movie_session.cu';text=src.read_text();flags=(a.build/'CMakeFiles/motioncorr_core.dir/flags.make').read_text();opts=[]
for key in ['CUDA_DEFINES','CUDA_INCLUDES','CUDA_FLAGS']:opts+=shlex.split(re.search('^'+key+r' = (.*)$',flags,re.M)[1])
compiler=re.search(r'^CMAKE_CUDA_COMPILER:[^=]+=(.*)$',(a.build/'CMakeCache.txt').read_text(),re.M)[1]
forward_start=text.index('bool CudaMovieSession::computeGlobalForwardFFT()')
inverse_start=text.index('bool CudaMovieSession::computeGlobalInverseFFT()')
inverse_end=text.index('bool CudaMovieSession::preparePatchInVram(',inverse_start)
forward=text[forward_start:inverse_start];inverse=text[inverse_start:inverse_end]
sync='HANDLE_ERROR(cudaDeviceSynchronize());'
assert forward.count(sync)==3 and inverse.count(sync)==3,'Expected frozen boundary inventory changed'
# Select occurrences in each actual method. Forward: failure drain, FFT boundary,
# scaling boundary. Inverse: D2D-error drain, Exec-error drain, success boundary.
changes=[('missing-forward-boundary','healthy',forward_start,forward,1),('missing-inverse-boundary','healthy',inverse_start,inverse,2),('missing-forward-drain','forward-immediate',forward_start,forward,0),('missing-inverse-exec-drain','inverse-immediate',inverse_start,inverse,1),('missing-inverse-copy-drain','inverse-copy',inverse_start,inverse,0)]
records=[]
for name,case,start,body,ordinal in changes:
 positions=[m.start() for m in re.finditer(re.escape(sync),body)];at=start+positions[ordinal]
 mutated=text[:at]+'/* negative control: omit this checked completion boundary */'+text[at+len(sync):]
 d=a.root/name;d.mkdir();mut=d/'cuda_movie_session.cu';mut.write_text(mutated);obj=d/'cuda_movie_session.cu.o'
 compile_cmd=[compiler,'-forward-unknown-to-host-compiler',*opts,'-x','cu','-c',str(mut.resolve()),'-o',str(obj.resolve())]
 subprocess.run(compile_cmd,cwd=a.build,check=True);lib=d/'libmotioncorr_core.a';shutil.copy2(a.build/'libmotioncorr_core.a',lib);subprocess.run(['ar','r',str(lib),str(obj)],check=True)
 assert subprocess.check_output(['ar','t',str(lib)],text=True).splitlines().count('cuda_movie_session.cu.o')==1
 link=shlex.split((a.build/'CMakeFiles/cuda_global_fft_sync.dir/link.txt').read_text());binary=d/'cuda_global_fft_sync';link[link.index('-o')+1]=str(binary.resolve());link=[str(lib.resolve()) if q=='libmotioncorr_core.a' else q for q in link];assert str(lib.resolve()) in link;subprocess.run(link,cwd=a.build,check=True)
 command=[str(binary.resolve()),'--case',case];r=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120);(d/'run.log').write_text(r.stdout)
 assert r.returncode==1 and 'FAIL' in r.stdout,'Actual-session test did not discriminate '+name+': '+r.stdout
 records.append({'case':name,'selected_control':case,'returncode':r.returncode,'status':'REJECTED','mutant_source_sha256':hashlib.sha256(mut.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'compile_command':compile_cmd,'link_command':link,'test_command':command});print(name,'REJECTED',flush=True)
(a.root/'result.json').write_text(json.dumps(records,indent=2))
