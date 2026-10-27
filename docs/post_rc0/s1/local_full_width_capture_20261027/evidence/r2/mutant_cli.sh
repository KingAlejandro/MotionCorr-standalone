#!/bin/bash
set -u
W=/tmp/mc-capext-20261027-r2; M=$W/mut_cli; rm -rf $M; mkdir -p $M; cp -R $W/src $M/src
python3 - $M/src/src/motioncorr_runner.cpp <<'PY'
import sys
p=sys.argv[1]; s=open(p).read(); old="experimental_isotropic_weight || ccf_downsample != 0\n\t\t    || bfactor"
assert s.count(old)==1; open(p,'w').write(s.replace(old,"experimental_isotropic_weight || experimental_local_full_width_weight || ccf_downsample != 0\n\t\t    || bfactor"))
PY
export PATH=/Users/alex.konstantinov/.local/bin:$PATH OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
unset MC_EXPERIMENT_CCF_DC_ARM MC_DIAG_LOCAL_CCF_DIR
cmake -S $M/src -B $M/build -DCMAKE_BUILD_TYPE=Release -DMC_EXPERIMENT_CCF_DC=ON -DPython3_EXECUTABLE=/Users/alex.konstantinov/.local/bin/python3 > $M/configure.log 2>&1; echo cfg_rc=$?
cmake --build $M/build -j2 --target motioncorr > $M/build.log 2>&1; echo build_rc=$?
/Users/alex.konstantinov/.local/bin/python3 $W/src/tests/test_local_ccf_capture_cli.py --binary $M/build/motioncorr > $M/cli.out 2>&1; echo "m1_guard_still_refuses_flag: cli rc=$? :: $(tail -1 $M/cli.out | cut -c1-200)"
