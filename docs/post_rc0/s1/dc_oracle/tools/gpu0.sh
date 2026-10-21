#!/bin/bash
set -eu
cd /mnt/clathrin/alex-motioncorr-dc-oracle
flock /tmp/motioncorr-gpu0-correctness.lock taskset -c 96-103 env CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib ctest --test-dir build -R '^(RunnerNumerics|CudaPeakFit|CudaHermitianCCF)$' --output-on-failure > native-tests.log 2>&1
printf 'native_tests_exit=0\n' > native-tests.exit
python3 tools/census.py /mnt/clathrin/alex-motioncorr-dc-oracle --movies e10216-00,e12963-00,e10474f3-00 --arms parentGPU,G_none --lane 0
python3 tools/census.py /mnt/clathrin/alex-motioncorr-dc-oracle --arms G_none,G_global,G_local,G_both --lane 0 --shards 2 --shard 0
