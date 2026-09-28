#!/bin/bash
#SBATCH -p gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --exclusive
#SBATCH -t 04:00:00
#SBATCH -J pr110-native-baseline
#SBATCH -o /work4/scd/scarf1415/motioncorr/pr110-baseline/slurm-%j.out
#
# PR110 combined correctness foundation -- NATIVE CUDA baseline.
#
# Dedicated SCARF allocation, authorized 28 Sep. Does NOT touch the shared
# 4-GPU VM (#53 owns GPU0/1 + CPUs 96-111, #69 owns GPU2 + CPUs 112-119,
# GPU3 unallocated), and does not read or alter another task's SCARF inputs:
# this job uses its own copy of the dataset under pr110-baseline/data.
#
# This is native EXECUTION on a device. A compile is not counted as native.
set -uo pipefail
trap '' PIPE                     # a dead tee must not SIGPIPE the job

D=/work4/scd/scarf1415/motioncorr/pr110-baseline
T=$D/data
BUNDLE=$D/source.bundle
BASE=4c952b3f54479653512c4d208e09c9a8c02f3726
export CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=8
export TMPDIR=/tmp
W=$D/run-$SLURM_JOB_ID
mkdir -p "$W"; cd "$W"

echo "################ ALLOCATION AND HOST ################"
date -Is; hostname
echo "SLURM_JOB_ID=$SLURM_JOB_ID NODELIST=${SLURM_JOB_NODELIST:-}"
scontrol show job "$SLURM_JOB_ID" | grep -E "JobId|NumNodes|NumCPUs|TRES|Gres|OverSubscribe" || true
echo "--- actual inherited cpuset / mems ---"
grep -E "Cpus_allowed_list|Mems_allowed_list" /proc/self/status
echo "--- topology ---"
lscpu | grep -iE "^Model name|^Socket|^Core|^Thread|^CPU\(s\)|^NUMA node"
echo "--- NUMA policy and memory ---"
numactl --show 2>/dev/null | grep -E "policy|physcpubind|nodebind|membind"
numactl --hardware 2>/dev/null | grep -E "^node [0-9]+ (size|free)"
free -g | head -2
echo "--- load at start ---"; cat /proc/loadavg; uptime
echo "--- DEVICE IDENTITY (UUID, never ordinal) ---"
nvidia-smi --query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu --format=csv
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
echo "--- compute apps before (must be empty: exclusive allocation) ---"
nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid --format=csv,noheader
echo "--- toolchain ---"; nvcc --version | tail -2; g++ --version | head -1; cmake --version | head -1
python3 --version; python3 -c "import numpy;print('numpy',numpy.__version__)"

echo; echo "################ SOURCE AND INPUT IDENTITY ################"
sha256sum "$BUNDLE"
git clone -q --branch integrate/round96-correctness-foundation "$BUNDLE" cand
git -C cand worktree add -q --detach "$W/main" "$BASE"
CAND_SHA=$(git -C cand rev-parse HEAD)
echo "candidate head : $CAND_SHA"
echo "candidate tree : $(git -C cand rev-parse HEAD^{tree})"
echo "main base      : $BASE"
echo "main tree      : $(git -C "$W/main" rev-parse HEAD^{tree})"
echo "candidate dirty: $(git -C cand status --porcelain | wc -l)   main dirty: $(git -C "$W/main" status --porcelain | wc -l)"
echo "--- input payload identity ---"
sha256sum "$T/movies.star"
( cd "$T/Movies" && sha256sum *.tiff | sha256sum | sed 's/^/movie digest-of-digests: /' )
sha256sum "$T/Movies/gain.mrc"
ls "$T/Movies"/*.tiff | wc -l | sed 's/^/movies: /'

build_arm () {   # $1 = dir
  cmake -S "$1" -B "$1/build" -DCMAKE_BUILD_TYPE=Release -DCUDA=ON \
        -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=OFF > "$W/$(basename $1)-cfg.log" 2>&1
  echo "  configure exit=$?"
  cmake --build "$1/build" -j8 > "$W/$(basename $1)-build.log" 2>&1
  echo "  build exit=$?  errors=$(grep -cE 'error:' "$W/$(basename $1)-build.log")"
  sha256sum "$1/build/motioncorr"
  ldd "$1/build/motioncorr" | grep -iE "cudart|cufft" | sed 's/^/  /'
  cuobjdump --list-elf "$1/build/motioncorr" 2>/dev/null | sort -u | head -3 | sed 's/^/  /'
}
echo; echo "################ BUILDS (CUDA=ON, sm80, Release) ################"
echo "[main $BASE]";        build_arm "$W/main"
echo "[candidate $CAND_SHA]"; build_arm "$W/cand"

run_arm () {   # $1=label  $2=binary  $3=outdir
  mkdir -p "$3"
  echo "--- $1 ---"
  ( cd "$T" && /usr/bin/time -v "$2" --i movies.star --o "$3" \
      --use_own --dose_weighting --dose_per_frame 1.277 \
      --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc \
      --gpu 0 --j 8 --seed 1 ) > "$W/$1.stdout" 2> "$W/$1.stderr"
  echo "  exit=$?"
  grep -E "Maximum resident set size|Elapsed \(wall" "$W/$1.stderr" | sed 's/^/  /'
  echo "  mrc products: $(ls $3/Movies/*.mrc 2>/dev/null | wc -l)"
}

echo; echo "################ NATIVE CUDA ALL-24, BOTH ARMS ################"
# Device witness sampled while the candidate arm is actually on the GPU.
( sleep 45; echo "--- compute-apps witness DURING the run ---" >> "$W/device-witness.log"
  nvidia-smi --query-compute-apps=pid,process_name,used_memory,gpu_uuid --format=csv >> "$W/device-witness.log" 2>&1
  nvidia-smi --query-gpu=uuid,utilization.gpu,memory.used --format=csv,noheader >> "$W/device-witness.log" 2>&1 ) &
WITNESS=$!
run_arm main-$BASE      "$W/main/build/motioncorr" "$W/out_main"
run_arm cand-$CAND_SHA  "$W/cand/build/motioncorr" "$W/out_cand"
wait $WITNESS 2>/dev/null
echo "--- device witness captured during execution ---"; cat "$W/device-witness.log" 2>/dev/null

echo; echo "################ COMPLETE PRODUCT COMPARISON ################"
python3 - "$W/out_main" "$W/out_cand" "$W/cand/tools/compare_motioncorr.py" "$W/compare.json" <<'PY'
import hashlib, json, re, subprocess, sys
from pathlib import Path
ref_root, test_root, comparator, out_json = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])

def digest(p):
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()

# Path strings differ between arms by construction; normalise before comparing text products.
def norm(text, a, b):
    return text.replace(str(a), "<OUT>").replace(str(b), "<OUT>")

report = {"what": "native CUDA same-backend A/B, main vs PR110 combined, 1 A100, --gpu 0 --j 8",
          "not_a_claim_about": ["CPU/CUDA agreement", "RELION parity", "scientific equivalence", "speed"],
          "files": [], "summary": {}}
ref_files = {p.relative_to(ref_root).as_posix() for p in ref_root.rglob("*") if p.is_file()}
test_files = {p.relative_to(test_root).as_posix() for p in test_root.rglob("*") if p.is_file()}
report["summary"]["only_in_main"] = sorted(ref_files - test_files)
report["summary"]["only_in_cand"] = sorted(test_files - ref_files)

npix = nmrc = nstar = nfail = naux = 0
for rel in sorted(ref_files & test_files):
    a, b = ref_root / rel, test_root / rel
    kind = "image" if rel.endswith(".mrc") else "star" if rel.endswith(".star") else "auxiliary"
    entry = {"path": rel, "kind": kind}
    if kind == "star" or rel.endswith((".log", ".txt")):
        same = norm(a.read_text(errors="replace"), ref_root, test_root) == norm(b.read_text(errors="replace"), ref_root, test_root)
        entry["identical_normalized"] = same
    else:
        same = digest(a) == digest(b)
        entry["identical_bytes"] = same
        entry["ref_sha256"], entry["test_sha256"] = digest(a), digest(b)
    entry["status"] = "PASS" if same else "FAIL"
    if kind == "image":
        nmrc += 1
        r = subprocess.run([sys.executable, comparator, "--ref-mrc", str(a), "--test-mrc", str(b),
                            "--gate", "exact", "--require-complete-coverage", "--json"],
                           capture_output=True, text=True)
        entry["comparator_exit"] = r.returncode
        try:
            cj = json.loads(r.stdout)
            entry["comparator"] = {k: cj.get(k) for k in ("gate", "verdict", "image") if k in cj}
            img = cj.get("image") or {}
            npix += int(img.get("pixels_compared") or img.get("n_pixels") or 0)
        except Exception as exc:
            entry["comparator_parse_error"] = str(exc)
        if r.returncode != 0:
            entry["status"] = "FAIL"
    elif kind == "star":
        nstar += 1
    else:
        naux += 1
    if entry["status"] == "FAIL":
        nfail += 1
    report["files"].append(entry)

report["summary"].update({"artifacts_total": len(ref_files & test_files), "artifacts_fail": nfail,
                          "images_compared": nmrc, "star_compared": nstar, "auxiliary_compared": naux,
                          "total_pixels_compared": npix})
out_json.write_text(json.dumps(report, indent=2))
print(json.dumps(report["summary"], indent=2))
print("FAILING:", [f["path"] for f in report["files"] if f["status"] == "FAIL"])
PY

echo; echo "################ DECODED-READER / FAILURE / RESUME CONTROLS (native) ################"
CTL=$W/controls; mkdir -p "$CTL"

echo "--- C1 decoded-reader: same movie, both arms, byte-identical decoded product ---"
for arm in main cand; do
  mkdir -p "$CTL/dec_$arm"
  ( cd "$T" && "$W/$arm/build/motioncorr" --i movies.star --o "$CTL/dec_$arm" \
      --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 \
      --bfactor 150 --gainref Movies/gain.mrc --gpu 0 --j 1 --seed 1 \
      --only_do_unfinished false ) > "$CTL/dec_$arm.log" 2>&1
  echo "  $arm j1 exit=$? products=$(ls $CTL/dec_$arm/Movies/*.mrc 2>/dev/null | wc -l)"
done
echo "  j1 vs j8 candidate product equality (thread-count invariance):"
for f in "$CTL/dec_cand/Movies"/*.mrc; do
  n=$(basename "$f"); x=$(sha256sum "$f"|cut -d' ' -f1); y=$(sha256sum "$W/out_cand/Movies/$n" 2>/dev/null|cut -d' ' -f1)
  [ "$x" = "$y" ] || echo "    DIFFER: $n"
done; echo "    (no DIFFER lines above = identical)"

echo "--- C2 failure: truncated TIFF must fail the movie, name it, and publish no joint product ---"
mkdir -p "$CTL/bad/Movies"
cp "$T/movies.star" "$CTL/bad/"; cp "$T/Movies/gain.mrc" "$CTL/bad/Movies/"
first=$(ls "$T/Movies"/*.tiff | head -1); cp "$first" "$CTL/bad/Movies/"
second=$(ls "$T/Movies"/*.tiff | sed -n 2p); head -c 8388608 "$second" > "$CTL/bad/Movies/$(basename $second)"
python3 - "$CTL/bad/movies.star" "$(basename $first)" "$(basename $second)" <<'PY'
import sys, re
p, keep1, keep2 = sys.argv[1], sys.argv[2], sys.argv[3]
lines = open(p).read().splitlines()
out = [l for l in lines if not l.strip().endswith(".tiff") or keep1 in l or keep2 in l]
open(p, "w").write("\n".join(out) + "\n")
PY
( cd "$CTL/bad" && "$W/cand/build/motioncorr" --i movies.star --o "$CTL/bad/out" \
    --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 \
    --bfactor 150 --gainref Movies/gain.mrc --gpu 0 --j 8 --seed 1 ) > "$CTL/bad.log" 2>&1
echo "  exit=$? (must be nonzero)"
echo "  damaged movie named in output: $(grep -ci "$(basename $second)" "$CTL/bad.log")"
echo "  healthy product retained:      $(ls "$CTL/bad/out/Movies/$(basename ${first%.tiff}).mrc" 2>/dev/null | wc -l)"
echo "  joint STAR withheld:           $([ -f "$CTL/bad/out/corrected_micrographs.star" ] && echo NO_WITHHELD_PRESENT || echo YES_WITHHELD)"
tail -4 "$CTL/bad.log" | sed 's/^/    /'

echo "--- C3 resume: repair the damaged movie, rerun with --only_do_unfinished ---"
cp "$second" "$CTL/bad/Movies/$(basename $second)"
( cd "$CTL/bad" && "$W/cand/build/motioncorr" --i movies.star --o "$CTL/bad/out" \
    --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 \
    --bfactor 150 --gainref Movies/gain.mrc --gpu 0 --j 8 --seed 1 \
    --only_do_unfinished ) > "$CTL/resume.log" 2>&1
echo "  exit=$? (must be 0)"
echo "  products now: $(ls "$CTL/bad/out/Movies"/*.mrc 2>/dev/null | wc -l) of 2"
echo "  joint STAR now present: $([ -f "$CTL/bad/out/corrected_micrographs.star" ] && echo YES || echo NO)"
echo "  healthy movie untouched by the resume:"
h=$(basename ${first%.tiff}).mrc
echo "    $h  full-run=$(sha256sum "$W/out_cand/Movies/$h"|cut -c1-16)  resumed=$(sha256sum "$CTL/bad/out/Movies/$h"|cut -c1-16)"

echo; echo "################ CLOSE-OUT ################"
echo "compute apps after:"; nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid --format=csv,noheader
nvidia-smi --query-gpu=uuid,memory.used,utilization.gpu --format=csv,noheader
du -sh "$W" | tail -1
date -Is
echo "DONE pr110 native baseline"
