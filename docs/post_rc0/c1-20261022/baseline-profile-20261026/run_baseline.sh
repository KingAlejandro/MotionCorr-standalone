#!/bin/bash
# Source-pinned single-GPU baseline profile of the unchanged C1 CUDA binary (e77a51a2) on one K269 census movie (dose1-s01). Timing task: it takes the GPU3 correctness lock
# and the venue benchmark lock nonblocking (contention = stop, nothing bypassed) and holds both for the whole series. The profiling kit (tools/profiling/mcprof.py of the same
# checkout) does the runs; it is called with --no-lock only because this script already holds the locks continuously across all phases.
# Order: W (warmup, kit) A1 A2 | P1 (built-in --profile, no Nsight) P2 (Nsight Systems, kit trace) | A3 A4.   usage: taskset -c 96-103 bash run_baseline.sh
set -u
SC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb-bp-20261026
SRC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/src
BIN=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/build-cuda/motioncorr
FIX=/mnt/clathrin/alex-motioncorr-km-truth/fixtures/dose1-s01
UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
PY=/home/alex/.mc-venv/bin/python3
T=$(cd "$(dirname "$0")" && pwd)
export C1_SCR=$SC C1_SHA=e77a51a220cb0d91f4ac3c7fac211876d0c6833f PYTHONDONTWRITEBYTECODE=1
source $T/c1_env.sh || exit 1
export OMP_NUM_THREADS=6 OPENBLAS_NUM_THREADS=1; unset OMP_PROC_BIND OMP_PLACES GLIBC_TUNABLES
L=$SC/logs; mkdir -p $L; cd $SC
[ "$(awk '/Cpus_allowed_list/{print $2}' /proc/self/status)" = 96-103 ] || { echo "not pinned to 96-103" | tee $L/STOP; exit 1; }
# --- locks, nonblocking, held for the whole series
exec 7>>/tmp/motioncorr-bench.lock; flock -n 7 || { echo "bench lock held: stop (nothing bypassed)" | tee $L/STOP; exit 5; }
exec 6>>/tmp/motioncorr-gpu3-correctness.lock; flock -n 6 || { echo "GPU3 correctness lock held: stop" | tee $L/STOP; exit 5; }
for f in /tmp/motioncorr-bench.lock /tmp/motioncorr-gpu3-correctness.lock; do echo "$f inode $(stat -c %i $f) acquired $(date -u +%FT%TZ)"; done | tee $L/locks.txt
# --- pins
echo "src HEAD $(git -C $SRC rev-parse HEAD) dirty-files $(git -C $SRC status --porcelain | wc -l)" | tee $L/pins.txt
sha256sum $BIN $FIX/movie.mrcs $FIX/RECEIPT.json $FIX/input.star $SRC/tools/profiling/mcprof.py | tee -a $L/pins.txt
grep -q 34e768128b83f7c94eb4a41ee6bb9a795c52c531a5d646ce4116df83d8d3535a $L/pins.txt && grep -q 3b6126efcd601173df79ddc657f7c9f72ac257fddb256e9dc11d7953c6d25def $L/pins.txt && grep -q 27d9a55b9318aaa3b89b200d7047670f766670babb0afb8b88956707f60608a6 $L/pins.txt && grep -q e77a51a220cb0d91f4ac3c7fac211876d0c6833f $L/pins.txt || { echo "pin mismatch" | tee $L/STOP; exit 4; }
# --- occupancy monitor (runner lane 102-103): GPU compute apps on all GPUs, load, payload-lane busy jiffies, once per second
( taskset -c 102,103 bash -c 'while :; do printf "%s\t%s\t%s\t%s\n" "$(date -u +%FT%T.%N)" "$(cut -d" " -f1 /proc/loadavg)" "$(nvidia-smi --query-compute-apps=gpu_uuid,pid --format=csv,noheader,nounits | tr "\n" ";")" "$(awk "/^cpu(9[6-9]|10[0-1]) /{b+=\$2+\$3+\$4+\$7+\$8+\$9} END{print b}" /proc/stat)"; sleep 1; done' > $L/monitor.tsv 2>&1 ) & MON=$!
trap 'kill $MON 2>/dev/null' EXIT
bash $T/c1_occ.sh bp-pre 3 || { echo "pre health failed" | tee $L/STOP; exit 3; }
PAY=(--use_own --j 6 --patch_x 5 --patch_y 5 --group_frames 1 --bin_factor 1 --seed 1 --skip_defect --save_noDW --first_frame_sum 1 --last_frame_sum 40 --ingest float --ingest_witness $SC/ingest-witness.txt --gpu 0)
KIT="$PY $SRC/tools/profiling/mcprof.py"
COMMON=(--data $FIX --star input.star --cpus 96-101 --runner-cpus 102-103 --gpu-uuid $UUID --no-lock --commit A=$C1_SHA)
echo "=== phase 1: warmup + A1 A2 $(date -u +%FT%TZ)" | tee -a $L/phases.txt
$KIT run A=$BIN --work $SC/kit-run1 "${COMMON[@]}" --rounds 2 --warmup 1 --keep-outputs -- "${PAY[@]}" > $L/phase1.log 2>&1; echo "phase1 rc=$?" | tee -a $L/phases.txt
echo "=== P1 built-in --profile (no Nsight) $(date -u +%FT%TZ)" | tee -a $L/phases.txt
mkdir -p $SC/p1/out; ( cd $FIX && CUDA_VISIBLE_DEVICES=$UUID CUDA_DEVICE_ORDER=PCI_BUS_ID /usr/bin/time -v -o $SC/p1/time.txt taskset -c 96-101 $BIN "${PAY[@]}" --i input.star --o $SC/p1/out/ --profile $SC/p1/p1.profile.jsonl --profile_device_timing 0 > $SC/p1/p1.log 2>&1 ); echo "P1 rc=$?" | tee -a $L/phases.txt
echo "=== P2 Nsight Systems trace (kit trace; cuda,nvtx; no CPU sampling; device timing off) $(date -u +%FT%TZ)" | tee -a $L/phases.txt
$KIT trace A=$BIN --work $SC/kit-trace "${COMMON[@]}" -- "${PAY[@]}" > $L/phase2.log 2>&1; echo "P2 rc=$?" | tee -a $L/phases.txt
echo "=== phase 3: A3 A4 $(date -u +%FT%TZ)" | tee -a $L/phases.txt
$KIT run A=$BIN --work $SC/kit-run2 "${COMMON[@]}" --rounds 2 --warmup 0 --keep-outputs -- "${PAY[@]}" > $L/phase3.log 2>&1; echo "phase3 rc=$?" | tee -a $L/phases.txt
bash $T/c1_occ.sh bp-post 3; echo "post health rc=$?" | tee -a $L/phases.txt
echo "=== done $(date -u +%FT%TZ)" | tee -a $L/phases.txt
