#!/usr/bin/env python3
"""Powered native resource/key controls, without touching frozen candidate files."""
import argparse,hashlib,json,re,shlex,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args();a.root.mkdir(parents=True,exist_ok=False)
src=a.source/'src/acc/cuda/cuda_alignpatch.cu';text=src.read_text();flags=(a.build/'CMakeFiles/motioncorr_core.dir/flags.make').read_text();opts=[]
for key in ['CUDA_DEFINES','CUDA_INCLUDES','CUDA_FLAGS']:opts+=shlex.split(re.search('^'+key+r' = (.*)$',flags,re.M)[1])
compiler=re.search(r'^CMAKE_CUDA_COMPILER:[^=]+=(.*)$',(a.build/'CMakeCache.txt').read_text(),re.M)[1];records=[]
changes=[('always-rebuild','const bool setup_required = !w.valid || !w.key.equals(requested);','const bool setup_required = true;'),('omit-B-key','std::memcmp(&scaled_B, &other.scaled_B, sizeof(RFLOAT)) == 0 &&','true &&')]
for name,old,new in changes:
 assert text.count(old)==1,'ambiguous mutation';d=a.root/name;d.mkdir();mut=d/'cuda_alignpatch.cu';mut.write_text(text.replace(old,new));obj=d/'cuda_alignpatch.cu.o'
 compile_cmd=[compiler,'-forward-unknown-to-host-compiler',*opts,'-x','cu','-c',str(mut.resolve()),'-o',str(obj.resolve())]
 subprocess.run(compile_cmd,cwd=a.build,check=True);lib=d/'libmotioncorr_core.a';shutil.copy2(a.build/'libmotioncorr_core.a',lib);subprocess.run(['ar','r',str(lib),str(obj)],check=True);assert subprocess.check_output(['ar','t',str(lib)],text=True).splitlines().count('cuda_alignpatch.cu.o')==1
 link=shlex.split((a.build/'CMakeFiles/cuda_patch_workspace.dir/link.txt').read_text());binary=d/'cuda_patch_workspace';link[link.index('-o')+1]=str(binary.resolve());link=[str(lib.resolve()) if q=='libmotioncorr_core.a' else q for q in link];assert str(lib.resolve()) in link;subprocess.run(link,cwd=a.build,check=True)
 r=subprocess.run([str(binary.resolve())],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120);(d/'run.log').write_text(r.stdout);assert r.returncode==1 and 'cache key/reuse allocation counts wrong' in r.stdout,'native test did not discriminate '+name
 records.append({'case':name,'returncode':r.returncode,'status':'REJECTED','mutant_source_sha256':hashlib.sha256(mut.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'compile_command':compile_cmd,'link_command':link});print(name,'REJECTED',flush=True)
(a.root/'result.json').write_text(json.dumps(records,indent=2))
