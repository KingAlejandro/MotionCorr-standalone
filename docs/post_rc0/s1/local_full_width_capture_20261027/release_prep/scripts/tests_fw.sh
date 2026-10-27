#!/bin/bash
# Runs under lane.py. The eight relevant checks; the DC arm is none only where a test needs it (a DC build aborts those without an arm).
set -u
root=/tmp/motioncorr-lfw-capture-20261027
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PATH=/home/ubuntu/.mc-venv/bin:$PATH
unset MC_DIAG_LOCAL_CCF_DIR
python3 -B "$root/prep/guard.py" "$root" tests || exit 9
cd "$root/build"
echo "== arm unset: LocalCcfCapture LocalCcfCaptureCli LocalB2Fit CcfDcHook ExperimentalFlagsCli"; unset MC_EXPERIMENT_CCF_DC_ARM
/home/ubuntu/.mc-venv/bin/ctest --output-on-failure -j1 -R '^(LocalCcfCapture|LocalCcfCaptureCli|LocalB2Fit|CcfDcHook|ExperimentalFlagsCli)$' > "$root/receipts/ctest_arm_unset.log" 2>&1; echo rc_unset=$?
echo "== arm none: PatchRetryState GlobalHalfGain CoupledPeak (+ LocalFullWidthWeight)"; export MC_EXPERIMENT_CCF_DC_ARM=none
/home/ubuntu/.mc-venv/bin/ctest --output-on-failure -j1 -R '^(PatchRetryState|GlobalHalfGain|CoupledPeak|LocalFullWidthWeight)$' > "$root/receipts/ctest_arm_none.log" 2>&1; echo rc_none=$?
