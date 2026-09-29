#!/bin/bash
set -euo pipefail
cd /home/alex/mc118-preprocess-20260929T1311
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda/bin:$PATH
export CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54
export OMP_NUM_THREADS=4
exec 9>/tmp/motioncorr-gpu0-correctness.lock
flock -n 9 || exit 30
nvidia-smi --query-compute-apps=pid,gpu_uuid,process_name --format=csv,noheader >main-proof/u16-observed-occupancy-before.csv
if grep -q GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 main-proof/u16-observed-occupancy-before.csv; then exit 31; fi
cp /home/alex/faultinject-io2-observed main-proof/faultinject-io2-observed
chmod +x main-proof/faultinject-io2-observed
sha256sum source/tests/run_u16_failure_controls.sh source/docs/issue85_laneC/compare_output_trees.py main-proof/faultinject-io2-observed build/motioncorr_faultinject /home/alex/MotionCorr-standalone/relion30_tutorial/Movies/20170629_00021_frameImage.tiff /home/alex/MotionCorr-standalone/relion30_tutorial/movies.star >main-proof/u16-observed-hashes.txt
bash source/tests/run_u16_failure_controls.sh main-proof/faultinject-io2-observed /home/alex/MotionCorr-standalone/relion30_tutorial/Movies/20170629_00021_frameImage.tiff 28477960 source/docs/issue85_laneC/compare_output_trees.py /home/alex/mc118-preprocess-20260929T1311/main-proof/u16-observed >main-proof/u16-observed.log 2>&1
nvidia-smi --query-compute-apps=pid,gpu_uuid,process_name --format=csv,noheader >main-proof/u16-observed-occupancy-after.csv
date -u >main-proof/u16-observed-finished.txt
