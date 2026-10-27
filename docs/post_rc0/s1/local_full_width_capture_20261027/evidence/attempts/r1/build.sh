#!/bin/bash
set -u
W=/tmp/mc-capext-20261027-r1
export PATH=/Users/alex.konstantinov/.local/bin:$PATH OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 MKL_NUM_THREADS=2
unset MC_EXPERIMENT_CCF_DC_ARM MC_DIAG_LOCAL_CCF_DIR
cmake -S $W/src -B $W/build -DCMAKE_BUILD_TYPE=Release -DMC_EXPERIMENT_CCF_DC=ON -DPython3_EXECUTABLE=/Users/alex.konstantinov/.local/bin/python3 > $W/configure.log 2>&1; echo configure_rc=$? > $W/build.status
cmake --build $W/build -j2 --target motioncorr local_ccf_capture local_full_width_weight ccf_dc_hook > $W/build.log 2>&1; echo build_rc=$? >> $W/build.status
