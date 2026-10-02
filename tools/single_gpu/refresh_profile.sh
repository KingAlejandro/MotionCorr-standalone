#!/bin/bash
set -euo pipefail
D=/work4/scd/scarf1415/motioncorr/post128-sgpu-20261001
CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
NVR=/home/vol05/scarf1415/nvcomp-sdk
export PATH="$CUDA_HOME/bin:$PATH" LD_LIBRARY_PATH="$CUDA_HOME/lib64:$NVR/lib:${LD_LIBRARY_PATH:-}" OMP_NUM_THREADS=6 TMPDIR=/tmp
cd "$D"
cp -a baseline-src profile2-src
python3 instrument_profile.py profile2-src
cmake -S profile2-src -B profile2-build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=ON -DUSE_NVCOMP=ON -DNVCOMP_ROOT="$NVR" -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_CUDA_COMPILER="$CUDA_HOME/bin/nvcc" -DCUDAToolkit_ROOT="$CUDA_HOME" >profile2-configure.log 2>&1
cmake --build profile2-build --parallel 8 >profile2-build.log 2>&1
MASK=$(sed -n 's/runtime mask=//p' venue.txt)
R=/work4/scd/scarf1415/motioncorr/i53-scarf/runroot
cd "$R"; mkdir -p "$D/profile2-output"
# Device-wide sampled usage is separate from traced allocations; the node is
# exclusive, so device0 has only this payload. Preserve every raw observation.
nvidia-smi -i 0 --query-gpu=timestamp,uuid,utilization.gpu,utilization.memory,memory.used --format=csv -lms 100 > "$D/profile2-device-samples.csv" & SAMPLE=$!
trap 'kill "$SAMPLE" 2>/dev/null || true; wait "$SAMPLE" 2>/dev/null || true' EXIT
taskset -c "$MASK" /usr/bin/time -v nsys profile --trace=cuda,nvtx,osrt --cuda-memory-usage=true --sample=none --cpuctxsw=none --force-overwrite=true --output="$D/profile2" "$D/profile2-build/motioncorr" --i movies.star --o "$D/profile2-output/" --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 6 --max_io_threads 6 --ingest nvcomp --ingest_witness "$D/profile2.witness" > "$D/profile2.log" 2>&1
kill "$SAMPLE"; wait "$SAMPLE" || true; trap - EXIT
nsys export --type=sqlite --force-overwrite=true --output="$D/profile2.sqlite" "$D/profile2.nsys-rep" >"$D/export2.log" 2>&1
python3 "$D/summarize_trace.py" "$D/profile2.sqlite" > "$D/profile2-summary.json"
python3 "$D/baseline-src/docs/issue85_laneC/compare_output_trees.py" "$D/baseline-r3" "$D/profile2-output" --manifest "$D/baseline-src/docs/issue85_laneC/tutorial_24_movie_manifest.json" --input-star "$R/movies.star" --products-only --json-out "$D/profile2-exact.json" > "$D/profile2-exact.log" 2>&1
touch "$D/PROFILE2_DONE"
