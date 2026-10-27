#!/bin/bash
# Runs under lane.py. Build the pinned source once: CPU, Release, DC hook on, CUDA off, -j2, OMP 2, BLAS 1.
set -eu
root=/tmp/motioncorr-lfw-capture-20261027
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PATH=/home/ubuntu/.mc-venv/bin:$PATH
unset MC_EXPERIMENT_CCF_DC_ARM MC_DIAG_LOCAL_CCF_DIR
python3 -B "$root/prep/guard.py" "$root" build
/home/ubuntu/.mc-venv/bin/cmake -S "$root/source" -B "$root/build" -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON -DMC_EXPERIMENT_CCF_DC=ON -DPython3_EXECUTABLE=/home/ubuntu/.mc-venv/bin/python3 > "$root/receipts/configure.log" 2>&1
/home/ubuntu/.mc-venv/bin/cmake --build "$root/build" --parallel 2 --target motioncorr local_ccf_capture local_b2_fit ccf_dc_hook patch_retry_state global_half_gain coupled_peak local_full_width_weight > "$root/receipts/build.log" 2>&1
