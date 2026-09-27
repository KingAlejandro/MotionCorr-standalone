#!/bin/bash
#SBATCH -p gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --exclusive
#SBATCH --constraint=scarf23
#SBATCH --nodelist=gn3000
#SBATCH -t 01:00:00
#SBATCH -J mc-77-confirm
#SBATCH -o /scratch/scarf1415/mc-issue77-reviewed/confirmation-%j.out
set -euo pipefail
D=/scratch/scarf1415/mc-issue77-reviewed
E="$D/evidence-3510495"
T=/home/vol05/scarf1415/i53-scarf/relion30_tutorial
C="$E/confirmation-$SLURM_JOB_ID"
mkdir -p "$C"
exec > "$C/job.log" 2>&1
export CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=8 TMPDIR=/tmp
MAIN="$D/src-main-3510495/build-cuda/motioncorr"
CAND="$D/src-candidate-3510495/build-cuda/motioncorr"
# Regrade retained timed artifacts with explicit original path provenance.
# Original failed job/report remains intact; these reports carry a v2 suffix.
for block in 1 2 3; do
 pair="$E/timing-pair-$block";mkdir -p "$pair"
 [ -d "$pair/out_main_j8" ] || cp -al "$E/timing/t_main_b$block" "$pair/out_main_j8"
 [ -d "$pair/out_candidate_j8" ] || cp -al "$E/timing/t_candidate_b$block" "$pair/out_candidate_j8"
 set +e
 python3 "$D/harness/compare_outputs.py" --repo "$D/src-main-3510495" --ref-binary "$MAIN" --test-binary "$CAND" --ref-label main --test-label candidate --tutorial "$T" --threads 8 --skip-run --work "$pair" --ref-output-root "$E/timing/t_main_b$block" --test-output-root "$E/timing/t_candidate_b$block" --json "$C/initial-timing-parity-$block-v2.json" > "$C/initial-timing-parity-$block-v2.log" 2>&1
 echo "$?" > "$C/initial-timing-parity-$block-v2.rc"
 set -e
 python3 - "$C/initial-timing-parity-$block-v2.json" <<'PY_CHECK'
import json,sys
assert json.load(open(sys.argv[1]))['overall_graded']=='PASS'
PY_CHECK
done
hostname;date -Is;uptime;grep Cpus_allowed_list /proc/self/status
scontrol show job "$SLURM_JOB_ID"
nvidia-smi
[ -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ]
sha256sum "$MAIN" "$CAND" > "$C/binaries.sha256"
python3 "$D/harness/timing_blocks.py" --ref-binary "$MAIN" --test-binary "$CAND" --ref-label main --test-label candidate --tutorial "$T" --threads 8 --blocks 3 --work "$C/timing" --json "$C/timing-confirmation.json" > "$C/timing.log" 2>&1
for block in 1 2 3; do
 pair="$C/timing-pair-$block";mkdir -p "$pair"
 cp -al "$C/timing/t_main_b$block" "$pair/out_main_j8"
 cp -al "$C/timing/t_candidate_b$block" "$pair/out_candidate_j8"
 set +e
 python3 "$D/harness/compare_outputs.py" --repo "$D/src-main-3510495" --ref-binary "$MAIN" --test-binary "$CAND" --ref-label main --test-label candidate --tutorial "$T" --threads 8 --skip-run --work "$pair" --ref-output-root "$C/timing/t_main_b$block" --test-output-root "$C/timing/t_candidate_b$block" --json "$C/timing-parity-$block.json" > "$C/timing-parity-$block.log" 2>&1
 echo "$?" > "$C/timing-parity-$block.rc"
 set -e
 python3 - "$C/timing-parity-$block.json" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))['overall_graded']=='PASS'
PY
done
date -Is
printf 'COMPLETE\n' > "$C/COMPLETE"
