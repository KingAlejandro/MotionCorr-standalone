#!/bin/bash
# Issue 10 control: 24-movie batch, allocator tunable vs source madvise vs plan cache alone.
# Run inside: flock -w 14400 /tmp/motioncorr-cpu64-bench.lock
cd /home/ubuntu/mc-cpu10-plancache
MAIN=/home/ubuntu/mc-cpuprof-116eb04/build/motioncorr
NEW=/home/ubuntu/mc-cpu10-plancache/build/motioncorr
PC=/home/ubuntu/mc-cpu10-plancache/motioncorr.plancache   # plan cache only, no madvise code
mkdir -p ab24c
ARGS="--use_own --j 4 --angpix 0.885 --voltage 300 --bfactor 150 --patch_x 5 --patch_y 5 --gainref Movies24/gain.mrc --dose_weighting --dose_per_frame 1.277 --save_noDW --even_odd_split"
cpubusy() { awk "/^cpu(8|9|10|11) /{b+=\$2+\$3+\$4+\$7+\$8+\$9} END{print b}" /proc/stat; }  # jiffies, CPUs 8-11
run() { # name bin env...
  local name=$1 bin=$2; shift 2
  rm -rf ab24c/out-$name-$R
  local l1=$(cut -d" " -f1 /proc/loadavg) b0=$(cpubusy)
  env "$@" taskset -c 8-11 /usr/bin/time -v $bin --i "Movies24/*.tiff" $ARGS --o ab24c/out-$name-$R/ --profile ab24c/prof-$name-$R.jsonl > ab24c/run-$name-$R.log 2> ab24c/time-$name-$R.log
  local rc=$? b1=$(cpubusy)
  python3 digest24.py ab24c/out-$name-$R > ab24c/digest-$name-$R.txt
  local u=$(awk -F": " "/User time/{u=\$2} /System time/{s=\$2} END{print int((u+s)*100)}" ab24c/time-$name-$R.log)
  echo "$name r$R rc=$rc load1_start=$l1 cpu8-11_jiffies=$((b1-b0)) own_jiffies=$u mrc=$(grep -c " mrc " ab24c/digest-$name-$R.txt) $(grep -E "Elapsed|User time|System time|Maximum resident|Minor" ab24c/time-$name-$R.log | awk -F": " "{printf \"%s \", \$2}")"
}
echo "THP: $(cat /sys/kernel/mm/transparent_hugepage/enabled) defrag: $(cat /sys/kernel/mm/transparent_hugepage/defrag) start $(date -u +%FT%TZ)"
H=GLIBC_TUNABLES=glibc.malloc.hugetlb=1
R=1; run main $MAIN X=1; run mainhuge $MAIN $H; run branch $NEW X=1; run pchuge $PC $H
R=2; run pchuge $PC $H; run branch $NEW X=1; run mainhuge $MAIN $H; run main $MAIN X=1
for d in ab24c/digest-*.txt; do cmp -s ab24c/digest-main-1.txt $d && echo "identity $d: IDENTICAL" || echo "identity $d: DIFFERS"; done
echo DONE $(date -u +%FT%TZ)
