#!/bin/bash
# (a) paired MotionCor3 stock vs host-O3  (b) full analysis. Under flock + taskset.
set -uo pipefail
ROOT=/home/alex/mc3-compare; W="$ROOT/work"
MC3="$ROOT/MotionCor3-stock/MotionCor3"; MC3O3="$ROOT/MotionCor3-o3/MotionCor3"
N="${1:-4}"; GPU=0
cd "$W"
SPID=""; SFILE=""
start_s(){ SFILE="$1"; ( while :; do ps -eo user:24,pcpu --no-headers | awk '$1!="alex"{s+=$2} END{printf "%.1f\n",s+0}'; sleep 1; done ) > "$1" 2>/dev/null & SPID=$!; }
stop_s(){ kill "$SPID" 2>/dev/null; wait "$SPID" 2>/dev/null
  FL=$(awk '{s+=$1; if($1>m)m=$1; n++} END{if(n)printf "%.1f/%.1f/%d",s/n,m,n; else printf "na/na/0"}' "$SFILE"); }
mc3(){ local bin="$1" o="$2" g="$3" lf="$4"
  rm -rf "$o" "$g"; mkdir -p "$o" "$g"
  /usr/bin/time -v "$bin" -InTiff Movies/ -InSuffix .tiff -Serial 1 -OutMrc "$o/" -LogDir "$g/" \
    -Gain Movies/gain.mrc -RotGain 0 -FlipGain 0 -InvGain 0 \
    -PixSize 0.885 -kV 200 -FmDose 1.277 -InitDose 0 \
    -Patch 5 5 0 -Bft 150 150 -Group 1 1 -FmRef 1 \
    -FtBin 1 -Align 1 -SumRange 0 0 -Throw 0 -Trunc 0 \
    -Cs 0 -InFmMotion 0 -SplitSum 0 -Gpu "$GPU" > "$lf" 2>&1; echo $?; }
emit(){ local e r; e=$(grep -m1 "Elapsed (wall" "$2"|awk '{print $NF}'); r=$(grep -m1 "Maximum resident" "$2"|awk '{print $NF}')
  local ok=INVALID; [ "$3" -eq 0 ] && [ "$4" -eq 24 ] && ok=OK
  echo "RESULT,$1,$e,na,$r,na,rc=$3,outputs=$4,$ok,foreign=${5:-na}"; }

# stock and -O3 were previously timed in different phases under different foreign load,
# so that one comparison was confounded. Pair them directly, alternating order.
echo "=== PAIRED MotionCor3 stock vs host-O3, n=$N"
for i in $(seq 1 "$N"); do
  if [ $((i%2)) -eq 1 ]; then ord=stock_first; a1="$MC3"; n1=stock; a2="$MC3O3"; n2=o3host
                        else ord=o3_first;    a1="$MC3O3"; n1=o3host; a2="$MC3"; n2=stock; fi
  start_s "$W/logs/fb-$i-1"; rc=$(mc3 "$a1" "$W/b1" "$W/b1-log" "$W/logs/b-$i-1.log"); stop_s
  emit "bpair$i,$ord,motioncor3_$n1" "$W/logs/b-$i-1.log" "$rc" "$(ls "$W"/b1/*_DW.mrc 2>/dev/null|wc -l)" "$FL"
  start_s "$W/logs/fb-$i-2"; rc=$(mc3 "$a2" "$W/b2" "$W/b2-log" "$W/logs/b-$i-2.log"); stop_s
  emit "bpair$i,$ord,motioncor3_$n2" "$W/logs/b-$i-2.log" "$rc" "$(ls "$W"/b2/*_DW.mrc 2>/dev/null|wc -l)" "$FL"
done
echo "=== TIMED PART DONE $(date -u +%FT%TZ)"
