#!/bin/bash
# usage: rrc.sh <binary> <tag>  -- run tests/run_resident_retry_controls.py on GPU2 (bench-lock aware)
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
bin=$1; tag=$2
export S bin tag
inner() {
 flock -n /tmp/motioncorr-bench.lock true || exit 75
 taskset -c 80-87 env CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 CUDA_DEVICE_ORDER=PCI_BUS_ID \
   python3 $S/src-branch/tests/run_resident_retry_controls.py --binary $bin --workdir $S/ctest/$tag > $S/ctest/$tag.out 2>&1
 echo "driver-rc=$?" >> $S/ctest/$tag.out
}
export -f inner
while true; do
 until flock -n /tmp/motioncorr-bench.lock true; do sleep 60; done
 flock /tmp/motioncorr-gpu2-correctness.lock bash -c inner; rc=$?
 [ $rc -ne 75 ] && break
done
tail -4 $S/ctest/$tag.out
