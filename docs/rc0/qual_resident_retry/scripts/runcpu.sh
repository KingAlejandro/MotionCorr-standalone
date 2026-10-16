#!/bin/bash
# usage: runcpu.sh <cpu binary> <tag>   (10641 config L, CPU backend, CPUs 80-87)
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
bin=$1; tag=$2
until flock -n /tmp/motioncorr-bench.lock true; do echo "$(date -u +%T) bench held" >> $S/runs/cpu-bench-wait.log; sleep 60; done
out=$S/runs/$tag; [ -e $out ] && { echo exists; exit 9; }
mkdir -p $S/runs/$tag.side; side=$S/runs/$tag.side
cd $S/inputs/corpus/e10641u
{
 echo "START $(date -u +%FT%TZ) bin=$bin sha=$(sha256sum $bin | cut -d' ' -f1)"
 /usr/bin/time -v taskset -c 80-87 env OMP_NUM_THREADS=8 $bin --use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --gainref gain.mrc --expected_frames 70 --patch_x 5 --patch_y 5 --i movies.star --o $out/ --j 8
 echo "rc=$?"
 echo "END $(date -u +%FT%TZ)"
} > $side/run.stdout 2> $side/run.stderr
echo done $tag $(grep '^rc=' $side/run.stdout)
