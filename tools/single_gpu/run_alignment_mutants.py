#!/usr/bin/env python3
"""Actual alignment boundary mutants, compiled with pinned production flags."""
import argparse,hashlib,json,re,shlex,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args();a.root.mkdir(parents=True,exist_ok=False)
src=a.source/'src/acc/cuda/cuda_alignpatch.cu';text=src.read_text();flags=(a.build/'CMakeFiles/motioncorr_core.dir/flags.make').read_text();opts=[]
for key in ['CUDA_DEFINES','CUDA_INCLUDES','CUDA_FLAGS']:opts+=shlex.split(re.search('^'+key+r' = (.*)$',flags,re.M)[1])
compiler=re.search(r'^CMAKE_CUDA_COMPILER:[^=]+=(.*)$',(a.build/'CMakeCache.txt').read_text(),re.M)[1]
changes=[]
old='if (work_may_be_pending)';assert text.count(old)==1
changes.append(('missing-drain',text.replace(old,'if (false && work_may_be_pending)'),['cufft-immediate','d2h-immediate','h2d-immediate'],'immediate failure did not check drain before resource cleanup'))
for name,k,needle in [('premature-k1',1,'        // 3. Batched cuFFT C2R'),('premature-k2',2,'        // Copy candidate shifts back to host')]:
 block=f'        float k{k}_ms = 0.0f;\n        ALIGN_CUDA(cudaEventElapsedTime(&k{k}_ms, ev_start_kernel, ev_stop_kernel));\n        accumulated_kernel_ms += k{k}_ms;\n'
 assert text.count(block)==1 and text.count(needle)==1,'ambiguous timing generation mutation'
 mutated=text.replace(block,'');mutated=mutated.replace(needle,block+needle)
 changes.append((name,mutated,['event-order'],'kernel elapsed was read before its kept stage boundary'))
records=[]
for name,mutated,cases,expected in changes:
 for case in cases:
  positive=subprocess.run([str((a.build/'cuda_alignment_sync').resolve()),'--case',case],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
  assert positive.returncode==0 and 'PASS: actual production alignment synchronization controls' in positive.stdout,'Positive control failed: '+positive.stdout
 d=a.root/name;d.mkdir();mut=d/'cuda_alignpatch.cu';mut.write_text(mutated);obj=d/'cuda_alignpatch.cu.o'
 compile_cmd=[compiler,'-forward-unknown-to-host-compiler',*opts,'-x','cu','-c',str(mut.resolve()),'-o',str(obj.resolve())];subprocess.run(compile_cmd,cwd=a.build,check=True)
 lib=d/'libmotioncorr_core.a';shutil.copy2(a.build/'libmotioncorr_core.a',lib);subprocess.run(['ar','r',str(lib),str(obj)],check=True)
 assert subprocess.check_output(['ar','t',str(lib)],text=True).splitlines().count('cuda_alignpatch.cu.o')==1
 link=shlex.split((a.build/'CMakeFiles/cuda_alignment_sync.dir/link.txt').read_text());binary=d/'cuda_alignment_sync';link[link.index('-o')+1]=str(binary.resolve());link=[str(lib.resolve()) if q=='libmotioncorr_core.a' else q for q in link];assert str(lib.resolve()) in link;subprocess.run(link,cwd=a.build,check=True)
 for case in cases:
  command=[str(binary.resolve()),'--case',case];r=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120);(d/(case+'.log')).write_text(r.stdout)
  assert r.returncode==1 and ('FAIL: '+expected) in r.stdout,'Mutant did not fail target assertion: '+r.stdout
  records.append({'mutation':name,'control':case,'status':'REJECTED','returncode':r.returncode,'mutant_source_sha256':hashlib.sha256(mut.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'compile_command':compile_cmd,'link_command':link,'test_command':command});print(name,case,'REJECTED',flush=True)
(a.root/'result.json').write_text(json.dumps(records,indent=2))
