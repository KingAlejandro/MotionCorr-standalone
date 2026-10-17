#!/bin/bash
# QF item 11 powered control (#208's o1n, extended to o5): build a scratch copy of the frozen source with the
# EER uint16 guard removed (the one-line mutation of #208's evidence/noguard.diff, applied by exact-string
# match), then run item11_eer.py --noguard-binary. Without the guard the replacement overflow fixtures must
# wrap uint16, so auto (now compact) must DIFFER from float: the cases PASS when the comparison fails as
# recorded. The mutant lives only in $QF_W/src-noguard and $QF_W/build-noguard; nothing in src/ changes.
# Requires QF_W QF_SHA QF_CPUS QF_GPU_UUID QF_GPU_LOCK.
set -u
: "${QF_W:?}" "${QF_SHA:?}" "${QF_CPUS:?}" "${QF_GPU_UUID:?}" "${QF_GPU_LOCK:?}"
T=$(cd "$(dirname "$0")" && pwd)
PY=/home/alex/.mc-venv/bin/python3
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
[ "$(git -C $QF_W/src rev-parse HEAD)" = "$QF_SHA" ] || { echo "src is not QF_SHA"; exit 91; }
rm -rf $QF_W/src-noguard && git -C $QF_W/src worktree prune && cp -a $QF_W/src $QF_W/src-noguard || exit 92
$PY - $QF_W/src-noguard/src/motioncorr_runner.cpp <<'PYEOF' || exit 93
import sys
p = sys.argv[1]; s = open(p).read()
old = 'const bool eer_fits_u16 = isEER && eer_max_count <= 65535;'
new = 'const bool eer_fits_u16 = isEER; /* NEGATIVE CONTROL: guard removed */ (void)eer_max_count;'
assert s.count(old) == 1, 'guard line not found exactly once'
open(p, 'w').write(s.replace(old, new))
PYEOF
until flock -n /tmp/motioncorr-bench.lock true; do sleep 60; done
NVC=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
taskset -c $QF_CPUS cmake -S $QF_W/src-noguard -B $QF_W/build-noguard -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  -DPython3_EXECUTABLE=$PY -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc \
  -DCUDAToolkit_ROOT=/usr/local/cuda-12.8 -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$NVC > $QF_W/build-noguard.configure.log 2>&1 || exit 94
taskset -c $QF_CPUS cmake --build $QF_W/build-noguard -j8 --target motioncorr > $QF_W/build-noguard.log 2>&1 || exit 95
grep -c 'NEGATIVE CONTROL: guard removed' $QF_W/src-noguard/src/motioncorr_runner.cpp
sha256sum $QF_W/build-noguard/motioncorr
taskset -c $QF_CPUS $PY $T/item11_eer.py --noguard-binary $QF_W/build-noguard/motioncorr
