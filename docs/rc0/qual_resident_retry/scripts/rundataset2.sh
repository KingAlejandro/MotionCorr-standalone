#!/bin/bash
# usage: rundataset2.sh <binary> <tag> <1|2> [extra worker args...]     env: MCENV="K=V ..."
# 1 worker: GPU2, CPUs 80-87.  2 workers: GPU2+GPU3, CPUs 80-87;72-79 (locks ascending, held for this run only).
# Waits (poll 60 s) while /tmp/motioncorr-bench.lock is held; never touches the holder.
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
bin=$1; tag=$2; n=$3; shift 3
U2=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598; U3=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
side=$S/runs/ds.side/$tag; mkdir -p $side
if [ "$n" = 1 ]; then DEV="--devices $U2 --cpus 80-87"; MASK=80-87; LOCKS="/tmp/motioncorr-gpu2-correctness.lock"
else DEV="--devices $U2,$U3 --cpus 80-87;72-79"; MASK=80-87,72-79; LOCKS="/tmp/motioncorr-gpu2-correctness.lock /tmp/motioncorr-gpu3-correctness.lock"; fi
export S bin tag U2 U3 DEV MASK MCENV side
export ARGS="$*"
inner() {
 flock -n /tmp/motioncorr-bench.lock true || exit 75
 echo "START $(date -u +%FT%TZ) bin=$bin sha=$(sha256sum $bin | cut -d' ' -f1) mask=$MASK"
 cd $S/inputs/corpus/mixed
 taskset -c $MASK env $MCENV /home/alex/mc-env/bin/python3 $S/src-branch/tools/multi_gpu/run_dataset.py --binary $bin \
   --star $S/inputs/corpus/mixed/movies.star --out $S/runs/ds_$tag --launcher-args "$(echo $DEV | sed "s/--cpus \(.*\)/--cpus '\1'/")" \
   -- --use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --patch_x 5 --patch_y 5 --j 8 $ARGS
 rc=$?
 echo "rc=$rc"; echo "END $(date -u +%FT%TZ)"
 exit $rc
}
export -f inner
while true; do
 until flock -n /tmp/motioncorr-bench.lock true; do echo "$(date -u +%T) bench held" >> $side/bench-wait.log; sleep 60; done
 nvidia-smi --query-compute-apps=gpu_uuid,pid,name --format=csv > $side/pre-nvidia-smi.txt
 if [ "$n" = 1 ]; then flock /tmp/motioncorr-gpu2-correctness.lock bash -c inner > $side/run.stdout 2> $side/run.stderr
 else flock /tmp/motioncorr-gpu2-correctness.lock flock /tmp/motioncorr-gpu3-correctness.lock bash -c inner > $side/run.stdout 2> $side/run.stderr; fi
 rc=$?; [ $rc -ne 75 ] && break
done
echo done $tag rc=$(grep '^rc=' $side/run.stdout)
