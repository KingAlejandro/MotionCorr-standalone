#!/bin/bash
# Runner mutants for the new CudaResidentRetryFailures driver. usage: mkmut2.sh <m1|m2>
#  m1: the resident-retry preparation never refuses a poisoned context
#  m2: a failed resident preparation is treated as done (no fall back to the download path)
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
cd $S
until flock -n /tmp/motioncorr-bench.lock true; do echo "$(date -u +%T) bench held" >> mut2-wait.log; sleep 60; done
[ -d src-mut2 ] || cp -a src-branch src-mut2
cp src-branch/src/motioncorr_runner.cpp src-mut2/src/motioncorr_runner.cpp
python3 - $1 <<'PY'
import re, sys
p='/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q/src-mut2/src/motioncorr_runner.cpp'
s=open(p).read()
if sys.argv[1]=='m1':
    pat=re.compile(r'(movie_session->getFailureState\(\), cudaGetLastError\(\)\);\s*)if \(decision\.verdict == CUDA_RETRY_FATAL\) \{')
    rep=r'\1if (false) {'
else:
    pat=re.compile(r'(group_start\.data\(\), group_size\.data\(\), Fpatches\);\s*)(RCTOC\(TIMING_PREP_PATCH\);)')
    rep=r'\1resident_retry_prep_done = true;\n\t\t\t\t\t\t\2'
s2,n=pat.subn(rep,s)
assert n==1, f'mutation matched {n} times'
open(p,'w').write(s2)
PY
[ $? = 0 ] || exit 3
if [ ! -d build/cuda-mut2 ]; then
  taskset -c 80-87 cmake -S src-mut2 -B build/cuda-mut2 -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/home/alex/mc-env/bin/python3 -DCUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8 -DUSE_NVCOMP=ON -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive > build/cuda-mut2.configure.log 2>&1
fi
taskset -c 80-87 cmake --build build/cuda-mut2 -j8 --target motioncorr_resident_retry_fault > build/cuda-mut2-$1.build.log 2>&1
echo "build $1 rc=$?" >> build/cuda-mut2.status
cp build/cuda-mut2/motioncorr_resident_retry_fault build/rrf-mut-$1
sha256sum build/rrf-mut-$1 >> build/cuda-mut2.status
