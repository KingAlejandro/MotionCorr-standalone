#!/bin/bash
# #244 opt-in destructive CudaStickyContext on GPU3 (docs/issue213/README.md runbook). usage: C1_STICKY_CPUS=<4 CPUs> c1_sticky.sh cuda|nvcomp
# The driver (tests/run_sticky_cuda_control.py) takes the canonical GPU3 lease itself and keeps it through its own final health checks, so no
# outer lock is taken here. The driver hardcodes --j 4 / OMP_NUM_THREADS=4 in its fault runs; C1's lane is 2 CPUs, so this row only runs in a
# parent-granted window of 4 CPUs (C1_STICKY_CPUS, e.g. 8-11) and is never run oversubscribed or with an edited driver.
set -u
D=$(dirname "$0"); source "$D/c1_env.sh" || exit 1
: "${C1_STICKY_CPUS:?sticky row needs a parent-granted 4-CPU window (driver hardcodes --j 4); not run on the 2-CPU lane}"
n=$(echo "$C1_STICKY_CPUS" | awk -F, '{n=0; for(i=1;i<=NF;i++){split($i,a,"-"); n+=(a[2]==""?1:a[2]-a[1]+1)}; print n}')
[ "$n" -ge 4 ] || { echo "C1_STICKY_CPUS must name >=4 CPUs (got $n)"; exit 2; }
cfg=$1; B=$C1_SCR/build-sticky-$cfg
if [ ! -x $B/motioncorr_sticky_fault ]; then
  CFG=$cfg "$D/c1_build.sh" $C1_SCR/src $B motioncorr_sticky_fault -DBUILD_TESTING=ON -DMC_ENABLE_STICKY_CUDA_TEST=ON || exit 2
fi
sha256sum $B/motioncorr_sticky_fault > $B.binaries.sha256
"$D/c1_occupancy.sh" sticky-$cfg-pre; pre=$?; [ $pre -eq 0 ] || { echo "pre-run health failed rc=$pre"; exit 3; }
CUDA_VISIBLE_DEVICES=$C1_GPU_UUID CUDA_DEVICE_ORDER=PCI_BUS_ID taskset -c $C1_STICKY_CPUS $C1_PY $C1_SCR/src/tests/run_sticky_cuda_control.py \
  --binary $B/motioncorr_sticky_fault --workdir $C1_SCR/sticky-$cfg; rc=$?
"$D/c1_occupancy.sh" sticky-$cfg-post; post=$?
if [ $post -ne 0 ]; then echo "post-run health failed rc=$post (driver rc=$rc)" >&2; [ $rc -eq 0 ] && rc=37; fi
exit $rc
