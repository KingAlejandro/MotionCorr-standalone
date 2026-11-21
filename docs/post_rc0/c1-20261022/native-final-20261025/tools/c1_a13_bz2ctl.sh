#!/bin/bash
# A13 discriminating control for the c-m1-bz2-native-{auto,float} records: the vendored QF item-13 harness, UNEDITED, run for its `compressed` section only
# (the unit the harness exposes: `synth_mrc_matrix.py --section compressed`, exactly the CUDA invocation of item13_mrc.sh), same e77a51a2 nvCOMP binary, same lane,
# but with the pinned pbzip2 directory REMOVED from the job PATH. Fresh work/output dirs (the i8-a13 trees are untouched).
# Prediction (written to logs/a13-bz2ctl.PREDICTION before the run): both c-m1-bz2-native-* records now pass, i.e. match their harness expectation (native bz2 fails
# because pbzip2 is absent), and no other of the 49 compressed records changes against i8-a13 (cuda-compressed.json).
# usage: c1_a13_bz2ctl.sh  (through c1_stage.sh)
set -u
D=$(cd "$(dirname "$0")" && pwd); source "$D/c1_env.sh" || exit 1
export QF_W=$C1_SCR; cd $C1_SCR
# remove the pinned pbzip2 dir from PATH and prove the decoder is absent
PATH=$(echo "$PATH" | tr ':' '\n' | grep -v -x -F "$C1_PBZIP2_DIR" | paste -sd: -); export PATH
command -v pbzip2 >/dev/null 2>&1 && { echo "pbzip2 still resolves to $(command -v pbzip2); refusing"; exit 4; }
echo "pbzip2 absent from PATH: $(echo $PATH)" 
( flock -n 9 || exit 5 ) 9>>"$C1_GPU_LOCK" || { echo "GPU3 lease contended; stopping (no retry)"; exit 5; }
"$D/c1_occ.sh" a13-bz2ctl-pre 3; pre=$?; [ $pre -eq 0 ] || { echo "pre-run health failed rc=$pre"; exit 3; }
Q=$C1_SCR/src/docs/rc0/qf/tools
O=$C1_SCR/a13-bz2ctl; mkdir -p $O/logs $O/tmp
export TMPDIR=$O/tmp QF_LANE_LOG=$O/logs/lane.log
PY=/home/alex/.mc-venv/bin/python3
sha256sum $Q/harness_mrc/synth_mrc_matrix.py $Q/qf_lane_exec.sh $C1_SCR/build-nvcomp/motioncorr > $O/identity.sha256
taskset -c $C1_CPUS bash -c "MC_BIN=$C1_SCR/build-nvcomp/motioncorr $PY -I $Q/harness_mrc/synth_mrc_matrix.py --binary $Q/qf_lane_exec.sh --gpu 0 --work $O/synth/cuda --out $O/cuda-compressed.json --section compressed > $O/logs/cuda-compressed.log 2>&1"; rc=$?
echo "cuda compressed rc=$rc"
find $O/synth -name '*.mrc' -delete 2>/dev/null
"$D/c1_occ.sh" a13-bz2ctl-post 3; post=$?
if [ $post -ne 0 ]; then echo "post-run health failed rc=$post (driver rc=$rc)" >&2; [ $rc -eq 0 ] && rc=37; fi
exit $rc
