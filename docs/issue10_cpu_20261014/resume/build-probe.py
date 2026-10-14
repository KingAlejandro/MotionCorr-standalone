from pathlib import Path
import subprocess, shlex
root=Path('/workspace/scratch/28038873ca11')
build=root/'build-reference';src=root/'probe-source'
values={}
for line in (build/'CMakeFiles/motioncorr_core.dir/flags.make').read_text().splitlines():
 if ' = ' in line:
  k,v=line.split(' = ',1);values[k]=v
flags=['/usr/bin/c++']+shlex.split(values['CXX_DEFINES'])+shlex.split(values['CXX_INCLUDES'].replace(str(root/'reference'),str(src)))+shlex.split(values['CXX_FLAGS'])
for file,name in [('src/motioncorr_runner.cpp','runner'),('src/jaz/single_particle/new_ft.cpp','newft')]:
 subprocess.run(flags+['-c',str(src/file),'-o',str(root/(name+'-probe.o'))],check=True)
args=shlex.split((build/'CMakeFiles/motioncorr.dir/link.txt').read_text())
args[args.index('-o')+1]=str(root/'probe-waits')
idx=args.index('libmotioncorr_core.a');args[idx:idx]=[str(root/'runner-probe.o'),str(root/'newft-probe.o')]
subprocess.run(args,cwd=build,check=True)
