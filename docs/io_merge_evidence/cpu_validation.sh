#!/bin/bash
set -euo pipefail
D=/home/ubuntu/mc-io-merge-evidence
BASE=/home/ubuntu/mc-io-evidence
T=/home/ubuntu/mc51/tutorial
mkdir -p "$D/evidence"
source /home/ubuntu/.mc-venv/bin/activate
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
cd "$D"
hostname;date -Is;uptime;grep Cpus_allowed_list /proc/self/status
[ "$(git -C "$BASE/src-main" rev-parse HEAD)" = 1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26 ]
[ "$(sha256sum "$BASE/src-main/build-cpu/motioncorr" | cut -d' ' -f1)" = 28918ae8438f1e953eda6648d6178544fc3b431158c41cf9907d67f3d8513a1d ]
git -C "$BASE/src-main" status --porcelain --untracked-files=no > evidence/baseline-status.txt
[ ! -s evidence/baseline-status.txt ]
cp "$BASE/evidence/pr90_outputs_j4.json" evidence/reused-baseline-j4-provenance.json
cp "$BASE/src-main/build-cpu/CMakeCache.txt" evidence/baseline-CMakeCache.txt
sha256sum "$BASE/src-main/build-cpu/motioncorr" "$BASE/dump_decoded_main" > evidence/baseline-binaries.sha256
sha256sum "$T/movies.star" "$T/Movies/gain.mrc" > evidence/input-hashes.txt
for label in standalone combined; do
 if [ "$label" = standalone ];then sha=7a4f93f782a970fd146527beb5fd49e64695c1dc;else sha=e4f6769b0e1eb565fb1aed8de760efe1e6dc86f6;fi
 git init --quiet "src-$label"
 git -C "src-$label" fetch --quiet "$D/$label.bundle" "$sha"
 git -C "src-$label" checkout --quiet --detach "$sha"
 [ "$(git -C "src-$label" rev-parse HEAD)" = "$sha" ]
 git -C "src-$label" show -s --format=fuller HEAD > "evidence/source-$label.txt"
 cmake -S "src-$label" -B "src-$label/build-cpu" -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DMETAL=OFF -DTIMING=ON -DBUILD_TESTING=ON > "evidence/configure-$label.log" 2>&1
 cmake --build "src-$label/build-cpu" --parallel 8 > "evidence/build-$label.log" 2>&1
 sha256sum "src-$label/build-cpu/motioncorr" > "evidence/binary-$label.sha256"
 set +e
 ctest --test-dir "src-$label/build-cpu" --output-on-failure > "evidence/ctest-$label.log" 2>&1
 echo "$?" > "evidence/ctest-$label.rc"
 set -e
 bash harness/build_harness.sh "$D/src-$label" "$D/src-$label/build-cpu" "$D/dump-$label" > "evidence/build-dumper-$label.log" 2>&1
 python3 harness/compare_decoded.py --repo "$D/src-$label" --ref-dumper "$BASE/dump_decoded_main" --test-dumper "$D/dump-$label" --work "$D/decoded-$label" --json "$D/evidence/decoded-$label.json" > "evidence/decoded-$label.log" 2>&1
 mkdir -p "$D/ab-$label"
 cp -al "$BASE/ab-j4/out_main_j4" "$D/ab-$label/out_main_j4"
 cd "$T"
 "$D/src-$label/build-cpu/motioncorr" --i movies.star --o "$D/ab-$label/out_${label}_j4" --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 4 > "$D/evidence/run-$label.stdout" 2> "$D/evidence/run-$label.stderr"
 cd "$D"
 set +e
 python3 harness/compare_outputs.py --repo "$BASE/src-main" --ref-binary "$BASE/src-main/build-cpu/motioncorr" --test-binary "$D/src-$label/build-cpu/motioncorr" --ref-label main --test-label "$label" --tutorial "$T" --threads 4 --skip-run --backend CPU --work "$D/ab-$label" --ref-output-root "$BASE/ab-j4/out_main_j4" --json "$D/evidence/parity-$label.json" > "evidence/parity-$label.log" 2>&1
 echo "$?" > "evidence/parity-$label.rc"
 set -e
 python3 - "$D/evidence/parity-$label.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert r['overall_graded']=='PASS',r['summary']
PY
done
g++ -shared -fPIC -O2 -I/usr/include/x86_64-linux-gnu harness/strip_fault_inject.cpp -ldl -o strip_fault_inject.so > evidence/strip-shim-build.log 2>&1
for label in standalone combined;do
 python3 harness/strip_rejection.py --repo "$D/src-$label" --dumper "$D/dump-$label" --shim "$D/strip_fault_inject.so" --work "$D/strips-$label" --json "$D/evidence/strip-rejections-$label.json" > "evidence/strip-rejections-$label.log" 2>&1
done
python3 harness/damaged_matrix.py --binary "$D/src-combined/build-cpu/motioncorr" --label combined --tutorial "$T" --work "$D/damaged-combined" --threads 1 4 --healthy 20170629_00021_frameImage.tiff --json "$D/evidence/damaged-combined.json" > evidence/damaged-combined.log 2>&1
for threads in 1 4;do
 python3 harness/resume_matrix.py --binary "$D/src-combined/build-cpu/motioncorr" --label combined --tutorial "$T" --work "$D/resume-j$threads" --threads "$threads" --healthy 20170629_00021_frameImage.tiff --json "$D/evidence/resume-j$threads.json" > "evidence/resume-j$threads.log" 2>&1
done
date -Is
printf 'COMPLETE\n' > evidence/COMPLETE
