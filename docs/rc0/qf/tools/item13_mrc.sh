#!/bin/bash
# QF item 13: raw integer MRC staging (#195) with #204's harness (PR #204 @ 5944617b, vendored in
# harness_mrc/ with only its source-root line changed) on the frozen binaries, then graded against
# #204's recorded verdicts by grade_item13.py. Requires QF_W QF_CPUS QF_GPU_UUID QF_GPU_LOCK.
# Mirrors #204's runs: CUDA synthetic sections all; CPU matrix + errors; real data G/L (pinned compact
# refusal on 10028 via the options runs); the six option sets of run_options.sh.
set -u
: "${QF_W:?}" "${QF_CPUS:?}" "${QF_GPU_UUID:?}" "${QF_GPU_LOCK:?}"
T=$(cd "$(dirname "$0")" && pwd)
PY=/home/alex/.mc-venv/bin/python3
O=$QF_W/item13-mrc; mkdir -p $O/inputs $O/logs
export QF_W TMPDIR=$O/tmp QF_LANE_LOG=$O/logs/lane.log; mkdir -p $TMPDIR
V=$HOME/motioncorr-validation-20261011-vm/corpus/data-https
Q1D=/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/data
# real-data inputs under #204's names (real_data_identity.py FAMILIES); sha256 must equal #204's evidence/inputs/sha256.txt
ln -sfn $Q1D/EMPIAR-10164/data/frames/TS_01_000_0.0.mrc $O/inputs/10164_TS_01_000_0.0.mrc
ln -sfn $Q1D/EMPIAR-10216/data/FoilHole_14961495_Data_14966722_14966723_20180615_1739_Fractions.mrc $O/inputs/10216_1739_Fractions.mrc
ln -sfn $V/EMPIAR-10028/data/Micrographs/Micrographs_part1/031_movie.mrcs $O/inputs/10028_031_movie.mrcs
(cd $O/inputs && sha256sum -c - <<SUMS) || { echo "input hashes differ from #204"; exit 3; }
117c303163480aa6bd3a1c1298c5635486dd077babce770dfcaf4ca944245039  10164_TS_01_000_0.0.mrc
f399bd30bfe1a9807bd494c348bfcf7d4aee312ccc18140b05abb1453ac23a56  10216_1739_Fractions.mrc
8ce479649ec00abf46b290aee2b43343d0ba0dc67f239f0e3fd0c6875b3c7213  10028_031_movie.mrcs
SUMS
GPU="$T/qf_lane_exec.sh"
echo "start $(date -u +%FT%TZ)"
for s in matrix refuse compressed errors options; do
  MC_BIN=$QF_W/build-nvcomp/motioncorr $PY -I $T/harness_mrc/synth_mrc_matrix.py --binary $GPU --gpu 0 \
    --work $O/synth/cuda --out $O/cuda-$s.json --section $s > $O/logs/cuda-$s.log 2>&1; echo "cuda $s rc=$?"
done
for s in matrix errors; do
  MC_BIN=$QF_W/build-cpu/motioncorr QF_LANE_CPU_ONLY=1 $PY -I $T/harness_mrc/synth_mrc_matrix.py --cpu --binary $GPU \
    --work $O/synth/cpu --out $O/cpu-$s.json --section $s > $O/logs/cpu-$s.log 2>&1; echo "cpu $s rc=$?"
done
MC_BIN=$QF_W/build-nvcomp/motioncorr $PY -I $T/harness_mrc/real_data_identity.py --binary $GPU --gpu 0 --inputs $O/inputs \
  --work $O/runs/real --out $O/real.json > $O/logs/real.log 2>&1; echo "real rc=$?"
opt() { tag=$1; shift; MC_BIN=$QF_W/build-nvcomp/motioncorr $PY -I $T/harness_mrc/real_data_identity.py --binary $GPU --gpu 0 \
  --inputs $O/inputs --work $O/runs/opts --out $O/opts_$tag.json --families e10216 --tag $tag --rss "$@" >> $O/logs/opts.log 2>&1; echo "opts $tag rc=$?"; }
opt baseline_rss --configs G
opt late_bin2 --configs G,L --extra '--no_early_binning --bin_factor 2'
opt early_bin2 --configs G,L --extra '--bin_factor 2' --expect-route float --pinned-compact
opt early_bin2_explicit --configs G --extra '--early_binning --bin_factor 2' --expect-route float --pinned-compact
opt noDW_evenodd --configs G,L --extra '--save_noDW --even_odd_split'
opt ps_group4 --configs G,L --extra '--grouping_for_ps 4'
find $O/synth $O/runs -name '*.mrc' -delete 2>/dev/null
$PY $T/grade_item13.py $O; echo "grade rc=$? end $(date -u +%FT%TZ)"
