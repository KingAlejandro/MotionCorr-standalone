#!/usr/bin/env bash
# round96 correctness-foundation -- CPU validation phase 3
# Controlled healthy reference: exact current main vs the combined candidate tree.
# All 24 tutorial movies, same backend (CPU), same options, same thread count.
# Complete ordered pixels, normalized full headers, STAR inventory, and an
# ordered decoded-buffer control. Reuses the in-repo io_review_evidence harness.
set -uo pipefail
ROOT=/home/ubuntu/mc-i96-integration
VENV=/home/ubuntu/.mc-venv
export PATH=$VENV/bin:$PATH
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
LOG=$ROOT/logs
BASE=4c952b3f54479653512c4d208e09c9a8c02f3726
TUT=/home/ubuntu/mc51/tutorial
J=8
exec > >(tee -a "$LOG/phase3.log") 2>&1
echo "##### PHASE 3 START #####"; date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
grep -E "Cpus_allowed_list" /proc/self/status; numactl --show | grep -E "membind|physcpubind"
echo "interference at start:"; ps -eo pid,user,pcpu,comm --sort=-pcpu | head -5

echo; echo "##### PRISTINE BASE BUILD (reference arm) #####"
REF=$ROOT/refsrc; rm -rf "$REF"
git -C "$ROOT/src" worktree add -q --detach "$REF" "$BASE"
cd "$REF"
echo "ref head: $(git rev-parse HEAD)"
echo "ref tree: $(git rev-parse HEAD^{tree})"
echo "ref dirty files: $(git status --porcelain | wc -l)  (must be 0 -- a contaminated reference invalidates the whole comparison)"
cmake -S "$REF" -B "$REF/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCUDA=OFF -DPython3_EXECUTABLE=$VENV/bin/python3 > "$LOG/ref-configure.log" 2>&1
echo "ref configure exit=$?"
grep -E "^CMAKE_BUILD_TYPE|^CMAKE_CXX_FLAGS_RELEASE" "$REF/build/CMakeCache.txt"
cmake --build "$REF/build" --parallel 16 > "$LOG/ref-build.log" 2>&1
echo "ref build exit=$?"

echo; echo "##### BINARY AND INPUT PROVENANCE #####"
sha256sum "$REF/build/motioncorr" "$ROOT/src/build/motioncorr"
echo "--- these two binaries MUST differ, or the A/B compares one build with itself ---"
[ "$(sha256sum < "$REF/build/motioncorr")" = "$(sha256sum < "$ROOT/src/build/motioncorr")" ] \
  && echo "!! IDENTICAL BINARIES -- comparison is vacuous" || echo "OK: distinct binaries"
echo "--- inputs ---"
ls "$TUT/Movies"/*.tiff | wc -l | sed 's/^/tutorial movies: /'
sha256sum "$TUT/movies.star"
( cd "$TUT/Movies" && sha256sum *.tiff | sha256sum | sed 's/^/movie payload digest-of-digests: /' )
ls -l "$TUT"/*gain* 2>/dev/null | head -3

echo; echo "##### A/B: all 24 movies, CPU backend, --j $J, default options #####"
rm -rf "$ROOT/ab24"
python3 "$ROOT/src/docs/io_review_evidence/harness/compare_outputs.py" \
  --repo "$ROOT/src" \
  --ref-binary "$REF/build/motioncorr" --ref-label main-4c952b3 \
  --test-binary "$ROOT/src/build/motioncorr" --test-label integrate-round96 \
  --tutorial "$TUT" --threads $J \
  --work "$ROOT/ab24" --json "$ROOT/ab24.json" > "$LOG/ab24.log" 2>&1
echo "A/B exit=$?"
tail -40 "$LOG/ab24.log"

echo; echo "##### A/B SUMMARY FROM JSON #####"
python3 - "$ROOT/ab24.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
def walk(o,pre=""):
    if isinstance(o,dict):
        for k,v in o.items():
            if isinstance(v,(dict,list)): walk(v,pre+"/"+str(k))
            else: print(f"{pre}/{k} = {v}")
    elif isinstance(o,list):
        print(f"{pre} = list[{len(o)}]")
        for i,v in enumerate(o[:3]): walk(v,f"{pre}[{i}]")
        if len(o)>3: print(f"{pre} ... {len(o)-3} more")
keys=list(d.keys())
print("top-level keys:", keys)
for k in keys:
    v=d[k]
    if isinstance(v,(str,int,float,bool)) or v is None: print(f"  {k} = {v}")
print()
walk(d)
PY

echo; echo "##### ORDERED DECODED-BUFFER CONTROL #####"
H="$ROOT/src/docs/io_review_evidence/harness"
bash "$H/build_harness.sh" "$REF"      "$REF/build"      "$ROOT/dump-ref"  > "$LOG/harness-ref.log" 2>&1;  echo "ref dumper build exit=$?"
bash "$H/build_harness.sh" "$ROOT/src" "$ROOT/src/build" "$ROOT/dump-cand" > "$LOG/harness-cand.log" 2>&1; echo "cand dumper build exit=$?"
sha256sum "$ROOT/dump-ref" "$ROOT/dump-cand" 2>/dev/null
rm -rf "$ROOT/decoded"
python3 "$H/compare_decoded.py" --repo "$ROOT/src" \
  --ref-dumper "$ROOT/dump-ref" --test-dumper "$ROOT/dump-cand" \
  --work "$ROOT/decoded" \
  --real-movie "$TUT/Movies/20170629_00021_frameImage.tiff" \
  --real-movie "$TUT/Movies/20170629_00035_frameImage.tiff" \
  --json "$ROOT/decoded.json" > "$LOG/decoded.log" 2>&1
echo "decoded-buffer control exit=$?"
tail -25 "$LOG/decoded.log"

echo; echo "##### DONE PHASE 3 #####"; date -u +"UTC %Y-%m-%dT%H:%M:%SZ"
