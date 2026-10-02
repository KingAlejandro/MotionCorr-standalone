#!/usr/bin/env python3
"""Build one production guard mutant without modifying the frozen candidate.
Uses the candidate's exact compiler flags/library/link command; replaces only
motioncorr_runner.cpp.o in a copied archive. For native negative control only.
"""
import argparse,hashlib,json,re,shlex,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args();a.root.mkdir(parents=True,exist_ok=False)
src=a.source/'src/motioncorr_runner.cpp';text=src.read_text();old='if (movie_session && !movie_session->releasePatchAlignmentWorkspace())';new='if (movie_session && (movie_session->releasePatchAlignmentWorkspace(), false))';assert text.count(old)==1;text=text.replace(old,new);mut=a.root/'motioncorr_runner.cpp';mut.write_text(text)
flags=(a.build/'CMakeFiles/motioncorr_core.dir/flags.make').read_text();opts=[]
for key in ['CXX_DEFINES','CXX_INCLUDES','CXX_FLAGS']:
 opts+=shlex.split(re.search('^'+key+r' = (.*)$',flags,re.M)[1])
cache=(a.build/'CMakeCache.txt').read_text();compiler=re.search(r'^CMAKE_CXX_COMPILER:FILEPATH=(.*)$',cache,re.M)[1]
obj=a.root/'motioncorr_runner.cpp.o';compile_cmd=[compiler,*opts,'-c',str(mut.resolve()),'-o',str(obj.resolve())];subprocess.run(compile_cmd,check=True)
lib=a.root/'libmotioncorr_core.a';shutil.copy2(a.build/'libmotioncorr_core.a',lib);subprocess.run(['ar','r',str(lib),str(obj)],check=True)
members=subprocess.check_output(['ar','t',str(lib)],text=True).splitlines();assert members.count('motioncorr_runner.cpp.o')==1,'ambiguous mutant archive member'
link=shlex.split((a.build/'CMakeFiles/motioncorr_faultinject.dir/link.txt').read_text());target=a.root/'motioncorr_faultinject';link[link.index('-o')+1]=str(target.resolve());link=[str(lib.resolve()) if q=='libmotioncorr_core.a' else q for q in link];assert str(lib.resolve()) in link;subprocess.run(link,cwd=a.build,check=True)
meta={'scope':'ignore one checked movie-workspace release return; real release still runs','source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'mutant_sha256':hashlib.sha256(mut.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'compile_command':compile_cmd,'link_command':link};(a.root/'provenance.json').write_text(json.dumps(meta,indent=2));print('MUTANT_BUILT')
