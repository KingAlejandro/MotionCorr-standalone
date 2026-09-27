#!/bin/bash
#SBATCH -p gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --exclusive
#SBATCH --constraint=scarf23
#SBATCH -t 01:00:00
#SBATCH -J mc-io-selfctl
#SBATCH -o /scratch/scarf1415/mc-io-split-evidence/slurm-selfctl-%j.out
#
# Two things job 3510355 left unsettled, both about attribution rather than
# about the product:
#
#  1. main was run once and hard-linked into ab-pr91, so the log lines inside
#     the main tree still named ab-pr90 as their output root. The comparator
#     rewrites the root it is given, not the root a file was produced under, so
#     every main log in the pr91 comparison differed on a path it had no way to
#     normalise. main is re-run here into its own directory.
#
#  2. The auxiliary artefacts that differ are PDFs, and the text that differs
#     inside them is the absolute path of the .eps the plot was built from,
#     plus the text-matrix offset that follows from that string's rendered
#     width. No regex can normalise that away, because the coordinate is a
#     consequence of the glyphs. So the question "is this difference caused by
#     the code change?" is answered by holding the code constant and varying
#     only the output directory and the clock: main against main.
#
# No builds. The binaries are the ones job 3510355 produced and hashed.
set -uo pipefail
trap '' PIPE
D=/scratch/scarf1415/mc-io-split-evidence
T=/home/vol05/scarf1415/i53-scarf/relion30_tutorial
date -Is; hostname; nvidia-smi --query-gpu=index,name,memory.total --format=csv
echo "=== no other compute apps on the device at job start ==="
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
sha256sum $D/src-main/build-cuda/motioncorr $D/src-pr90/build-cuda/motioncorr \
          $D/src-pr91/build-cuda/motioncorr
md5sum $D/harness/compare_outputs.py

OPTIONS=(--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5
         --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8)

run_gpu () {  # srclabel outdir tag
  local label=$1 outdir=$2 tag=$3
  echo "=== GPU run $tag (binary: $label) ==="
  rm -rf "$outdir"; mkdir -p "$outdir"
  ( while true; do
      echo "$(date -Is) $(nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader)"
      sleep 2
    done ) > "$D/evidence/gpu-sample-$tag.txt" 2>&1 &
  local sampler=$!
  cd "$T"
  "$D/src-$label/build-cuda/motioncorr" --i movies.star --o "$outdir" \
      "${OPTIONS[@]}" --gpu 0 > "$D/evidence/run-$tag.stdout" 2>&1
  local rc=$?
  kill "$sampler" 2>/dev/null; wait "$sampler" 2>/dev/null
  cd "$D"
  echo "$tag exit=$rc"
  grep -m1 "Using CUDA acceleration on GPU device" "$D/evidence/run-$tag.stdout" \
    || echo "MARKER ABSENT ($tag)"
  echo "device samples naming motioncorr: $(grep -c motioncorr "$D/evidence/gpu-sample-$tag.txt")"
}

# 1. main, re-run into its own pr91 directory so its logs name that directory.
run_gpu main "$D/ab-pr91/out_main_j8" pr91main

# 2. self-control: the same binary, twice, into two directories.
mkdir -p "$D/ab-selfctl"
run_gpu main "$D/ab-selfctl/out_mainA_j8" mainA
run_gpu main "$D/ab-selfctl/out_mainB_j8" mainB

echo "=== self-control grade: main vs main, CUDA, 24 movies ==="
python3 $D/harness/compare_outputs.py --repo $D/src-main \
  --ref-binary $D/src-main/build-cuda/motioncorr --ref-label mainA \
  --test-binary $D/src-main/build-cuda/motioncorr --test-label mainB \
  --tutorial $T --threads 8 --skip-run \
  --work $D/ab-selfctl --json $D/evidence/selfcontrol_main_vs_main_cuda_j8.json
echo "selfctl exit=$?"

for pr in pr90 pr91; do
  echo "=== $pr vs main, CUDA backend, 24 movies, re-graded ==="
  python3 $D/harness/compare_outputs.py --repo $D/src-$pr \
    --ref-binary $D/src-main/build-cuda/motioncorr --ref-label main \
    --test-binary $D/src-$pr/build-cuda/motioncorr --test-label $pr \
    --tutorial $T --threads 8 --skip-run \
    --work $D/ab-$pr --json $D/evidence/${pr}_outputs_cuda_j8.json
  echo "$pr exit=$?"
done
echo "=== SELFCTL JOB DONE ==="; date -Is
