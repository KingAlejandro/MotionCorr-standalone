#!/bin/bash
# Does MPS help the real application, and at what cost to correctness and
# failure behaviour? Timing alone would not be enough to adopt it: MPS shares a
# GPU context across clients, so product equality and cross-worker fault
# isolation both have to be rechecked, not assumed.
set -uo pipefail
B=/home/alex/mps-campaign; T=/home/alex/MotionCorr-standalone/relion30_tutorial
P=/home/alex/p1-4gpu; BIN=$P/build/motioncorr
# Harness from the ff30678 checkout: p1-4gpu/src is 098b4bd and predates
# --product-interval, so argparse rejected every timed run there. The C++
# source is identical between the two, so the 098b4bd binary still matches.
SRC=/home/alex/g4-timing/src
NVR=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
export LD_LIBRARY_PATH="$NVR/lib:${LD_LIBRARY_PATH:-}"; export TMPDIR=/tmp
rm -rf "$B"; mkdir -p "$B"; cd "$B"
trap 'echo quit | nvidia-cuda-mps-control >/dev/null 2>&1; pkill -f nvidia-cuda-mps 2>/dev/null; true' EXIT
echo "### MPS CAMPAIGN ###"; date -Is
OPTS="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 \
--bfactor 150 --gainref Movies/gain.mrc --seed 1"
declare -A DEV=( [1]="0" [2]="0,2" [4]="0,1,2,3" )
declare -A CPUS=( [1]="0-31" [2]="0-15;16-31" [4]="0-7;8-15;16-23;24-31" )
declare -A JJ=( [1]="32" [2]="16;16" [4]="8;8;8;8" )

launch () { local out=$1 n=$2 star=$3; shift 3
  local extra=() IFS=';'; read -ra js <<< "${JJ[$n]}"; unset IFS
  for j in "${js[@]}"; do extra+=(--worker-extra "--j $j"); done
  ( cd "$T" && python3 "$SRC/tools/multi_gpu/run_multi_gpu.py" --star "$star" --out "$out" \
      --binary "$BIN" --devices "${DEV[$n]}" --cpus "${CPUS[$n]}" --cpu-budget 32 \
      --product-interval 0.02 "${extra[@]}" -- $OPTS "$@" ); }

mps_up () {
  export CUDA_MPS_PIPE_DIRECTORY=/tmp/mps-$USER CUDA_MPS_LOG_DIRECTORY=/tmp/mps-$USER-log
  rm -rf $CUDA_MPS_PIPE_DIRECTORY $CUDA_MPS_LOG_DIRECTORY
  mkdir -p $CUDA_MPS_PIPE_DIRECTORY $CUDA_MPS_LOG_DIRECTORY
  # 3>&- is required, not tidiness. nvidia-cuda-mps-control -d daemonises and
  # inherits every open fd, including fd 3 which flock holds the bench lock on.
  # The daemon then keeps that lock after this script exits, and the box reads as
  # busy with nothing running -- the same dead-hold a backgrounded sampler causes.
  nvidia-cuda-mps-control -d 3>&- && sleep 2
  # warm the server on every device so the first timed run does not pay for it
  for u in $(nvidia-smi --query-gpu=uuid --format=csv,noheader); do
    CUDA_VISIBLE_DEVICES=$u /home/alex/initprobe/probe 64 64 warm >/dev/null 2>&1; done; }
mps_down () { echo quit | nvidia-cuda-mps-control >/dev/null 2>&1; sleep 1
  unset CUDA_MPS_PIPE_DIRECTORY CUDA_MPS_LOG_DIRECTORY
  rm -rf /tmp/mps-$USER /tmp/mps-$USER-log; }

echo; echo "---- TIMING: 5 interleaved reps, MPS off then on ----"
for mode in off on; do
  [ $mode = on ] && mps_up
  for rep in 1 2 3 4 5; do for off in 0 1 2; do
    case $(( (off+rep) % 3 )) in 0) n=1;; 1) n=2;; 2) n=4;; esac
    out=$B/t; rm -rf "$out"; a=$(date +%s.%N)
    launch "$out" $n "$T/movies.star" >"$B/last.out" 2>&1; rc=$?; b=$(date +%s.%N)
    v=$(python3 -c "import json;print(json.load(open('$out/status.json'))['verdict'])" 2>/dev/null)
    printf "MPSARM mps=%s gpu=%s rep=%s rc=%s wall=%.3f verdict=%s mrc=%s\n" \
      "$mode" "$n" "$rep" "$rc" "$(echo "$b-$a"|bc)" "$v" "$(find $out -name '*_frameImage.mrc'|wc -l)"
    rm -rf "$out"
  done; done
  [ $mode = on ] && mps_down
done

echo; echo "---- EQUALITY: products under MPS vs the serial oracle ----"
mps_up
for n in 1 2 4; do
  rm -rf "$B/c$n"; launch "$B/c$n" $n "$T/movies.star" >"$B/c$n.out" 2>&1
  python3 "$P/digest.py" "$B/c$n" > "$B/c$n.digest"
  echo "  $n worker(s): $(wc -l < $B/c$n.digest) products; vs oracle: $(cmp -s $P/oracle.digest $B/c$n.digest && echo IDENTICAL || echo DIFFERS)"
done

echo; echo "---- FAULT ISOLATION: one worker gets a truncated movie ----"
# MPS shares a GPU context across clients. The question this answers is whether
# one worker's failure takes the others down with it. Run it under MPS AND
# without, so the comparison is like-for-like rather than against an assumption.
mps_down
mkdir -p "$B/bad/Movies"; cp "$T/movies.star" "$B/bad/"
for f in "$T"/Movies/*.tiff; do ln -sf "$f" "$B/bad/Movies/"; done
ln -sf "$T/Movies/gain.mrc" "$B/bad/Movies/gain.mrc"
VICTIM=$(ls "$T"/Movies/*.tiff | head -1 | xargs basename)
rm -f "$B/bad/Movies/$VICTIM"
head -c 400000 "$T/Movies/$VICTIM" > "$B/bad/Movies/$VICTIM"   # truncated: decode must fail
echo "  truncated: $VICTIM"
for mode in off on; do
  [ $mode = on ] && mps_up
  rm -rf "$B/f_$mode"
  ( cd "$B/bad" && python3 "$SRC/tools/multi_gpu/run_multi_gpu.py" --star "$B/bad/movies.star" \
      --out "$B/f_$mode" --binary "$BIN" --devices "0,1,2,3" \
      --cpus "0-7;8-15;16-23;24-31" --cpu-budget 32 -- $OPTS ) >"$B/f_$mode.out" 2>&1
  rc=$?
  good=$(find "$B/f_$mode" -name '*_frameImage.mrc'|wc -l)
  echo "  mps=$mode launcher_rc=$rc products=$good/23 expected (1 of 24 is corrupt)"
  python3 -c "
import json;s=json.load(open('$B/f_$mode/status.json'))
print('    worker rcs:', [w['returncode'] for w in s['workers']], 'verdict:', s['verdict'])" 2>&1|tail -1
  [ $mode = on ] && mps_down
done
echo; echo "MPS_CAMPAIGN_DONE"; date -Is
