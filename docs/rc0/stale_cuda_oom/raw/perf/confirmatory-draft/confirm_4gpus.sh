#!/bin/bash
# Frozen-design launcher for the W-D11 confirmatory timing on 4GPUs GPU3 (rule.txt). NOT RUN until "GO".
#   confirm_4gpus.sh freeze    write the manifest (no resource taken)
#   confirm_4gpus.sh windows   run the four windows once, in the declared order, then combine
# The driver takes and releases the locks itself, under the 45-min deadline; this script holds none.
set -euo pipefail
W=/mnt/clathrin/alex-motioncorr-rc0/W-D11
SRC=$W/src-confirm                                  # clean checkout of the frozen PR head
D=$SRC/docs/rc0/stale_cuda_oom/raw/perf/confirmatory-draft
E=$W/confirm4
UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
MAIN=$W/build-main-nvcomp/motioncorr; FIX=$W/build-fix-nvcomp/motioncorr
TUT=/home/alex/motioncorr-validation-20261011-vm/tutorial-data; E10216=$W/perf-e10216
G="--use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp"
EL="--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5 --ingest compact"
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH PYTHONDONTWRITEBYTECODE=1
export CUDA_VISIBLE_DEVICES=$UUID CUDA_DEVICE_ORDER=PCI_BUS_ID OMP_NUM_THREADS=8
unset GLIBC_TUNABLES OMP_PROC_BIND OMP_PLACES

case "${1:-}" in
freeze)
  [ -z "$(git -C $SRC status --porcelain)" ] || { echo "source checkout not clean"; exit 1; }
  mkdir -p $E
  [ ! -e $E/manifest.json ] || { echo "manifest exists: frozen once"; exit 1; }
  python3 $D/confirm_pairs.py freeze --manifest $E/manifest.json --venue "4GPUs GPU3 $UUID, payload 88-95, runner 120-123" \
    --gpu-uuid $UUID --src $SRC --main-sha 71ab841e69869b615555bb02f8f393db59c22d73 \
    --fix-build-sha 78aae2d3e79298913c904f0616a27432119d3988 \
    --a $MAIN --a-sha256 c2263c22611dc72bf575b7c40410d7be8dfca100f8f3319023e9bef62ec9f8dd \
    --b $FIX --b-sha256 29b894f0643f1b8f1cbcb33954165bd70f1613f9095be36e963660f7939ac185 \
    --build-settings "Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DUSE_NVCOMP=ON (nvCOMP 5.3.0.16) -DBUILD_TESTING=ON, g++ 13.3.0, CUDA 12.8; W-D11 build.sh" \
    --workload "tutG:256:$TUT:$G" --workload "e10216L:176:$E10216:$EL" --windows 2
  sha256sum $E/manifest.json ;;
windows)
  for spec in tutG:1 e10216L:1 tutG:2 e10216L:2; do
    w=${spec%:*}; i=${spec#*:}
    echo "=== $w window $i $(date -u +%FT%TZ)"
    python3 $D/confirm_pairs.py run --manifest $E/manifest.json --workload $w --window $i --out $E \
      --cpus 88-95 --runner-cpus 120-123 --gpu-uuid $UUID --scratch /tmp \
      --lock /tmp/motioncorr-bench.lock --lock /tmp/motioncorr-gpu3-correctness.lock --samplers || true
  done
  for w in tutG e10216L; do
    python3 $D/confirm_pairs.py combine --manifest $E/manifest.json --workload $w --out $E --result $E/$w-result.json
  done ;;
*) echo "usage: $0 freeze|windows"; exit 2 ;;
esac
