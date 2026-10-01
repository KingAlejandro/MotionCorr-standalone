#!/bin/bash
set -euo pipefail
D=/work4/scd/scarf1415/motioncorr/post128-fft-sync-20261001
OLD=/work4/scd/scarf1415/motioncorr/post128-sgpu-20261001
R=/work4/scd/scarf1415/motioncorr/i53-scarf/runroot
CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
NVR=/home/vol05/scarf1415/nvcomp-sdk
cd "$D"
git clone --no-hardlinks baseline-src alignment-src >alignment-clone.log 2>&1
git -C alignment-src fetch "$D/mc-alignment-source.bundle" experiment/post128-alignment-sync >>alignment-clone.log 2>&1
git -C alignment-src checkout FETCH_HEAD >>alignment-clone.log 2>&1
cp mc-alignment-source-pin.json alignment-src/SOURCE_PIN.json
cmake -S alignment-src -B alignment-build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=ON -DUSE_NVCOMP=ON -DNVCOMP_ROOT="$NVR" -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc" -DCUDAToolkit_ROOT="$CUDA_HOME" >alignment-configure.log 2>&1
taskset -c 0-7 cmake --build alignment-build --parallel 8 >alignment-build.log 2>&1
taskset -c 0-7 ctest --test-dir alignment-build --output-on-failure >alignment-ctest.log 2>&1
taskset -c 0-7 python3 alignment-src/tools/single_gpu/run_alignment_mutants.py --source "$D/alignment-src" --build "$D/alignment-build" --root "$D/alignment-mutants" >alignment-mutants.log 2>&1
taskset -c 0-7 python3 alignment-src/tools/single_gpu/run_option_matrix.py --baseline "$OLD/candidate-build/motioncorr" --candidate "$D/alignment-build/motioncorr" --source "$D/alignment-src" --input-dir "$R" --root "$D/alignment-options" >alignment-options.log 2>&1
python3 alignment-src/tools/single_gpu/run_pairs.py --root "$D" --baseline "$OLD/candidate-build/motioncorr" --candidate "$D/alignment-build/motioncorr" --source "$D/alignment-src" --input-dir "$R" --cpus 0-7 --gpu-uuid "$(cat gpu-uuid.txt)" --phase alignment-screen --pairs 3 >alignment-screen.log 2>&1
touch ALIGNMENT_SCREEN_DONE
for n in $(seq 1 60);do
 if test -f PHASE4_READY;then bash phase4.sh;exit $?;fi
 sleep 15
done
exit 4
