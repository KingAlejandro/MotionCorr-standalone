#!/bin/bash
# Issue 10 provenance re-run at exact revisions. Run inside:
#   flock -w 14400 /tmp/motioncorr-cpu64-bench.lock ./ab24d.sh
# Builds main 116eb04a and #187 head 3fb58c2a from git-archive trees, runs the FloatPlanCache
# test (and an alignment-key mutant), then times main vs #187, both with the hugetlb tunable.
P=/home/ubuntu/mc-prov
CM=/home/ubuntu/.mc-venv/bin/cmake
PY=/home/ubuntu/.mc-venv/bin/python
build() { # srcdir builddir targets...
  local s=$1 b=$2; shift 2
  mkdir -p $b && (cd $b && taskset -c 8-15 $CM -S $s -B . -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DPython3_EXECUTABLE=$PY > cmake.log 2>&1 \
    && taskset -c 8-15 $CM --build . --target "$@" -j8 > build.log 2>&1; echo "build $b rc=$?")
}
echo "start $(date -u +%FT%TZ)"
build $P/src-main $P/build-main motioncorr
build $P/src-187 $P/build-187 motioncorr runner_numerics
echo "FloatPlanCache on #187 head:"; $P/build-187/runner_numerics float_plan_cache 2>&1 | tail -1; echo "rc=${PIPESTATUS[0]}"
# Mutant: drop both alignment terms from the cache key; the test must fail.
rm -rf $P/src-mut && cp -r $P/src-187 $P/src-mut
sed -i 's/fftwf_alignment_of(realPtr),/0,/; s/fftwf_alignment_of(complexPtr),/0,/' $P/src-mut/src/jaz/single_particle/new_ft.cpp
grep -c "fftwf_alignment_of" $P/src-mut/src/jaz/single_particle/new_ft.cpp
build $P/src-mut $P/build-mut runner_numerics
echo "FloatPlanCache on alignment-key mutant (must fail):"; $P/build-mut/runner_numerics float_plan_cache 2>&1 | tail -1; echo "rc=${PIPESTATUS[0]}"

cd /home/ubuntu/mc-cpu10-plancache
MAIN=$P/build-main/motioncorr
NEW=$P/build-187/motioncorr
mkdir -p ab24d
ARGS="--use_own --j 4 --angpix 0.885 --voltage 300 --bfactor 150 --patch_x 5 --patch_y 5 --gainref Movies24/gain.mrc --dose_weighting --dose_per_frame 1.277 --save_noDW --even_odd_split"
cpubusy() { awk "/^cpu(8|9|10|11) /{b+=\$2+\$3+\$4+\$7+\$8+\$9} END{print b}" /proc/stat; }
run() { local name=$1 bin=$2; shift 2
  rm -rf ab24d/out-$name-$R
  local l1=$(cut -d" " -f1 /proc/loadavg) b0=$(cpubusy)
  env "$@" taskset -c 8-11 /usr/bin/time -v $bin --i "Movies24/*.tiff" $ARGS --o ab24d/out-$name-$R/ --profile ab24d/prof-$name-$R.jsonl > ab24d/run-$name-$R.log 2> ab24d/time-$name-$R.log
  local rc=$? b1=$(cpubusy)
  python3 digest24.py ab24d/out-$name-$R > ab24d/digest-$name-$R.txt
  local u=$(awk -F": " "/User time/{u=\$2} /System time/{s=\$2} END{print int((u+s)*100)}" ab24d/time-$name-$R.log)
  echo "$name r$R rc=$rc load1_start=$l1 cpu8-11_jiffies=$((b1-b0)) own_jiffies=$u mrc=$(grep -c " mrc " ab24d/digest-$name-$R.txt) $(grep -E "Elapsed|User time|System time|Maximum resident|Minor" ab24d/time-$name-$R.log | awk -F": " "{printf \"%s \", \$2}")"
}
H=GLIBC_TUNABLES=glibc.malloc.hugetlb=1
echo "THP: $(cat /sys/kernel/mm/transparent_hugepage/enabled) defrag: $(cat /sys/kernel/mm/transparent_hugepage/defrag)"
R=warm; run warmmain $MAIN $H; run warm187 $NEW $H
R=1; run main $MAIN $H; run p187 $NEW $H
R=2; run p187 $NEW $H; run main $MAIN $H
R=3; run main $MAIN $H; run p187 $NEW $H
R=4; run p187 $NEW $H; run main $MAIN $H
for d in ab24d/digest-*.txt; do cmp -s ab24c/digest-main-1.txt $d && echo "identity $d: IDENTICAL" || echo "identity $d: DIFFERS"; done
{ echo "main src: git archive 116eb04a"; echo "187 src: git archive 3fb58c2afc7540694b50e66da99e57c84396519d"
  sha256sum $MAIN $NEW; $CM --version | head -1; g++ --version | head -1; lscpu | grep -E "Model name|^CPU\(s\)"; uname -r
  grep -h "CMAKE_BUILD_TYPE:\|CMAKE_CXX_FLAGS_RELEASE:" $P/build-main/CMakeCache.txt $P/build-187/CMakeCache.txt
  ldd --version | head -1; } > ab24d/provenance.txt 2>&1
( cd Movies24 && sha256sum -L *.tiff gain.mrc ) > ab24d/inputs.sha256
echo "DONE $(date -u +%FT%TZ)"
