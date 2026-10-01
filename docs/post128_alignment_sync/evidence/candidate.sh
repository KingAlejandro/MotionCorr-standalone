#!/bin/bash
set -euo pipefail
D=/work4/scd/scarf1415/motioncorr/post128-fft-sync-20261001
R=/work4/scd/scarf1415/motioncorr/i53-scarf/runroot
CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
NVR=/home/vol05/scarf1415/nvcomp-sdk
cd "$D"
CM=(-DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=ON -DUSE_NVCOMP=ON -DNVCOMP_ROOT="$NVR" -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc" -DCUDAToolkit_ROOT="$CUDA_HOME")
cmake -S fft-src -B fft-build "${CM[@]}" >fft-configure.log 2>&1
taskset -c 0-7 cmake --build fft-build --parallel 8 >fft-build.log 2>&1
sha256sum fft-build/motioncorr >fft-binary.sha256
taskset -c 0-7 ctest --test-dir fft-build --output-on-failure --timeout 900 >fft-ctest.log 2>&1
taskset -c 0-7 python3 fft-src/tools/single_gpu/run_fft_mutants.py --source "$D/fft-src" --build "$D/fft-build" --root "$D/fft-mutants" >fft-mutants.log 2>&1
taskset -c 0-7 python3 fft-src/tools/single_gpu/run_option_matrix.py --baseline "$D/baseline-build/motioncorr" --candidate "$D/fft-build/motioncorr" --source "$D/fft-src" --input-dir "$R" --root "$D/options" >options.log 2>&1
python3 fft-src/tools/single_gpu/run_pairs.py --root "$D" --baseline "$D/baseline-build/motioncorr" --candidate "$D/fft-build/motioncorr" --source "$D/fft-src" --input-dir "$R" --cpus 0-7 --gpu-uuid "$(cat gpu-uuid.txt)" --phase screen --pairs 3 >screen.log 2>&1
touch FFT_SCREEN_DONE
for n in $(seq 1 60);do
 if test -f PHASE2_READY;then bash phase2.sh;exit $?;fi
 sleep 15
done
exit 4
