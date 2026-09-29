#!/bin/bash
set -euo pipefail
R=/home/alex/mc-pr115-enumeration-20260929
cd "$R"
export PATH=/usr/local/cuda-12.8/bin:$PATH CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 OMP_NUM_THREADS=4
exec 9>/tmp/motioncorr-gpu2-correctness.lock
flock -n 9
if [ -n "$(nvidia-smi -i 2 --query-compute-apps=pid --format=csv,noheader)" ]; then echo 'GPU2 occupied'; exit 2; fi
git -C src fetch /home/alex/pr115-enumeration-driver-20260929.bundle HEAD
git -C src checkout --detach FETCH_HEAD
{
 date -u; hostname; git -C src rev-parse HEAD; git -C src status --porcelain
 nvcc --version; nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader
 nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader
 grep -E 'Cpus_allowed_list|Mems_allowed_list' /proc/$$/status
 numactl --show; lscpu -e=CPU,CORE,SOCKET,NODE; uptime
 sha256sum build/{motioncorr,cuda_fault_matrix,motioncorr_faultinject}
 sha256sum /home/alex/MotionCorr-standalone/relion30_tutorial/Movies/{20170629_00021_frameImage.tiff,gain.mrc}
} > provenance.txt 2>&1
ctest --test-dir build --output-on-failure -j1 > ctest.log 2>&1
build/cuda_fault_matrix > matrix.log 2>&1
mkdir binaries
cp build/{motioncorr,cuda_fault_matrix,motioncorr_faultinject} binaries/
restore() { git -C src restore src/acc/cuda/cuda_movie_session.cu src/acc/cuda/cuda_fft_prep.cu; }
trap restore EXIT
for B in initialize patch; do
 python3 - "$B" <<'PY'
from pathlib import Path
import sys
if sys.argv[1] == 'initialize':
 p=Path('src/src/acc/cuda/cuda_movie_session.cu'); line='    recordFailure(count_err, __func__, __LINE__);\n'
else:
 p=Path('src/src/acc/cuda/cuda_fft_prep.cu'); line='    if (failure) failure->record(count_err, __func__, __LINE__);\n'
s=p.read_text(); assert s.count(line)==1; p.write_text(s.replace(line,''))
PY
 git -C src diff > "mutant-$B.patch"
 flock /tmp/motioncorr-vm-build.lock cmake --build build -j4 --target cuda_fault_matrix motioncorr_faultinject > "mutant-$B-build.log" 2>&1
 set +e
 build/cuda_fault_matrix > "mutant-$B-matrix.log" 2>&1
 RC=$?
 set -e
 [ "$RC" -ne 0 ]; grep -q "FAIL enumeration boundary=$([ "$B" = initialize ] && echo initialize || echo cudaPreparePatch) mode=fatal" "mutant-$B-matrix.log"
 cp build/motioncorr_faultinject "binaries/$B-mutant"
 restore
done
flock /tmp/motioncorr-vm-build.lock cmake --build build -j4 > restored-build.log 2>&1
build/cuda_fault_matrix > restored-matrix.log 2>&1
python3 src/tests/run_enumeration_boundary_control.py build/motioncorr_faultinject /home/alex/MotionCorr-standalone/relion30_tutorial/Movies/20170629_00021_frameImage.tiff production --initialize-mutant binaries/initialize-mutant --patch-mutant binaries/patch-mutant > production.log 2>&1
mkdir healthy24
build/motioncorr --i '/home/alex/MotionCorr-standalone/relion30_tutorial/Movies/*.tiff' --gainref /home/alex/MotionCorr-standalone/relion30_tutorial/Movies/gain.mrc --o "$R/healthy24/" --use_own --gpu 0 --j 4 --max_io_threads 2 --patch_x 5 --patch_y 5 --bfactor 150 --seed 1 --dose_weighting --dose_per_frame 1 --voltage 300 --angpix 0.885 > healthy24/run.log 2>&1
/home/alex/mc-env/bin/python3 /home/alex/mc-pr115-ownership-20260929/compare-native.py /home/alex/mc-pr115-ownership-20260929/base24 healthy24 --images 24 --stars 25 --report parity24.json
sha256sum build/{motioncorr,cuda_fault_matrix,motioncorr_faultinject} binaries/* > binary-hashes.txt
git -C src rev-parse HEAD > source.txt
git -C src status --porcelain > source-status.txt
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader > release-compute.txt
printf 'PASS enumeration boundaries and complete current-main all24 parity\n'
