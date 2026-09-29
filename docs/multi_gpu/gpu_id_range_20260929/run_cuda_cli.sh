#!/usr/bin/env bash
set -euo pipefail
set -x
R=/home/alex/mc-pr117-gpu-range-20260929
cd "$R"
exec 9>/tmp/motioncorr-gpu1-correctness.lock
flock -n 9
export PATH=/usr/local/cuda-12.8/bin:$PATH
export CUDA_VISIBLE_DEVICES=GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader > occupancy-before.txt
if grep -q "$CUDA_VISIBLE_DEVICES" occupancy-before.txt; then echo 'Allocated GPU occupied'; exit 1; fi
date -Is
hostname
ps -p $$ -o pid,ppid,lstart,args
readlink /proc/$$/exe
grep -E 'Cpus_allowed_list|Mems_allowed_list' /proc/$$/status
numactl --show
git -C src rev-parse HEAD
test -z "$(git -C src status --porcelain)"
g++ -shared -fPIC -I/usr/local/cuda-12.8/include enum_witness.cpp -o enum_witness.so
OLD=/home/alex/mc-i53-native-20260928/work/build-cuda/motioncorr
git -C /home/alex/mc-i53-native-20260928/src rev-parse HEAD
sha256sum "$OLD"
/home/alex/mc-env/bin/python3 check_cuda_cli.py --binary "$OLD" --shim enum_witness.so --out old-cli --old
(
 flock 8
 cmake -S src -B build -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF > configure.log 2>&1
 cmake --build build --target motioncorr -j4 > build.log 2>&1
) 8>/tmp/motioncorr-vm-build.lock
sha256sum build/motioncorr
/home/alex/mc-env/bin/python3 check_cuda_cli.py --binary build/motioncorr --shim enum_witness.so --out fixed-cli
LD_PRELOAD="$R/enum_witness.so" MC_ENUM_WITNESS="$R/suite.enum" /home/alex/mc-env/bin/python3 src/tests/test_multi_gpu_scheduling.py --binary "$R/build/motioncorr" --only case_device_list_rejected
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader > occupancy-after.txt
date -Is
echo CUDA_CLI_CONTROL_PASS
