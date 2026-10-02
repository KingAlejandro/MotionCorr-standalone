#!/usr/bin/env python3
"""Actual dose-denominator mutants, compiled with pinned production flags."""
import argparse,hashlib,json,re,shlex,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args();a.root.mkdir(parents=True,exist_ok=False)
src=a.source/'src/acc/cuda/cuda_realspace_dw.cu';text=src.read_text();flags=(a.build/'CMakeFiles/motioncorr_core.dir/flags.make').read_text();opts=[]
for key in ['CUDA_DEFINES','CUDA_INCLUDES','CUDA_FLAGS']:opts+=shlex.split(re.search('^'+key+r' = (.*)$',flags,re.M)[1])
compiler=re.search(r'^CMAKE_CUDA_COMPILER:[^=]+=(.*)$',(a.build/'CMakeCache.txt').read_text(),re.M)[1]
changes=[]
old='j < n_frames;';assert text.count(old)==1
changes.append(('omitted-dose',text.replace(old,'j < n_frames - 1;'),['exact'],'dose-normalized Fourier bytes differ from frozen original kernel'))
old='expf(-d_doses[j] / Ne)';assert text.count(old)==1
changes.append(('wrong-dose',text.replace(old,'expf(-d_doses[0] / Ne)'),['exact'],'dose-normalized Fourier bytes differ from frozen original kernel'))
old='1.0f / sqrtf((float)n_frames)';assert text.count(old)==1
changes.append(('wrong-dc',text.replace(old,'1.0f'),['exact'],'dose-normalized Fourier bytes differ from frozen original kernel'))
records=[]
for name,mutated,cases,expected in changes:
 for case in cases:
  positive=subprocess.run([str((a.build/'cuda_dose_normalization').resolve()),'--case',case],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
  assert positive.returncode==0 and 'PASS: exact reconstruction-scoped dose normalization controls' in positive.stdout,'Positive control failed: '+positive.stdout
 d=a.root/name;d.mkdir();mut=d/'cuda_realspace_dw.cu';mut.write_text(mutated);obj=d/'cuda_realspace_dw.cu.o'
 compile_cmd=[compiler,'-forward-unknown-to-host-compiler',*opts,'-x','cu','-c',str(mut.resolve()),'-o',str(obj.resolve())];subprocess.run(compile_cmd,cwd=a.build,check=True)
 lib=d/'libmotioncorr_core.a';shutil.copy2(a.build/'libmotioncorr_core.a',lib);subprocess.run(['ar','r',str(lib),str(obj)],check=True)
 assert subprocess.check_output(['ar','t',str(lib)],text=True).splitlines().count('cuda_realspace_dw.cu.o')==1
 link=shlex.split((a.build/'CMakeFiles/cuda_dose_normalization.dir/link.txt').read_text());binary=d/'cuda_dose_normalization';link[link.index('-o')+1]=str(binary.resolve());link=[str(lib.resolve()) if q=='libmotioncorr_core.a' else q for q in link];assert str(lib.resolve()) in link;subprocess.run(link,cwd=a.build,check=True)
 for case in cases:
  command=[str(binary.resolve()),'--case',case];r=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120);(d/(case+'.log')).write_text(r.stdout)
  assert r.returncode==1 and ('FAIL: '+expected) in r.stdout,'Mutant did not fail target assertion: '+r.stdout
  records.append({'mutation':name,'control':case,'status':'REJECTED','returncode':r.returncode,'mutant_source_sha256':hashlib.sha256(mut.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'compile_command':compile_cmd,'link_command':link,'test_command':command});print(name,case,'REJECTED',flush=True)
(a.root/'result.json').write_text(json.dumps(records,indent=2))
