#!/bin/bash
# Run as: setsid taskset -c 80-87 bash build_chain.sh   (whole chain confined to CPUs 80-87)
set -u
S=/home/alex/mc-dcnative-20261026
L=$S/logs; mkdir -p $L
PY=/home/alex/.mc-venv/bin/python3
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda/bin:$PATH
export CUDACXX=/usr/local/cuda/bin/nvcc
export CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 CUDA_DEVICE_ORDER=PCI_BUS_ID
i=10
for lk in /tmp/motioncorr-dcnative-gpu2-cpu80-87.lock /tmp/motioncorr-cuda-boundary-cpu80-87.lock /tmp/motioncorr-gpu2-correctness.lock /tmp/motioncorr-build.lock; do
  eval "exec $i>>$lk"; flock -n $i || { echo "LEASE_BUSY $lk"; exit 90; }; echo "lease $lk acquired $(date -u +%FT%TZ)"; i=$((i+1))
done
echo "== admission inside lease $(date -u +%FT%TZ)"
nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader
nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv
echo "affinity: $(taskset -cp $$)"; nproc; uptime
/usr/bin/cmake --version | head -1; nvcc --version | tail -2; $PY -c "import numpy,sys;print(sys.version.split()[0],numpy.__version__)"; gcc --version | head -1
echo "src tar sha: $(cat $S/src.tar.sha256)  git: $(cat $S/GIT_HEAD)"
SEL='CcfDc|ExperimentCcfDc|PatchRetry|PeakFit|Hermitian|CudaLocalAdmission|CudaStaleErrorAfterOom|SyntheticRegression|HotPixelRng|GlobalIfftElision|Runner_|RunnerInterpolate|RunnerModelParser'
for kind in def exp iso; do
  B=$S/build-$kind
  X=""; [ $kind != def ] && X="-DMC_EXPERIMENT_CCF_DC=ON"; [ $kind = iso ] && X="$X -DMC_TEST_ONLY_ISOTROPIC_GLOBAL_WEIGHT=ON"
  echo "== configure $kind [$X] $(date -u +%FT%TZ)"
  /usr/bin/cmake -S $S/src -B $B -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON -DPython3_EXECUTABLE=$PY $X > $L/configure-$kind.log 2>&1; echo "configure-$kind rc=$?"
  echo "== build $kind $(date -u +%FT%TZ)"
  /usr/bin/cmake --build $B -j8 > $L/build-$kind.log 2>&1; rc=$?; echo "build-$kind rc=$rc"
  sha256sum $B/motioncorr > $L/binary-$kind.sha256 2>/dev/null
  [ $rc = 0 ] || continue
  echo "== ctest $kind $(date -u +%FT%TZ)"
  ctest --test-dir $B -R "$SEL" --output-on-failure --timeout 3600 > $L/ctest-$kind.log 2>&1; echo "ctest-$kind rc=$?"
  tail -4 $L/ctest-$kind.log
done
echo "== done $(date -u +%FT%TZ)"
