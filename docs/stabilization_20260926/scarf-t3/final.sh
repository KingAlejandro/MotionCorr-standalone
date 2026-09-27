#!/bin/bash
# Final head-to-head: ONE node generation, both tools interleaved, verified cold/warm.
set -u
CUDAHOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export LD_LIBRARY_PATH=$CUDAHOME/lib64:$CUDAHOME/lib:${LD_LIBRARY_PATH:-}
export TMPDIR=/tmp
B=$HOME/i53-scarf; OURS=$B/src/build-cuda/motioncorr; MC3=$B/bin/MotionCor3-stock
T=$B/relion30_tutorial; R=$B/resultsF; mkdir -p "$R"; LOG=$R/final.txt
OPT="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1"
cd "$B/runroot"
echo "=== FINAL START $(date -Is) node=$(hostname) job=${SLURM_JOB_ID:-na} features=$(scontrol show node $(hostname -s) 2>/dev/null|grep -oE 'AvailableFeatures=[^ ]*') ===" | tee -a "$LOG"
ev(){ python3 $HOME/evict2.py "$T/Movies" 2>&1 | sed 's/^/    /' | tee -a "$LOG"; }
pg(){ find "$1" -name '*.mrc' -type f -delete 2>/dev/null; }
ours(){ local TAG=$1; local D=$R/o_$TAG; rm -rf "$D"; local S=$(date +%s.%N) p=()
  for k in 0 1 2 3; do mkdir -p "$D/w$k"
    timeout -k 20 900 /usr/bin/time -v taskset -c 0-15 $OURS --i "chunk_4way_${k}.star" --o "$D/w$k/" --gpu $k --j 8 $OPT \
      > "$D/w$k/run.log" 2> "$D/w$k/time.txt" & p+=($!); done
  local rc=0; for x in "${p[@]}"; do wait $x||rc=1; done
  local W=$(echo "$(date +%s.%N) - $S"|bc)
  local C=0; for k in 0 1 2 3; do
    u=$(grep -oP 'User time \(seconds\): \K[0-9.]+' "$D/w$k/time.txt"||echo 0); s=$(grep -oP 'System time \(seconds\): \K[0-9.]+' "$D/w$k/time.txt"||echo 0)
    C=$(echo "$C+$u+$s"|bc); done
  echo "OURS4 $TAG rc=$rc wall=${W}s aggCPU=$(echo "scale=1;100*$C/$W"|bc)% mrcs=$(find $D -name '*.mrc' ! -name '*_PS.mrc' ! -name '*_noDW.mrc'|wc -l)" | tee -a "$LOG"; pg "$D"; }
mc3(){ local TAG=$1; local D=$R/m_$TAG; rm -rf "$D"; local S=$(date +%s.%N) p=()
  for k in 0 1 2 3; do mkdir -p "$D/w$k/out" "$D/w$k/log"
    timeout -k 20 900 /usr/bin/time -v taskset -c 0-15 $MC3 -InTiff "$B/results4/part4/s$k/" -InSuffix .tiff -Serial 1 \
      -OutMrc "$D/w$k/out/" -LogDir "$D/w$k/log/" -Gain "$T/Movies/gain.mrc" -RotGain 0 -FlipGain 0 -InvGain 0 \
      -PixSize 0.885 -kV 200 -FmDose 1.277 -InitDose 0 -Patch 5 5 0 -Bft 150 150 -Group 1 1 -FmRef 1 \
      -FtBin 1 -Align 1 -SumRange 0 0 -Throw 0 -Trunc 0 -Cs 0 -InFmMotion 0 -SplitSum 0 \
      -Gpu $k -GpuMemUsage 0.75 > "$D/w$k/run.log" 2> "$D/w$k/time.txt" & p+=($!); done
  local rc=0; for x in "${p[@]}"; do wait $x||rc=1; done
  local W=$(echo "$(date +%s.%N) - $S"|bc)
  local C=0; for k in 0 1 2 3; do
    u=$(grep -oP 'User time \(seconds\): \K[0-9.]+' "$D/w$k/time.txt"||echo 0); s=$(grep -oP 'System time \(seconds\): \K[0-9.]+' "$D/w$k/time.txt"||echo 0)
    C=$(echo "$C+$u+$s"|bc); done
  local TL=$(grep -h -oP 'Load Tiff movie: \K[0-9.]+' "$D"/w*/run.log|paste -sd+|bc)
  local CT=$(grep -h -oP '^Computation time: \K[0-9.]+' "$D"/w*/run.log|paste -sd+|bc)
  echo "MC3x4 $TAG rc=$rc wall=${W}s aggCPU=$(echo "scale=1;100*$C/$W"|bc)% tiff=${TL}s compute=${CT}s mrc=$(ls $D/w*/out/*.mrc 2>/dev/null|grep -vcE '_DW\.mrc$') dw=$(ls $D/w*/out/*_DW.mrc 2>/dev/null|wc -l) forbidden=$(ls $D/w*/out/ 2>/dev/null|grep -cE '_DWS|_ODD|_EVN')" | tee -a "$LOG"; pg "$D"; }
echo "--- COLD, order alternated, eviction verified before each ---" | tee -a "$LOG"
ev; ours coldA; ev; mc3 coldA
ev; mc3 coldB; ev; ours coldB
echo "--- WARM, n=5 each, interleaved ---" | tee -a "$LOG"
for i in 1 2 3 4 5; do ours warm$i; mc3 warm$i; done
echo "FINAL DONE $(date -Is)" | tee -a "$LOG"
