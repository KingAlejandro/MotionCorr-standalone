#!/bin/bash
set -u
W=/tmp/mc-capext-20261027-r2; cd $W/build
export PATH=/Users/alex.konstantinov/.local/bin:$PATH OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2
unset MC_DIAG_LOCAL_CCF_DIR MC_EXPERIMENT_CCF_DC_ARM
echo "== unit"; ./local_ccf_capture > $W/test_unit.stdout 2> $W/test_unit.stderr; echo unit_rc=$?; tail -1 $W/test_unit.stdout | cut -c1-200
echo "== cli"; /Users/alex.konstantinov/.local/bin/python3 $W/src/tests/test_local_ccf_capture_cli.py --binary $W/build/motioncorr > $W/test_cli.stdout 2> $W/test_cli.stderr; echo cli_rc=$?; tail -1 $W/test_cli.stdout
echo "== extra targets"; cmake --build . -j2 --target patch_retry_state local_b2_fit global_half_gain coupled_peak isotropic_weight > $W/build2.log 2>&1; echo build2_rc=$?
echo "== ctest without DC arm env (preserved)"; ctest -R '^(LocalCcfCapture|LocalCcfCaptureCli|LocalB2Fit|CcfDcHook|ExperimentalFlagsCli|PatchRetryState|GlobalHalfGain|CoupledPeak|LocalFullWidthWeight|IsotropicWeight)$' --output-on-failure -j2 > $W/ctest_noarm.log 2>&1; echo rc=$?; grep -E "Test +#|tests passed" $W/ctest_noarm.log | cut -c1-100
echo "== ctest arm none for the tests that need it"; MC_EXPERIMENT_CCF_DC_ARM=none ctest -R '^(PatchRetryState|GlobalHalfGain|CoupledPeak|IsotropicWeight)$' --output-on-failure > $W/ctest_arm_none.log 2>&1; echo rc=$?; grep -E "Test +#|tests passed" $W/ctest_arm_none.log | cut -c1-100
echo "== legacy differential dump"; bash $W/run_dump.sh 2>&1 | tee $W/dump/result.txt
echo "== sanitizers"; bash $W/sanitize.sh
echo "== unit mutants"; bash $W/mutants.sh 2>&1 | tee $W/mutants_unit.txt
echo "== cli mutant"; bash $W/mutant_cli.sh 2>&1 | tee $W/mutant_cli.txt
echo ALL_DONE
