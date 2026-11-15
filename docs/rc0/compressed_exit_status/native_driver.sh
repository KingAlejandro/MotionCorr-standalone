#!/bin/bash
set -euo pipefail
W=/mnt/clathrin/alex-motioncorr-214
export QF_W=$W QF_SHA=39aca256c248e6209c6cbf8edc183b7400551b43 QF_CPUS=88-95
export QF_GPU_UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d QF_GPU_LOCK=/tmp/motioncorr-gpu3-correctness.lock
export PATH=$W/tools/usr/bin:/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
cd "$W"
if [ ! -d src/.git ]; then mv src exported-src; mv git-src src; fi
mkdir -p tools
(cd tools && apt-get download pbzip2 && dpkg-deb -x pbzip2*.deb .) > logs/pbzip2-setup.log 2>&1 || true
command -v pbzip2 || true
lscpu > logs/hardware.txt
nvidia-smi --query-gpu=index,uuid,name,memory.total --format=csv >> logs/hardware.txt
bash src/docs/rc0/qf/tools/build.sh > logs/driver-build.log 2>&1
for cfg in cpu cuda nvcomp; do
 bash src/docs/rc0/qf/tools/run_ctest.sh "$cfg"
 cat "$W/ctest-$cfg.exit"
 [ "$(cat "$W/ctest-$cfg.exit")" = 0 ] || exit 10
 done
for codec in bz2 xz zst; do
 flock -n /tmp/motioncorr-bench.lock true
 (
 flock -n 9
 if nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep -q "$QF_GPU_UUID"; then exit 80; fi
 export CUDA_VISIBLE_DEVICES=$QF_GPU_UUID CUDA_DEVICE_ORDER=PCI_BUS_ID
 taskset -c 88-95 /home/alex/.mc-venv/bin/python3 src/tests/test_compressed_mrc_status.py --binary "$W/build-nvcomp/motioncorr" --codec "$codec" --gpu 0 --work "$W/native-$codec" > "$W/logs/native-$codec.log" 2>&1
 ) 9>"$QF_GPU_LOCK"
 done
sha256sum build-{cpu,cuda,nvcomp}/motioncorr > logs/binaries.sha256
echo ALL_DONE
