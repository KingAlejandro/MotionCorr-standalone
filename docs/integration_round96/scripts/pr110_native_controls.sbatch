#!/bin/bash
#SBATCH -p gpu-devel
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --exclusive
#SBATCH -t 01:00:00
#SBATCH -J pr110-native-controls
#SBATCH -o /work4/scd/scarf1415/motioncorr/pr110-baseline/slurm-controls-%j.out
#
# PR110 native decoded-reader / failure / resume controls, corrected.
#
# The first attempt's three "failures" were all harness defects, not product
# defects, and both root causes are fixed here:
#   * j1-vs-j8 equality was tested with whole-file MRC sha256. An MRC label is
#     timestamped (label_header_diff_bytes=3, normalized=0), so identical
#     products hash differently. Now uses tools/compare_motioncorr.py.
#   * the damaged-movie sandbox filtered movies.star with a rule that never
#     matched (data lines carry a trailing optics-group column), so 22 movies
#     were legitimately absent and the run failed for the wrong reason. The
#     STAR is now rebuilt from the template with exactly two movies.
set -uo pipefail
trap '' PIPE
D=/work4/scd/scarf1415/motioncorr/pr110-baseline
SRC=$D/run-3511135/cand            # already-built candidate from the baseline job
T=$D/data
W=$D/controls-$SLURM_JOB_ID; mkdir -p "$W"; cd "$W"
export CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH="$CUDA_HOME/bin:$PATH"; export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=8
MC=$SRC/build/motioncorr
CMP=$SRC/tools/compare_motioncorr.py

echo "=== allocation ==="; date -Is; hostname; echo "JOB=$SLURM_JOB_ID"
grep Cpus_allowed_list /proc/self/status
nvidia-smi --query-gpu=index,uuid,memory.used --format=csv,noheader
echo "compute apps before:"; nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid --format=csv,noheader
echo "binary: $(sha256sum $MC)"
echo "source head: $(git -C $SRC rev-parse HEAD)"

img_equal () {  # $1 ref mrc  $2 test mrc  -> prints verdict
  python3 "$CMP" --ref-mrc "$1" --test-mrc "$2" --gate exact --json 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin); c=d['checks']['corrected_image']
print(f\"pixel_identical={c['pixel_identical']} num_pixels={c['num_pixels']} rmse={c['rmse']} max_abs={c['max_abs_pixel_error']} core_hdr_diff={c['core_header_diff_bytes']} normalized_label_diff={c['normalized_label_diff_bytes']}\")"
}

echo; echo "################ C1 decoded-reader: thread-count invariance, j1 vs j8 ################"
mkdir -p "$W/j1"
( cd "$T" && $MC --i movies.star --o "$W/j1" --use_own --dose_weighting --dose_per_frame 1.277 \
    --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --gpu 0 --j 1 --seed 1 ) > "$W/j1.log" 2>&1
echo "j1 exit=$? products=$(ls $W/j1/Movies/*.mrc 2>/dev/null | wc -l)"
ok=0; bad=0
for f in "$W/j1/Movies"/*.mrc; do
  n=$(basename "$f"); r="$D/run-3511135/out_cand/Movies/$n"
  v=$(img_equal "$r" "$f")
  case "$v" in *"pixel_identical=True"*) ok=$((ok+1));; *) bad=$((bad+1)); echo "  NOT IDENTICAL $n : $v";; esac
done
echo "C1 result: $ok/$((ok+bad)) movies pixel-identical between --j 1 and --j 8 on the same device"
echo "  sample: $(img_equal "$D/run-3511135/out_cand/Movies/20170629_00021_frameImage.mrc" "$W/j1/Movies/20170629_00021_frameImage.mrc")"

echo; echo "################ C2 failure: truncated TIFF ################"
B=$W/bad; mkdir -p "$B/Movies"
A_MOV=20170629_00021_frameImage.tiff; B_MOV=20170629_00022_frameImage.tiff
cp "$T/Movies/gain.mrc" "$B/Movies/"; cp "$T/Movies/$A_MOV" "$B/Movies/"
head -c 8388608 "$T/Movies/$B_MOV" > "$B/Movies/$B_MOV"
# Rebuild the STAR with exactly two movies instead of filtering it.
python3 - "$T/movies.star" "$B/movies.star" "$A_MOV" "$B_MOV" <<'PY'
import sys
src, dst, a, b = sys.argv[1:5]
lines = open(src).read().splitlines()
out, in_movies, emitted = [], False, 0
for ln in lines:
    s = ln.strip()
    if s == "data_movies":
        in_movies = True
    if in_movies and s and not s.startswith(("data_", "loop_", "_rln", "#")):
        if a in s or b in s:
            out.append(ln); emitted += 1
        continue
    out.append(ln)
assert emitted == 2, f"expected exactly 2 movie rows, wrote {emitted}"
open(dst, "w").write("\n".join(out) + "\n")
print(f"  rebuilt STAR with {emitted} movie rows")
PY
grep -c "tiff" "$B/movies.star" | sed 's/^/  tiff references in sandbox STAR: /'
( cd "$B" && $MC --i movies.star --o "$B/out" --use_own --dose_weighting --dose_per_frame 1.277 \
    --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --gpu 0 --j 8 --seed 1 ) > "$W/c2.log" 2>&1
echo "C2 exit=$? (must be nonzero)"
echo "  damaged movie named:    $(grep -c "$B_MOV" "$W/c2.log")"
echo "  failed-movie count:     $(grep -oE "failed for [0-9]+ movie" "$W/c2.log" | head -1)"
echo "  healthy .mrc retained:  $(ls "$B/out/Movies/${A_MOV%.tiff}.mrc" 2>/dev/null | wc -l)"
echo "  joint STAR withheld:    $([ -f "$B/out/corrected_micrographs.star" ] && echo NO || echo YES)"

echo; echo "################ C3 resume after repair ################"
cp "$T/Movies/$B_MOV" "$B/Movies/$B_MOV"
HEALTHY_BEFORE=$B/out/Movies/${A_MOV%.tiff}.mrc
cp "$HEALTHY_BEFORE" "$W/healthy_before.mrc"
( cd "$B" && $MC --i movies.star --o "$B/out" --use_own --dose_weighting --dose_per_frame 1.277 \
    --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --gpu 0 --j 8 --seed 1 \
    --only_do_unfinished ) > "$W/c3.log" 2>&1
echo "C3 exit=$? (must be 0)"
echo "  products now:           $(ls "$B/out/Movies"/*.mrc 2>/dev/null | wc -l) of 2"
echo "  joint STAR now present: $([ -f "$B/out/corrected_micrographs.star" ] && echo YES || echo NO)"
echo "  healthy movie untouched by the resume (pixels, not whole-file hash):"
echo "    $(img_equal "$W/healthy_before.mrc" "$HEALTHY_BEFORE")"
echo "  repaired movie matches the full healthy run:"
echo "    $(img_equal "$D/run-3511135/out_cand/Movies/${B_MOV%.tiff}.mrc" "$B/out/Movies/${B_MOV%.tiff}.mrc")"

echo; echo "=== close-out ==="; nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid --format=csv,noheader; echo "(empty = nothing left)"; date -Is; echo "DONE native controls"
