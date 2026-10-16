#!/bin/bash
# Tunable vs no tunable on the exact main build (116eb04a) from ab24d.sh. Run inside the cpu64 flock.
P=/home/ubuntu/mc-prov
cd /home/ubuntu/mc-cpu10-plancache
MAIN=$P/build-main/motioncorr
mkdir -p ab24e
ARGS="--use_own --j 4 --angpix 0.885 --voltage 300 --bfactor 150 --patch_x 5 --patch_y 5 --gainref Movies24/gain.mrc --dose_weighting --dose_per_frame 1.277 --save_noDW --even_odd_split"
cpubusy() { awk "/^cpu(8|9|10|11) /{b+=\$2+\$3+\$4+\$7+\$8+\$9} END{print b}" /proc/stat; }
run() { local name=$1 bin=$2; shift 2
  rm -rf ab24e/out-$name-$R
  local l1=$(cut -d" " -f1 /proc/loadavg) b0=$(cpubusy)
  env "$@" taskset -c 8-11 /usr/bin/time -v $bin --i "Movies24/*.tiff" $ARGS --o ab24e/out-$name-$R/ --profile ab24e/prof-$name-$R.jsonl > ab24e/run-$name-$R.log 2> ab24e/time-$name-$R.log
  local rc=$? b1=$(cpubusy)
  python3 digest24.py ab24e/out-$name-$R > ab24e/digest-$name-$R.txt
  local u=$(awk -F": " "/User time/{u=\$2} /System time/{s=\$2} END{print int((u+s)*100)}" ab24e/time-$name-$R.log)
  echo "$name r$R rc=$rc load1_start=$l1 cpu8-11_jiffies=$((b1-b0)) own_jiffies=$u mrc=$(grep -c " mrc " ab24e/digest-$name-$R.txt) $(grep -E "Elapsed|User time|System time|Maximum resident|Minor" ab24e/time-$name-$R.log | awk -F": " "{printf \"%s \", \$2}")"
}
H=GLIBC_TUNABLES=glibc.malloc.hugetlb=1
echo "start $(date -u +%FT%TZ) THP: $(cat /sys/kernel/mm/transparent_hugepage/enabled)"
R=1; run plain $MAIN X=1; run tunable $MAIN $H
R=2; run tunable $MAIN $H; run plain $MAIN X=1
R=3; run plain $MAIN X=1; run tunable $MAIN $H
R=4; run tunable $MAIN $H; run plain $MAIN X=1
for d in ab24e/digest-*.txt; do cmp -s ab24c/digest-main-1.txt $d && echo "identity $d: IDENTICAL" || echo "identity $d: DIFFERS"; done
echo DONE $(date -u +%FT%TZ)
