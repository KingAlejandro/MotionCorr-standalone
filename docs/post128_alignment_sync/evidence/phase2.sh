#!/bin/bash
set -euo pipefail
D=/work4/scd/scarf1415/motioncorr/post128-fft-sync-20261001
OLD=/work4/scd/scarf1415/motioncorr/post128-sgpu-20261001
R=/work4/scd/scarf1415/motioncorr/i53-scarf/runroot
CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
NVR=/home/vol05/scarf1415/nvcomp-sdk
cd "$D"
python3 fft-src/tools/single_gpu/run_pairs.py --root "$D" --baseline "$D/baseline-build/motioncorr" --candidate "$D/fft-build/motioncorr" --source "$D/fft-src" --input-dir "$R" --cpus 0-7 --gpu-uuid "$(cat gpu-uuid.txt)" --phase confirmation --pairs 5 >confirmation.log 2>&1
cmake -S fft-src -B fft-cpu-build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF -DUSE_NVCOMP=OFF >fft-cpu-configure.log 2>&1
taskset -c 0-7 cmake --build fft-cpu-build --parallel 8 >fft-cpu-build.log 2>&1
taskset -c 0-7 ctest --test-dir fft-cpu-build --output-on-failure >fft-cpu-ctest.log 2>&1
cmake -S fft-src -B fft-no-nvcomp-build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=ON -DUSE_NVCOMP=OFF -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc" -DCUDAToolkit_ROOT="$CUDA_HOME" >fft-no-nvcomp-configure.log 2>&1
taskset -c 0-7 cmake --build fft-no-nvcomp-build --parallel 8 >fft-no-nvcomp-build.log 2>&1
taskset -c 0-7 ctest --test-dir fft-no-nvcomp-build --output-on-failure >fft-no-nvcomp-ctest.log 2>&1
git clone --no-hardlinks baseline-src combined-src >combined-clone.log 2>&1
git -C combined-src fetch "$D/mc-combined-source.bundle" experiment/post128-workspace-fft >>combined-clone.log 2>&1
git -C combined-src checkout FETCH_HEAD >>combined-clone.log 2>&1
cp mc-combined-source-pin.json combined-src/SOURCE_PIN.json
cmake -S combined-src -B combined-build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=ON -DUSE_NVCOMP=ON -DNVCOMP_ROOT="$NVR" -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc" -DCUDAToolkit_ROOT="$CUDA_HOME" >combined-configure.log 2>&1
taskset -c 0-7 cmake --build combined-build --parallel 8 >combined-build.log 2>&1
taskset -c 0-7 ctest --test-dir combined-build --output-on-failure >combined-ctest.log 2>&1
taskset -c 0-7 python3 combined-src/tools/single_gpu/run_option_matrix.py --baseline "$D/baseline-build/motioncorr" --candidate "$D/combined-build/motioncorr" --source "$D/combined-src" --input-dir "$R" --root "$D/combined-options" >combined-options.log 2>&1
python3 combined-src/tools/single_gpu/run_pairs.py --root "$D" --baseline "$OLD/candidate-build/motioncorr" --candidate "$D/combined-build/motioncorr" --source "$D/combined-src" --input-dir "$R" --cpus 0-7 --gpu-uuid "$(cat gpu-uuid.txt)" --phase workspace-combined-screen --pairs 3 >workspace-combined-screen.log 2>&1
touch FFT_PHASE2_DONE
for n in $(seq 1 60);do
 if test -f PHASE3_READY;then bash phase3.sh;exit $?;fi
 sleep 15
done
exit 4
