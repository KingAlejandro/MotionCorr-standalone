#!/bin/bash
set -euo pipefail
cd /home/alex/mc-pr115-enumeration-20260929
mkdir composed-proof
exec >composed-proof/driver.log 2>&1
export PATH=/usr/local/cuda/bin:$PATH
export CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598
export OMP_NUM_THREADS=4
exec 9>/tmp/motioncorr-gpu2-correctness.lock
flock -n 9 || exit 30
nvidia-smi --query-compute-apps=pid,gpu_uuid,process_name --format=csv,noheader >composed-proof/occupancy-before.csv
if grep -q GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 composed-proof/occupancy-before.csv; then exit 31; fi
{ date -u; uname -a; df -h .; lscpu; cat /proc/self/status; nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.used --format=csv; nvcc --version; } >composed-proof/host.txt
test -z "$(git -C src status --porcelain)"
git -C src fetch /home/alex/composed115.bundle HEAD
git -C src checkout --detach FETCH_HEAD
git -C src rev-parse HEAD HEAD:src >composed-proof/source.txt
git -C src status --short >composed-proof/source-status.txt
cp build/motioncorr_faultinject composed-proof/predecessor-faultinject
flock /tmp/motioncorr-vm-build.lock bash -c 'cmake -S src -B build -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python > composed-proof/configure.log 2>&1 && cmake --build build -j4 > composed-proof/build.log 2>&1'
sha256sum build/motioncorr build/motioncorr_faultinject build/cuda_fault_matrix >composed-proof/binary-hashes.txt
/home/alex/.mc-venv/bin/python src/tests/run_preprocessing_failure_controls.py --binary build/motioncorr_faultinject --workdir composed-proof/preprocessing --float-host >composed-proof/preprocessing.log 2>&1
ctest --test-dir build --output-on-failure >composed-proof/ctest.log 2>&1
/home/alex/.mc-venv/bin/python src/tests/run_enumeration_boundary_control.py build/motioncorr_faultinject /home/alex/MotionCorr-standalone/relion30_tutorial/Movies/20170629_00021_frameImage.tiff composed-proof/enumeration >composed-proof/enumeration.log 2>&1
nvidia-smi --query-compute-apps=pid,gpu_uuid,process_name --format=csv,noheader >composed-proof/occupancy-after.csv
date -u >composed-proof/finished.txt
