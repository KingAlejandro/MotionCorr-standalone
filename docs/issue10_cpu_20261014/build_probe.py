from pathlib import Path
import subprocess,shlex
root=Path('/workspace/cpu10');inc=root/'deps/usr/include';src=root/'probe-src'
flags=['g++','-O3','-DNDEBUG','-std=gnu++17','-fopenmp','-DHAVE_JPEG','-DHAVE_PNG','-DHAVE_TIFF','-I'+str(src),'-isystem',str(inc),'-isystem',str(inc/'x86_64-linux-gnu')]
for file,name in [('src/motioncorr_runner.cpp','runner'),('src/jaz/single_particle/new_ft.cpp','newft')]:
 subprocess.run(flags+['-c',str(src/file),'-o',str(root/(name+'-probe.o'))],check=True)
args=shlex.split((root/'build-base/CMakeFiles/motioncorr.dir/link.txt').read_text())
args=[x for x in args if not x.startswith('-Wl,--dependency-file=')]
idx=args.index('-o');args[idx+1]=str(root/'bin/probe-waits')
idx=args.index('libmotioncorr_core.a');args[idx:idx]=[str(root/'runner-probe.o'),str(root/'newft-probe.o')]
subprocess.run(args,cwd=root/'build-base',check=True)
